#!/usr/bin/env python3

import sys
import json
import struct
import time
import psutil
import requests
import subprocess
import re
import socks
import socket
import logging
import shutil
import os
import logging.handlers
import getpass
import platform
from pathlib import Path
from urllib.parse import urlparse

POSIX = os.name == 'posix'

# --- Setup Logging ---
log_dir = Path(__file__).resolve().parent.parent / "log"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "holocron_native_host.log"

# Set a persistent flag to check if this is the first run
# A simple way is to check for the existence of the log file at startup.
# Note: This means logs are only re-initialized if the main log file is deleted.
is_first_run = not log_file.exists()

handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger()

# --- Key Change 1: Set a higher default logging level ---
# Set the default level to INFO. We'll use DEBUG for verbose, frequent messages.
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# --- Key Change 2: Log the startup message only once ---
if is_first_run:
    logging.info("--- Native host script started for the first time ---")

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "work_connect.sh"
OPENVPN_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "openvpn_connect.sh"
V2RAY_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "v2ray_connect.sh"
PASSWALL2_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "passwall2_control.sh"
CONN_LOG_DIR = log_dir / "connections"
CONN_LOG_DIR.mkdir(exist_ok=True)
HTTP_PROXY_LOCK_FILE = CONN_LOG_DIR / "holocron_http_proxy.lock"



def read_message():
    """Reads a message from stdin, prefixed with a 4-byte length."""
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        sys.exit(0)
    message_length = struct.unpack('@I', raw_length)[0]
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)

def send_message(message_content):
    """Sends a message to stdout, prefixed with a 4-byte length."""
    encoded_content = json.dumps(message_content).encode('utf-8')
    encoded_length = struct.pack('@I', len(encoded_content))
    sys.stdout.buffer.write(encoded_length)
    sys.stdout.buffer.write(encoded_content)
    sys.stdout.buffer.flush()

def _get_proxy_type_from_protocol(protocol_str):
    """Maps a protocol string to a PySocks proxy type constant."""
    protocol_map = {
        "SOCKS5": socks.SOCKS5,
        "SOCKS4": socks.SOCKS4,
        "HTTP": socks.HTTP,
    }
    return protocol_map.get(protocol_str.upper())

