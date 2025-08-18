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
import logging.handlers
import getpass
import platform
from pathlib import Path

# --- Setup Logging ---
log_dir = Path(__file__).resolve().parent.parent / "log"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "holocron_native_host.log"
handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
logging.info("--- Native host script started ---")

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "work_connect.sh"
OPENVPN_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "openvpn_connect.sh"

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

def get_ovpn_socks_port(ovpn_content):
    """Parses .ovpn file content to find the SOCKS proxy port."""
    if not ovpn_content:
        return None
    match = re.search(r'^\s*socks-proxy\s+127\.0\.0\.1\s+(\d+)', ovpn_content, re.MULTILINE)
    if match:
        port = int(match.group(1))
        logging.info(f"Found SOCKS proxy port {port} in OVPN config.")
        return port
    logging.info("No SOCKS proxy port found in OVPN config.")
    return None

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
                        logging.info(f"Found matching SSH process with PID: {proc.pid}")
                        match = re.search(r'-D\s*(\d+)', cmd_str)
                        socks_port = int(match.group(1)) if match else None
                        return {"connected": True, "socks_port": socks_port}
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    elif conn_type == "openvpn":
        lock_file = Path(f"/tmp/holocron_openvpn_{identifier}.lock")
        if lock_file.is_file():
            try:
                pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(pid) and 'openvpn' in psutil.Process(pid).name():
                    logging.info(f"Found matching OpenVPN process with PID: {pid}")
                    socks_port = get_ovpn_socks_port(config.get('ovpnFileContent'))
                    return {"connected": True, "socks_port": socks_port}
            except (ValueError, psutil.NoSuchProcess):
                logging.warning(f"Stale lock file found for OpenVPN identifier '{identifier}'.")
    return {"connected": False, "socks_port": None}

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
            if config.get("sshUser"): cmd_list.extend(["--user", config.get("sshUser")])
            if config.get("sshHost"): cmd_list.extend(["--host", config.get("sshHost")])
            for ssid in config.get("wifiSsidList", []):
                if ssid: cmd_list.extend(["--ssid", ssid])
            for rule in config.get("portForwards", []):
                if rule.get("type") == "D" and rule.get("localPort"):
                    cmd_list.extend(["-D", str(rule.get("localPort"))])
                elif rule.get("type") == "L" and all(k in rule for k in ["localPort", "remoteHost", "remotePort"]):
                    cmd_list.extend(["-L", f"{rule['localPort']}:{rule['remoteHost']}:{rule['remotePort']}"])
                elif rule.get("type") == "R" and all(k in rule for k in ["localPort", "remoteHost", "remotePort"]):
                    cmd_list.extend(["-R", f"{rule['localPort']}:{rule['remoteHost']}:{rule['remotePort']}"])
    elif conn_type == "openvpn":
        script_path = OPENVPN_SCRIPT_PATH
        cmd_list = [str(script_path), command, "--identifier", identifier]
        if command == "start":
            ovpn_content = config.get("ovpnFileContent")
            if not ovpn_content:
                return {"success": False, "message": "OpenVPN content is missing."}
            cmd_list.extend(["--ovpn-content", ovpn_content])
    else:
        return {"success": False, "message": f"Unknown connection type: {conn_type}"}

    if not script_path.is_file() or not os.access(script_path, os.X_OK):
        error_msg = f"Shell script not found or not executable at {script_path}"
        logging.error(error_msg)
        return {"success": False, "message": error_msg}

    try:
        logging.info(f"Executing command: {' '.join(cmd_list)}")
        timeout = 45 if command == "start" else 10
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout, check=False)
        logging.info(f"Script stdout: {result.stdout.strip()}")
        if result.returncode == 3:
            return {"success": True, "already_running": True, "message": result.stdout.strip() or "Tunnel is already running."}
        if result.returncode != 0:
            if result.returncode == 2:
                return {"success": False, "message": result.stdout.strip() or result.stderr.strip()}
            error_output = result.stderr.strip() or result.stdout.strip()
            logging.error(f"Script execution failed. Exit code: {result.returncode}. Output: {error_output}")
            return {"success": False, "message": f"Failed to {command} tunnel: {error_output}"}
        return {"success": True, "message": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"Timeout: The command '{command}' took too long."}
    except Exception as e:
        logging.error(f"An unexpected error occurred during script execution: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred: {e}"}

def get_logs():
    """Reads the last part of the log file and returns it."""
    try:
        if not log_file.is_file():
            return {"success": True, "log_content": "Log file does not exist yet."}
        file_size = log_file.stat().st_size
        read_size = min(file_size, 20 * 1024)
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()
            content = f.read()
        return {"success": True, "log_content": content}
    except Exception as e:
        logging.error(f"Error reading log file: {e}", exc_info=True)
        return {"success": False, "message": f"Error reading log file: {e}"}

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

def main():
    """Main loop to read commands and send status."""
    import os
    while True:
        try:
            message = read_message()
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
                # This needs to be updated to better support OpenVPN testing
                config = message.get("config")
                status = get_tunnel_status(config)
                response = {"success": True, "connected": status["connected"], "socks_port": status.get("socks_port")}
                if status["connected"] and status.get("socks_port"):
                    web_latency, web_status, _ = perform_web_check(url=message.get("webCheckUrl"), socks_port=status["socks_port"])
                    tcp_latency, _ = perform_tcp_ping(host=message.get("pingHost"), socks_port=status["socks_port"])
                    response.update({"web_check_latency_ms": web_latency, "web_check_status": web_status, "tcp_ping_ms": tcp_latency})
                elif config.get("type") == "ssh":
                    ssh_host = config.get("sshHost")
                    ssh_ping_latency, ssh_ping_error = perform_tcp_ping(host=ssh_host, port=22, timeout=5)
                    response.update({"ssh_host_name": ssh_host, "ssh_host_ping_ms": ssh_ping_latency, "ssh_host_ping_error": ssh_ping_error})
            elif command == "getLogs":
                response = get_logs()
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
    # Add os import here to avoid it at the top level for non-main execution
    import os
    main()