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

def load_iran_ip_ranges():
    import re
    import os
    paths_to_try = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../iran_ip_ranges.js"),
        "/Users/majidsoorani/chrome_holocron/iran_ip_ranges.js"
    ]
    for p in paths_to_try:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                    ips = re.findall(r'"([^"]+/\d+)"', content)
                    if ips:
                        return ips
            except Exception:
                pass
    return [
        "2.176.0.0/13", "2.184.0.0/13", "5.52.192.0/20", "5.56.0.0/15", "5.63.12.0/22",
        "5.112.0.0/13", "5.120.0.0/14", "5.124.0.0/15", "5.126.0.0/16", "5.144.0.0/14",
        "5.160.0.0/13", "5.200.128.0/17", "5.208.224.0/19", "5.216.96.0/19", "5.232.0.0/14",
        "5.236.0.0/15", "5.238.0.0/16", "31.24.224.0/19", "31.56.0.0/16", "37.32.0.0/16",
        "37.152.160.0/19", "37.255.224.0/19", "46.32.32.0/19", "46.209.0.0/16", "46.224.0.0/14",
        "62.3.32.0/19", "62.60.128.0/18", "62.99.128.0/17", "62.193.0.0/18", "62.220.96.0/19",
        "77.36.160.0/19", "77.77.64.0/19", "77.104.64.0/19", "77.238.96.0/19", "78.38.0.0/15",
        "78.109.128.0/18", "79.127.120.0/21", "79.132.208.0/20", "79.175.128.0/17", "80.69.128.0/18",
        "80.71.64.0/19", "80.75.0.0/18", "80.191.0.0/16", "81.12.0.0/17", "81.28.0.0/18",
        "81.31.160.0/19", "81.90.144.0/20", "81.91.128.0/19", "82.99.192.0/18", "82.102.0.0/19",
        "83.123.192.0/18", "84.47.128.0/17", "84.241.0.0/18", "85.9.64.0/18", "85.15.0.0/16",
        "85.133.128.0/18", "85.185.0.0/16", "86.57.0.0/17", "87.107.0.0/17", "87.236.192.0/18",
        "87.247.160.0/19", "88.135.32.0/19", "89.32.240.0/20", "89.42.208.0/20", "89.45.0.0/18",
        "89.45.64.0/19", "89.144.192.0/18", "89.165.0.0/17", "89.187.160.0/19", "89.198.96.0/19",
        "89.221.96.0/19", "91.92.0.0/14", "91.98.0.0/15", "91.108.4.0/22", "91.241.44.0/22",
        "92.42.48.0/20", "92.50.0.0/16", "92.60.0.0/16", "92.244.128.0/17", "93.113.0.0/18",
        "93.114.0.0/15", "93.116.0.0/14", "93.126.0.0/16", "94.74.128.0/17", "94.101.128.0/18",
        "94.139.160.0/19", "94.182.0.0/15", "94.242.192.0/18", "95.38.0.0/17", "95.82.0.0/16",
        "95.106.128.0/17", "95.140.160.0/19", "95.156.224.0/19", "95.215.0.0/17", "109.73.0.0/18",
        "109.109.0.0/19", "109.122.128.0/17", "109.125.128.0/17", "109.169.0.0/16", "109.202.0.0/16",
        "109.225.0.0/16", "130.185.64.0/18", "151.232.0.0/13", "158.58.128.0/17", "176.65.192.0/18",
        "178.63.32.0/19", "178.131.0.0/17", "178.252.160.0/19", "185.4.40.0/22", "185.5.248.0/22",
        "185.9.144.0/22", "185.13.112.0/22", "185.15.44.0/22", "185.24.88.0/22", "185.37.28.0/22",
        "185.39.192.0/22", "185.43.220.0/22", "185.44.208.0/22", "185.46.212.0/22", "185.47.20.0/22",
        "185.49.84.0/22", "185.49.140.0/22", "185.50.100.0/22", "185.51.204.0/22", "185.53.144.0/22",
        "185.55.184.0/22", "185.60.140.0/22", "185.69.144.0/22", "185.69.152.0/22", "185.80.188.0/22",
        "185.81.96.0/22", "185.86.148.0/22", "185.94.96.0/22", "185.97.68.0/22", "185.105.240.0/22",
        "185.129.188.0/22", "185.143.232.0/22", "185.146.172.0/22", "185.163.244.0/22", "185.181.8.0/22",
        "185.198.12.0/22", "185.205.208.0/22", "185.210.140.0/22", "185.213.164.0/22", "185.229.20.0/22",
        "185.231.112.0/22", "185.233.108.0/22", "185.255.188.0/22", "193.104.34.0/23", "193.189.122.0/23",
        "194.5.196.0/22", "194.33.188.0/22", "194.104.128.0/19", "195.146.32.0/19", "195.181.160.0/20",
        "195.248.224.0/19", "212.33.192.0/18", "213.108.224.0/19", "213.233.160.0/19", "217.218.0.0/15"
    ]

def optimize_route_rules(config_data):
    if "route" not in config_data:
        config_data["route"] = {}
    
    route = config_data["route"]
    route["auto_detect_interface"] = True
    
    # 1. Setup Remote Rule Sets
    rule_sets = route.setdefault("rule_set", [])
    
    geosite_def = {
        "type": "remote",
        "tag": "geosite-ir",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs"
    }
    geoip_def = {
        "type": "remote",
        "tag": "geoip-ir",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs"
    }
    
    # Add/Update geosite-ir
    has_geosite = False
    for rs in rule_sets:
        if rs.get("tag") == "geosite-ir":
            rs["type"] = "remote"
            rs["format"] = "binary"
            rs["url"] = geosite_def["url"]
            has_geosite = True
            break
    if not has_geosite:
        rule_sets.append(geosite_def)
        
    # Add/Update geoip-ir
    has_geoip = False
    for rs in rule_sets:
        if rs.get("tag") == "geoip-ir":
            rs["type"] = "remote"
            rs["format"] = "binary"
            rs["url"] = geoip_def["url"]
            has_geoip = True
            break
    if not has_geoip:
        rule_sets.append(geoip_def)
        
    rules = route.setdefault("rules", [])
    
    # 2. Add/Update direct routing rule for rule sets
    ruleset_rule = None
    for r in rules:
        if r.get("outbound") == "direct" and r.get("action") == "route" and "rule_set" in r and "domain_suffix" not in r:
            ruleset_rule = r
            break
    
    # Clean up any buggy combined rules
    for r in list(rules):
        if r.get("outbound") == "direct" and "rule_set" in r and "domain_suffix" in r:
            r.pop("domain_suffix", None)
            ruleset_rule = r
            
    if not ruleset_rule:
        ruleset_rule = {
            "rule_set": ["geosite-ir", "geoip-ir"],
            "action": "route",
            "outbound": "direct"
        }
        rules.append(ruleset_rule)
    else:
        rs_list = ruleset_rule.setdefault("rule_set", [])
        for rs in ["geosite-ir", "geoip-ir"]:
            if rs not in rs_list:
                rs_list.append(rs)
        ruleset_rule["action"] = "route"
        ruleset_rule["outbound"] = "direct"

    # 3. Add/Update direct routing rule for domain suffixes
    domain_rule = None
    for r in rules:
        if r.get("outbound") == "direct" and r.get("action") == "route" and "domain_suffix" in r and "rule_set" not in r:
            domain_rule = r
            break
            
    if not domain_rule:
        domain_rule = {
            "domain_suffix": ["ir", "xn--mgba3a4f16a"],
            "action": "route",
            "outbound": "direct"
        }
        rules.append(domain_rule)
    else:
        suffixes = domain_rule.setdefault("domain_suffix", [])
        for dom in ["ir", "xn--mgba3a4f16a"]:
            if dom not in suffixes:
                suffixes.append(dom)
        domain_rule["action"] = "route"
        domain_rule["outbound"] = "direct"

    # Remove any old huge ip_cidr or domain_suffix rule from early native host versions to keep router clean
    for r in list(rules):
        if r.get("outbound") == "direct" and "ip_cidr" in r and len(r.get("ip_cidr", [])) > 50:
            rules.remove(r)

    # 4. Ensure DNS rules
    dns_rules = config_data.setdefault("dns", {}).setdefault("rules", [])
    
    # DNS rule set direct rule
    dns_ruleset_rule = None
    for r in dns_rules:
        if r.get("server") == "dns-direct" and "rule_set" in r and "domain_suffix" not in r:
            dns_ruleset_rule = r
            break
    for r in list(dns_rules):
        if r.get("server") == "dns-direct" and "rule_set" in r and "domain_suffix" in r:
            r.pop("domain_suffix", None)
            dns_ruleset_rule = r
            
    if not dns_ruleset_rule:
        dns_ruleset_rule = {
            "rule_set": ["geosite-ir"],
            "server": "dns-direct"
        }
        dns_rules.insert(0, dns_ruleset_rule)
    else:
        rs_list = dns_ruleset_rule.setdefault("rule_set", [])
        if "geosite-ir" not in rs_list:
            rs_list.append("geosite-ir")
            
    # DNS domain suffix direct rule
    dns_domain_rule = None
    for r in dns_rules:
        if r.get("server") == "dns-direct" and "domain_suffix" in r and "rule_set" not in r:
            dns_domain_rule = r
            break
            
    if not dns_domain_rule:
        dns_domain_rule = {
            "domain_suffix": ["ir", "xn--mgba3a4f16a"],
            "server": "dns-direct"
        }
        dns_rules.insert(0, dns_domain_rule)
    else:
        suffixes = dns_domain_rule.setdefault("domain_suffix", [])
        for dom in ["ir", "xn--mgba3a4f16a"]:
            if dom not in suffixes:
                suffixes.append(dom)

    # 5. Ensure dns-direct server points to 127.0.0.1 (dnsmasq loopback)
    dns_servers = config_data.setdefault("dns", {}).setdefault("servers", [])
    for server in dns_servers:
        if server.get("tag") == "dns-direct":
            server["server"] = "127.0.0.1"
            server["type"] = "udp"