def perform_tcp_ping(host, port=443, timeout=2, proxy_config=None):
    """Performs a TCP 'ping' by attempting a socket connection."""
    sock = None
    hostname_to_check = host
    try:
        is_proxied = proxy_config and proxy_config.get("host") and proxy_config.get("port")
        # --- Robustness Improvement ---
        # If a full URL is passed, extract the hostname. This prevents `gaierror`.
        if '://' in hostname_to_check:
            parsed_url = urlparse(hostname_to_check)
            hostname_to_check = parsed_url.hostname
            if not hostname_to_check:
                logging.error(f"Could not extract a valid hostname from '{host}'.")
                return -1, "InvalidHost"
        # --- End of Improvement ---

        sock = socks.socksocket() if is_proxied else socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if is_proxied:
            proxy_type = _get_proxy_type_from_protocol(proxy_config.get("protocol", "SOCKS5"))
            if not proxy_type:
                # HTTPS proxy is not supported for raw socket connection via PySocks
                return -1, f"UnsupportedProxyType"
            sock.set_proxy(proxy_type, proxy_config["host"], proxy_config["port"])

        sock.settimeout(timeout)
        addr = socket.gethostbyname(hostname_to_check)
        start_time = time.perf_counter()
        sock.connect((addr, port))
        end_time = time.perf_counter()
        latency_ms = int((end_time - start_time) * 1000)
        proxy_msg = f" via {proxy_config['protocol']} proxy" if is_proxied else " (direct)"
        logging.debug(f"TCP ping to {hostname_to_check}:{port}{proxy_msg} successful. Latency: {latency_ms}ms.")
        return latency_ms, None
    except (socks.ProxyError, socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
        error_name = e.__class__.__name__
        proxy_msg = f" via proxy" if is_proxied else " (direct)"
        logging.warning(f"TCP ping to '{host}':{port}{proxy_msg} failed: {error_name}")
        return -1, error_name
    finally:
        if sock:
            sock.close()

def perform_web_check(url, timeout=10, proxy_config=None):
    """Performs an HTTP HEAD request, optionally through a configured proxy."""
    if not url or not url.startswith(('http://', 'https://')):
        return -1, "Invalid URL", "ConfigurationError"

    proxies = None
    if proxy_config and proxy_config.get("host") and proxy_config.get("port"):
        protocol = proxy_config.get("protocol", "SOCKS5").lower()
        host = proxy_config["host"]
        port = proxy_config["port"]
        # Use socks5h to ensure DNS resolution happens on the proxy side.
        if protocol == "socks5":
            proxy_url = f"socks5h://{host}:{port}"
        else:
            proxy_url = f"{protocol}://{host}:{port}"
        proxies = {'http': proxy_url, 'https': proxy_url}

    headers = {'User-Agent': 'HolocronStatusCheck/1.0'}
    try:
        start_time = time.perf_counter()
        response = requests.head(url, proxies=proxies, timeout=timeout, headers=headers)
        end_time = time.perf_counter()
        latency_ms = int((end_time - start_time) * 1000)
        if 200 <= response.status_code < 400:
            return latency_ms, "OK", None
        return latency_ms, f"Failed (Status {response.status_code})", None
    except requests.exceptions.RequestException as e:
        error_name = e.__class__.__name__
        logging.error(f"Web check for {url} failed with exception: {error_name}")
        if "SOCKSHTTPSConnectionPool" in str(e):
            return -1, "Failed (Proxy Error)", "ProxyError"
        return -1, "Failed (Connection Error)", "ConnectionError"

def perform_docker_auth_check(timeout=10, proxy_config=None):
    """
    Checks the connection to Docker's authentication service and analyzes the response.
    Returns a tuple: (status_code, status_message, error_type)
    """
    url = "https://auth.docker.io/token"
    proxies = None
    if proxy_config and proxy_config.get("host") and proxy_config.get("port"):
        protocol = proxy_config.get("protocol", "SOCKS5").lower()
        host = proxy_config["host"]
        port = proxy_config["port"]
        if protocol == "socks5":
            proxy_url = f"socks5h://{host}:{port}"
        else:
            proxy_url = f"{protocol}://{host}:{port}"
        proxies = {'https': proxy_url}

    headers = {'User-Agent': 'HolocronDockerCheck/1.0'}
    proxy_log_msg = f"via {proxy_config['protocol']} proxy" if proxy_config else "directly"

    try:
        response = requests.get(url, proxies=proxies, timeout=timeout, headers=headers)

        # Check for successful token response
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            try:
                data = response.json()
                if 'token' in data:
                    logging.info(f"Docker auth check successful ({proxy_log_msg}): Received token.")
                    return 200, "OK (Token)", None
            except json.JSONDecodeError:
                logging.warning(f"Docker auth check ({proxy_log_msg}): Received 200 OK but failed to decode JSON.")
                return 200, "Fail (JSON)", "JSONDecodeError"

        # Check for the specific 403 block
        if response.status_code == 403 and "US export control regulations" in response.text:
            logging.warning(f"Docker auth check ({proxy_log_msg}): Connection blocked (403 Forbidden).")
            return 403, "Blocked (Geo)", "GeoBlock"

        # Handle other non-200 statuses
        logging.warning(f"Docker auth check ({proxy_log_msg}): Received unexpected status {response.status_code}.")
        return response.status_code, f"Fail (HTTP {response.status_code})", "HTTPError"
    except requests.exceptions.RequestException as e:
        error_name = e.__class__.__name__
        logging.error(f"Docker auth check ({proxy_log_msg}) failed with exception: {error_name}", exc_info=True)
        if "SOCKSHTTPSConnectionPool" in str(e):
            return -1, "Fail (Proxy)", "ProxyError"
        return -1, "Fail (Network)", "ConnectionError"

def get_process_using_port(port):
    """
    Checks if a TCP port is in use. If so, returns info about the process using it.
    This implementation is more robust for macOS to avoid psutil.AccessDenied
    crashes when scanning system-wide connections.
    Returns a descriptive string if the port is in use, None otherwise.
    """
    listen_addrs = ('127.0.0.1', '0.0.0.0', '::1', '::')
    
    # On macOS, psutil.net_connections() can fail with AccessDenied if it can't
    # inspect a process owned by another user (e.g., root). We iterate through
    # processes manually and handle the exception gracefully for each one.
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # is_running() is a quick check to skip zombies and other defunct processes.
            if not proc.is_running():
                continue
            conns = proc.connections(kind='inet')
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # This is expected for some system processes, just skip them.
            continue
        for conn in conns:
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port and conn.laddr.ip in listen_addrs:
                return f"process '{proc.info['name']}' (PID: {proc.pid})"
    return None

def get_ovpn_socks_port(ovpn_content):
    """Parses .ovpn file content to find the SOCKS proxy port."""
    if not ovpn_content:
        return None
    match = re.search(r'^\s*socks-proxy\s+127\.0\.0\.1\s+(\d+)', ovpn_content, re.MULTILINE)
    if match:
        port = int(match.group(1))
        logging.debug(f"Found SOCKS proxy port {port} in OVPN config.")
        return port
    logging.debug("No SOCKS proxy port found in OVPN config.")
    return None

def find_openvpn_executable():
    """Finds the openvpn executable in common locations or PATH."""
    common_paths = [
        "/usr/local/sbin/openvpn",       # Homebrew on macOS (Intel)
        "/opt/homebrew/sbin/openvpn",    # Homebrew on macOS (Apple Silicon)
        "/usr/sbin/openvpn",             # Debian/Ubuntu, CentOS
    ]
    for path in common_paths:
        if os.access(path, os.X_OK):
            return path
    # Fallback to searching in PATH using shutil.which
    return shutil.which("openvpn")

def get_ovpn_temp_paths(identifier):
    """Returns a dictionary of all temporary file paths for an OpenVPN connection."""
    base = CONN_LOG_DIR / f"holocron_openvpn_{identifier}"
    return {
        "lock": base.with_suffix(".lock"),
        "config": base.with_suffix(".ovpn"),
        "log": base.with_suffix(".log"),
        "auth": base.with_suffix(".auth"),
        "stderr": base.with_suffix(".stderr.log"),
    }

def get_tunnel_status(config):
    """Checks for the tunnel process (SSH or OpenVPN) and extracts the SOCKS port."""
    if not config or not (config.get('sshCommandIdentifier') or config.get('id')):
        logging.warning("No config or identifier provided to get_tunnel_status.")
        return {"connected": False, "socks_port": None}

    conn_type = config.get("type", "ssh")
    identifier = config.get('sshCommandIdentifier') or config.get('id')
    logging.debug(f"Checking for {conn_type} process with identifier: '{identifier}'")

    if conn_type == "ssh":
        lock_file = Path.home() / ".ssh" / f"holocron_tunnel_{identifier}.lock"
        if lock_file.is_file():
            try:
                pid = int(lock_file.read_text().strip())
                proc = psutil.Process(pid)
                # Verify the process is still running and is an ssh process.
                if proc.is_running() and proc.name() == 'ssh':
                    logging.debug(f"Found matching SSH process with PID: {proc.pid} from lock file.")
                    cmd_str = " ".join(proc.cmdline())
                    match = re.search(r'-D\s*(\d+)', cmd_str)
                    socks_port = int(match.group(1)) if match else None
                    return {"connected": True, "socks_port": socks_port}
            except (ValueError, psutil.NoSuchProcess, FileNotFoundError):
                # Handle cases where lock file is stale or PID is gone.
                logging.warning(f"Stale lock file found for SSH identifier '{identifier}'.")
                # The function will fall through and return disconnected.
            except Exception as e:
                logging.error(f"Error checking SSH status via lock file for identifier '{identifier}': {e}")
    elif conn_type == "openvpn":
        paths = get_ovpn_temp_paths(identifier)
        lock_file = paths["lock"]
        if lock_file.is_file():
            try:
                pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(pid) and 'openvpn' in psutil.Process(pid).name():
                    logging.debug(f"Found matching OpenVPN process with PID: {pid}")
                    socks_port = get_ovpn_socks_port(config.get('ovpnFileContent'))
                    return {"connected": True, "socks_port": socks_port}
            except (ValueError, psutil.NoSuchProcess):
                logging.warning(f"Stale lock file found for OpenVPN identifier '{identifier}'.")
    elif conn_type == "v2ray":
        lock_file = CONN_LOG_DIR / f"holocron_v2ray_{identifier}.lock"
        if lock_file.is_file():
            try:
                pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(pid) and ('v2ray' in psutil.Process(pid).name() or 'xray' in psutil.Process(pid).name()):
                    logging.debug(f"Found matching V2Ray process with PID: {pid}")
                    # This is a simplification. The actual port should be read from the generated config.
                    # For now, we'll assume a default, which the v2ray_connect.sh script must ensure it uses.
                    return {"connected": True, "socks_port": 10808}
            except (ValueError, psutil.NoSuchProcess):
                logging.warning(f"Stale lock file found for V2Ray identifier '{identifier}'.")
    elif conn_type == "openwrt_passwall2":
        # For Passwall2, we query its status directly on the OpenWrt router.
        # It doesn't have a local process or SOCKS port in the same way as other tunnels.
        status_response = execute_passwall2_command("status", config)
        if status_response.get("success"):
            passwall2_status = status_response.get("status", "unknown").strip()
            # Passwall2 is considered "connected" if its status is "enabled"
            is_connected = (passwall2_status == "enabled")
            return {"connected": is_connected, "socks_port": None, "passwall2_status": passwall2_status}
        else:
            logging.error(f"Failed to get Passwall2 status: {status_response.get('message')}")
            return {"connected": False, "socks_port": None, "passwall2_status": "error"}
    elif conn_type == "protonvpn":
        # ProtonVPN uses OpenVPN, check for OpenVPN process with this identifier
        paths = get_ovpn_temp_paths(identifier)
        lock_file = paths["lock"]
        if lock_file.is_file():
            try:
                pid = int(lock_file.read_text().strip())
                proc = psutil.Process(pid)
                if proc.is_running() and 'openvpn' in proc.name().lower():
                    logging.debug(f"Found ProtonVPN (OpenVPN) process with PID: {proc.pid}")
                    # ProtonVPN/OpenVPN typically uses a default SOCKS port via dante or similar
                    # For now, return connected status without SOCKS port
                    return {"connected": True, "socks_port": 1080}  # Default SOCKS port
            except (ValueError, psutil.NoSuchProcess):
                logging.warning(f"Stale lock file found for ProtonVPN identifier '{identifier}'.")
    return {"connected": False, "socks_port": None}

def _cleanup_openvpn_files(identifier):
    """
    Cleans up all temporary files for a given OpenVPN connection identifier.
    This is crucial because OpenVPN runs with sudo, creating root-owned files
    that the user-level script cannot otherwise remove.
    """
    if not identifier:
        return

    paths = get_ovpn_temp_paths(identifier)
    files_to_clean = list(paths.values())

    if POSIX:
        # Use sudo to remove all potentially root-owned files at once.
        existing_files = [str(f) for f in files_to_clean if f.is_file()]
        if existing_files:
            rm_cmd = ["/usr/bin/sudo", "/bin/rm", "-f"] + existing_files
            logging.info(f"Cleaning up temp files with command: {' '.join(rm_cmd)}")
            subprocess.run(rm_cmd, check=False, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # On non-POSIX systems, we assume no sudo was used.
        for f in files_to_clean:
            f.unlink(missing_ok=True)

def generate_protonvpn_config(server, username, protocol="openvpn-tcp"):
    """
    Generate OpenVPN configuration for ProtonVPN server.
    
    Args:
        server: dict with server info (ip, name, country, ports)
        username: ProtonVPN username
        protocol: "openvpn-tcp" or "openvpn-udp"
    
    Returns:
        str: OpenVPN configuration content
    """
    # Extract server details
    server_ip = server.get('ip')
    server_name = server.get('name', 'unknown')
    server_country = server.get('country', 'Unknown')
    
    # Determine port and protocol
    if protocol == "openvpn-udp":
        proto = "udp"
        port = 1194
    else:  # openvpn-tcp (default, best for censored regions)
        proto = "tcp"
        port = 443  # Use port 443 to bypass censorship (looks like HTTPS)
    
    # ProtonVPN OpenVPN configuration template
    config = f"""# ProtonVPN {server_country} {server_name} - Auto-generated by Holocron
# Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

client
dev tun
proto {proto}

# Server connection
remote {server_ip} {port}

# Retry settings
resolv-retry infinite
remote-random
nobind

# TUN/TAP settings
tun-mtu 1500
tun-mtu-extra 32
mssfix 1450

# Persistence
persist-key
persist-tun

# Security settings - ProtonVPN uses strong encryption
cipher AES-256-GCM
auth SHA512
tls-version-min 1.2
tls-cipher TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384

# Compression (disabled for security - prone to VORACLE attacks)
compress

# Logging
verb 3
mute 20

# Authentication - file path will be set by connection script
auth-user-pass

# Disable IPv6 to prevent leaks
pull-filter ignore "ifconfig-ipv6"
pull-filter ignore "route-ipv6"

# Security hardening
remote-cert-tls server

# Additional security
script-security 2

# DNS leak protection
dhcp-option DNS 10.2.0.1
dhcp-option DNS 10.8.8.1

# Note: ProtonVPN certificates would normally be embedded here
# For production use, you should download the official config from ProtonVPN
# This is a basic template that should work with ProtonVPN servers

# ============================================
# WARNING: This is a minimal configuration
# For full security, use official ProtonVPN configs
# ============================================
"""
    
    return config

def execute_tunnel_command(command, config):
    """Executes the appropriate connection script (SSH or OpenVPN)."""
    if command not in ["start", "stop"]:
        return {"success": False, "message": f"Invalid command: {command}"}
    if not config:
        return {"success": False, "message": "Configuration must be provided."}

    conn_type = config.get("type", "ssh")
    identifier = config.get("sshCommandIdentifier") or config.get("id")
    if not identifier:
        return {"success": False, "message": "Identifier could not be determined from config."}
    
    if conn_type == "ssh":
        script_path = SHELL_SCRIPT_PATH
        cmd_list = [str(script_path), command, "--identifier", identifier]
        if command == "start":
            # --- Port Pre-flight Check ---
            port_forwards = config.get("portForwards", [])
            for rule in port_forwards:
                # We only care about local ports that SSH will try to bind.
                # This applies to -L (local) and -D (dynamic) forwards.
                # For -R (remote) forwards, the binding is on the remote server.
                if rule.get("type") in ["L", "D"]:
                    local_port_str = rule.get("localPort")
                    if local_port_str:
                        try:
                            local_port = int(local_port_str)
                            process_info = get_process_using_port(local_port)
                            if process_info:
                                message = f"Port {local_port} is already in use by {process_info}. Please close the application or change the configuration."
                                logging.error(message)
                                return {"success": False, "message": message}
                        except (ValueError, TypeError):
                            # Ignore invalid port numbers, they will be caught by other validation
                            # in the options page, but we shouldn't crash here.
                            logging.warning(f"Invalid port '{local_port_str}' in forwarding rule. Skipping check.")
                            pass
            ssh_user = config.get("sshUser")
            ssh_host = config.get("sshHost")

            # Handle cases where user enters 'user@host' in the host field
            if ssh_host and '@' in ssh_host:
                host_user, host_host = ssh_host.rsplit('@', 1)
                if ssh_user and ssh_user.lower() != host_user.lower():
                    logging.warning(f"Both user '{ssh_user}' and host '{ssh_host}' contain a username. "
                                    f"Using username '{host_user}' from host field.")
                final_user = host_user
                final_host = host_host
            else:
                final_user = ssh_user
                final_host = ssh_host

            if final_user: cmd_list.extend(["--user", final_user])
            if final_host: cmd_list.extend(["--host", final_host])
            if config.get("sshRemoteCommand"):
                cmd_list.extend(["--remote-command", config.get("sshRemoteCommand")])
            for ssid in config.get("wifiSsidList", []):
                if ssid: cmd_list.extend(["--ssid", ssid])
            for rule in config.get("portForwards", []):
                if rule.get("type") == "D" and rule.get("localPort"):
                    cmd_list.extend(["-D", str(rule.get("localPort"))])
                elif rule.get("type") == "L" and all(k in rule for k in ["localPort", "remoteHost", "remotePort"]):
                    cmd_list.extend(["-L", f"{rule['localPort']}:{rule['remoteHost']}:{rule['remotePort']}"])
                elif rule.get("type") == "R" and all(k in rule for k in ["localPort", "remoteHost", "remotePort"]):
                    cmd_list.extend(["-R", f"{rule['localPort']}:{rule['remoteHost']}:{rule['remotePort']}"])
        
        if command == "start":
            try:
                logging.info(f"Executing 'start' for SSH tunnel '{identifier}'...")
                process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8', errors='ignore')
                stdout, stderr = process.communicate(timeout=45)
                returncode = process.returncode

                logging.debug(f"Start script stdout: {stdout.strip()}")
                logging.debug(f"Start script stderr: {stderr.strip()}")

                if returncode == 3:
                    logging.info("Start script reported 'already running'. Verifying status.")
                elif returncode != 0:
                    if returncode == 2:
                        message = stdout.strip() or stderr.strip()
                        logging.warning(f"SSH start blocked by script: {message}")
                        return {"success": False, "message": message}
                    error_output = stderr.strip() or stdout.strip()
                    logging.error(f"Start script failed. Exit code: {returncode}. Output: {error_output}")
                    return {"success": False, "message": f"Failed to start tunnel: {error_output}"}

                # --- Verification Step ---
                logging.info("Start script finished. Waiting 2s to verify tunnel stability...")
                time.sleep(2)

                status = get_tunnel_status(config)
                if status.get("connected"):
                    logging.info(f"Successfully started and verified tunnel '{identifier}'.")
                    # --- Start HTTP Proxy Forwarder if enabled ---
                    if config.get("httpProxyEnabled") and status.get("socks_port"):
                        http_port = config.get("httpProxyPort", 8888)
                        logging.info(f"HTTP proxy forwarder is enabled. Attempting to start on port {http_port}.")
                        if get_process_using_port(http_port):
                             logging.warning(f"Port {http_port} is already in use. Cannot start HTTP proxy forwarder.")
                        else:
                            _start_http_proxy_forwarder(
                                upstream_socks_port=status.get("socks_port"),
                                http_listen_port=http_port
                            )

                    return {"success": True, "message": "Tunnel started and verified."}

                else:
                    logging.error(f"Verification failed. Tunnel '{identifier}' is not running after start command.")
                    log_path = get_log_path_for_config(identifier, "ssh")
                    error_details = "Verification failed: The SSH process is not running. Check logs for details."
                    if log_path.is_file():
                        try:
                            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                                log_lines = f.readlines()
                                last_lines = "".join(log_lines[-10:]).strip()
                                if last_lines:
                                    error_details = f"The SSH process failed after connecting. Last log entries:\n---\n{last_lines}"
                        except Exception as log_e:
                            logging.warning(f"Could not read SSH log file at {log_path}: {log_e}")
                            error_details = "The SSH process failed. Could not read its log file."
                    return {"success": False, "message": error_details}

            except subprocess.TimeoutExpired:
                logging.error(f"Timeout: The 'start' command for tunnel '{identifier}' took too long to execute.")
                return {"success": False, "message": "Timeout: The start command took too long."}
            except Exception as e:
                logging.error(f"An unexpected error occurred during 'start' for '{identifier}': {e}", exc_info=True)
                return {"success": False, "message": f"An unexpected error occurred: {e}"}

        elif command == "stop":
            # The existing logic for stop is sufficient.
            _stop_http_proxy_forwarder()
            result = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10, check=False)
            if result.returncode != 0:
                return {"success": False, "message": result.stderr.strip() or result.stdout.strip()}
            return {"success": True, "message": result.stdout.strip() or "Stop command sent."}

    elif conn_type == "openvpn":
        openvpn_exec = find_openvpn_executable()
        if not openvpn_exec:
            return {"success": False, "message": "❌ Error: 'openvpn' executable not found. Please install OpenVPN."}

        paths = get_ovpn_temp_paths(identifier)
        lock_file = paths["lock"]
        config_file = paths["config"]
        log_file = paths["log"]
        auth_file = paths["auth"]
        stderr_log_file = paths["stderr"]

        if command == "start":
            # Proactively clean up any stale files from previous runs. This is critical
            # to prevent permission errors if root-owned files were left behind from
            # a previous failed or improperly stopped session.
            _cleanup_openvpn_files(identifier)
            
            ovpn_content = config.get("ovpnFileContent")
            if not ovpn_content:
                return {"success": False, "message": "OpenVPN content is missing."}
            
            # Sanitize OVPN content to remove directives that could interfere with our script's
            # management of logs, status files, daemonization, and PID files.
            # Also remove deprecated/insecure compression directives that can cause connection failures.
            lines = ovpn_content.splitlines()
            # The \b ensures we match whole words (e.g. 'log' but not 'log-file').
            directives_to_remove = re.compile(r"^\s*(log|log-append|status|daemon|writepid|comp-lzo|compress)\b", re.IGNORECASE)
            sanitized_lines = [line for line in lines if not directives_to_remove.match(line)]
            # Add directives for robust connections to address warnings and potential restart failures.
            sanitized_lines.append("persist-tun")
            sanitized_lines.append("persist-key")
            sanitized_ovpn_content = "\n".join(sanitized_lines)
            
            config_file.write_text(sanitized_ovpn_content)
            
            # On POSIX systems, creating a TUN/TAP interface requires root privileges.
            # We prepend 'sudo' to the command. The user must have configured passwordless
            # sudo for the openvpn executable for this to work seamlessly.
            # We run OpenVPN in the foreground relative to this script (no --daemon) and manage
            # the process directly. This provides reliable control over logging and process state,
            # avoiding issues where --daemon redirects logs to syslog.
            cmd_list = [openvpn_exec, "--config", str(config_file)]
            if POSIX:
                username = getpass.getuser()
                # Determine the correct group name for privilege dropping.
                # On macOS, the primary group is 'staff'. On many Linux distros,
                # the primary group name matches the username.
                if platform.system() == "Darwin":
                    groupname = "staff"
                else:
                    try:
                        groupname = os.getgrgid(os.getgid()).gr_name
                    except (KeyError, AttributeError):
                        # Fallback to username, which is a common convention.
                        groupname = username
                
                # This is the key change: Instruct OpenVPN to drop root privileges
                # to the current user after initialization. This ensures that the
                # log and pid files it creates are owned by the user, preventing
                # permission errors on subsequent reads or cleanup operations.
                cmd_list.extend(["--user", username, "--group", groupname])
                cmd_list.insert(0, "/usr/bin/sudo")
            # Handle username/password authentication
            ovpn_user = config.get("ovpnUser")
            ovpn_pass = config.get("ovpnPass")
            
            # Handle private key passphrase (if the OVPN config has an encrypted key)
            # Check if the ovpn content contains an encrypted private key
            ovpn_key_passphrase = config.get("ovpnKeyPassphrase")
            has_encrypted_key = "BEGIN ENCRYPTED PRIVATE KEY" in ovpn_content or "BEGIN RSA PRIVATE KEY" in ovpn_content
            
            # If we have user/pass or key passphrase, write them to auth file
            if (ovpn_user is not None and ovpn_pass is not None) or (has_encrypted_key and ovpn_key_passphrase):
                try:
                    if ovpn_user is not None and ovpn_pass is not None:
                        # Write credentials to a temporary file
                        auth_file.write_text(f"{ovpn_user}\n{ovpn_pass}")
                    elif has_encrypted_key and ovpn_key_passphrase:
                        # For encrypted keys, the passphrase goes on the first line
                        auth_file.write_text(f"{ovpn_key_passphrase}")
                    
                    # Set secure permissions (read/write for owner only)
                    os.chmod(auth_file, 0o600)
                except Exception as e:
                    logging.error(f"Failed to write credentials to auth file: {e}", exc_info=True)
                    return {"success": False, "message": f"Failed to write credentials to auth file: {e}"}
                
                if ovpn_user is not None and ovpn_pass is not None:
                    cmd_list.extend(["--auth-user-pass", str(auth_file)])
                elif has_encrypted_key and ovpn_key_passphrase:
                    # Use --askpass for private key passphrases
                    cmd_list.extend(["--askpass", str(auth_file)])

            logging.info(f"Starting OpenVPN with command: {' '.join(cmd_list)}")
            
            try:
                # The Python script creates and owns the log files. We redirect the
                # process's stdout/stderr to these files.
                # Open files in line-buffered text mode. This ensures that complete lines
                # written by OpenVPN are flushed to the file immediately, making them
                # visible to our real-time monitoring loop. Binary unbuffered mode
                # (`buffering=0`) can sometimes cause issues with `sudo`'s I/O handling.
                with open(log_file, 'w', buffering=1, encoding='utf-8', errors='ignore') as stdout_f, \
                     open(stderr_log_file, 'w', buffering=1, encoding='utf-8', errors='ignore') as stderr_f:
                    process = subprocess.Popen(cmd_list, stdout=stdout_f, stderr=stderr_f)

                # Actively monitor the log file for success or failure, with a timeout.
                timeout_seconds = 20
                poll_interval_seconds = 0.5
                start_time = time.time()
                
                success_pattern = re.compile(r"Initialization Sequence Completed")
                failure_patterns = re.compile(r"AUTH_FAILED|Cannot resolve host|Exiting due to fatal error|TLS Error|route_gateway_iface", re.IGNORECASE)

                # Use a 'tail -f' like approach to read the log file in real-time.
                # This is more robust than re-reading the entire file in a loop.
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as log_reader:
                    while time.time() - start_time < timeout_seconds:
                        # Check if the process has already exited
                        if process.poll() is not None:
                            logging.warning(f"OpenVPN process exited prematurely with code {process.returncode}.")
                            break # Exit loop to report failure

                        line = log_reader.readline()
                        if not line:
                            # No new line yet, wait a bit before checking again.
                            time.sleep(poll_interval_seconds)
                            continue

                        # We have a new line, check it for success or failure patterns.
                        logging.debug(f"Read from OVPN log: {line.strip()}")
                        if success_pattern.search(line):
                            logging.info("OpenVPN 'Initialization Sequence Completed' found in log.")
                            lock_file.write_text(str(process.pid))
                            # --- Start HTTP Proxy Forwarder if enabled ---
                            socks_port = get_ovpn_socks_port(config.get('ovpnFileContent'))
                            if config.get("httpProxyEnabled") and socks_port:
                                http_port = config.get("httpProxyPort", 8888)
                                logging.info(f"HTTP proxy forwarder is enabled. Attempting to start on port {http_port}.")
                                if get_process_using_port(http_port):
                                    logging.warning(f"Port {http_port} is already in use. Cannot start HTTP proxy forwarder.")
                                else:
                                    _start_http_proxy_forwarder(
                                        upstream_socks_port=socks_port,
                                        http_listen_port=http_port
                                    )
                            stderr_log_file.unlink(missing_ok=True) # Clean up on success
                            return {"success": True, "message": f"OpenVPN tunnel started with PID {process.pid}."}
                        
                        if failure_patterns.search(line):
                            logging.error(f"OpenVPN failure pattern found in log: {line.strip()}")
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            break # Exit loop to report failure
                
                # If we get here, the loop ended without success (timeout or premature exit)
                if process.poll() is None:
                    logging.error(f"OpenVPN connection timed out after {timeout_seconds} seconds.")
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()

                # Construct the final error message
                launch_error = stderr_log_file.read_text().strip() if stderr_log_file.is_file() else ""
                log_content = log_file.read_text().strip() if log_file.is_file() else "No log file found or log was empty."
                
                final_error = "OpenVPN failed to start."
                if "connection timed out" in log_content.lower():
                     final_error = "OpenVPN connection timed out. Check server address and network."
                elif "AUTH_FAILED" in log_content:
                     final_error = "Authentication failed. Please check your username and password."

                if launch_error:
                    final_error += f"\n\nLaunch Error:\n---\n{launch_error}\n---"
                final_error += f"\n\nConnection Log:\n---\n{log_content}\n---"
                
                _cleanup_openvpn_files(identifier)
                return {"success": False, "message": final_error}
                
            except Exception as e:
                logging.error(f"An unexpected exception occurred during OpenVPN start: {e}", exc_info=True)
                _cleanup_openvpn_files(identifier)
                return {"success": False, "message": f"A critical error occurred while starting OpenVPN: {e}"}

        elif command == "stop":
            _stop_http_proxy_forwarder()
            if not lock_file.is_file():
                return {"success": True, "message": "Tunnel already stopped."}
            try:
                pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(pid):
                    # On POSIX, if we started the process with sudo, we must stop it with sudo.
                    if POSIX:
                        kill_cmd = ["/usr/bin/sudo", "/bin/kill", str(pid)]
                        logging.info(f"Stopping OpenVPN with command: {' '.join(kill_cmd)}")
                        subprocess.run(kill_cmd, check=False, timeout=5)
                    else:
                        # On non-POSIX systems (e.g., Windows), psutil is fine.
                        p = psutil.Process(pid)
                        p.terminate()
                        p.wait(timeout=2)
            except (psutil.Error, ValueError, IOError, subprocess.TimeoutExpired) as e:
                logging.warning(f"An error occurred while trying to stop OpenVPN process (PID {pid if 'pid' in locals() else 'unknown'}): {e}")
            finally:
                # Use the robust helper to clean up all temp files.
                _cleanup_openvpn_files(identifier)
            return {"success": True, "message": "OpenVPN tunnel stopped."}

    elif conn_type == "v2ray":
        script_path = V2RAY_SCRIPT_PATH
        cmd_list = [str(script_path), command, "--identifier", identifier]
        if command == "start":
            if not config.get("v2rayUrl"):
                return {"success": False, "message": "V2Ray URL is missing in the configuration."}
            cmd_list.extend(["--url", config["v2rayUrl"]])

        if not script_path.is_file() or not os.access(script_path, os.X_OK):
            error_msg = f"V2Ray script not found or not executable at {script_path}"
            logging.error(error_msg)
            return {"success": False, "message": error_msg}

        try:
            logging.info(f"Executing '{command}' for V2Ray tunnel '{identifier}'...")
            timeout = 45 if command == "start" else 10
            result = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout, check=False)
            logging.debug(f"V2Ray script stdout: {result.stdout.strip()}")
            logging.debug(f"V2Ray script stderr: {result.stderr.strip()}")

            if result.returncode == 3: # Already running
                return {"success": True, "already_running": True, "message": "V2Ray tunnel is already running."}
            if result.returncode != 0:
                error_output = result.stderr.strip() or result.stdout.strip()
                logging.error(f"V2Ray script failed. Exit code: {result.returncode}. Output: {error_output}")
                return {"success": False, "message": f"Failed to {command} V2Ray tunnel: {error_output}"}

            # --- Start HTTP Proxy Forwarder if enabled ---
            if command == "start" and config.get("httpProxyEnabled"):
                # V2Ray script uses a hardcoded SOCKS port
                socks_port = 10808
                http_port = config.get("httpProxyPort", 8888)
                logging.info(f"HTTP proxy forwarder is enabled. Attempting to start on port {http_port}.")
                if get_process_using_port(http_port):
                    logging.warning(f"Port {http_port} is already in use. Cannot start HTTP proxy forwarder.")
                else:
                    _start_http_proxy_forwarder(
                        upstream_socks_port=socks_port,
                        http_listen_port=http_port
                    )

            return {"success": True, "message": result.stdout.strip() or "V2Ray tunnel command executed successfully."}
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout: The command '{command}' for V2Ray tunnel '{identifier}' took too long.")
            return {"success": False, "message": f"Timeout: The command '{command}' for V2Ray took too long."}
        except Exception as e:
            logging.error(f"An unexpected error occurred during V2Ray script execution for '{identifier}': {e}", exc_info=True)
            return {"success": False, "message": f"An unexpected error occurred with V2Ray: {e}"}
    elif conn_type == "protonvpn":
        # ProtonVPN auto-connect: generates config and connects via OpenVPN
        logging.info(f"ProtonVPN connection requested for identifier '{identifier}'. Command: {command}")
        
        if command == "start":
            # Extract ProtonVPN-specific config
            server = config.get("protonvpnServer", {})
            username = config.get("protonvpnUsername")
            password = config.get("protonvpnPassword")
            protocol = config.get("protonvpnProtocol", "openvpn-tcp")
            
            if not all([server, username, password]):
                return {
                    "success": False,
                    "message": "ProtonVPN requires server, username, and password to be configured."
                }
            
            # Check OpenVPN executable
            openvpn_exec = find_openvpn_executable()
            if not openvpn_exec:
                return {"success": False, "message": "❌ Error: 'openvpn' executable not found. Please install OpenVPN."}
            
            # Generate OpenVPN configuration
            try:
                # Clean up any stale files first
                _cleanup_openvpn_files(identifier)
                
                ovpn_config = generate_protonvpn_config(server, username, protocol)
                
                # Get file paths
                paths = get_ovpn_temp_paths(identifier)
                config_path = paths["config"]
                auth_path = paths["auth"]
                log_file = paths["log"]
                lock_file = paths["lock"]
                stderr_log_file = paths["stderr"]
                
                # Save config to temp file
                config_path.write_text(ovpn_config, encoding='utf-8')
                logging.info(f"Generated ProtonVPN config at: {config_path}")
                
                # Save credentials to auth file
                auth_content = f"{username}\n{password}\n"
                auth_path.write_text(auth_content, encoding='utf-8')
                if POSIX:
                    auth_path.chmod(0o600)  # Secure permissions
                logging.info(f"Saved ProtonVPN credentials to: {auth_path}")
                
                # Build OpenVPN command
                cmd_list = [openvpn_exec, "--config", str(config_path), "--auth-user-pass", str(auth_path)]
                
                if POSIX:
                    username_sys = getpass.getuser()
                    if platform.system() == "Darwin":
                        groupname = "staff"
                    else:
                        try:
                            groupname = os.getgrgid(os.getgid()).gr_name
                        except (KeyError, AttributeError):
                            groupname = username_sys
                    
                    cmd_list.extend(["--user", username_sys, "--group", groupname])
                    cmd_list.insert(0, "/usr/bin/sudo")
                
                logging.info(f"Starting ProtonVPN connection to {server.get('name', server.get('ip'))} with command: {' '.join(cmd_list)}")
                
                # Start OpenVPN process
                with open(log_file, 'w', buffering=1, encoding='utf-8', errors='ignore') as stdout_f, \
                     open(stderr_log_file, 'w', buffering=1, encoding='utf-8', errors='ignore') as stderr_f:
                    process = subprocess.Popen(cmd_list, stdout=stdout_f, stderr=stderr_f)
                
                # Monitor log for success/failure
                timeout_seconds = 30
                poll_interval_seconds = 0.5
                start_time = time.time()
                
                success_pattern = re.compile(r"Initialization Sequence Completed")
                failure_patterns = re.compile(r"AUTH_FAILED|Cannot resolve host|Exiting due to fatal error|TLS Error|route_gateway_iface", re.IGNORECASE)
                
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as log_reader:
                    while time.time() - start_time < timeout_seconds:
                        if process.poll() is not None:
                            logging.warning(f"ProtonVPN OpenVPN process exited prematurely with code {process.returncode}.")
                            break
                        
                        line = log_reader.readline()
                        if not line:
                            time.sleep(poll_interval_seconds)
                            continue
                        
                        logging.debug(f"ProtonVPN log: {line.strip()}")
                        
                        if success_pattern.search(line):
                            logging.info("ProtonVPN connection 'Initialization Sequence Completed' found in log.")
                            lock_file.write_text(str(process.pid))
                            stderr_log_file.unlink(missing_ok=True)
                            return {
                                "success": True,
                                "message": f"Successfully connected to ProtonVPN server {server.get('name', server.get('ip'))} ({server.get('country', 'Unknown')})",
                                "server": server
                            }
                        
                        if failure_patterns.search(line):
                            logging.error(f"ProtonVPN failure pattern found in log: {line.strip()}")
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            break
                
                # Connection failed or timed out
                if process.poll() is None:
                    logging.error(f"ProtonVPN connection timed out after {timeout_seconds} seconds.")
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                
                # Construct error message
                launch_error = stderr_log_file.read_text().strip() if stderr_log_file.is_file() else ""
                log_content = log_file.read_text().strip() if log_file.is_file() else "No log file found or log was empty."
                
                final_error = "ProtonVPN connection failed."
                if "connection timed out" in log_content.lower():
                    final_error = "ProtonVPN connection timed out. The server may be blocked or unreachable."
                elif "AUTH_FAILED" in log_content:
                    final_error = "ProtonVPN authentication failed. Please check your username and password."
                
                if launch_error:
                    final_error += f"\n\nLaunch Error:\n---\n{launch_error}\n---"
                final_error += f"\n\nConnection Log:\n---\n{log_content}\n---"
                
                _cleanup_openvpn_files(identifier)
                return {"success": False, "message": final_error}
                    
            except Exception as e:
                logging.error(f"Error during ProtonVPN connection: {e}", exc_info=True)
                _cleanup_openvpn_files(identifier)
                return {
                    "success": False,
                    "message": f"ProtonVPN connection error: {str(e)}"
                }
                
        elif command == "stop":
            # Stop ProtonVPN connection (uses OpenVPN)
            _stop_http_proxy_forwarder()
            paths = get_ovpn_temp_paths(identifier)
            lock_file = paths["lock"]
            
            if not lock_file.is_file():
                return {"success": True, "message": "ProtonVPN connection already stopped."}
            
            try:
                pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(pid):
                    if POSIX:
                        kill_cmd = ["/usr/bin/sudo", "/bin/kill", str(pid)]
                        logging.info(f"Stopping ProtonVPN with command: {' '.join(kill_cmd)}")
                        subprocess.run(kill_cmd, check=False, timeout=5)
                    else:
                        p = psutil.Process(pid)
                        p.terminate()
                        p.wait(timeout=2)
            except (psutil.Error, ValueError, IOError, subprocess.TimeoutExpired) as e:
                logging.warning(f"Error stopping ProtonVPN process: {e}")
            finally:
                _cleanup_openvpn_files(identifier)
            
            return {"success": True, "message": "ProtonVPN connection stopped successfully."}
    else:
        return {"success": False, "message": f"Unknown connection type: {conn_type}"}

