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
CONN_LOG_DIR = log_dir / "connections"
CONN_LOG_DIR.mkdir(exist_ok=True)



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

def perform_tcp_ping(host, port=443, timeout=2, socks_port=None):
    """Performs a TCP 'ping' by attempting a socket connection."""
    sock = None
    try:
        sock = socks.socksocket() if socks_port else socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if socks_port:
            sock.set_proxy(socks.SOCKS5, "127.0.0.1", socks_port)
        sock.settimeout(timeout)
        addr = socket.gethostbyname(host)
        start_time = time.perf_counter()
        sock.connect((addr, port))
        end_time = time.perf_counter()
        latency_ms = int((end_time - start_time) * 1000)
        proxy_msg = f" via SOCKS port {socks_port}" if socks_port else " (direct)"
        logging.debug(f"TCP ping to {host}:{port}{proxy_msg} successful. Latency: {latency_ms}ms.")
        return latency_ms, None
    except (socks.ProxyError, socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
        error_name = e.__class__.__name__
        proxy_msg = f" via SOCKS port {socks_port}" if socks_port else " (direct)"
        logging.warning(f"TCP ping to {host}:{port}{proxy_msg} failed: {error_name}")
        return -1, error_name
    finally:
        if sock:
            sock.close()

def perform_web_check(url, socks_port, timeout=10):
    """Performs an HTTP HEAD request, optionally through a SOCKS5 proxy."""
    if not url or not url.startswith(('http://', 'https://')):
        return -1, "Invalid URL", "ConfigurationError"
    proxies = {'http': f'socks5h://127.0.0.1:{socks_port}', 'https': f'socks5h://127.0.0.1:{socks_port}'} if socks_port else None
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
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'username']):
            try:
                if proc.info['name'] == 'ssh' and proc.info['cmdline'] and proc.info['username'] == getpass.getuser():
                    cmd_str = " ".join(proc.info['cmdline'])
                    if f"ControlPath=/tmp/holocron.ssh.socket.{identifier}" in cmd_str:
                        logging.debug(f"Found matching SSH process with PID: {proc.pid}")
                        match = re.search(r'-D\s*(\d+)', cmd_str)
                        socks_port = int(match.group(1)) if match else None
                        return {"connected": True, "socks_port": socks_port}
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
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
        lock_file = Path(f"/tmp/holocron_v2ray_{identifier}.lock")
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
            if ovpn_user is not None and ovpn_pass is not None:
                try:
                    # Write credentials to a temporary file
                    auth_file.write_text(f"{ovpn_user}\n{ovpn_pass}")
                    # Set secure permissions (read/write for owner only)
                    os.chmod(auth_file, 0o600)
                except Exception as e:
                    logging.error(f"Failed to write credentials to auth file: {e}", exc_info=True)
                    return {"success": False, "message": f"Failed to write credentials to auth file: {e}"}
                cmd_list.extend(["--auth-user-pass", str(auth_file)])

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

            return {"success": True, "message": result.stdout.strip() or "V2Ray tunnel command executed successfully."}
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout: The command '{command}' for V2Ray tunnel '{identifier}' took too long.")
            return {"success": False, "message": f"Timeout: The command '{command}' for V2Ray took too long."}
        except Exception as e:
            logging.error(f"An unexpected error occurred during V2Ray script execution for '{identifier}': {e}", exc_info=True)
            return {"success": False, "message": f"An unexpected error occurred with V2Ray: {e}"}
    else:
        return {"success": False, "message": f"Unknown connection type: {conn_type}"}

def get_log_path_for_config(identifier, conn_type):
    """Determines the log file path for a given configuration."""
    if not identifier or not conn_type:
        return log_file # Default to the main native host log

    # This assumes work_connect.sh will log to a file with this naming convention.
    if conn_type == "ssh":
        return Path(f"/tmp/holocron_ssh_{identifier}.log") # SSH script still uses /tmp
    elif conn_type == "openvpn":
        return get_ovpn_temp_paths(identifier)["log"]
    elif conn_type == "v2ray":
        return Path(f"/tmp/holocron_v2ray_{identifier}.log")
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

    if not config:
        return {"success": False, "message": "No configuration provided to test."}
    if not ping_host or not web_check_url:
        return {"success": False, "message": "Ping Host and Web Check URL must be provided for testing."}

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
    web_latency, web_status, web_error = perform_web_check(url=web_check_url, socks_port=socks_port)
    tcp_latency, tcp_error = perform_tcp_ping(host=ping_host, socks_port=socks_port)
    
    # 4. Stop the tunnel if we started it for the test.
    if not tunnel_was_running:
        logging.info(f"Test Connection: Test complete. Stopping temporary tunnel for '{config.get('name')}'.")
        execute_tunnel_command("stop", config)

    # 5. Format and send the response.
    is_overall_success = web_latency > -1 and tcp_latency > -1 and web_status == "OK"
    final_message = f"Test completed. Web: {web_latency}ms ({web_status or web_error}), TCP: {tcp_latency}ms." if is_overall_success else "Test failed. See details."
    if tunnel_was_running:
        final_message = f"(Tunnel was already running) {final_message}"

    return {"success": is_overall_success, "connected": True, "web_check_latency_ms": web_latency, "web_check_status": web_status or web_error, "tcp_ping_ms": tcp_latency, "tcp_ping_error": tcp_error, "message": final_message}

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
                if status["connected"] and status.get("socks_port"):
                    web_latency, web_status, _ = perform_web_check(url=message.get("webCheckUrl"), socks_port=status["socks_port"])
                    tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost", "youtube.com"), socks_port=status["socks_port"])
                    response.update({"web_check_latency_ms": web_latency, "web_check_status": web_status, "tcp_ping_ms": tcp_latency})
                else:
                    tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost", "youtube.com"), socks_port=None)
                    response.update({"web_check_latency_ms": -1, "web_check_status": "N/A (Tunnel Down)", "tcp_ping_ms": tcp_latency})
            elif command == "testConnection":
                response = handle_test_connection(message)
            elif command == "getLogs":
                identifier = message.get("identifier")
                conn_type = message.get("conn_type")
                response = get_logs(identifier=identifier, conn_type=conn_type)
            elif command == "clearLogs":
                response = clear_logs()
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