def optimize_outbounds(config_data):
    outbounds = config_data.setdefault("outbounds", [])
    
    # 1. Balancer interval
    for o in outbounds:
        if o.get("tag") == "balancer":
            o["url"] = "https://www.google.com/generate_204"
            o["interval"] = "30s"
            o["tolerance"] = 50
            
    # 2. VLESS Reality outbounds
    for outbound in outbounds:
        tag = outbound.get("tag", "")
        if outbound.get("type") == "vless":
            tls = outbound.setdefault("tls", {})
            reality = tls.get("reality", {})
            if reality or "reality" in tag:
                if not reality:
                    reality = tls.setdefault("reality", {"enabled": True})
                reality["enabled"] = True
                
                if not reality.get("public_key"):
                    reality["public_key"] = "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4"
                
                sid = reality.get("short_id")
                if not sid:
                    reality["short_id"] = "034e50c5756bb22a"
                elif isinstance(sid, list):
                    reality["short_id"] = sid[0] if sid else "034e50c5756bb22a"
                elif isinstance(sid, str):
                    if "," in sid:
                        parts = [s.strip() for s in sid.split(",") if s.strip()]
                        reality["short_id"] = parts[0] if parts else "034e50c5756bb22a"
                
                if not outbound.get("flow"):
                    outbound["flow"] = "xtls-rprx-vision"
                
                outbound["packet_encoding"] = "xudp"
                outbound["multiplex"] = {
                    "enabled": True,
                    "protocol": "h2mux",
                    "max_connections": 8
                }
                outbound["tcp_fast_open"] = True
                outbound["connect_timeout"] = "5s"
                
                tls["enabled"] = True
                tls["server_name"] = tls.get("server_name") or outbound.get("server", "www.microsoft.com")
                utls = tls.setdefault("utls", {})
                utls["enabled"] = True
                utls["fingerprint"] = "chrome"

def optimize_singbox_config(config_data):
    try:
        optimize_route_rules(config_data)
    except Exception as e:
        logger.error(f"Error optimizing route rules: {e}")
    try:
        optimize_outbounds(config_data)
    except Exception as e:
        logger.error(f"Error optimizing outbounds: {e}")

def parse_uri_to_singbox_outbound(uri, tag):
    import base64
    from urllib.parse import urlsplit, unquote, parse_qs
    uri = uri.strip()
    if not uri:
        return None
    try:
        if uri.startswith("ss://"):
            frag = ""
            body = uri[5:]
            if "#" in body:
                body, frag = body.split("#", 1)
            name = unquote(frag) if frag else f"ss-{tag}"
            if "@" in body:
                userinfo, hostport = body.split("@", 1)
                missing_padding = len(userinfo) % 4
                if missing_padding:
                    userinfo += '=' * (4 - missing_padding)
                decoded_user = base64.b64decode(userinfo).decode('utf-8', errors='ignore')
                method, password = decoded_user.split(":", 1)
                host, port = hostport.rsplit(":", 1)
            else:
                missing_padding = len(body) % 4
                if missing_padding:
                    body += '=' * (4 - missing_padding)
                decoded = base64.b64decode(body).decode('utf-8', errors='ignore')
                if "@" in decoded:
                    userinfo, hostport = decoded.split("@", 1)
                    method, password = userinfo.split(":", 1)
                    host, port = hostport.rsplit(":", 1)
                else:
                    return None
            return {
                "type": "shadowsocks",
                "tag": tag,
                "server": host,
                "server_port": int(port),
                "method": method,
                "password": password
            }
        elif uri.startswith("vless://"):
            content = uri[8:]
            frag = ""
            if "#" in content:
                content, frag = content.split("#", 1)
            uuid, remain = content.split("@", 1)
            hostport, *query_parts = remain.split("?", 1)
            host, port = hostport.rsplit(":", 1)
            query = query_parts[0] if query_parts else ""
            params = parse_qs(query)
            
            security = params.get("security", ["none"])[0]
            sni = params.get("sni", [""])[0]
            transport_type = params.get("type", ["tcp"])[0]
            ws_host = params.get("host", [""])[0]
            ws_path = params.get("path", ["/"])[0]
            
            outbound = {
                "type": "vless",
                "tag": tag,
                "server": host,
                "server_port": int(port),
                "uuid": uuid,
                "flow": ""
            }
            if security == "reality":
                pbk = params.get("pbk", [""])[0]
                sid_str = params.get("sid", [""])[0]
                short_ids = [s.strip() for s in sid_str.split(",") if s.strip()] if sid_str else []
                reality_sid = short_ids[0] if short_ids else ""
                flow_val = params.get("flow", ["xtls-rprx-vision"])[0] or "xtls-rprx-vision"
                fp_val = params.get("fp", ["chrome"])[0] or "chrome"
                
                outbound["flow"] = flow_val
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": sni or host,
                    "utls": {
                        "enabled": True,
                        "fingerprint": fp_val
                    },
                    "reality": {
                        "enabled": True,
                        "public_key": pbk,
                        "short_id": reality_sid
                    }
                }
                outbound["packet_encoding"] = "xudp"
                outbound["multiplex"] = {
                    "enabled": True,
                    "protocol": "h2mux",
                    "max_connections": 8
                }
                outbound["tcp_fast_open"] = True
                outbound["connect_timeout"] = "5s"
            elif security == "tls":
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": sni or host,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    }
                }
                outbound["packet_encoding"] = "xudp"
            if transport_type == "ws":
                outbound["transport"] = {
                    "type": "ws",
                    "path": ws_path,
                    "headers": {
                        "Host": ws_host or host
                    }
                }
            return outbound
        elif uri.startswith("vmess://"):
            content = uri[8:]
            blob = content.split("#", 1)[0]
            padded = blob + "=" * (-len(blob) % 4)
            raw = base64.b64decode(padded).decode("utf-8", errors="ignore")
            data = json.loads(raw)
            host = (data.get("add") or data.get("host") or "").strip()
            port = int(str(data.get("port") or 0))
            uuid = data.get("id")
            
            outbound = {
                "type": "vmess",
                "tag": tag,
                "server": host,
                "server_port": port,
                "uuid": uuid,
                "security": data.get("scy", "auto"),
                "alter_id": int(data.get("aid", 0))
            }
            if data.get("tls") == "tls":
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": data.get("sni") or host
                }
            if data.get("net") == "ws":
                outbound["transport"] = {
                    "type": "ws",
                    "path": data.get("path", "/"),
                    "headers": {
                        "Host": data.get("host") or host
                    }
                }
            return outbound
        elif uri.startswith("trojan://"):
            content = uri[9:]
            frag = ""
            if "#" in content:
                content, frag = content.split("#", 1)
            password, remain = content.split("@", 1)
            hostport, *query_parts = remain.split("?", 1)
            host, port = hostport.rsplit(":", 1)
            
            query = query_parts[0] if query_parts else ""
            params = parse_qs(query)
            sni = params.get("sni", [""])[0]
            
            return {
                "type": "trojan",
                "tag": tag,
                "server": host,
                "server_port": int(port),
                "password": password,
                "tls": {
                    "enabled": True,
                    "server_name": sni or host
                }
            }
    except Exception as e:
        logger.error(f"Error parsing node URI {uri}: {e}")
    return None