def execute_passwall2_command(action, config, proxy_id=None, proxy_data=None, urls=None):
    """
    Executes Passwall2 management commands via SSH on the OpenWrt router.
    
    Supported actions:
    - list_proxies: Get all configured proxies from Passwall2
    - add_proxy: Add a new proxy to Passwall2
    - delete_proxy: Remove a proxy by ID
    - enable_proxy: Enable a specific proxy
    - disable_proxy: Disable a specific proxy
    - start_service: Start the Passwall2 service
    - stop_service: Stop the Passwall2 service
    - restart_service: Restart the Passwall2 service
    """
    logger.info(f"[execute_passwall2_command] ===== START =====")
    logger.info(f"[execute_passwall2_command] Action: {action}")
    logger.info(f"[execute_passwall2_command] Config: {config}")
    logger.info(f"[execute_passwall2_command] ProxyId: {proxy_id}")
    
    valid_actions = [
        "list_proxies", "add_proxy", "delete_proxy",
        "enable_proxy", "disable_proxy", "use_proxy",
        "test_node", "status",
        "start_service", "stop_service", "restart_service",
        "update_balance_nodes", "update_subscription", "optimize_balance_nodes",
        "reset_and_refresh_nodes",
        "refresh_gemini_ipset", "pin_kixy_jumpserver",
        "list_subscriptions", "replace_subscription",
        "add_subscription", "remove_subscription", "optimize_balancing_with_remark",
        "remove_sub_from_balancing_group"
    ]

    if action not in valid_actions:
        logger.error(f"[execute_passwall2_command] Invalid action: {action}")
        return {"success": False, "message": f"Invalid Passwall2 action: {action}. Must be one of: {', '.join(valid_actions)}"}

    if not config:
        logger.error("[execute_passwall2_command] No config provided")
        return {"success": False, "message": "Configuration must be provided for Passwall2 command."}

    passwall2_host = config.get("passwall2Host") or config.get("openwrtHost")
    passwall2_user = config.get("passwall2User") or config.get("openwrtUser", "root")
    passwall2_password = config.get("passwall2Password") or config.get("openwrtPassword")
    passwall2_key_path = config.get("passwall2KeyPath") or config.get("sshKeyPath")
    passwall2_socks_port = config.get("passwall2SocksPort") or config.get("openwrtSocksPort", "1080")
    passwall2_http_port = config.get("passwall2HttpPort", "")

    logger.info(f"[execute_passwall2_command] Extracted config - Host: {passwall2_host}, User: {passwall2_user}, KeyPath: {passwall2_key_path}")

    if not passwall2_host:
        logger.error("[execute_passwall2_command] No passwall2Host in config")
        return {"success": False, "message": "OpenWrt router host must be configured."}

    # Build SSH command
    ssh_cmd = ["ssh"]
    
    # Authentication: prefer key-based, fall back to password
    if passwall2_key_path and os.path.exists(passwall2_key_path):
        ssh_cmd.extend(["-i", passwall2_key_path])
    elif passwall2_password:
        # Use sshpass for password authentication
        if not shutil.which("sshpass"):
            return {"success": False, "message": "sshpass is required for password authentication but not found. Please install it or use SSH key authentication."}
        ssh_cmd = ["sshpass", "-p", passwall2_password] + ssh_cmd
    else:
        return {"success": False, "message": "Either SSH key or password must be provided for router authentication."}
    
    # Add SSH options
    ssh_cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        f"{passwall2_user}@{passwall2_host}"
    ])

    try:
        if action == "status":
            remote_cmd = (
                "if ps | grep -E '/tmp/etc/passwall2/bin/(xray|sing-box)' | grep -v grep >/dev/null 2>&1; "
                "then echo enabled; else echo disabled; fi"
            )
            ssh_cmd.append(remote_cmd)
            logger.info("[status] Checking Passwall2 service status")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            if result.returncode != 0:
                error_msg = (result.stderr or result.stdout).strip()
                logger.error(f"[status] Failed: {error_msg}")
                return {"success": False, "message": f"Failed to get status: {error_msg}"}
            return {"success": True, "status": result.stdout.strip()}

        if action == "reset_and_refresh_nodes":
            # Remove all nodes and trigger subscription refresh
            remote_cmd = (
                "uci show passwall2 | grep '=nodes' | awk -F'.' '{print $2}' | awk -F'=' '{print $1}' | "
                "xargs -I{} uci delete passwall2.{} 2>/dev/null; "
                "uci commit passwall2; "
                "/etc/init.d/passwall2 reload >/dev/null 2>&1; "
                "[ -x /usr/share/passwall2/subscribe.lua ] && lua /usr/share/passwall2/subscribe.lua start || "
                "/etc/init.d/passwall2 restart >/dev/null 2>&1; "
                "echo OK"
            )
            ssh_cmd.append(remote_cmd)
            logger.info("[reset_and_refresh_nodes] Deleting all nodes and refreshing from subscription")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    universal_newlines=True, timeout=120)
            if result.returncode != 0:
                error_msg = (result.stderr or result.stdout).strip()
                logger.error(f"[reset_and_refresh_nodes] Failed: {error_msg}")
                return {"success": False, "message": f"Failed to reset and refresh nodes: {error_msg}"}
            return {"success": True, "message": "All nodes deleted and refreshed from subscription."}

        if action == "list_proxies":
            logger.info(f"[list_proxies] Starting proxy list operation")
            # Get all nodes from Passwall2 UCI config with their properties.
            # Also include the currently-active global node, service status, and hardware stats
            # so the UI can highlight which node is in use.
            # Support both indexed (@nodes[0]) and named (nodeId=nodes) formats
            remote_cmd = (
                "echo '---NODES---'; "
                "uci show passwall2 | grep -E '(^passwall2\\.[^.@]+=(nodes|shunt_rules)|\\.(type|remarks|address|port|protocol|enabled)=)'; "
                "echo '---ACTIVE---'; "
                "uci -q get passwall2.@global[0].node || echo ''; "
                "echo '---STATUS---'; "
                "if ps | grep -E '/tmp/etc/passwall2/bin/(xray|sing-box)' | grep -v grep >/dev/null 2>&1; "
                "then echo running; else echo stopped; fi; "
                "echo '---STATS---'; "
                "mem=$(awk '/MemTotal/ {total=$2} /MemAvailable/ {avail=$2} /MemFree/ {free=$2} /Buffers/ {buffers=$2} /Cached/ {cached=$2} END {if (total>0) {a=avail?avail:(free+buffers+cached); printf \"%d%%\", (total-a)/total*100} else {print \"N/A\"}}' /proc/meminfo); "
                "load=$(cut -d' ' -f1-3 /proc/loadavg); "
                "echo \"Mem: $mem | Load: $load\""
            )
            ssh_cmd.append(remote_cmd)
            
            logger.info(f"[list_proxies] SSH command: {' '.join(ssh_cmd)}")
            logger.info(f"[list_proxies] Listing Passwall2 proxies on {passwall2_host}")
            
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   universal_newlines=True, timeout=30)
            
            logger.info(f"[list_proxies] Command returncode: {result.returncode}")
            logger.info(f"[list_proxies] STDOUT length: {len(result.stdout)}")
            logger.info(f"[list_proxies] STDERR: {result.stderr[:200]}")
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                logger.error(f"[list_proxies] Failed with error: {error_msg}")
                return {"success": False, "message": f"Failed to list proxies: {error_msg}"}
            
            logger.info(f"[list_proxies] Raw output (first 500 chars): {result.stdout[:500]}")
            
            # Parse UCI output to extract proxy information
            proxies = []
            raw_output = result.stdout
            active_node_id = ""
            service_status = "unknown"
            router_stats = ""

            # Split into sections using markers emitted by the remote command.
            section = "NODES"
            node_lines = []
            active_lines = []
            status_lines = []
            stats_lines = []
            for line in raw_output.splitlines():
                if line.strip() == "---NODES---":
                    section = "NODES"; continue
                if line.strip() == "---ACTIVE---":
                    section = "ACTIVE"; continue
                if line.strip() == "---STATUS---":
                    section = "STATUS"; continue
                if line.strip() == "---STATS---":
                    section = "STATS"; continue
                if section == "NODES":
                    node_lines.append(line)
                elif section == "ACTIVE":
                    active_lines.append(line)
                elif section == "STATUS":
                    status_lines.append(line)
                elif section == "STATS":
                    stats_lines.append(line)

            active_node_id = "\n".join(active_lines).strip()
            router_stats = "\n".join(stats_lines).strip()

            status_text = "\n".join(status_lines).lower()
            if "running" in status_text:
                service_status = "running"
            elif "stopped" in status_text or "inactive" in status_text or "not running" in status_text:
                service_status = "stopped"

            proxy_sections = {}

            logger.info(f"[list_proxies] Processing {len(node_lines)} node lines; active='{active_node_id}'; status='{service_status}'")

            for line in node_lines:
                # Parse UCI format - supports both:
                # 1. Named sections: passwall2.nodeId=nodes
                # 2. Indexed sections: passwall2.@nodes[0]=nodes
                # 3. Properties: passwall2.nodeId.type='vmess'
                
                # Match: passwall2.nodeId=nodes (node definition)
                node_def_match = re.match(r"passwall2\.([A-Za-z0-9_]+)=nodes", line)
                if node_def_match:
                    node_id = node_def_match.group(1)
                    logger.info(f"[list_proxies] Found named node: {node_id}")
                    if node_id not in proxy_sections:
                        proxy_sections[node_id] = {"id": node_id}
                    continue
                
                # Match: passwall2.@nodes[0]=nodes (indexed format)
                indexed_match = re.match(r"passwall2\.@nodes\[(\d+)\]=nodes", line)
                if indexed_match:
                    index = indexed_match.group(1)
                    logger.info(f"[list_proxies] Found indexed node: {index}")
                    if index not in proxy_sections:
                        proxy_sections[index] = {"id": index}
                    continue
                
                # Match properties: passwall2.nodeId.property='value' or passwall2.@nodes[0].property='value'
                prop_match = re.match(r"passwall2\.([A-Za-z0-9_@\[\]]+)\.(\w+)=(.*)", line)
                if prop_match:
                    section_id, key, value = prop_match.groups()
                    value = value.strip()
                    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
                        value = value[1:-1]
                    # Extract ID from @nodes[0] format
                    indexed_id_match = re.match(r"@nodes\[(\d+)\]", section_id)
                    if indexed_id_match:
                        section_id = indexed_id_match.group(1)
                    
                    if section_id in proxy_sections:
                        proxy_sections[section_id][key] = value
            
            # Convert to list format
            for proxy in proxy_sections.values():
                pid = proxy.get("id", "")
                proxies.append({
                    "id": pid,
                    "type": proxy.get("type", "Unknown"),
                    "remarks": proxy.get("remarks", "Unnamed"),
                    "name": proxy.get("remarks", "Unnamed"),
                    "address": proxy.get("address", ""),
                    "port": proxy.get("port", ""),
                    "enabled": proxy.get("enabled", "0") == "1",
                    "is_active": bool(active_node_id) and pid == active_node_id,
                })

            logger.info(f"[list_proxies] Found {len(proxies)} proxies")
            return {
                "success": True,
                "proxies": proxies,
                "active_node_id": active_node_id,
                "service_status": service_status,
                "router_stats": router_stats,
                "message": f"Found {len(proxies)} proxies"
            }
        
        elif action == "add_proxy":
            if not proxy_data:
                return {"success": False, "message": "Proxy data must be provided for add_proxy action."}
            
            # Extract proxy details
            proxy_type = proxy_data.get("type", "vmess")
            remarks = proxy_data.get("remarks", "New Proxy")
            address = proxy_data.get("address", "")
            port = proxy_data.get("port", "")
            method = proxy_data.get("method", "")
            password = proxy_data.get("password", "")
            url = proxy_data.get("url", "")
            
            # Build UCI commands to add proxy
            uci_commands = [
                "uci add passwall2 nodes",
                f"uci set passwall2.@nodes[-1].type='{proxy_type}'",
                f"uci set passwall2.@nodes[-1].remarks='{remarks}'",
                f"uci set passwall2.@nodes[-1].enabled='1'"
            ]
            
            if url:
                # If URL provided, let Passwall2 parse it
                uci_commands.append(f"uci set passwall2.@nodes[-1].url='{url}'")
            else:
                # Manual configuration
                if address:
                    uci_commands.append(f"uci set passwall2.@nodes[-1].address='{address}'")
                if port:
                    uci_commands.append(f"uci set passwall2.@nodes[-1].port='{port}'")
                if method:
                    uci_commands.append(f"uci set passwall2.@nodes[-1].method='{method}'")
                if password:
                    uci_commands.append(f"uci set passwall2.@nodes[-1].password='{password}'")
            
            uci_commands.extend([
                "uci commit passwall2",
                "/etc/init.d/passwall2 reload"
            ])
            
            remote_cmd = " && ".join(uci_commands)
            ssh_cmd.append(remote_cmd)
            
            logging.info(f"Adding new proxy '{remarks}' to Passwall2")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to add proxy: {error_msg}")
                return {"success": False, "message": f"Failed to add proxy: {error_msg}"}
            
            return {"success": True, "message": f"Proxy '{remarks}' added successfully"}
        
        elif action == "delete_proxy":
            if proxy_id is None:
                return {"success": False, "message": "Proxy ID must be provided for delete_proxy action."}
            
            remote_cmd = f"uci delete passwall2.@nodes[{proxy_id}] && uci commit passwall2 && /etc/init.d/passwall2 reload"
            ssh_cmd.append(remote_cmd)
            
            logging.info(f"Deleting proxy ID {proxy_id} from Passwall2")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to delete proxy: {error_msg}")
                return {"success": False, "message": f"Failed to delete proxy: {error_msg}"}
            
            return {"success": True, "message": "Proxy deleted successfully"}
        
        elif action == "enable_proxy":
            if proxy_id is None:
                return {"success": False, "message": "Proxy ID must be provided for enable_proxy action."}
            
            remote_cmd = f"uci set passwall2.@nodes[{proxy_id}].enabled='1' && uci commit passwall2 && /etc/init.d/passwall2 reload"
            ssh_cmd.append(remote_cmd)
            
            logging.info(f"Enabling proxy ID {proxy_id} in Passwall2")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to enable proxy: {error_msg}")
                return {"success": False, "message": f"Failed to enable proxy: {error_msg}"}
            
            return {"success": True, "message": "Proxy enabled successfully"}
        
        elif action == "disable_proxy":
            if proxy_id is None:
                return {"success": False, "message": "Proxy ID must be provided for disable_proxy action."}
            
            remote_cmd = f"uci set passwall2.@nodes[{proxy_id}].enabled='0' && uci commit passwall2 && /etc/init.d/passwall2 reload"
            ssh_cmd.append(remote_cmd)
            
            logging.info(f"Disabling proxy ID {proxy_id} in Passwall2")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to disable proxy: {error_msg}")
                return {"success": False, "message": f"Failed to disable proxy: {error_msg}"}
            
            return {"success": True, "message": "Proxy disabled successfully"}
        
        elif action == "use_proxy":
            if proxy_id is None or proxy_id == "":
                return {"success": False, "message": "Proxy ID must be provided for use_proxy action."}

            # Only allow alphanumeric IDs (UCI section names) to prevent SSH injection.
            safe_id = re.sub(r"[^A-Za-z0-9_]", "", str(proxy_id))
            if not safe_id:
                return {"success": False, "message": "Invalid proxy ID."}

            remote_cmd = (
                f"uci set passwall2.@global[0].node='{safe_id}' && "
                "uci commit passwall2 && "
                "/etc/init.d/passwall2 restart && "
                "([ -x /usr/share/passwall2/holocron_refresh_gemini_ipset.sh ] && "
                "/usr/share/passwall2/holocron_refresh_gemini_ipset.sh || true)"
            )
            ssh_cmd.append(remote_cmd)

            logging.info(f"Setting active Passwall2 node to {safe_id}")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=45)

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to set active node: {error_msg}")
                return {"success": False, "message": f"Failed to switch node: {error_msg}"}

            return {"success": True, "message": "Active node updated", "active_node_id": safe_id}

        elif action == "test_node":
            if not proxy_id:
                return {"success": False, "message": "Proxy ID is required for test_node."}
            safe_id = re.sub(r"[^A-Za-z0-9_]", "", str(proxy_id))
            if not safe_id:
                return {"success": False, "message": "Invalid proxy ID."}

            test_urls = urls or [
                "https://www.youtube.com",
                "https://www.kixy.com",
                "https://www.whatsapp.com",
                "https://telegram.org",
            ]
            url_re = re.compile(r"^https?://[A-Za-z0-9._:/\-?&=%@~+]+$")
            safe_urls = [u for u in test_urls if isinstance(u, str) and url_re.match(u)]
            if not safe_urls:
                return {"success": False, "message": "No valid URLs to test."}

            # Kixy (company) URLs must always be tested through the jumpserver/bastion
            # SSH node, regardless of which node the user is testing. This reflects the
            # real Passwall2 shunt routing where *.kixy.com is pinned to the bastion.
            KIXY_NODE_ID = "ssh_7Hd5rcr0"
            kixy_re = re.compile(r"^https?://([A-Za-z0-9_-]+\.)*kixy\.com(?:[:/].*)?$", re.IGNORECASE)

            def _node_for_url(u):
                return KIXY_NODE_ID if kixy_re.match(u) else safe_id

            # Use Passwall2's own per-URL test, which routes the request through
            # the selected node (works for Shunt and Balancing rules too).
            # Output of each call: "<url>\t<node>\t<http_code>:<seconds>" or "000:0" on failure.
            pairs = []
            for u in safe_urls:
                node_for_u = _node_for_url(u)
                u_q = "'" + u.replace("'", "'\\''") + "'"
                n_q = "'" + node_for_u.replace("'", "'\\''") + "'"
                pairs.append(f"{n_q} {u_q}")
            pair_args = " ".join(pairs)
            remote_cmd = (
                "TEST=/usr/share/passwall2/test.sh; "
                "if [ ! -f \"$TEST\" ]; then echo 'NOTEST'; exit 0; fi; "
                "set -- " + pair_args + "; "
                "while [ $# -ge 2 ]; do "
                "  node=\"$1\"; u=\"$2\"; shift 2; "
                "  out=$(sh \"$TEST\" url_test_node \"$node\" \"$u\" 2>/dev/null); "
                "  echo \"$u\t$node\t$out\"; "
                "done"
            )

            ssh_cmd.append(remote_cmd)
            logger.info(
                f"[test_node] URL-testing node {safe_id} on {len(safe_urls)} URLs "
                f"(kixy URLs pinned to {KIXY_NODE_ID})"
            )

            # Each URL test spawns a temporary xray instance (~3-5s) so allow plenty of time.
            total_timeout = max(60, 12 * len(safe_urls))
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       universal_newlines=True, timeout=total_timeout)
            except subprocess.TimeoutExpired:
                logger.error(f"[test_node] SSH timed out for node {safe_id}")
                return {"success": False, "message": "SSH timed out"}

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                logger.error(f"[test_node] Failed: {error_msg}")
                return {"success": False, "message": f"Test failed: {error_msg}"}

            stdout = (result.stdout or "").strip()
            logger.info(f"[test_node] Node {safe_id} raw: {stdout!r}")

            if stdout == "NOTEST":
                return {"success": False, "message": "Router missing /usr/share/passwall2/test.sh"}

            results = {u: -1 for u in safe_urls}
            tested_via = {}
            for line in stdout.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                if len(parts) >= 3:
                    url_part, node_part, out_part = parts[0].strip(), parts[1].strip(), parts[2].strip()
                else:
                    # Backward-compat: older output without node column
                    url_part, out_part = parts[0].strip(), parts[1].strip()
                    node_part = safe_id
                # out_part format: "<code>:<seconds>" e.g. "204:0.532"
                code = None
                secs = None
                if ":" in out_part:
                    code_str, _, time_str = out_part.partition(":")
                    code = code_str.strip()
                    try:
                        secs = float(time_str.strip())
                    except ValueError:
                        secs = None
                if code in ("200", "204", "301", "302", "307", "308") and secs is not None:
                    ms = max(1, int(secs * 1000))
                    results[url_part] = ms
                else:
                    results[url_part] = -1
                tested_via[url_part] = node_part

            return {"success": True, "node_id": safe_id, "results": results, "tested_via": tested_via}

        elif action in ["start_service", "stop_service", "restart_service"]:
            service_action = action.split('_')[0]  # Extract: start, stop, restart
            remote_cmd = f"/etc/init.d/passwall2 {service_action}"
            ssh_cmd.append(remote_cmd)
            
            logging.info(f"Executing Passwall2 service: {service_action}")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to {service_action} service: {error_msg}")
                return {"success": False, "message": f"Failed to {service_action} service: {error_msg}"}
            
            return {"success": True, "message": f"Passwall2 service {service_action}ed successfully"}

        elif action in ("update_balance_nodes", "update_subscription"):
            # Trigger a subscription refresh on the router; subscribe.lua fetches
            # fresh nodes from the subscription URL and rebuilds all balance groups
            # (including 'all balance youtube' and 'balancing whatsaap').
            remote_cmd = "lua /usr/share/passwall2/subscribe.lua start all manual > /tmp/subscribe_update.log 2>&1; echo \"exit:$?\""
            ssh_cmd.append(remote_cmd)
            logger.info(f"[{action}] Triggering subscription update on {passwall2_host}")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    universal_newlines=True, timeout=120)
            stdout = result.stdout.strip()
            logger.info(f"[{action}] stdout: {stdout!r}, stderr: {result.stderr.strip()!r}")
            # The script echoes 'exit:0' on success
            if "exit:0" in stdout:
                return {"success": True, "message": "Subscription updated. Node list and balance groups refreshed."}
            error_msg = result.stderr.strip() or stdout or "Unknown error during subscription update"
            logger.error(f"[{action}] Failed: {error_msg}")
            return {"success": False, "message": f"Subscription update failed: {error_msg}"}

        elif action == "optimize_balance_nodes":
            remote_cmd = r"""
TOP_N=5
PROBE_INTERVAL=2m
TEST=/usr/share/passwall2/test.sh
YT_GROUP=o0bwijd1
WA_GROUP=qk8qf_blc
YT_URL=https://www.youtube.com/generate_204
WA_URL=https://web.whatsapp.com/

if [ ! -f "$TEST" ]; then
    echo "ERROR|missing_test_script"
    exit 2
fi

run_test() {
    node_id="$1"
    url="$2"
    if command -v timeout >/dev/null 2>&1; then
        out=$(timeout 14 sh "$TEST" url_test_node "$node_id" "$url" 2>/dev/null | tail -n 1 | tr -d '\r')
    else
        out=$(sh "$TEST" url_test_node "$node_id" "$url" 2>/dev/null | tail -n 1 | tr -d '\r')
    fi
    code=${out%%:*}
    seconds=${out#*:}
    case "$code" in
        200|204|301|302|307|308)
            awk -v seconds="$seconds" 'BEGIN { ms = int(seconds * 1000); if (ms < 1) ms = 1; print ms }'
            ;;
        *)
            echo 999999
            ;;
    esac
}

is_valid_node() {
    node_id="$1"
    type=$(uci -q get passwall2.$node_id.type)
    protocol=$(uci -q get passwall2.$node_id.protocol)
    address=$(uci -q get passwall2.$node_id.address)
    port=$(uci -q get passwall2.$node_id.port)
    [ -n "$type" ] || return 1
    [ -n "$protocol" ] || return 1
    [ -n "$address" ] || return 1
    [ -n "$port" ] || return 1
    [ "$protocol" = "_balancing" ] && return 1
    [ "$protocol" = "_shunt" ] && return 1
    return 0
}

all_valid_nodes() {
    uci show passwall2 | sed -n "s/^passwall2\.\([A-Za-z0-9_][A-Za-z0-9_]*\)=nodes$/\1/p" | while read -r node_id; do
        if is_valid_node "$node_id"; then
            echo "$node_id"
        fi
    done
}

group_candidates() {
    group_id="$1"
    nodes=""
    for node_id in $(uci -q get passwall2.$group_id.balancing_node); do
        if is_valid_node "$node_id"; then
            nodes="$nodes $node_id"
        else
            echo "SKIP|$group_id|$node_id|invalid_or_stale"
        fi
    done

    count=$(printf '%s\n' $nodes | awk 'NF { n++ } END { print n + 0 }')
    if [ "$count" -lt "$TOP_N" ]; then
        for node_id in $(all_valid_nodes); do
            case " $nodes " in
                *" $node_id "*) ;;
                *) nodes="$nodes $node_id" ;;
            esac
        done
    fi

    printf '%s\n' $nodes | awk 'NF'
}

optimize_group() {
    group_id="$1"
    label="$2"
    url="$3"
    tmp="/tmp/holocron_opt_${group_id}_$$"
    : > "$tmp"

    nodes=$(group_candidates "$group_id")
    if [ -z "$nodes" ]; then
        echo "ERROR|$label|no_valid_candidates"
        return 1
    fi

    for node_id in $nodes; do
        ms=$(run_test "$node_id" "$url")
        remarks=$(uci -q get passwall2.$node_id.remarks | tr '|' ' ')
        printf '%06d|%s|%s\n' "$ms" "$node_id" "$remarks" >> "$tmp"
        echo "TEST|$label|$node_id|$ms|$remarks"
    done

    selected=$(sort -n "$tmp" | awk -F'|' -v top="$TOP_N" '$1 < 999999 && count < top { print $2; count++ }')
    if [ -z "$selected" ]; then
        selected=$(printf '%s\n' $nodes | awk -v top="$TOP_N" 'NR <= top { print }')
    fi

    uci -q delete passwall2.$group_id.balancing_node >/dev/null 2>&1 || true
    for node_id in $selected; do
        uci add_list passwall2.$group_id.balancing_node="$node_id"
    done
    uci set passwall2.$group_id.balancingStrategy='leastPing'
    uci set passwall2.$group_id.probeInterval="$PROBE_INTERVAL"

    count=$(printf '%s\n' $selected | awk 'NF { n++ } END { print n + 0 }')
    ids=$(printf '%s ' $selected)
    echo "SUMMARY|$label|count=$count|interval=$PROBE_INTERVAL|nodes=$ids"
    rm -f "$tmp"
}

echo "OPTIMIZE|start|top=$TOP_N|interval=$PROBE_INTERVAL"
optimize_group "$YT_GROUP" youtube "$YT_URL"
yt_status=$?
optimize_group "$WA_GROUP" whatsapp "$WA_URL"
wa_status=$?

if [ "$yt_status" -ne 0 ] || [ "$wa_status" -ne 0 ]; then
    echo "ERROR|optimize_failed|youtube=$yt_status|whatsapp=$wa_status"
    exit 3
fi

uci commit passwall2
/etc/init.d/passwall2 restart >/dev/null 2>&1 || /etc/init.d/passwall2 start >/dev/null 2>&1 || true
[ -x /usr/share/passwall2/holocron_refresh_gemini_ipset.sh ] && /usr/share/passwall2/holocron_refresh_gemini_ipset.sh || true
echo "OPTIMIZE|done"
"""
            ssh_cmd.append(remote_cmd)
            logger.info(f"[optimize_balance_nodes] Optimizing balance groups on {passwall2_host}")
            result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    universal_newlines=True, timeout=900)
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[optimize_balance_nodes] stdout: {stdout!r}, stderr: {stderr!r}")
            summaries = [line for line in stdout.splitlines() if line.startswith("SUMMARY|")]
            if result.returncode != 0 and not summaries:
                error_msg = stderr or stdout or "Unknown error during balance optimization"
                logger.error(f"[optimize_balance_nodes] Failed: {error_msg}")
                return {"success": False, "message": f"Balance optimization failed: {error_msg}"}

            return {
                "success": True,
                "message": "Optimized YouTube and WhatsApp balance groups to up to 5 working nodes with 2m probes.",
                "summary": summaries,
                "output": stdout
            }

        elif action == "refresh_gemini_ipset":
            # Re-resolve Gemini/Google AI domains and reload the router ipset so
            # the PAC/iptables rules match again when Google rotates IPs.
            remote_cmd = (
                "SCRIPT=/usr/share/passwall2/holocron_refresh_gemini_ipset.sh; "
                "if [ ! -x \"$SCRIPT\" ]; then echo 'ERROR|missing_script'; exit 2; fi; "
                "\"$SCRIPT\" 2>&1; echo \"exit:$?\""
            )
            ssh_cmd.append(remote_cmd)
            logger.info(f"[refresh_gemini_ipset] Refreshing Gemini ipset on {passwall2_host}")
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=120)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Gemini ipset refresh timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[refresh_gemini_ipset] stdout: {stdout!r}, stderr: {stderr!r}")
            if "ERROR|missing_script" in stdout:
                return {"success": False, "message": "Router is missing holocron_refresh_gemini_ipset.sh."}
            if "exit:0" not in stdout:
                error_msg = stderr or stdout or "Unknown error"
                return {"success": False, "message": f"Gemini ipset refresh failed: {error_msg}"}
            return {"success": True, "message": "Gemini ipset refreshed.", "output": stdout}

        elif action == "pin_kixy_jumpserver":
            # Pin *.kixy.com on Passwall2 to the bastion / jumpserver SSH node so
            # company traffic always goes through the AWS bastion regardless of
            # the active exit node.
            jump_node = re.sub(r"[^A-Za-z0-9_]", "", str((proxy_data or {}).get("jumpNodeId") or proxy_id or "ssh_7Hd5rcr0"))
            shunt_rule = re.sub(r"[^A-Za-z0-9_]", "", str((proxy_data or {}).get("shuntRuleId") or "iran_shunt_node"))
            if not jump_node or not shunt_rule:
                return {"success": False, "message": "Invalid jumpNodeId or shuntRuleId."}
            domain_list = "domain:.kixy.com"
            company_id = "company_sites"

            remote_cmd = (
                "set -e; "
                f"JUMP={jump_node}; SHUNT={shunt_rule}; CID={company_id}; "
                f"DLIST='{domain_list}'; "
                "if ! uci -q get \"passwall2.$JUMP\" >/dev/null; then echo 'ERROR|missing_jump_node'; exit 2; fi; "
                "if ! uci -q get \"passwall2.$SHUNT\" >/dev/null; then echo 'ERROR|missing_shunt_node'; exit 3; fi; "
                "if ! uci -q get \"passwall2.$CID\" >/dev/null; then "
                "  uci set \"passwall2.$CID=shunt_rules\"; "
                "  uci set \"passwall2.$CID.remarks=Company Sites (Kixy via jumpserver)\"; "
                "fi; "
                "uci set \"passwall2.$CID.domain_list=$DLIST\"; "
                "uci set \"passwall2.$CID.node=$JUMP\"; "
                "uci set \"passwall2.$CID.enabled=1\"; "
                "uci set \"passwall2.$SHUNT.$CID=$JUMP\"; "
                "uci commit passwall2; "
                "/etc/init.d/passwall2 restart >/dev/null 2>&1 || /etc/init.d/passwall2 reload >/dev/null 2>&1 || true; "
                "echo \"PINNED|$CID|$JUMP|$DLIST\"; "
                "echo \"exit:$?\""
            )
            ssh_cmd.append(remote_cmd)
            logger.info(
                f"[pin_kixy_jumpserver] Pinning {domain_list} -> {jump_node} via shunt {shunt_rule} on {passwall2_host}"
            )
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=60)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Pin Kixy timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[pin_kixy_jumpserver] stdout: {stdout!r}, stderr: {stderr!r}")
            if "ERROR|missing_jump_node" in stdout:
                return {"success": False, "message": f"Jumpserver node '{jump_node}' not found on router."}
            if "ERROR|missing_shunt_node" in stdout:
                return {"success": False, "message": f"Shunt node '{shunt_rule}' not found on router."}
            if "exit:0" not in stdout:
                error_msg = stderr or stdout or "Unknown error"
                return {"success": False, "message": f"Pin Kixy failed: {error_msg}"}
            return {
                "success": True,
                "message": f"*.kixy.com pinned to {jump_node}.",
                "output": stdout,
            }

        elif action == "list_subscriptions":
            # Enumerate all passwall2 @subscribe_list[N] entries on the router,
            # and additionally compute which balancing groups consume nodes from
            # each subscription. Nodes imported by subscribe.lua carry a `group`
            # field whose value equals the parent subscription's `remark`.
            remote_cmd = (
                "echo '---SUBS---'; "
                "i=0; "
                "while uci -q get passwall2.@subscribe_list[$i] >/dev/null 2>&1; do "
                "  url=$(uci -q get passwall2.@subscribe_list[$i].url); "
                "  remark=$(uci -q get passwall2.@subscribe_list[$i].remark); "
                "  auto=$(uci -q get passwall2.@subscribe_list[$i].auto_update); "
                "  ua=$(uci -q get passwall2.@subscribe_list[$i].user_agent); "
                "  printf 'SUB\\t%s\\t%s\\t%s\\t%s\\t%s\\n' \"$i\" \"$auto\" \"$ua\" \"$remark\" \"$url\"; "
                "  i=$((i+1)); "
                "done; "
                "echo '---NODES---'; "
                "for n in $(uci show passwall2 | sed -n 's/^passwall2\\.\\([A-Za-z0-9_]*\\)=nodes$/\\1/p'); do "
                "  proto=$(uci -q get passwall2.$n.protocol); "
                "  grp=$(uci -q get passwall2.$n.group); "
                "  rem=$(uci -q get passwall2.$n.remarks); "
                "  bnodes=$(uci -q get passwall2.$n.balancing_node | tr '\\n' ' '); "
                "  printf 'NODE\\t%s\\t%s\\t%s\\t%s\\t%s\\n' \"$n\" \"$proto\" \"$grp\" \"$rem\" \"$bnodes\"; "
                "done"
            )
            ssh_cmd.append(remote_cmd)
            logger.info(f"[list_subscriptions] Listing Passwall2 subscriptions on {passwall2_host}")
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=30)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "list_subscriptions timed out."}
            if result.returncode != 0:
                err = (result.stderr or result.stdout).strip()
                logger.error(f"[list_subscriptions] Failed: {err}")
                return {"success": False, "message": f"Failed to list Passwall2 subscriptions: {err}"}

            section = None
            subs = []
            nodes = {}            # node_id -> {protocol, group, remarks, members}
            for line in (result.stdout or "").splitlines():
                line = line.rstrip("\r")
                if line == "---SUBS---":
                    section = "SUBS"; continue
                if line == "---NODES---":
                    section = "NODES"; continue
                parts = line.split("\t")
                if section == "SUBS" and parts and parts[0] == "SUB" and len(parts) >= 5:
                    try:
                        idx = int(parts[1])
                    except ValueError:
                        continue
                    subs.append({
                        "index": idx,
                        "auto_update": parts[2].strip() == "1",
                        "user_agent": parts[3].strip(),
                        "remark": parts[4].strip() if len(parts) > 4 else "",
                        "url": parts[5].strip() if len(parts) > 5 else "",
                    })
                elif section == "NODES" and parts and parts[0] == "NODE" and len(parts) >= 6:
                    node_id = parts[1].strip()
                    nodes[node_id] = {
                        "protocol": parts[2].strip(),
                        "group": parts[3].strip(),
                        "remarks": parts[4].strip(),
                        "members": [m for m in parts[5].strip().split() if m],
                    }

            # Build sub.remark -> [{id, name}] of balancing groups that reference it.
            groups_by_remark = {}
            nodes_count_by_remark = {}
            for nid, ndata in nodes.items():
                grp = ndata.get("group")
                if grp and ndata.get("protocol") != "_balancing" and ndata.get("protocol") != "_shunt":
                    nodes_count_by_remark[grp] = nodes_count_by_remark.get(grp, 0) + 1
            for nid, ndata in nodes.items():
                if ndata.get("protocol") != "_balancing":
                    continue
                grp_label = ndata.get("remarks") or nid
                # Which subscription remarks are represented by this balancing group's members?
                seen = set()
                for member_id in ndata.get("members", []):
                    member = nodes.get(member_id)
                    if not member:
                        continue
                    member_grp = member.get("group")
                    if not member_grp or member_grp in seen:
                        continue
                    seen.add(member_grp)
                    bucket = groups_by_remark.setdefault(member_grp, [])
                    if not any(g.get("id") == nid for g in bucket):
                        bucket.append({"id": nid, "name": grp_label})

            for s in subs:
                rem = s.get("remark") or ""
                s["balancing_groups"] = groups_by_remark.get(rem, [])
                s["nodes_count"] = nodes_count_by_remark.get(rem, 0)

            # Top-level: every balancing group on the router, with member info.
            all_balancing_groups = []
            for nid, ndata in nodes.items():
                if ndata.get("protocol") != "_balancing":
                    continue
                member_ids = ndata.get("members", [])
                # Which sub-remarks are represented in this group's members?
                member_remarks = []
                seen_r = set()
                for mid in member_ids:
                    member = nodes.get(mid)
                    if not member:
                        continue
                    mr = member.get("group") or ""
                    if mr and mr not in seen_r:
                        seen_r.add(mr)
                        member_remarks.append(mr)
                all_balancing_groups.append({
                    "id": nid,
                    "name": ndata.get("remarks") or nid,
                    "member_count": len(member_ids),
                    "member_remarks": member_remarks,
                })

            return {
                "success": True,
                "subscriptions": subs,
                "balancing_groups": all_balancing_groups,
                "message": f"Found {len(subs)} subscriptions.",
            }

        elif action == "replace_subscription":
            data = proxy_data or {}
            try:
                index = int(data.get("index"))
            except (TypeError, ValueError):
                return {"success": False, "message": "replace_subscription requires an integer 'index'."}
            new_url = (data.get("newUrl") or "").strip()
            new_remark = (data.get("newRemark") or "").strip()
            trigger_update = bool(data.get("triggerUpdate", True))
            if index < 0:
                return {"success": False, "message": "Invalid subscription index."}
            if not re.match(r"^https?://", new_url):
                return {"success": False, "message": "newUrl must be an http(s) URL."}
            # Only allow URL chars; reject anything that could break shell quoting.
            if not re.match(r"^[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+$", new_url):
                return {"success": False, "message": "newUrl contains unsafe characters."}
            # Sanitize remark (keep it printable, no quotes/backticks).
            safe_remark = re.sub(r"[`'\"\\]", "", new_remark)[:80]

            set_remark_cmd = (
                f"uci set passwall2.@subscribe_list[{index}].remark='{safe_remark}'; "
                if safe_remark else ""
            )
            update_cmd = (
                "lua /usr/share/passwall2/subscribe.lua start all manual "
                ">/tmp/subscribe_update.log 2>&1; "
                if trigger_update else ""
            )
            remote_cmd = (
                "set -e; "
                f"if ! uci -q get passwall2.@subscribe_list[{index}] >/dev/null 2>&1; then "
                "  echo 'ERROR|missing_index'; exit 2; fi; "
                f"OLD=$(uci -q get passwall2.@subscribe_list[{index}].url); "
                f"uci set passwall2.@subscribe_list[{index}].url='{new_url}'; "
                f"{set_remark_cmd}"
                f"uci -q delete passwall2.@subscribe_list[{index}].md5 || true; "
                "uci commit passwall2; "
                "echo \"REPLACED|$OLD\"; "
                f"{update_cmd}"
                "echo \"exit:$?\""
            )
            ssh_cmd.append(remote_cmd)
            logger.info(f"[replace_subscription] idx={index} new_url={new_url!r} remark={safe_remark!r}")
            try:
                # Subscription refresh can take a while if there are many nodes.
                timeout = 180 if trigger_update else 30
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "replace_subscription timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[replace_subscription] stdout: {stdout!r}, stderr: {stderr!r}")
            if "ERROR|missing_index" in stdout:
                return {"success": False, "message": f"Subscription index {index} does not exist on the router."}
            if "exit:0" not in stdout and trigger_update:
                err = stderr or stdout or "Unknown error"
                return {"success": False, "message": f"Subscription refresh failed after URL swap: {err}"}
            old_url = ""
            for line in stdout.splitlines():
                if line.startswith("REPLACED|"):
                    old_url = line.split("|", 1)[1]
                    break
            return {
                "success": True,
                "message": (
                    f"Slot {index} replaced. Subscription refresh triggered."
                    if trigger_update else f"Slot {index} URL updated."
                ),
                "index": index,
                "old_url": old_url,
                "new_url": new_url,
                "remark": safe_remark or None,
            }

        elif action == "add_subscription":
            data = proxy_data or {}
            url = (data.get("url") or "").strip()
            remark = (data.get("remark") or "").strip()
            user_agent = (data.get("userAgent") or "v2rayN/6.40").strip()
            auto_update = "1" if data.get("autoUpdate", True) else "0"
            trigger_update = bool(data.get("triggerUpdate", True))
            if not re.match(r"^https?://", url):
                return {"success": False, "message": "add_subscription: url must be http(s)."}
            if not re.match(r"^[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+$", url):
                return {"success": False, "message": "add_subscription: url contains unsafe characters."}
            safe_remark = re.sub(r"[`'\"\\]", "", remark)[:80] or "user-added"
            safe_ua = re.sub(r"[`'\"\\]", "", user_agent)[:80]
            set_ua_cmd = f"uci set passwall2.@subscribe_list[$IDX].user_agent='{safe_ua}'; " if safe_ua else ""
            update_cmd = (
                "lua /usr/share/passwall2/subscribe.lua start all manual "
                ">/tmp/subscribe_update.log 2>&1; "
                if trigger_update else ""
            )
            remote_cmd = (
                "set -e; "
                "IDX=0; while uci -q get passwall2.@subscribe_list[$IDX] >/dev/null 2>&1; do IDX=$((IDX+1)); done; "
                "uci add passwall2 subscribe_list >/dev/null; "
                f"uci set passwall2.@subscribe_list[$IDX].url='{url}'; "
                f"uci set passwall2.@subscribe_list[$IDX].auto_update='{auto_update}'; "
                f"uci set passwall2.@subscribe_list[$IDX].remark='{safe_remark}'; "
                f"{set_ua_cmd}"
                "uci commit passwall2; "
                "echo \"ADDED|$IDX\"; "
                f"{update_cmd}"
                "echo \"exit:$?\""
            )
            ssh_cmd.append(remote_cmd)
            logger.info(f"[add_subscription] url={url!r} remark={safe_remark!r} trigger_update={trigger_update}")
            timeout = 180 if trigger_update else 30
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "add_subscription timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[add_subscription] stdout={stdout!r} stderr={stderr!r}")
            added_idx = None
            for line in stdout.splitlines():
                if line.startswith("ADDED|"):
                    try:
                        added_idx = int(line.split("|", 1)[1])
                    except ValueError:
                        pass
                    break
            if added_idx is None:
                return {"success": False, "message": f"Add failed: {stderr or stdout or 'unknown error'}"}
            if trigger_update and "exit:0" not in stdout:
                return {"success": False, "message": f"Subscription added (slot {added_idx}) but refresh failed: {stderr or stdout}"}
            return {
                "success": True,
                "index": added_idx,
                "remark": safe_remark,
                "message": (
                    f"Added as slot {added_idx} (\"{safe_remark}\"). Subscription refresh triggered."
                    if trigger_update else f"Added as slot {added_idx} (\"{safe_remark}\")."
                ),
            }

        elif action == "remove_subscription":
            data = proxy_data or {}
            try:
                index = int(data.get("index"))
            except (TypeError, ValueError):
                return {"success": False, "message": "remove_subscription requires an integer 'index'."}
            delete_nodes = bool(data.get("deleteNodes", True))
            restart_service = bool(data.get("restartService", True))
            if index < 0:
                return {"success": False, "message": "Invalid index."}
            parts = [
                "set -e; ",
                f"if ! uci -q get passwall2.@subscribe_list[{index}] >/dev/null 2>&1; then echo 'ERROR|missing_index'; exit 2; fi; ",
                f"REMARK=$(uci -q get passwall2.@subscribe_list[{index}].remark); ",
                "DELETED=0; ",
            ]
            if delete_nodes:
                parts.append(
                    "if [ -n \"$REMARK\" ]; then "
                    "  NODES=$(uci show passwall2 | grep -F \".group='$REMARK'\" | sed -n 's/^passwall2\\.\\([A-Za-z0-9_]*\\)\\.group=.*/\\1/p'); "
                    "  for n in $NODES; do "
                    "    for grp in $(uci show passwall2 | sed -n \"s/^passwall2\\.\\([A-Za-z0-9_]*\\)\\.protocol='_balancing'$/\\1/p\"); do "
                    "      uci del_list passwall2.$grp.balancing_node=\"$n\" 2>/dev/null || true; "
                    "    done; "
                    "    uci -q delete passwall2.$n && DELETED=$((DELETED+1)) || true; "
                    "  done; "
                    "fi; "
                )
            parts.append(
                f"uci delete passwall2.@subscribe_list[{index}]; "
                "uci commit passwall2; "
                "echo \"REMOVED|$REMARK|$DELETED\"; "
            )
            if restart_service:
                parts.append("/etc/init.d/passwall2 restart >/dev/null 2>&1; ")
            parts.append("echo \"exit:$?\"")
            remote_cmd = "".join(parts)
            ssh_cmd.append(remote_cmd)
            logger.info(f"[remove_subscription] idx={index} delete_nodes={delete_nodes}")
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=60)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "remove_subscription timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[remove_subscription] stdout={stdout!r} stderr={stderr!r}")
            if "ERROR|missing_index" in stdout:
                return {"success": False, "message": f"Subscription index {index} not found."}
            deleted = 0
            remark_out = ""
            for line in stdout.splitlines():
                if line.startswith("REMOVED|"):
                    p2 = line.split("|")
                    if len(p2) >= 3:
                        remark_out = p2[1]
                        try:
                            deleted = int(p2[2])
                        except ValueError:
                            pass
                    break
            if "exit:0" not in stdout:
                return {"success": False, "message": f"Remove may have failed: {stderr or stdout}"}
            return {
                "success": True,
                "message": f"Removed slot {index} (\"{remark_out}\") and {deleted} node(s).",
                "index": index,
                "remark": remark_out,
                "deleted_nodes": deleted,
            }

        elif action == "optimize_balancing_with_remark":
            data = proxy_data or {}
            remark = (data.get("remark") or "").strip()
            probes = max(1, min(int(data.get("probes", 3)), 5))
            min_advantage = max(0, int(data.get("minAdvantage", 1)))
            only_group = (data.get("onlyGroup") or "").strip()
            if only_group and not re.match(r"^[A-Za-z0-9_]+$", only_group):
                return {"success": False, "message": "onlyGroup must be a uci section id."}
            if not remark:
                return {"success": False, "message": "remark required."}
            safe_remark = re.sub(r"[`'\"\\]", "", remark)[:80]
            if not safe_remark:
                return {"success": False, "message": "remark contained no safe characters."}

            # Stage 1: gather node metadata.
            gather_cmd = (
                "for n in $(uci show passwall2 | sed -n 's/^passwall2\\.\\([A-Za-z0-9_]*\\)=nodes$/\\1/p'); do "
                "  proto=$(uci -q get passwall2.$n.protocol); "
                "  grp=$(uci -q get passwall2.$n.group); "
                "  addr=$(uci -q get passwall2.$n.address); "
                "  port=$(uci -q get passwall2.$n.port); "
                "  bnodes=$(uci -q get passwall2.$n.balancing_node | tr '\\n' ' '); "
                "  printf 'N\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' \"$n\" \"$proto\" \"$grp\" \"$addr\" \"$port\" \"$bnodes\"; "
                "done"
            )
            ssh_cmd_gather = list(ssh_cmd) + [gather_cmd]
            try:
                result = subprocess.run(ssh_cmd_gather, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=30)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "optimize_balancing: gather timed out."}
            if result.returncode != 0:
                return {"success": False, "message": f"Gather failed: {(result.stderr or '').strip()}"}

            nodes = {}
            for line in (result.stdout or "").splitlines():
                p2 = line.split("\t")
                if not p2 or p2[0] != "N" or len(p2) < 6:
                    continue
                nid = p2[1]
                nodes[nid] = {
                    "protocol": p2[2],
                    "group": p2[3],
                    "address": p2[4],
                    "port": p2[5],
                    "members": [m for m in (p2[6].strip().split() if len(p2) > 6 else []) if m],
                }

            candidates = {nid: n for nid, n in nodes.items()
                          if n["group"] == safe_remark
                          and n["protocol"] not in ("_balancing", "_shunt")
                          and n["address"] and n["port"]}
            balancing_groups = {nid: n for nid, n in nodes.items() if n["protocol"] == "_balancing"}
            if only_group:
                balancing_groups = {gid: g for gid, g in balancing_groups.items() if gid == only_group}
                if not balancing_groups:
                    return {"success": False, "message": f"Balancing group '{only_group}' not found."}
            if not candidates:
                return {"success": True, "message": f"No nodes found for remark '{safe_remark}'.", "added": []}
            if not balancing_groups:
                return {"success": True, "message": "No balancing groups configured.", "added": []}

            to_probe = set(candidates.keys())
            for grp in balancing_groups.values():
                for m in grp["members"]:
                    if m in nodes and nodes[m]["address"] and nodes[m]["port"]:
                        to_probe.add(m)

            # Stage 2: TCP-probe each (probes attempts, count successes).
            probe_lines = []
            for nid in to_probe:
                n = nodes[nid]
                addr = (n["address"] or "").replace("'", "")
                port = (n["port"] or "").replace("'", "")
                if not addr or not port:
                    continue
                probe_lines.append(
                    f"OK=0; for i in $(seq 1 {probes}); do nc -zw2 '{addr}' '{port}' 2>/dev/null && OK=$((OK+1)); done; echo 'P|{nid}|'$OK"
                )
            probe_cmd = "; ".join(probe_lines) if probe_lines else "echo no-probes"
            ssh_cmd_probe = list(ssh_cmd) + [probe_cmd]
            try:
                result = subprocess.run(ssh_cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=30 + 4 * len(to_probe))
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "optimize_balancing: probing timed out."}

            scores = {}
            for line in (result.stdout or "").splitlines():
                p2 = line.split("|")
                if p2 and p2[0] == "P" and len(p2) >= 3:
                    try:
                        scores[p2[1]] = int(p2[2])
                    except ValueError:
                        pass

            # Stage 3: pick winners per balancing group.
            additions = []  # (group_id, node_id, score, threshold)
            for grp_id, grp in balancing_groups.items():
                member_scores = [scores.get(m, 0) for m in grp["members"] if m in nodes]
                if member_scores:
                    sorted_ms = sorted(member_scores)
                    median = sorted_ms[len(sorted_ms) // 2]
                else:
                    median = 0
                existing = set(grp["members"])
                for cid in candidates:
                    if cid in existing:
                        continue
                    cs = scores.get(cid, 0)
                    if cs > 0 and cs >= median + min_advantage:
                        additions.append((grp_id, cid, cs, median))

            if not additions:
                return {
                    "success": True,
                    "message": "No new nodes beat existing balancing members.",
                    "added": [],
                    "scores": scores,
                }

            # Stage 4: apply uci changes.
            apply_parts = ["set -e; "]
            for grp_id, nid, _, _ in additions:
                apply_parts.append(f"uci add_list passwall2.{grp_id}.balancing_node='{nid}'; ")
            apply_parts.append("uci commit passwall2; /etc/init.d/passwall2 restart >/dev/null 2>&1; echo 'APPLY_OK'")
            ssh_cmd_apply = list(ssh_cmd) + ["".join(apply_parts)]
            try:
                result = subprocess.run(ssh_cmd_apply, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=30)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "optimize_balancing: apply timed out."}
            if "APPLY_OK" not in (result.stdout or ""):
                return {"success": False, "message": f"Apply failed: {(result.stderr or '').strip() or (result.stdout or '').strip()}"}

            return {
                "success": True,
                "message": f"Added {len(additions)} new node(s) to {len({a[0] for a in additions})} balancing group(s).",
                "added": [{"group": g, "node": n, "score": s, "threshold": t} for (g, n, s, t) in additions],
                "scores": scores,
            }

        elif action == "remove_sub_from_balancing_group":
            data = proxy_data or {}
            group_id = (data.get("groupId") or "").strip()
            remark = (data.get("remark") or "").strip()
            restart_service = bool(data.get("restartService", True))
            if not re.match(r"^[A-Za-z0-9_]+$", group_id):
                return {"success": False, "message": "groupId must be a uci section id."}
            safe_remark = re.sub(r"[`'\"\\]", "", remark)[:80]
            if not safe_remark:
                return {"success": False, "message": "remark required."}
            remote_cmd = (
                "set -e; "
                f"if [ \"$(uci -q get passwall2.{group_id}.protocol)\" != \"_balancing\" ]; then echo 'ERROR|not_balancing'; exit 2; fi; "
                # Find node IDs whose group matches the given remark.
                f"NODES=$(uci show passwall2 | grep -F \".group='{safe_remark}'\" | sed -n 's/^passwall2\\.\\([A-Za-z0-9_]*\\)\\.group=.*/\\1/p'); "
                "REMOVED=0; "
                "for n in $NODES; do "
                f"  if uci del_list passwall2.{group_id}.balancing_node=\"$n\" 2>/dev/null; then REMOVED=$((REMOVED+1)); fi; "
                "done; "
                "uci commit passwall2; "
                + ("/etc/init.d/passwall2 restart >/dev/null 2>&1; " if restart_service else "")
                + "echo \"DONE|$REMOVED\""
            )
            ssh_cmd.append(remote_cmd)
            logger.info(f"[remove_sub_from_balancing_group] group_id={group_id} remark={safe_remark!r}")
            try:
                result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, timeout=30)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "remove_sub_from_balancing_group timed out."}
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            logger.info(f"[remove_sub_from_balancing_group] stdout={stdout!r} stderr={stderr!r}")
            if "ERROR|not_balancing" in stdout:
                return {"success": False, "message": f"Section '{group_id}' is not a balancing group."}
            removed = 0
            for line in stdout.splitlines():
                if line.startswith("DONE|"):
                    try:
                        removed = int(line.split("|", 1)[1])
                    except ValueError:
                        pass
                    break
            return {
                "success": True,
                "message": f"Removed {removed} node(s) (group='{safe_remark}') from balancing group '{group_id}'.",
                "group": group_id,
                "remark": safe_remark,
                "removed": removed,
            }

    except subprocess.TimeoutExpired:
        logging.error(f"Timeout: Passwall2 command '{action}' took too long")
        return {"success": False, "message": f"Timeout: The command took too long to execute"}
    except Exception as e:
        logging.error(f"Unexpected error during Passwall2 command '{action}': {e}", exc_info=True)
        return {"success": False, "message": f"Unexpected error: {e}"}


def _start_http_proxy_forwarder(upstream_socks_port, http_listen_port):
    """Starts proxy.py to forward HTTP traffic to the upstream SOCKS proxy."""
    if HTTP_PROXY_LOCK_FILE.is_file():
        logging.warning("HTTP proxy forwarder lock file exists. Attempting to clean up before starting.")
        _stop_http_proxy_forwarder()

    # Find the python executable from the current virtual environment
    python_exec = sys.executable
    
    cmd = [
        python_exec,
        "-m", "proxy",
        "--hostname", "127.0.0.1",
        "--port", str(http_listen_port),
        "--proxy", f"socks5://127.0.0.1:{upstream_socks_port}",
        "--log-level", "WARNING" # Keep logs clean unless debugging
    ]
    
    logging.info(f"Starting HTTP proxy forwarder: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        HTTP_PROXY_LOCK_FILE.write_text(str(process.pid))
        logging.info(f"HTTP proxy forwarder started with PID {process.pid}.")
        return True
    except Exception as e:
        logging.error(f"Failed to start HTTP proxy forwarder: {e}", exc_info=True)
        return False

def _stop_http_proxy_forwarder():
    """Stops the proxy.py process if it's running."""
    if not HTTP_PROXY_LOCK_FILE.is_file():
        return

    try:
        pid = int(HTTP_PROXY_LOCK_FILE.read_text().strip())
        if psutil.pid_exists(pid):
            logging.info(f"Stopping HTTP proxy forwarder with PID {pid}.")
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=2)
    except (psutil.Error, ValueError, IOError, subprocess.TimeoutExpired) as e:
        logging.warning(f"Error stopping HTTP proxy forwarder process: {e}")
    finally:
        # Always remove the lock file
        HTTP_PROXY_LOCK_FILE.unlink(missing_ok=True)
        logging.info("Cleaned up HTTP proxy forwarder lock file.")