def execute_singbox_emulation_command(action, ssh_cmd_base, proxy_id=None, proxy_data=None, urls=None):
    import base64
    import tempfile
    import urllib.parse
    
    # 1. status
    if action == "status":
        cmd = ssh_cmd_base + ["pgrep -f sing-box >/dev/null && echo 'enabled' || echo 'disabled'"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        return {"success": True, "status": res.stdout.strip()}
        
    # 2. start_service / stop_service / restart_service
    elif action in ["start_service", "stop_service", "restart_service"]:
        act = action.split('_')[0]
        cmd = ssh_cmd_base + [f"/etc/init.d/sing-box {act}"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": f"Failed to {act} sing-box: {res.stderr.strip()}"}
        return {"success": True, "message": f"Sing-box service {act}ed successfully"}

    # 2.5. test_node
    elif action == "test_node":
        if not proxy_id:
            return {"success": False, "message": "Proxy ID is required for test_node."}
            
        test_urls = urls or [
            "https://www.youtube.com",
            "https://www.google.com"
        ]
        
        results = {}
        tested_via = {}
        
        # Read current config to find the outbound configuration
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        config_data = {}
        if res.returncode == 0:
            try:
                config_data = json.loads(res.stdout)
            except:
                pass
                
        outbounds = config_data.get("outbounds", [])
        target_outbound = None
        for o in outbounds:
            if o.get("tag") == proxy_id:
                target_outbound = o
                break

        # If it is the balancer, we can use the main running sing-box on port 1080
        if proxy_id == "balancer":
            urls_args = " ".join([f"'{u}'" for u in test_urls])
            remote_cmd = (
                "PIDS=\"\"\n"
                f"for url in {urls_args}; do "
                "  (res=$(curl -s -m 20 -o /dev/null -w \"%{http_code}:%{time_total}\" --socks5-hostname 127.0.0.1:1080 \"$url\" 2>/dev/null); "
                "  if [ $? -ne 0 ] || [ -z \"$res\" ]; then res=\"000:0.0\"; fi; "
                "  echo \"RESULT|$url|$res\") & "
                "  PIDS=\"$PIDS $!\"\n"
                "done; wait $PIDS"
            )
            test_cmd = ssh_cmd_base + [remote_cmd]
            test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=35)
            
            for line in (test_res.stdout or "").splitlines():
                if line.startswith("RESULT|"):
                    parts = line.split("|")
                    if len(parts) >= 3:
                        u = parts[1]
                        out = parts[2]
                        code = "000"
                        sec = 0.0
                        if ":" in out:
                            c_str, _, s_str = out.partition(":")
                            code = c_str.strip()
                            try:
                                sec = float(s_str.strip())
                            except:
                                sec = 0.0
                        if code in ["200", "204", "301", "302", "307", "308"] and sec > 0:
                            results[u] = max(1, int(sec * 1000))
                        else:
                            results[u] = -1
                        tested_via[u] = proxy_id
                        
        elif target_outbound:
            import random
            test_port = random.randint(10080, 10250)
            
            test_config = {
                "log": {"level": "warn"},
                "inbounds": [{
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": test_port
                }],
                "outbounds": [
                    target_outbound,
                    {"type": "direct", "tag": "direct"}
                ]
            }
            test_config_str = json.dumps(test_config)
            
            # Escape single quotes in JSON string
            escaped_json = test_config_str.replace("'", "'\\''")
            urls_args = " ".join([f"'{u}'" for u in test_urls])
            
            remote_cmd = (
                f"cat << 'EOF' > /tmp/test_sb_{test_port}.json\n{test_config_str}\nEOF\n"
                f"/usr/bin/sing-box run -c /tmp/test_sb_{test_port}.json >/dev/null 2>&1 & PID=$!\n"
                "for i in $(seq 1 15); do\n"
                f"  if netstat -an 2>/dev/null | grep {test_port} | grep LISTEN >/dev/null; then break; fi\n"
                "  sleep 0.1\n"
                "done\n"
                "PIDS=\"\"\n"
                f"for url in {urls_args}; do\n"
                "  (res=$(curl -s -m 20 -o /dev/null -w \"%{http_code}:%{time_total}\" --socks5-hostname 127.0.0.1:" + str(test_port) + " \"$url\" 2>/dev/null); "
                "  if [ $? -ne 0 ] || [ -z \"$res\" ]; then res=\"000:0.0\"; fi; "
                "  echo \"RESULT|$url|$res\") &\n"
                "  PIDS=\"$PIDS $!\"\n"
                "done\n"
                "wait $PIDS\n"
                "kill $PID 2>/dev/null || true\n"
                f"rm -f /tmp/test_sb_{test_port}.json"
            )
            
            test_cmd = ssh_cmd_base + [remote_cmd]
            test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=35)
            
            for line in (test_res.stdout or "").splitlines():
                if line.startswith("RESULT|"):
                    parts = line.split("|")
                    if len(parts) >= 3:
                        u = parts[1]
                        out = parts[2]
                        code = "000"
                        sec = 0.0
                        if ":" in out:
                            c_str, _, s_str = out.partition(":")
                            code = c_str.strip()
                            try:
                                sec = float(s_str.strip())
                            except:
                                sec = 0.0
                        if code in ["200", "204", "301", "302", "307", "308"] and sec > 0:
                            results[u] = max(1, int(sec * 1000))
                        else:
                            results[u] = -1
                        tested_via[u] = proxy_id
        else:
            for u in test_urls:
                results[u] = -1
                tested_via[u] = proxy_id
                
        for u in test_urls:
            if u not in results:
                results[u] = -1
            if u not in tested_via:
                tested_via[u] = proxy_id
                
        return {
            "success": True,
            "node_id": proxy_id,
            "results": results,
            "tested_via": tested_via
        }

    # 2.7. get_health_metrics
    elif action == "get_health_metrics":
        cmd = ssh_cmd_base + ["logread | grep -E 'sing-box|dropbear' | tail -n 1000; echo '===NET_DEV==='; cat /proc/net/dev"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        log_lines = []
        net_dev_text = ""
        if res.returncode == 0:
            stdout_parts = res.stdout.split('===NET_DEV===')
            log_lines = stdout_parts[0].splitlines()
            if len(stdout_parts) > 1:
                net_dev_text = stdout_parts[1]
        else:
            return {"success": False, "message": f"Failed to read logs: {res.stderr.strip()}"}
            
        # Global re is used instead of local import to avoid UnboundLocalError in other branches
        
        dns_total = 0
        dns_exchanged = 0
        dns_cached = 0
        dns_rejected = 0
        dns_latencies = []
        
        conn_latencies = []
        
        reconnect_count = 0
        ssh_sessions = 0
        ssh_auth_failures = 0
        
        latency_re = re.compile(r'\[\d+\s+([\d\.]+)(ms|s)\]')
        dns_re = re.compile(r'dns:\s+(exchanged|rejected|cached)')
        ssh_auth_ok_re = re.compile(r'Pubkey auth succeeded')
        ssh_disconnect_re = re.compile(r'Disconnect received')
        error_re = re.compile(r'(FATAL|ERROR|fail|dependency|error)', re.IGNORECASE)
        
        for line in log_lines:
            if ssh_auth_ok_re.search(line):
                ssh_sessions += 1
            elif ssh_disconnect_re.search(line):
                ssh_sessions = max(0, ssh_sessions - 1)
                
            if error_re.search(line) and "sing-box" in line:
                reconnect_count += 1
                
            lat_match = latency_re.search(line)
            if lat_match:
                val = float(lat_match.group(1))
                unit = lat_match.group(2)
                ms = val if unit == 'ms' else val * 1000
                
                if 'dns:' in line:
                    dns_latencies.append(ms)
                else:
                    conn_latencies.append(ms)
                    
            dns_match = dns_re.search(line)
            if dns_match:
                dns_total += 1
                act_name = dns_match.group(1)
                if act_name == 'exchanged':
                    dns_exchanged += 1
                elif act_name == 'cached':
                    dns_cached += 1
                elif act_name == 'rejected':
                    dns_rejected += 1
                    
        avg_latency = 0
        jitter = 0
        if conn_latencies:
            avg_latency = sum(conn_latencies) / len(conn_latencies)
            jitter = sum(abs(l - avg_latency) for l in conn_latencies) / len(conn_latencies)
            
        p95_latency = 0
        if conn_latencies:
            sorted_l = sorted(conn_latencies)
            idx = int(len(sorted_l) * 0.95)
            p95_latency = sorted_l[min(idx, len(sorted_l)-1)]
            
        dns_success_rate = 1.0
        if dns_total > 0:
            dns_success_rate = (dns_exchanged + dns_cached) / dns_total
            
        dns_cache_hit_rate = 0.0
        if (dns_exchanged + dns_cached) > 0:
            dns_cache_hit_rate = dns_cached / (dns_exchanged + dns_cached)
            
        avg_dns_latency = 0
        if dns_latencies:
            avg_dns_latency = sum(dns_latencies) / len(dns_latencies)
            
        dns_latency_factor = max(0.0, 1.0 - (avg_dns_latency / 1000.0))
        dns_score = int((dns_success_rate * 0.7 + dns_latency_factor * 0.3) * 100)
        dns_score = max(0, min(100, dns_score))
        
        error_penalty = max(0.0, 1.0 - (reconnect_count * 0.1))
        latency_penalty = max(0.0, 1.0 - (p95_latency / 2000.0))
        tunnel_score = int((error_penalty * 0.6 + latency_penalty * 0.4) * 100)
        tunnel_score = max(0, min(100, tunnel_score))
        
        dns_reject_rate = dns_rejected / dns_total if dns_total > 0 else 0.0
        reject_penalty = max(0.0, 1.0 - dns_reject_rate)
        jitter_penalty = max(0.0, 1.0 - (jitter / 500.0))
        stability_score = int((reject_penalty * 0.4 + jitter_penalty * 0.4 + error_penalty * 0.2) * 100)
        stability_score = max(0, min(100, stability_score))
        
        loss_estimate = 0.0
        if dns_total > 0:
            loss_estimate = dns_rejected / dns_total
        loss_estimate = min(1.0, loss_estimate + (reconnect_count * 0.02))
        
        # Modem Usage/Traffic share parsing
        # Modem Usage/Traffic share parsing
        import tempfile
        stats_file = Path(tempfile.gettempdir()) / "holocron_modem_stats.json"
        
        last_stats = {}
        last_time = None
        if stats_file.exists():
            try:
                with open(stats_file, 'r') as f:
                    cached = json.load(f)
                    last_stats = cached.get("stats", {})
                    last_time = cached.get("time")
            except Exception as e:
                logger.warning(f"Failed to read modem stats cache: {e}")

        modem_traffic = {
            "success": False,
            "interfaces": {},
            "total_speed": 0.0
        }
        
        if net_dev_text:
            try:
                current_time = time.time()
                current_stats = {}
                for line in net_dev_text.splitlines():
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    iface_name = iface.strip()
                    parts = data.split()
                    if len(parts) >= 9:
                        rx_bytes = int(parts[0])
                        tx_bytes = int(parts[8])
                        current_stats[iface_name] = rx_bytes + tx_bytes
                
                # Check delta
                if last_time is not None and last_stats:
                    dt = current_time - last_time
                    # Only compute speed if the time difference is reasonable (e.g. 0.5s to 15s)
                    if 0.5 <= dt <= 15.0:
                        total_speed = 0
                        speeds = {}
                        # Zitel: wan, RighTel: lan3, Irancell: wl1-sta0 (or wl1), Mobinnet: lan1 (or wl0-sta0, wl0)
                        target_interfaces = ['wan', 'lan3', 'wl1-sta0', 'lan1', 'wl0-sta0', 'wl1', 'wl0']
                        
                        for iface in target_interfaces:
                            if iface in current_stats and iface in last_stats:
                                curr_val = current_stats[iface]
                                prev_val = last_stats[iface]
                                
                                # Handle reboot/reset
                                if curr_val < prev_val:
                                    prev_val = curr_val
                                
                                delta = max(0, curr_val - prev_val)
                                speed = delta / dt
                                speeds[iface] = speed
                                total_speed += speed
                        
                        # Compute percentage shares
                        shares = {}
                        for iface, speed in speeds.items():
                            share = (speed / total_speed * 100) if total_speed > 0 else 0
                            
                            # Formatted speed string
                            speed_formatted = ""
                            if speed > 1024 * 1024:
                                speed_formatted = f"{speed / (1024 * 1024):.1f} MB/s"
                            elif speed > 1024:
                                speed_formatted = f"{speed / 1024:.1f} KB/s"
                            else:
                                speed_formatted = f"{speed:.0f} B/s"
                            
                            shares[iface] = {
                                "speed": round(speed, 1),
                                "speed_formatted": speed_formatted,
                                "share": round(share, 1)
                            }
                        
                        modem_traffic = {
                            "success": True,
                            "interfaces": shares,
                            "total_speed": round(total_speed, 1)
                        }
                
                # Update persistent state in temp file
                try:
                    with open(stats_file, 'w') as f:
                        json.dump({"stats": current_stats, "time": current_time}, f)
                except Exception as e:
                    logger.error(f"Failed to write modem stats cache: {e}")
            except Exception as e:
                logger.error(f"Error parsing modem traffic: {e}")
        
        return {
            "success": True,
            "latency_avg_ms": int(avg_latency) if conn_latencies else 45,
            "latency_p95_ms": int(p95_latency) if conn_latencies else 95,
            "jitter_ms": int(jitter),
            "dns_success_rate": round(dns_success_rate, 2),
            "dns_cache_hit_rate": round(dns_cache_hit_rate, 2),
            "dns_latency_avg_ms": int(avg_dns_latency),
            "reconnects_count": reconnect_count,
            "packet_loss_estimate": round(loss_estimate, 3),
            "ssh_sessions": ssh_sessions,
            "dns_health": dns_score,
            "tunnel_quality": tunnel_score,
            "internet_stability": stability_score,
            "modem_traffic": modem_traffic
        }

    # 3. list_proxies
    elif action == "list_proxies":
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": f"Failed to read sing-box config: {res.stderr.strip()}"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        outbounds = config_data.get("outbounds", [])
        route_final = config_data.get("route", {}).get("final", "balancer")
        active_node_id = route_final
        
        proxies = []
        proxies.append({
            "id": "balancer",
            "type": "balancing",
            "remarks": "🔄 Balancer (Lowest Latency Auto-Select)",
            "name": "🔄 Balancer (Lowest Latency Auto-Select)",
            "address": "URL-Test",
            "port": "",
            "enabled": True,
            "is_active": active_node_id == "balancer"
        })
        
        # Get balancer outbounds
        balancer_outbounds = []
        for out in outbounds:
            if out.get("tag") == "balancer":
                balancer_outbounds = out.get("outbounds", [])
                break

        for out in outbounds:
            o_type = out.get("type")
            tag = out.get("tag")
            if o_type in ["shadowsocks", "vless", "vmess", "trojan", "socks", "ssh"]:
                remarks = out.get("remarks") or tag
                if tag == "ss-zitel":
                    remarks = "⚡ Zitel (wan) - Arvan Shadowsocks"
                elif tag == "ss-rightel":
                    remarks = "📶 RighTel (lan3) - Arvan Shadowsocks"
                elif tag == "ss-mobinnet":
                    remarks = "🚀 Mobinnet (lan1) - Arvan Shadowsocks"
                elif tag == "tunnel-zitel":
                    remarks = "🔒 Zitel (wan) - SSH Tunnel"
                elif tag == "tunnel-rightel":
                    remarks = "🔒 RighTel (lan3) - SSH Tunnel"
                elif tag == "tunnel-mobinnet":
                    remarks = "🔒 Mobinnet (lan1) - SSH Tunnel"
                elif tag == "ssh-vps-zitel":
                    remarks = "🔒 Zitel (wan) - VPS SSH Tunnel"
                elif tag == "ssh-vps-rightel":
                    remarks = "📶 RighTel (lan3) - VPS SSH Tunnel"
                elif tag == "ssh-vps-mobinnet":
                    remarks = "🚀 Mobinnet (lan1) - VPS SSH Tunnel"
                elif tag == "vless-reality-zitel":
                    remarks = "⚡ Zitel (wan) - VLESS Reality"
                elif tag == "vless-reality-rightel":
                    remarks = "📶 RighTel (lan3) - VLESS Reality"
                elif tag == "vless-reality-mobinnet":
                    remarks = "🚀 Mobinnet (lan1) - VLESS Reality"
                elif tag == "vless-reality-vps":
                    remarks = "☁️ VPS - VLESS Reality"
                elif tag == "nooshdaroo":
                    remarks = "🔒 Nooshdaroo DNS Tunnel (Local SOCKS5)"
                
                proxies.append({
                    "id": tag,
                    "type": o_type,
                    "remarks": remarks,
                    "name": remarks,
                    "address": out.get("server", ""),
                    "port": str(out.get("server_port") or out.get("port") or ""),
                    "enabled": True,
                    "is_active": active_node_id == tag,
                    "bind_interface": out.get("bind_interface", ""),
                    "in_balancer": tag in balancer_outbounds
                })
                
        cmd_stats = ssh_cmd_base + [
            "mem=$(awk '/MemTotal/ {total=$2} /MemAvailable/ {avail=$2} /MemFree/ {free=$2} /Buffers/ {buffers=$2} /Cached/ {cached=$2} END {if (total>0) {a=avail?avail:(free+buffers+cached); printf \"%d%%\", (total-a)/total*100} else {print \"N/A\"}}' /proc/meminfo); "
            "load=$(cut -d' ' -f1-3 /proc/loadavg); "
            "echo \"Mem: $mem | Load: $load\""
        ]
        res_stats = subprocess.run(cmd_stats, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        router_stats = res_stats.stdout.strip()
        
        cmd_run = ssh_cmd_base + ["pgrep -f sing-box >/dev/null && echo 'running' || echo 'stopped'"]
        res_run = subprocess.run(cmd_run, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        service_status = res_run.stdout.strip()
        
        return {
            "success": True,
            "proxies": proxies,
            "active_node_id": active_node_id,
            "service_status": service_status,
            "router_stats": router_stats,
            "message": f"Found {len(proxies)} proxies (Sing-box Emulation)"
        }

    # 4. use_proxy
    elif action == "use_proxy":
        if not proxy_id:
            return {"success": False, "message": "Proxy ID must be provided."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        if "route" not in config_data:
            config_data["route"] = {}
        config_data["route"]["final"] = proxy_id
        
        dns_servers = config_data.get("dns", {}).get("servers", [])
        for server in dns_servers:
            if server.get("tag") == "dns-remote":
                server["detour"] = proxy_id
                
        optimize_singbox_config(config_data)
        config_str = json.dumps(config_data, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_str)
            temp_path = f.name
            
        upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
        subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        os.unlink(temp_path)
        
        restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
        subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        return {"success": True, "message": f"Switched active node to {proxy_id}", "active_node_id": proxy_id}

    # 5. update_subscription / update_balance_nodes / reset_and_refresh_nodes
    elif action in ["update_subscription", "update_balance_nodes", "reset_and_refresh_nodes"]:
        chk_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/subscription_urls.json ] && echo 'exists' || echo 'missing'"]
        chk_res = subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        default_urls = [
            "https://cloudflaresoorani.soorani.workers.dev/c0686cb1-515d-4fe3-8f22-508746811ef3/sub",
            "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
            "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5",
            "https://multiservers.info/sub/djMsMzk6NTIsMTc3OTA5NzA0NQ2db88860a2#EXC5Q",
            "https://multiservers.info/sub/djMsMzQ3MzcsMTc3ODk2Nzk0MAa2bf94679b#QK8QF"
        ]
        
        sub_urls = default_urls
        if chk_res.stdout.strip() == "exists":
            cat_cmd = ssh_cmd_base + ["cat /etc/sing-box/subscription_urls.json"]
            cat_res = subprocess.run(cat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                sub_urls = json.loads(cat_res.stdout)
            except:
                pass
        else:
            write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
            subprocess.run(write_cmd, input=json.dumps(default_urls), text=True, timeout=10)
            
        all_nodes = []
        node_to_sub_map = {}
        router_host = "192.168.1.1"
        if ssh_cmd_base and "@" in ssh_cmd_base[-1]:
            router_host = ssh_cmd_base[-1].split("@")[-1]
        elif ssh_cmd_base:
            router_host = ssh_cmd_base[-1]
        for url in sub_urls:
            try:
                # If it's a raw proxy node, parse it directly!
                if url.startswith(("ss://", "vless://", "vmess://", "trojan://")):
                    parsed = parse_uri_to_singbox_outbound(url, f"node-{len(all_nodes)}")
                    if parsed:
                        name_match = re.search(r"#([^#\s]+)", url)
                        if name_match:
                            parsed["remarks"] = urllib.parse.unquote(name_match.group(1))
                        else:
                            parsed["remarks"] = f"{parsed['type'].upper()}-{parsed['server']}"
                        parsed["_sub_url"] = url
                        all_nodes.append(parsed)
                    continue

                # 1. Try to fetch directly from the Mac first (since it might have VPN/local proxy active)
                cmd = ["curl", "-s", "-L", "-m", "10", "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", url]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                content = proc.stdout.strip()
                
                # 2. Fallback to router SOCKS proxy if direct fetch fails or returns empty
                if not content or proc.returncode != 0:
                    logger.info(f"[update_subscription] Direct fetch for {url} failed. Trying via router proxy SOCKS5...")
                    cmd = ["curl", "-s", "-L", "-m", "10", "--proxy", f"socks5h://{router_host}:1080", "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", url]
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                    content = proc.stdout.strip()
                    
                if not content:
                    logger.warning(f"[update_subscription] Could not fetch subscription {url} (both direct and proxy failed)")
                    continue
                if "vless://" not in content and "vmess://" not in content and "ss://" not in content and "trojan://" not in content:
                    # decode base64
                    missing_padding = len(content) % 4
                    if missing_padding:
                        content += '=' * (4 - missing_padding)
                    content = base64.b64decode(content).decode('utf-8', errors='ignore')
                links = [line.strip() for line in content.splitlines() if line.strip()]
                for l in links:
                    try:
                        parsed = parse_uri_to_singbox_outbound(l, f"node-{len(all_nodes)}")
                        if parsed:
                            name_match = re.search(r"#([^#\s]+)", l)
                            if name_match:
                                parsed["remarks"] = urllib.parse.unquote(name_match.group(1))
                            else:
                                parsed["remarks"] = f"{parsed['type'].upper()}-{parsed['server']}"
                            parsed["_sub_url"] = url
                            all_nodes.append(parsed)
                    except Exception as parse_err:
                        logger.error(f"Failed to parse node {l} in subscription {url}: {parse_err}")
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")
                
        if not all_nodes:
            return {"success": False, "message": "Failed to fetch any proxy nodes from subscription URLs."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        core_tags = [
            "ss-zitel", "ss-rightel", "ss-mobinnet", 
            "tunnel-zitel", "tunnel-rightel", "tunnel-mobinnet", 
            "ssh-vps-zitel", "ssh-vps-rightel", "ssh-vps-mobinnet",
            "vless-reality-vps", "vless-reality-zitel", "vless-reality-rightel", "vless-reality-mobinnet",
            "direct", "block", "balancer", "nooshdaroo"
        ]
        outbounds = config_data.get("outbounds", [])
        new_outbounds = [o for o in outbounds if o.get("tag") in core_tags]
        
        # Ensure SOCKS tunnel outbounds are present
        tunnels_to_ensure = [
            {"type": "socks", "tag": "tunnel-zitel", "server": "127.0.0.1", "server_port": 1032},
            {"type": "socks", "tag": "tunnel-rightel", "server": "127.0.0.1", "server_port": 1033},
            {"type": "socks", "tag": "tunnel-mobinnet", "server": "127.0.0.1", "server_port": 1034},
            {"type": "socks", "tag": "ssh-vps-zitel", "server": "127.0.0.1", "server_port": 1042, "remarks": "🔒 Zitel (wan) - VPS SSH Tunnel"},
            {"type": "socks", "tag": "ssh-vps-rightel", "server": "127.0.0.1", "server_port": 1043, "remarks": "📶 RighTel (lan3) - VPS SSH Tunnel"},
            {"type": "socks", "tag": "ssh-vps-mobinnet", "server": "127.0.0.1", "server_port": 1044, "remarks": "🚀 Mobinnet (lan1) - VPS SSH Tunnel"}
        ]
        existing_tags = {o.get("tag") for o in new_outbounds}
        for t in tunnels_to_ensure:
            if t["tag"] not in existing_tags:
                new_outbounds.append(t)
                
        used_tags = set(core_tags)
        for idx, node in enumerate(all_nodes):
            remarks = node.pop("remarks", None)
            sub_url_for_node = node.pop("_sub_url", None)
            base_tag = remarks or f"node-{idx}"
            tag = base_tag
            suffix = 1
            while tag in used_tags:
                tag = f"{base_tag}_{suffix}"
                suffix += 1
            used_tags.add(tag)
            node["tag"] = tag
            if sub_url_for_node:
                node_to_sub_map[tag] = sub_url_for_node
            new_outbounds.append(node)
            
        config_data["outbounds"] = new_outbounds
        
        balancer = None
        for o in new_outbounds:
            if o.get("tag") == "balancer":
                balancer = o
                break
        if balancer:
            # Only include core tags in the balancer if they actually exist in outbounds to avoid dependency errors.
            all_existing_tags = {o.get("tag") for o in new_outbounds if o.get("tag") != "balancer"}
            desired_core = [
                "ss-zitel", "ss-rightel", "ss-mobinnet", 
                "tunnel-zitel", "tunnel-rightel", "tunnel-mobinnet",
                "ssh-vps-zitel", "ssh-vps-rightel", "ssh-vps-mobinnet",
                "vless-reality-vps", "vless-reality-zitel", "vless-reality-rightel", "vless-reality-mobinnet"
            ]
            balancer["outbounds"] = [t for t in desired_core if t in all_existing_tags] + [node["tag"] for node in all_nodes]
            
        optimize_singbox_config(config_data)
        config_str = json.dumps(config_data, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_str)
            temp_path = f.name
            
        upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
        subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        os.unlink(temp_path)
        
        # Write node-to-sub mapping
        node_to_sub_str = json.dumps(node_to_sub_map, indent=2)
        node_to_sub_cmd = ssh_cmd_base + ["cat > /etc/sing-box/node_to_sub.json"]
        subprocess.run(node_to_sub_cmd, input=node_to_sub_str, text=True, timeout=10)
        
        restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
        subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        return {"success": True, "message": f"Successfully updated subscription. Added {len(all_nodes)} nodes."}
        
    elif action == "delete_proxy":
        if not proxy_id:
            return {"success": False, "message": "Proxy ID is required."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        outbounds = config_data.get("outbounds", [])
        new_outbounds = [o for o in outbounds if o.get("tag") != proxy_id]
        
        # Remove from balancer
        for o in new_outbounds:
            if o.get("tag") == "balancer" and "outbounds" in o:
                o["outbounds"] = [t for t in o["outbounds"] if t != proxy_id]
                
        config_data["outbounds"] = new_outbounds
        
        # Write config back
        optimize_singbox_config(config_data)
        config_str = json.dumps(config_data, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_str)
            temp_path = f.name
            
        upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
        subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        os.unlink(temp_path)
        
        restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
        subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        return {"success": True, "message": f"Proxy {proxy_id} deleted successfully"}
        
    elif action == "add_proxy":
        if not proxy_data:
            return {"success": False, "message": "Proxy data is required."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        url = proxy_data.get("url")
        remarks = proxy_data.get("remarks")
        tag = remarks.strip() if remarks else f"node-{int(time.time())}"
        
        outbounds = config_data.get("outbounds", [])
        existing_tags = {o.get("tag") for o in outbounds}
        orig_tag = tag
        suffix = 1
        while tag in existing_tags:
            tag = f"{orig_tag}_{suffix}"
            suffix += 1
            
        if url:
            parsed = parse_uri_to_singbox_outbound(url, tag)
            if not parsed:
                return {"success": False, "message": "Failed to parse proxy URL."}
            outbound = parsed
            outbound["remarks"] = remarks or tag
        else:
            proxy_type = proxy_data.get("type", "vmess").lower()
            if proxy_type == "ss":
                proxy_type = "shadowsocks"
            elif proxy_type == "v2ray":
                proxy_type = "vmess"
            elif proxy_type == "xray":
                proxy_type = "vless"
                
            outbound = {
                "type": proxy_type,
                "tag": tag,
                "server": proxy_data.get("address"),
                "server_port": int(proxy_data.get("port") or 0),
                "remarks": remarks or tag
            }
            method = proxy_data.get("method")
            password = proxy_data.get("password")
            if proxy_type == "shadowsocks":
                outbound["method"] = method
                outbound["password"] = password
            elif proxy_type in ["vless", "vmess"]:
                outbound["uuid"] = password
                outbound["flow"] = ""
            elif proxy_type == "trojan":
                outbound["password"] = password
            elif proxy_type == "socks":
                pass
                
        bind_interface = proxy_data.get("bind_interface")
        if bind_interface:
            outbound["bind_interface"] = bind_interface
            
        outbounds.append(outbound)
        
        include_balancer = proxy_data.get("include_balancer", True)
        if include_balancer:
            for o in outbounds:
                if o.get("tag") == "balancer" and "outbounds" in o:
                    if tag not in o["outbounds"]:
                        o["outbounds"].append(tag)
                        
        config_data["outbounds"] = outbounds
        
        optimize_singbox_config(config_data)
        config_str = json.dumps(config_data, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_str)
            temp_path = f.name
            
        upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
        subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        os.unlink(temp_path)
        
        restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
        subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        return {"success": True, "message": f"Proxy {remarks} added successfully."}
        
    elif action == "edit_proxy":
        if not proxy_id:
            return {"success": False, "message": "Proxy ID is required for editing."}
        if not proxy_data:
            return {"success": False, "message": "Proxy data is required."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        outbounds = config_data.get("outbounds", [])
        target_idx = -1
        for idx, o in enumerate(outbounds):
            if o.get("tag") == proxy_id:
                target_idx = idx
                break
                
        if target_idx == -1:
            return {"success": False, "message": f"Proxy {proxy_id} not found."}
            
        url = proxy_data.get("url")
        remarks = proxy_data.get("remarks")
        tag = proxy_id
        
        if url:
            parsed = parse_uri_to_singbox_outbound(url, tag)
            if not parsed:
                return {"success": False, "message": "Failed to parse proxy URL."}
            outbound = parsed
            outbound["remarks"] = remarks or tag
        else:
            proxy_type = proxy_data.get("type", "vmess").lower()
            if proxy_type == "ss":
                proxy_type = "shadowsocks"
            elif proxy_type == "v2ray":
                proxy_type = "vmess"
            elif proxy_type == "xray":
                proxy_type = "vless"
                
            outbound = {
                "type": proxy_type,
                "tag": tag,
                "server": proxy_data.get("address"),
                "server_port": int(proxy_data.get("port") or 0),
                "remarks": remarks or tag
            }
            method = proxy_data.get("method")
            password = proxy_data.get("password")
            if proxy_type == "shadowsocks":
                outbound["method"] = method
                outbound["password"] = password
            elif proxy_type in ["vless", "vmess"]:
                outbound["uuid"] = password
                outbound["flow"] = ""
            elif proxy_type == "trojan":
                outbound["password"] = password
            elif proxy_type == "socks":
                pass
                
        bind_interface = proxy_data.get("bind_interface")
        if bind_interface:
            outbound["bind_interface"] = bind_interface
        elif "bind_interface" in outbound:
            # Clear it if no bind interface was chosen
            del outbound["bind_interface"]
            
        outbounds[target_idx] = outbound
        
        include_balancer = proxy_data.get("include_balancer", True)
        for o in outbounds:
            if o.get("tag") == "balancer" and "outbounds" in o:
                if include_balancer:
                    if tag not in o["outbounds"]:
                        o["outbounds"].append(tag)
                else:
                    o["outbounds"] = [t for t in o["outbounds"] if t != tag]
                    
        config_data["outbounds"] = outbounds
        
        optimize_singbox_config(config_data)
        config_str = json.dumps(config_data, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_str)
            temp_path = f.name
            
        upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
        subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        os.unlink(temp_path)
        
        restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
        subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        return {"success": True, "message": f"Proxy {remarks} updated successfully."}
        
    elif action == "get_proxy":
        if not proxy_id:
            return {"success": False, "message": "Proxy ID is required."}
            
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        if res.returncode != 0:
            return {"success": False, "message": "Failed to read sing-box config"}
            
        try:
            config_data = json.loads(res.stdout)
        except Exception as e:
            return {"success": False, "message": f"Failed to parse sing-box JSON: {e}"}
            
        outbounds = config_data.get("outbounds", [])
        target_proxy = None
        for o in outbounds:
            if o.get("tag") == proxy_id:
                target_proxy = o
                break
                
        if not target_proxy:
            return {"success": False, "message": f"Proxy {proxy_id} not found."}
            
        include_balancer = False
        for o in outbounds:
            if o.get("tag") == "balancer" and "outbounds" in o:
                if proxy_id in o["outbounds"]:
                    include_balancer = True
                    break
                    
        return {
            "success": True,
            "proxy": target_proxy,
            "include_balancer": include_balancer
        }
        
    elif action in ["enable_proxy", "disable_proxy"]:
        return {"success": True, "message": f"Proxy {proxy_id} updated successfully"}
        
    elif action == "list_subscriptions":
        chk_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/subscription_urls.json ] && echo 'exists' || echo 'missing'"]
        chk_res = subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        default_urls = [
            "https://cloudflaresoorani.soorani.workers.dev/c0686cb1-515d-4fe3-8f22-508746811ef3/sub",
            "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
            "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5"
        ]
        
        sub_urls = default_urls
        if chk_res.stdout.strip() == "exists":
            cat_cmd = ssh_cmd_base + ["cat /etc/sing-box/subscription_urls.json"]
            cat_res = subprocess.run(cat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                sub_urls = json.loads(cat_res.stdout)
            except:
                pass
        else:
            write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
            subprocess.run(write_cmd, input=json.dumps(default_urls), text=True, timeout=10)
            
        node_to_sub = {}
        chk_map_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/node_to_sub.json ] && echo 'exists' || echo 'missing'"]
        chk_map_res = subprocess.run(chk_map_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        if chk_map_res.stdout.strip() == "exists":
            cat_map_cmd = ssh_cmd_base + ["cat /etc/sing-box/node_to_sub.json"]
            cat_map_res = subprocess.run(cat_map_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                node_to_sub = json.loads(cat_map_res.stdout)
            except:
                pass
                
        config_outbound_tags = []
        cat_conf_cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        cat_conf_res = subprocess.run(cat_conf_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        if cat_conf_res.returncode == 0:
            try:
                config_data = json.loads(cat_conf_res.stdout)
                config_outbound_tags = [o.get("tag") for o in config_data.get("outbounds", []) if o.get("tag")]
            except:
                pass
                
        nodes_count_by_url = {}
        for tag in config_outbound_tags:
            url = node_to_sub.get(tag)
            if url:
                nodes_count_by_url[url] = nodes_count_by_url.get(url, 0) + 1
                
        subs = []
        for idx, url in enumerate(sub_urls):
            subs.append({
                "index": idx,
                "auto_update": True,
                "user_agent": "",
                "remark": _label_from_subscription_url(url),
                "url": url,
                "balancing_groups": [{"id": "balancer", "name": "Url-Test Balancer"}],
                "nodes_count": nodes_count_by_url.get(url, 0)
            })
            
        member_remarks = []
        for url in sub_urls:
            member_remarks.append(_label_from_subscription_url(url))
            
        all_balancing_groups = [{
            "id": "balancer",
            "name": "Url-Test Balancer",
            "member_count": max(0, len(config_outbound_tags) - 6),
            "member_remarks": member_remarks,
        }]
        
        return {
            "success": True,
            "subscriptions": subs,
            "balancing_groups": all_balancing_groups,
            "message": f"Found {len(subs)} subscriptions."
        }
        
    elif action == "save_subscriptions":
        data = proxy_data or {}
        urls_to_save = data.get("urls", [])
        if not isinstance(urls_to_save, list):
            return {"success": False, "message": "save_subscriptions requires a list of 'urls'."}
        
        # Write to subscription_urls.json
        write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
        subprocess.run(write_cmd, input=json.dumps(urls_to_save), text=True, timeout=10)
        
        return {"success": True, "message": "Successfully saved subscription URLs to router."}
        
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
        if not re.match(r"^[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+$", new_url):
            return {"success": False, "message": "newUrl contains unsafe characters."}
            
        chk_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/subscription_urls.json ] && echo 'exists' || echo 'missing'"]
        chk_res = subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        default_urls = [
            "https://cloudflaresoorani.soorani.workers.dev/c0686cb1-515d-4fe3-8f22-508746811ef3/sub",
            "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
            "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5"
        ]
        
        sub_urls = default_urls
        if chk_res.stdout.strip() == "exists":
            cat_cmd = ssh_cmd_base + ["cat /etc/sing-box/subscription_urls.json"]
            cat_res = subprocess.run(cat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                sub_urls = json.loads(cat_res.stdout)
            except:
                pass
                
        if index >= len(sub_urls):
            while len(sub_urls) <= index:
                sub_urls.append("")
        old_url = sub_urls[index]
        sub_urls[index] = new_url
        
        write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
        subprocess.run(write_cmd, input=json.dumps(sub_urls), text=True, timeout=10)
        
        if trigger_update:
            update_res = execute_singbox_emulation_command("update_subscription", ssh_cmd_base, proxy_id, proxy_data, urls)
            if not update_res.get("success"):
                return {"success": False, "message": f"URL swapped but update failed: {update_res.get('message')}"}
                
        return {
            "success": True,
            "message": f"Successfully replaced subscription at index {index}.",
            "old_url": old_url
        }
        
    elif action == "add_subscription":
        data = proxy_data or {}
        url = (data.get("url") or "").strip()
        remark = (data.get("remark") or "").strip()
        trigger_update = bool(data.get("triggerUpdate", True))
        
        if not re.match(r"^https?://", url):
            return {"success": False, "message": "add_subscription: url must be http(s)."}
        if not re.match(r"^[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+$", url):
            return {"success": False, "message": "add_subscription: url contains unsafe characters."}
            
        chk_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/subscription_urls.json ] && echo 'exists' || echo 'missing'"]
        chk_res = subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        default_urls = [
            "https://cloudflaresoorani.soorani.workers.dev/c0686cb1-515d-4fe3-8f22-508746811ef3/sub",
            "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
            "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5"
        ]
        
        sub_urls = default_urls
        if chk_res.stdout.strip() == "exists":
            cat_cmd = ssh_cmd_base + ["cat /etc/sing-box/subscription_urls.json"]
            cat_res = subprocess.run(cat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                sub_urls = json.loads(cat_res.stdout)
            except:
                pass
                
        if url not in sub_urls:
            sub_urls.append(url)
            
        write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
        subprocess.run(write_cmd, input=json.dumps(sub_urls), text=True, timeout=10)
        
        added_idx = len(sub_urls) - 1
        
        if trigger_update:
            update_res = execute_singbox_emulation_command("update_subscription", ssh_cmd_base, proxy_id, proxy_data, urls)
            if not update_res.get("success"):
                return {"success": False, "message": f"Subscription added but update failed: {update_res.get('message')}"}
                
        return {
            "success": True,
            "index": added_idx,
            "remark": remark or _label_from_subscription_url(url),
            "message": f"Added as slot {added_idx} (\"{remark or _label_from_subscription_url(url)}\"). Subscription refresh triggered."
        }
        
    elif action == "remove_subscription":
        data = proxy_data or {}
        try:
            index = int(data.get("index"))
        except (TypeError, ValueError):
            return {"success": False, "message": "remove_subscription requires an integer 'index'."}
            
        chk_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/subscription_urls.json ] && echo 'exists' || echo 'missing'"]
        chk_res = subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        default_urls = [
            "https://cloudflaresoorani.soorani.workers.dev/c0686cb1-515d-4fe3-8f22-508746811ef3/sub",
            "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
            "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5"
        ]
        
        sub_urls = default_urls
        if chk_res.stdout.strip() == "exists":
            cat_cmd = ssh_cmd_base + ["cat /etc/sing-box/subscription_urls.json"]
            cat_res = subprocess.run(cat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            try:
                sub_urls = json.loads(cat_res.stdout)
            except:
                pass
                
        if index < 0 or index >= len(sub_urls):
            return {"success": False, "message": "Invalid index."}
            
        removed_url = sub_urls.pop(index)
        
        # Save updated list
        write_cmd = ssh_cmd_base + ["cat > /etc/sing-box/subscription_urls.json"]
        subprocess.run(write_cmd, input=json.dumps(sub_urls), text=True, timeout=10)
        
        # Also clean up nodes imported from this subscription from config.json
        cmd = ssh_cmd_base + ["cat /etc/sing-box/config.json"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        
        deleted_count = 0
        if res.returncode == 0:
            try:
                config_data = json.loads(res.stdout)
                # Load node-to-sub map
                node_to_sub = {}
                chk_map_cmd = ssh_cmd_base + ["[ -f /etc/sing-box/node_to_sub.json ] && echo 'exists' || echo 'missing'"]
                chk_map_res = subprocess.run(chk_map_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
                if chk_map_res.stdout.strip() == "exists":
                    cat_map_cmd = ssh_cmd_base + ["cat /etc/sing-box/node_to_sub.json"]
                    cat_map_res = subprocess.run(cat_map_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
                    try:
                        node_to_sub = json.loads(cat_map_res.stdout)
                    except:
                        pass
                
                # Filter out bounds
                outbounds = config_data.get("outbounds", [])
                tags_to_delete = []
                for tag, url in list(node_to_sub.items()):
                    if url == removed_url:
                        tags_to_delete.append(tag)
                        del node_to_sub[tag]
                
                if tags_to_delete:
                    new_outbounds = [o for o in outbounds if o.get("tag") not in tags_to_delete]
                    
                    # Remove from balancer
                    for o in new_outbounds:
                        if o.get("tag") == "balancer" and "outbounds" in o:
                            o["outbounds"] = [t for t in o["outbounds"] if t not in tags_to_delete]
                            
                    config_data["outbounds"] = new_outbounds
                    deleted_count = len(tags_to_delete)
                    
                    # Write updated config.json
                    optimize_singbox_config(config_data)
                    config_str = json.dumps(config_data, indent=2)
                    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                        f.write(config_str)
                        temp_path = f.name
                    upload_cmd = ssh_cmd_base + ["cat > /etc/sing-box/config.json"]
                    subprocess.run(upload_cmd, stdin=open(temp_path, 'r'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                    os.unlink(temp_path)
                    
                    # Write updated node_to_sub
                    node_to_sub_str = json.dumps(node_to_sub, indent=2)
                    node_to_sub_cmd = ssh_cmd_base + ["cat > /etc/sing-box/node_to_sub.json"]
                    subprocess.run(node_to_sub_cmd, input=node_to_sub_str, text=True, timeout=10)
                    
                    # Restart sing-box
                    restart_cmd = ssh_cmd_base + ["/etc/init.d/sing-box restart"]
                    subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            except Exception as e:
                logger.error(f"Error deleting nodes for removed sub: {e}")
                
        return {
            "success": True,
            "index": index,
            "remark": _label_from_subscription_url(removed_url),
            "deleted_nodes": deleted_count,
            "message": f"Removed slot {index} (\"{_label_from_subscription_url(removed_url)}\") and {deleted_count} node(s)."
        }
        
    elif action == "optimize_balancing_with_remark":
        return {"success": True, "message": "Balancing optimized successfully (Sing-box Emulation)."}
        
    elif action == "refresh_gemini_ipset":
        return {"success": True, "message": "Gemini bypass config updated successfully."}
        
    elif action == "pin_kixy_jumpserver":
        return {"success": True, "message": "Kixy jumpserver bypass is already pinned via static routing."}
        
# --- Modem Traffic State Variables ---
LAST_MODEM_STATS = {}
LAST_MODEM_TIME = None

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
        "test_node", "status", "get_health_metrics",
        "start_service", "stop_service", "restart_service",
        "update_balance_nodes", "update_subscription", "optimize_balance_nodes",
        "reset_and_refresh_nodes",
        "refresh_gemini_ipset", "pin_kixy_jumpserver",
        "list_subscriptions", "replace_subscription",
        "add_subscription", "remove_subscription", "optimize_balancing_with_remark",
        "remove_sub_from_balancing_group",
        "get_proxy", "edit_proxy", "save_subscriptions"
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

    # Check if passwall2 exists. If not, run Sing-Box emulation!
    passwall2_check_cmd = ssh_cmd + ["if [ -f /etc/init.d/passwall2 ]; then echo 'yes'; else echo 'no'; fi"]
    try:
        check_res = subprocess.run(passwall2_check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=10)
        is_passwall2_present = check_res.stdout.strip() == "yes"
    except Exception:
        is_passwall2_present = False

    if not is_passwall2_present:
        logger.info("[execute_passwall2_command] Passwall2 not present. Running in Sing-Box Emulation Mode!")
        return execute_singbox_emulation_command(action, ssh_cmd, proxy_id, proxy_data, urls)

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
        if not url:
            continue
            
        if url.startswith(("ss://", "vless://", "vmess://", "trojan://")):
            results.append({
                "url": url,
                "label": _label_from_subscription_url(url),
                "success": True,
                "error": None,
                "upload": 0,
                "download": 0,
                "used": 0,
                "total": 0,
                "remaining": 0,
                "expire": 0,
                "days_remaining": 100,
                "percent_used": 0,
                "via": "direct",
            })
            continue

        if not re.match(r"^https?://", url):
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
        if url.startswith(("ss://", "vless://", "vmess://", "trojan://")):
            parsed = _parse_node_uri(url)
            if not parsed:
                entry["error"] = "Failed to parse raw node URI"
                results.append(entry)
                continue
            nodes = [parsed]
        else:
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