def get_log_path_for_config(identifier, conn_type):
    """Determines the log file path for a given configuration."""
    if not identifier or not conn_type:
        return log_file # Default to the main native host log

    # This assumes work_connect.sh will log to a file with this naming convention.
    if conn_type == "ssh":
        return CONN_LOG_DIR / f"holocron_ssh_{identifier}.log"
    elif conn_type == "openvpn":
        return get_ovpn_temp_paths(identifier)["log"]
    elif conn_type == "v2ray":
        return CONN_LOG_DIR / f"holocron_v2ray_{identifier}.log"
    elif conn_type == "protonvpn":
        # ProtonVPN uses OpenVPN, so use the same log path structure
        return get_ovpn_temp_paths(identifier)["log"]
    else:
        # Fallback for unknown types
        return log_file

def get_logs(identifier=None, conn_type=None):
    """Reads the last part of the log file and returns it."""
    log_to_read = get_log_path_for_config(identifier, conn_type)
    try:
        if not log_to_read.is_file():
            if identifier:
                return {"success": True, "log_content": "Waiting for log output..."}
            return {"success": True, "log_content": "Log file does not exist yet."}
        file_size = log_to_read.stat().st_size
        read_size = file_size if identifier else min(file_size, 20 * 1024)
        with open(log_to_read, 'r', encoding='utf-8', errors='ignore') as f:
            if file_size > read_size and not identifier:
                f.seek(file_size - read_size)
                f.readline()
            content = f.read()
        return {"success": True, "log_content": content}
    except Exception as e:
        logging.error(f"Error reading log file {log_to_read}: {e}", exc_info=True)
        return {"success": False, "message": f"Error reading log file {log_to_read}: {e}"}

def clear_logs():
    """Clears the content of the log file."""
    try:
        if log_file.is_file():
            with open(log_file, 'w'):
                pass
            logging.info("--- Log file cleared by user request ---")
            return {"success": True, "message": "Log file cleared successfully."}
        return {"success": True, "message": "Log file does not exist, nothing to clear."}
    except Exception as e:
        logging.error(f"Error clearing log file: {e}", exc_info=True)
        return {"success": False, "message": f"Error clearing log file: {e}"}

def handle_test_connection(message):
    """
    Handles the entire test connection lifecycle: start, test, and stop.
    """
    config = message.get("config")
    ping_host = message.get("pingHost")
    web_check_url = message.get("webCheckUrl")
    docker_check_enabled = message.get("dockerCheckEnabled", False)

    if not config:
        return {"success": False, "message": "No configuration provided to test."}
    if not ping_host or not web_check_url:
        return {"success": False, "message": "Ping Host and Web Check URL must be provided for testing."}

    # --- Handle External Proxy Test ---
    # External proxies do not have a tunnel process to start/stop.
    # We perform the checks directly against the configured proxy.
    if config.get("type") == "external":
        logging.info(f"Test Connection: Performing direct checks for external proxy '{config.get('name')}'.")
        proxy_protocol = config.get("proxyProtocol", "SOCKS5")
        proxy_host = config.get("proxyHost")
        proxy_port_str = config.get("proxyPort")

        if not proxy_host or not proxy_port_str:
            return {"success": False, "message": "External proxy configuration is missing a host or port."}

        try:
            proxy_port = int(proxy_port_str)
        except (ValueError, TypeError):
            return {"success": False, "message": f"Invalid port '{proxy_port_str}' for external proxy."}

        # Create a generic proxy config object for the check functions
        proxy_check_config = {
            "protocol": proxy_protocol,
            "host": proxy_host,
            "port": proxy_port
        }

        web_latency, web_status, web_error = perform_web_check(url=web_check_url, proxy_config=proxy_check_config)
        tcp_latency, tcp_error = perform_tcp_ping(host=ping_host, proxy_config=proxy_check_config)

        docker_check_status_code, docker_check_status_msg, docker_check_error = (None, None, None)
        if docker_check_enabled:
            docker_check_status_code, docker_check_status_msg, docker_check_error = perform_docker_auth_check(proxy_config=proxy_check_config)

        is_web_ok = web_latency > -1 and web_status == "OK"
        is_tcp_ok = tcp_latency > -1
        is_docker_ok = not docker_check_enabled or (docker_check_status_code == 200 and docker_check_status_msg == "OK (Token)")
        is_overall_success = is_web_ok and is_tcp_ok and is_docker_ok

        return {
            "success": is_overall_success, "connected": True, "message": "External proxy test completed.",
            "web_check_latency_ms": web_latency, "web_check_status": web_status or web_error,
            "tcp_ping_ms": tcp_latency, "tcp_ping_error": tcp_error,
            "docker_check_status_code": docker_check_status_code, "docker_check_status_msg": docker_check_status_msg, "docker_check_error": docker_check_error,
        }

    # 1. Check current status and decide if we need to start/stop later.
    status_before_test = get_tunnel_status(config)
    tunnel_was_running = status_before_test.get("connected")
    
    if not tunnel_was_running:
        logging.info(f"Test Connection: Tunnel for '{config.get('name')}' is not running. Attempting to start it for the test.")
        # A manual test should bypass any configured Wi-Fi SSID restrictions.
        # The execute_tunnel_command function correctly handles this because the config
        # from the options page does not include the 'wifiSsidList' key.
        start_response = execute_tunnel_command("start", config)
        if not start_response.get("success"):
            logging.error(f"Test Connection: Failed to start tunnel for test. Reason: {start_response.get('message')}")
            return {"success": False, "message": start_response.get('message', 'Failed to start tunnel for testing.')}
    
    # 2. Get status again to find the SOCKS port.
    status_after_start = get_tunnel_status(config)
    if not status_after_start.get("connected"):
        logging.error("Test Connection: Tunnel started but is not connected. Aborting test.")
        if not tunnel_was_running:
            execute_tunnel_command("stop", config) # Cleanup
        return {"success": False, "message": "Tunnel process failed to stabilize after starting. Check logs."}

    socks_port = status_after_start.get("socks_port")
    
    # 3. Perform the actual checks.
    if not socks_port:
        logging.warning(f"Test Connection: Tunnel for '{config.get('name')}' is running but no SOCKS port is configured. Cannot perform checks.")
        if not tunnel_was_running:
            execute_tunnel_command("stop", config) # Cleanup
        return {"success": False, "message": "Tunnel is active but has no SOCKS proxy (-D rule) configured for testing."}

    logging.info(f"Test Connection: Performing checks for '{config.get('name')}' via SOCKS port {socks_port}.")
    # For tunnel-based checks, the proxy is always a SOCKS5 on localhost
    proxy_check_config = {
        "protocol": "SOCKS5",
        "host": "127.0.0.1",
        "port": socks_port
    }
    # 5. Format and send the response.
    is_web_ok = web_latency > -1 and web_status == "OK"
    is_tcp_ok = tcp_latency > -1
    is_docker_ok = not docker_check_enabled or (docker_check_status_code == 200 and docker_check_status_msg == "OK (Token)")
    is_overall_success = is_web_ok and is_tcp_ok and is_docker_ok

    final_message = "Test completed."
    if tunnel_was_running:
        final_message = f"(Tunnel was already running) {final_message}"

    response_payload = {
        "success": is_overall_success,
        "connected": True,
        "web_check_latency_ms": web_latency,
        "web_check_status": web_status or web_error,
        "tcp_ping_ms": tcp_latency,
        "tcp_ping_error": tcp_error,
        "message": final_message,
        "docker_check_status_code": docker_check_status_code,
        "docker_check_status_msg": docker_check_status_msg,
        "docker_check_error": docker_check_error,
    }
    return response_payload

def _get_active_network_service():
    """Finds the active network service on macOS (e.g., 'Wi-Fi' or 'Ethernet')."""
    if not POSIX or platform.system() != "Darwin":
        return None, "Unsupported OS for system proxy management."

    try:
        # This command finds the default route and extracts the interface name (e.g., 'en0')
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, check=True, timeout=5
        )
        interface_match = re.search(r"interface:\s*(\w+)", result.stdout)
        if not interface_match:
            return None, "Could not determine the active network interface."
        interface = interface_match.group(1)

        # This command lists all services and their corresponding device names in blocks.
        # We need to find the 'Hardware Port' name for the block that contains our active interface.
        # Example block:
        #   Hardware Port: Wi-Fi
        #   Device: en0
        #   Ethernet Address: a1:b2:c3:d4:e5:f6
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, check=True, timeout=5
        )
        # The regex looks for a block starting with "Hardware Port:", captures the service name,
        # and ensures it's the block for our specific interface device.
        # `re.MULTILINE` is crucial for `^` to match the start of each line.
        service_match = re.search(
            r"^Hardware Port: (.*?)\nDevice: {interface}(?:\n|$)".format(interface=re.escape(interface)),
            result.stdout,
            re.MULTILINE
        )
        if not service_match:
            return None, f"Could not find network service for interface '{interface}'."
        
        service_name = service_match.group(1).strip()
        logging.info(f"Active network service found: '{service_name}' on interface '{interface}'.")
        return service_name, None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logging.error(f"Error finding active network service: {e}")
        return None, f"Error finding active network service: {e}"

def handle_set_system_proxy(message):
    """Sets or clears the system-wide SOCKS proxy on macOS."""
    service, err = _get_active_network_service()
    if err:
        return {"success": False, "message": err}

    enable = message.get("enable", False)
    try:
        # Use full paths for reliability and prepend with sudo for permissions.
        sudo_cmd = ["/usr/bin/sudo"]
        networksetup_cmd = ["/usr/sbin/networksetup"]
        if enable:
            port = message.get("port")
            subprocess.run(sudo_cmd + networksetup_cmd + ["-setsocksfirewallproxy", service, "127.0.0.1", str(port)], check=True, timeout=5)
            subprocess.run(sudo_cmd + networksetup_cmd + ["-setsocksfirewallproxystate", service, "on"], check=True, timeout=5)
            return {"success": True, "message": f"System SOCKS proxy set to 127.0.0.1:{port} on '{service}'."}
        else:
            subprocess.run(sudo_cmd + networksetup_cmd + ["-setsocksfirewallproxystate", service, "off"], check=True, timeout=5)
            subprocess.run(sudo_cmd + networksetup_cmd + ["-setsocksfirewallproxy", service, "", ""], check=True, timeout=5)
            return {"success": True, "message": f"System SOCKS proxy disabled and cleared on '{service}'."}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_message = f"Failed to modify system proxy settings: {e}. This requires passwordless sudo configuration. See README.md."
        logging.error(error_message)
        return {"success": False, "message": error_message}

def handle_test_router_connection(message):
    """
    Test SSH connection to OpenWrt router.
    
    Args:
        message: Dict containing 'config' with router connection details
        
    Returns:
        Dict with success status and message
    """
    try:
        config = message.get("config", {})
        router_ip = config.get("ip")
        ssh_user = config.get("user", "root")
        ssh_port = config.get("port", 22)
        ssh_password = config.get("password", "")
        ssh_key_path = config.get("keyPath", "")
        
        if not router_ip:
            return {"success": False, "message": "Router IP is required"}
        
        if not ssh_user:
            return {"success": False, "message": "SSH username is required"}
        
        # Build SSH command to test connection
        # Use a simple command that should work on any router
        test_command = ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no"]
        
        # Add port if not default
        if ssh_port and ssh_port != 22:
            test_command.extend(["-p", str(ssh_port)])
        
        # Add key if provided
        if ssh_key_path and ssh_key_path.strip():
            expanded_key_path = os.path.expanduser(ssh_key_path)
            
            # Remove .pub extension if user accidentally provided public key path
            if expanded_key_path.endswith('.pub'):
                expanded_key_path = expanded_key_path[:-4]
                logging.info(f"Removed .pub extension from key path: {expanded_key_path}")
            
            if os.path.exists(expanded_key_path):
                # Check if key permissions are secure (not too open)
                try:
                    key_stat = os.stat(expanded_key_path)
                    key_mode = key_stat.st_mode & 0o777
                    if key_mode & 0o077:  # Check if group or others have any permissions
                        # Try to fix permissions automatically
                        try:
                            os.chmod(expanded_key_path, 0o600)
                            logging.info(f"Fixed SSH key permissions to 0600: {expanded_key_path}")
                        except OSError as e:
                            return {
                                "success": False, 
                                "message": f"SSH key has insecure permissions ({oct(key_mode)}). Please run: chmod 600 {expanded_key_path}"
                            }
                except OSError as e:
                    logging.warning(f"Could not check key permissions: {e}")
                
                test_command.extend(["-i", expanded_key_path])
            else:
                return {"success": False, "message": f"SSH key not found: {expanded_key_path}"}
        
        # Add user@host
        test_command.append(f"{ssh_user}@{router_ip}")
        
        # Simple test command - just echo success
        test_command.append("echo 'connection_ok'")
        
        logging.info(f"Testing router connection: {' '.join(test_command[:-1])} [command]")
        
        # If password is provided and no key, we'll need to use sshpass
        if ssh_password and not ssh_key_path:
            # Check if sshpass is available
            if shutil.which("sshpass"):
                test_command = ["sshpass", "-p", ssh_password] + test_command
            else:
                return {
                    "success": False, 
                    "message": "Password authentication requires 'sshpass' to be installed. Please install it or use SSH key authentication."
                }
        
        # Execute the test
        result = subprocess.run(
            test_command,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and "connection_ok" in result.stdout:
            logging.info(f"Router connection test successful: {router_ip}")
            return {
                "success": True,
                "message": f"Successfully connected to router at {router_ip}"
            }
        else:
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            
            # Make error messages more user-friendly
            if "Permission denied" in error_msg:
                if ssh_password:
                    error_msg = "Authentication failed. Please check your password."
                elif ssh_key_path:
                    error_msg = "SSH key authentication failed. Please check your key file or try using a password."
                else:
                    error_msg = "Authentication failed. Please provide a password or SSH key."
            elif "Connection refused" in error_msg:
                error_msg = "Connection refused. Please check if SSH is enabled on your router."
            elif "No route to host" in error_msg or "Host is down" in error_msg:
                error_msg = f"Cannot reach router at {router_ip}. Please check the IP address and network connection."
            elif "timeout" in error_msg.lower():
                error_msg = "Connection timeout. Router is not responding."
            
            logging.warning(f"Router connection test failed: {error_msg}")
            return {
                "success": False,
                "message": f"Connection failed: {error_msg}"
            }
            
    except subprocess.TimeoutExpired:
        logging.error(f"Router connection test timed out: {router_ip}")
        return {"success": False, "message": "Connection timeout. Check if router IP is correct and accessible."}
    except Exception as e:
        logging.error(f"Router connection test error: {e}", exc_info=True)
        return {"success": False, "message": f"Test failed: {str(e)}"}


def _parse_subscription_userinfo(header_value):
    """Parse a 'Subscription-Userinfo' header into an int dict.

    Format (case-insensitive): upload=X; download=Y; total=Z; expire=T
    Values are bytes (or unix seconds for expire). Returns {} on parse failure.
    """
    info = {}
    if not header_value:
        return info
    for part in str(header_value).split(';'):
        part = part.strip()
        if '=' not in part:
            continue
        k, _, v = part.partition('=')
        k = k.strip().lower()
        v = v.strip()
        try:
            info[k] = int(v)
        except ValueError:
            continue
    return info


def _label_from_subscription_url(url):
    """Derive a short label from a subscription URL (uses #fragment if present)."""
    try:
        from urllib.parse import urlsplit, unquote
        parts = urlsplit(url)
        if parts.fragment:
            return unquote(parts.fragment)
        host = parts.netloc or url
        # last path segment as fallback
        seg = (parts.path or "").rstrip("/").rsplit("/", 1)[-1]
        return f"{host}/{seg}" if seg else host
    except Exception:
        return url


def check_subscription_quota(urls):
    """Fetch each subscription URL and parse its remaining-volume header.

    Returns a list of per-URL summaries. Each summary contains:
      - url, label
      - success (bool), error (str|None)
      - upload, download, used, total, remaining (bytes; -1 if unknown)
      - expire (unix seconds; 0 if unknown)
      - days_remaining (int; -1 if unknown)
      - percent_used (float, 0-100; -1 if unknown)
      - via (str: 'direct' or 'socks5://host:port')
    """
    if not isinstance(urls, list) or not urls:
        return {"success": False, "message": "No subscription URLs provided.", "results": []}

    # Many VPN providers gate the userinfo header on a recognised client UA.
    headers = {
        "User-Agent": "v2rayN/6.40",
        "Accept": "*/*",
    }

    # Try direct first; on network/SSL failure, automatically retry through any
    # local SOCKS proxy that's already listening (Holocron tunnels expose 1081
    # / 1090 / 1080 by default).
    candidate_proxies = []
    for port in (1081, 1090, 1080):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                candidate_proxies.append(f"socks5h://127.0.0.1:{port}")
        except OSError:
            pass

    def _fetch(url, proxy_url):
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        # HEAD first (cheap); fall back to GET if HEAD missing the header.
        resp = requests.head(url, headers=headers, timeout=15,
                             allow_redirects=True, proxies=proxies)
        userinfo = resp.headers.get("Subscription-Userinfo") or resp.headers.get("subscription-userinfo")
        status_code = resp.status_code
        if not userinfo:
            resp2 = requests.get(url, headers=headers, timeout=20,
                                 allow_redirects=True, stream=True, proxies=proxies)
            userinfo = resp2.headers.get("Subscription-Userinfo") or resp2.headers.get("subscription-userinfo")
            status_code = resp2.status_code
            try:
                resp2.close()
            except Exception:
                pass
        return userinfo, status_code

    results = []
    for raw_url in urls:
        url = str(raw_url or "").strip()
        if not url or not re.match(r"^https?://", url):
            results.append({
                "url": url,
                "label": _label_from_subscription_url(url),
                "success": False,
                "error": "Invalid URL",
                "via": "direct",
            })
            continue

        entry = {
            "url": url,
            "label": _label_from_subscription_url(url),
            "success": False,
            "error": None,
            "upload": -1,
            "download": -1,
            "used": -1,
            "total": -1,
            "remaining": -1,
            "expire": 0,
            "days_remaining": -1,
            "percent_used": -1,
            "via": "direct",
        }

        attempts = [(None, "direct")] + [(p, p) for p in candidate_proxies]
        last_error = None
        userinfo = None
        last_status = None
        used_via = "direct"
        for proxy_url, via_label in attempts:
            try:
                userinfo, last_status = _fetch(url, proxy_url)
                used_via = via_label
                if userinfo:
                    break
                # No header on this attempt; try the next route if any.
                last_error = f"Server did not return a Subscription-Userinfo header (HTTP {last_status})."
            except requests.exceptions.Timeout:
                last_error = "Timed out fetching subscription."
            except requests.exceptions.SSLError as e:
                last_error = f"SSL error: {e}"
            except requests.exceptions.ProxyError as e:
                last_error = f"Proxy error: {e}"
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
            except requests.exceptions.RequestException as e:
                last_error = f"Network error: {e}"
            except Exception as e:
                logging.warning(f"[check_subscription_quota] Unexpected error for {url} via {via_label}: {e}")
                last_error = f"Unexpected error: {e}"

        entry["via"] = used_via
        if not userinfo:
            entry["error"] = last_error or "Could not retrieve quota header."
            results.append(entry)
            continue

        info = _parse_subscription_userinfo(userinfo)
        upload = info.get("upload", 0)
        download = info.get("download", 0)
        total = info.get("total", 0)
        expire = info.get("expire", 0)
        used = upload + download
        remaining = max(total - used, 0) if total > 0 else -1
        percent = (used / total * 100.0) if total > 0 else -1
        days_left = -1
        if expire > 0:
            days_left = max(0, int((expire - time.time()) // 86400))

        entry.update({
            "success": True,
            "upload": upload,
            "download": download,
            "used": used,
            "total": total,
            "remaining": remaining,
            "expire": expire,
            "days_remaining": days_left,
            "percent_used": percent,
        })
        results.append(entry)

    return {"success": True, "results": results}


# ---------------------------------------------------------------------------
# Subscription node quality check
# ---------------------------------------------------------------------------

def _decode_subscription_body(body):
    """Try to base64-decode a subscription body; if that fails, return as-is."""
    import base64
    if not body:
        return ""
    text = body.strip()
    # The body is usually one big base64 blob of all node URIs separated by \n.
    try:
        # urlsafe variant tolerant of missing padding.
        padded = text + "=" * (-len(text) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        if "://" in decoded:
            return decoded
    except Exception:
        pass
    try:
        padded = text + "=" * (-len(text) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
        if "://" in decoded:
            return decoded
    except Exception:
        pass
    return text


def _parse_node_uri(uri):
    """Extract {scheme, name, host, port} from a node URI.

    Supports vless, vmess, trojan, ss, hysteria, hysteria2, hy2, tuic.
    Returns None if the URI can't be parsed.
    """
    import base64
    from urllib.parse import urlsplit, unquote, parse_qs

    uri = (uri or "").strip()
    if not uri or "://" not in uri:
        return None

    scheme, _, rest = uri.partition("://")
    scheme = scheme.lower()

    if scheme == "vmess":
        # vmess://base64({add,port,ps,...})
        try:
            blob = rest.split("#", 1)[0]
            padded = blob + "=" * (-len(blob) % 4)
            try:
                raw = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
            except Exception:
                raw = base64.b64decode(padded).decode("utf-8", errors="ignore")
            data = json.loads(raw)
            host = (data.get("add") or data.get("host") or "").strip()
            port = int(str(data.get("port") or 0))
            name = (data.get("ps") or "").strip() or f"{host}:{port}"
            if host and port:
                return {"scheme": "vmess", "name": name, "host": host, "port": port}
        except Exception:
            return None
        return None

    if scheme == "ss":
        # ss://base64(method:password)@host:port#name  OR  ss://base64(method:password@host:port)#name
        try:
            frag = ""
            body = rest
            if "#" in body:
                body, frag = body.split("#", 1)
            if "@" in body:
                # auth@host:port
                _, _, hostport = body.rpartition("@")
            else:
                # whole thing might be base64
                padded = body + "=" * (-len(body) % 4)
                try:
                    raw = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
                except Exception:
                    raw = base64.b64decode(padded).decode("utf-8", errors="ignore")
                _, _, hostport = raw.rpartition("@")
            host, _, port_s = hostport.partition(":")
            port_s = port_s.split("/", 1)[0].split("?", 1)[0]
            port = int(port_s) if port_s.isdigit() else 0
            name = unquote(frag) if frag else f"{host}:{port}"
            if host and port:
                return {"scheme": "ss", "name": name, "host": host, "port": port}
        except Exception:
            return None
        return None

    # Generic URL-style: scheme://[user@]host:port[/path][?query]#name
    try:
        parts = urlsplit(uri)
        host = parts.hostname or ""
        port = parts.port or 0
        if not port:
            # Some providers omit the explicit port for hy2/tuic; bail out.
            return None
        name = unquote(parts.fragment) if parts.fragment else f"{host}:{port}"
        return {"scheme": scheme, "name": name, "host": host, "port": int(port)}
    except Exception:
        return None


def _tcp_ping(host, port, timeout=3.0):
    """Return (latency_ms, error). latency_ms is int >=1; -1 on failure."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            elapsed = (time.monotonic() - start) * 1000.0
            return max(1, int(elapsed)), None
    except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
        return -1, type(e).__name__


def check_subscription_nodes(urls, max_nodes_per_sub=120, concurrency=24, timeout=3.0):
    """Fetch each subscription URL, parse the node list, and TCP-ping each node.

    Returns {success, results: [{url, label, total, alive, dead, best_ms,
    median_ms, by_scheme: {vless: {alive, total}, ...}, top: [...]}]}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not isinstance(urls, list) or not urls:
        return {"success": False, "message": "No subscription URLs provided.", "results": []}

    headers = {"User-Agent": "v2rayN/6.40", "Accept": "*/*"}

    # Auto-discover local SOCKS proxies (same fallback strategy as quota check).
    candidate_proxies = []
    for port in (1081, 1090, 1080):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                candidate_proxies.append(f"socks5h://127.0.0.1:{port}")
        except OSError:
            pass

    def _fetch_body(url):
        last_err = None
        for proxy_url, via in [(None, "direct")] + [(p, p) for p in candidate_proxies]:
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            try:
                resp = requests.get(url, headers=headers, timeout=20,
                                    allow_redirects=True, proxies=proxies)
                if resp.status_code == 200 and resp.text:
                    return resp.text, via, None
                last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
        return None, "direct", last_err

    results = []
    for raw_url in urls:
        url = str(raw_url or "").strip()
        entry = {
            "url": url,
            "label": _label_from_subscription_url(url),
            "success": False,
            "error": None,
            "via": "direct",
            "total": 0,
            "alive": 0,
            "dead": 0,
            "best_ms": -1,
            "median_ms": -1,
            "by_scheme": {},
            "top": [],
        }
        if not url or not re.match(r"^https?://", url):
            entry["error"] = "Invalid URL"
            results.append(entry)
            continue

        body, via, err = _fetch_body(url)
        entry["via"] = via
        if not body:
            entry["error"] = err or "Empty subscription response."
            results.append(entry)
            continue

        decoded = _decode_subscription_body(body)
        nodes = []
        for line in decoded.splitlines():
            parsed = _parse_node_uri(line)
            if parsed:
                nodes.append(parsed)
            if len(nodes) >= max_nodes_per_sub:
                break

        entry["total"] = len(nodes)
        if not nodes:
            entry["error"] = "Could not parse any nodes from this subscription."
            results.append(entry)
            continue

        # Concurrent TCP ping.
        pinged = []
        with ThreadPoolExecutor(max_workers=min(concurrency, max(1, len(nodes)))) as ex:
            future_map = {
                ex.submit(_tcp_ping, n["host"], n["port"], timeout): n
                for n in nodes
            }
            for fut in as_completed(future_map):
                n = future_map[fut]
                try:
                    ms, err = fut.result()
                except Exception as e:
                    ms, err = -1, type(e).__name__
                pinged.append({
                    "scheme": n["scheme"],
                    "name": n["name"],
                    "host": n["host"],
                    "port": n["port"],
                    "ms": ms,
                    "error": err,
                })

        alive = [n for n in pinged if n["ms"] > 0]
        dead = [n for n in pinged if n["ms"] <= 0]
        entry["alive"] = len(alive)
        entry["dead"] = len(dead)

        if alive:
            sorted_alive = sorted(alive, key=lambda n: n["ms"])
            entry["best_ms"] = sorted_alive[0]["ms"]
            mid = len(sorted_alive) // 2
            entry["median_ms"] = (
                sorted_alive[mid]["ms"]
                if len(sorted_alive) % 2 == 1
                else (sorted_alive[mid - 1]["ms"] + sorted_alive[mid]["ms"]) // 2
            )
            # Top 10 fastest for the UI.
            entry["top"] = sorted_alive[:10]

        # Per-scheme breakdown.
        by_scheme = {}
        for n in pinged:
            s = n["scheme"]
            slot = by_scheme.setdefault(s, {"total": 0, "alive": 0})
            slot["total"] += 1
            if n["ms"] > 0:
                slot["alive"] += 1
        entry["by_scheme"] = by_scheme
        entry["success"] = True
        results.append(entry)

    return {"success": True, "results": results}


def execute_router_command(router_command, config):
    """
    Execute arbitrary command on OpenWrt router via SSH.
    
    Args:
        router_command: The command to execute on the router
        config: Dict containing router connection details (ip, user, password/keyPath)
        
    Returns:
        Dict with success status, output, and error message
    """
    try:
        if not router_command:
            return {"success": False, "message": "No command provided"}
        
        if not config:
            return {"success": False, "message": "Router configuration is required"}
        
        router_ip = config.get("ip")
        ssh_user = config.get("user", "root")
        ssh_port = config.get("port", 22)
        ssh_password = config.get("password", "")
        ssh_key_path = config.get("keyPath", "")
        
        if not router_ip:
            return {"success": False, "message": "Router IP is required"}
        
        # Build SSH command
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        
        # Add port if not default
        if ssh_port and ssh_port != 22:
            ssh_cmd.extend(["-p", str(ssh_port)])
        
        # Add key if provided
        if ssh_key_path and ssh_key_path.strip():
            expanded_key_path = os.path.expanduser(ssh_key_path)
            if expanded_key_path.endswith('.pub'):
                expanded_key_path = expanded_key_path[:-4]
            
            if os.path.exists(expanded_key_path):
                ssh_cmd.extend(["-i", expanded_key_path])
            else:
                return {"success": False, "message": f"SSH key not found: {expanded_key_path}"}
        
        # Add user@host
        ssh_cmd.append(f"{ssh_user}@{router_ip}")
        
        # Add the actual command to execute
        ssh_cmd.append(router_command)
        
        # If password is provided and no key, use sshpass
        if ssh_password and not ssh_key_path:
            if shutil.which("sshpass"):
                ssh_cmd = ["sshpass", "-p", ssh_password] + ssh_cmd
            else:
                return {
                    "success": False, 
                    "message": "Password authentication requires 'sshpass'. Please install it or use SSH key authentication."
                }
        
        logging.info(f"Executing router command: {router_command}")
        
        # Execute the command
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=60  # Longer timeout for commands that might take time
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode == 0:
            logging.info(f"Router command executed successfully")
            return {
                "success": True,
                "output": output,
                "message": "Command executed successfully"
            }
        else:
            logging.warning(f"Router command failed with code {result.returncode}: {error}")
            return {
                "success": False,
                "output": output,
                "error": error,
                "message": f"Command failed with exit code {result.returncode}"
            }
            
    except subprocess.TimeoutExpired:
        logging.error(f"Router command timed out: {router_command}")
        return {"success": False, "message": "Command execution timed out"}
    except Exception as e:
        logging.error(f"Router command execution error: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

def main():
    """Main loop to read commands and send status."""
    while True:
        try:
            message = read_message()
            # --- Key Change 5: Demote frequent, routine messages to DEBUG ---
            logging.debug(f"Received message: {message}")
            command = message.get("command")
            response = {}

            if command == "startTunnel":
                response = execute_tunnel_command("start", message.get("config"))
            elif command == "stopTunnel":
                response = execute_tunnel_command("stop", message.get("config"))
            elif command == "getStatus":
                config = message.get("config")
                status = get_tunnel_status(config)
                response = status
                
                if config and config.get("type") == "openwrt_passwall2":
                    # For Passwall2, perform the web/tcp checks through the router's
                    # exposed SOCKS port so the latency charts get real data.
                    router_host = (config.get("openwrtHost") or config.get("passwall2Host") or "").strip()
                    try:
                        router_socks_port = int(config.get("openwrtSocksPort") or config.get("passwall2SocksPort") or 1080)
                    except (TypeError, ValueError):
                        router_socks_port = 1080

                    if status.get("connected") and router_host:
                        proxy_check_config = {
                            "protocol": "SOCKS5",
                            "host": router_host,
                            "port": router_socks_port,
                        }
                        web_latency, web_status, _ = perform_web_check(url=message.get("webCheckUrl"), proxy_config=proxy_check_config)
                        tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost", "youtube.com"), proxy_config=proxy_check_config)
                        response.update({
                            "web_check_latency_ms": web_latency,
                            "web_check_status": web_status,
                            "tcp_ping_ms": tcp_latency,
                            "connection_type": "openwrt_service",
                            "socks_port": router_socks_port,
                            "passwall2_status": status.get("passwall2_status", "unknown"),
                        })
                    else:
                        response.update({
                            "web_check_latency_ms": -1,
                            "web_check_status": "N/A (OpenWrt Service)",
                            "tcp_ping_ms": -1,
                            "connection_type": "openwrt_service",
                            "passwall2_status": status.get("passwall2_status", "unknown"),
                        })
                elif status.get("connected") and status.get("socks_port"):
                    # For external proxies, we must use the configured host.
                    # For tunnel-based proxies, the host is always 127.0.0.1.
                    is_external = config.get("type") == "external"
                    
                    proxy_check_config = {
                        "protocol": config.get("proxyProtocol", "SOCKS5") if is_external else "SOCKS5",
                        "host": config.get("proxyHost") if is_external else "127.0.0.1",
                        "port": status["socks_port"]
                    }

                    if proxy_check_config["host"]:
                        web_latency, web_status, _ = perform_web_check(url=message.get("webCheckUrl"), proxy_config=proxy_check_config)
                        tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost", "youtube.com"), proxy_config=proxy_check_config)
                        response.update({"web_check_latency_ms": web_latency, "web_check_status": web_status, "tcp_ping_ms": tcp_latency, "connection_type": "proxy"})
                    else:
                        response.update({"web_check_latency_ms": -1, "web_check_status": "N/A (No Proxy Host)", "tcp_ping_ms": -1})
                else:
                    # Direct ping if tunnel is down or has no SOCKS port
                    tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost", "youtube.com")) 
                    response.update({"web_check_latency_ms": -1, "web_check_status": "N/A (Tunnel Down)", "tcp_ping_ms": tcp_latency, "connection_type": "direct"})
            elif command == "testConnection":
                response = handle_test_connection(message)
            elif command == "getLogs":
                identifier = message.get("identifier")
                conn_type = message.get("conn_type")
                response = get_logs(identifier=identifier, conn_type=conn_type)
            elif command == "clearLogs":
                response = clear_logs()
            elif command == "setSystemProxy":
                response = handle_set_system_proxy(message)
            elif command == "webCheck":
                # This command is now aware of the host for external checks
                proxy_config = {
                    "protocol": message.get("proxy_protocol", "SOCKS5"),
                    "host": message.get("proxy_host", "127.0.0.1"),
                    "port": message.get("proxy_port")
                } if message.get("proxy_port") else None
                latency, status, error = perform_web_check(url=message.get("url"), proxy_config=proxy_config)
                response = {"latency": latency, "status": status, "error": error}
            elif command == "tcpPing":
                proxy_config = {
                    "protocol": message.get("proxy_protocol", "SOCKS5"),
                    "host": message.get("proxy_host", "127.0.0.1"),
                    "port": message.get("proxy_port")
                } if message.get("proxy_port") else None
                latency, error = perform_tcp_ping(
                    host=message.get("host"), 
                    port=message.get("port", 443),
                    timeout=message.get("timeout", 5) / 1000.0,  # Convert ms to seconds
                    proxy_config=proxy_config
                )
                response = {"success": error is None, "latency": latency, "error": error}
            elif command == "passwall2":
                action = message.get("action")
                config = message.get("config")
                proxy_id = message.get("proxyId")
                proxy_data = message.get("proxyData")
                urls = message.get("urls")
                response = execute_passwall2_command(action, config, proxy_id, proxy_data, urls)
            elif command == "testRouterConnection":
                response = handle_test_router_connection(message)
            elif command == "executeRouterCommand":
                router_command = message.get("routerCommand")
                config = message.get("config")
                response = execute_router_command(router_command, config)
            elif command == "checkSubscriptionQuota":
                response = check_subscription_quota(message.get("urls") or [])
            elif command == "checkSubscriptionNodes":
                response = check_subscription_nodes(
                    message.get("urls") or [],
                    max_nodes_per_sub=int(message.get("maxNodes") or 120),
                    concurrency=int(message.get("concurrency") or 24),
                    timeout=float(message.get("timeout") or 3.0),
                )
            else:
                logging.warning(f"Unknown command received: {command}")
                continue

            logging.debug(f"Sending response: {response}")
            send_message(response)

        except Exception as e:
            logging.error(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            # Send an error response if possible, so the extension isn't left hanging
            try:
                send_message({"success": False, "message": f"A critical error occurred in the native host: {e}"})
            except:
                pass # If sending fails, just continue
            continue

if __name__ == '__main__':
    main()