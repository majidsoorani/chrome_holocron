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
# This configures a rotating log file to prevent it from growing indefinitely.
log_dir = Path(__file__).resolve().parent.parent / "log"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "holocron_native_host.log"

# Create a rotating file handler: 1MB max size, 3 backup files.
handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=1_048_576, backupCount=3
)
# Add function name to the log format for better debugging context.
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

logging.info("--- Native host script started ---")

# --- Paths & Constants ---
SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_SCRIPT_PATH = SCRIPT_DIR.parent / "sh" / "work_connect.sh"
V2RAY_CONFIG_PATH = Path("/tmp/holocron_v2ray_config.json")
V2RAY_LOCK_FILE = Path.home() / ".holocron_v2ray.lock"
SHADOWSOCKS_CONFIG_PATH = Path("/tmp/holocron_shadowsocks_config.json")
SHADOWSOCKS_LOCK_FILE = Path.home() / ".holocron_shadowsocks.lock"


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
    """
    Performs a TCP 'ping' by attempting a socket connection.
    If a socks_port is provided, the connection is routed through the SOCKS5 proxy.

    Returns:
        tuple[int, str|None]: A tuple of (latency_ms, error_name).
    """
    sock = None  # Initialize to ensure it's defined for the finally block
    try:
        if socks_port:
            # Use a proxied socket for an accurate tunnel latency check
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, "127.0.0.1", socks_port)
        else:
            # Fallback to a direct socket if no proxy is available
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        sock.settimeout(timeout)
        # Note: gethostbyname resolves DNS locally. For a simple latency check, this is
        # acceptable. The more critical web_check uses 'socks5h' for proxied DNS.
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
    """
    Performs an HTTP HEAD request, optionally through a SOCKS5 proxy, and measures latency.

    Returns:
        tuple[int, str, str|None]: A tuple of (latency_ms, status_string, error_name).
    """
    if not url or not url.startswith(('http://', 'https://')):
        return -1, "Invalid URL", "ConfigurationError"

    proxies = None
    if socks_port:
        proxies = {
            'http': f'socks5h://127.0.0.1:{socks_port}',
            'https': f'socks5h://127.0.0.1:{socks_port}'
        }
    headers = {'User-Agent': 'HolocronStatusCheck/1.0'}

    try:
        start_time = time.perf_counter()
        response = requests.head(url, proxies=proxies, timeout=timeout, headers=headers)
        end_time = time.perf_counter()
        latency_ms = int((end_time - start_time) * 1000)

        if 200 <= response.status_code < 400:
            logging.debug(f"Web check for {url} successful with status {response.status_code}. Latency: {latency_ms}ms.")
            return latency_ms, "OK", None
        else:
            logging.warning(f"Web check for {url} failed with status {response.status_code}. Latency: {latency_ms}ms.")
            return latency_ms, f"Failed (Status {response.status_code})", None
    except requests.exceptions.RequestException as e:
        error_name = e.__class__.__name__
        logging.error(f"Web check for {url} failed with exception: {error_name}")
        if "SOCKSHTTPSConnectionPool" in str(e):
            return -1, "Failed (Proxy Error)", "ProxyError"
        return -1, "Failed (Connection Error)", "ConnectionError"

def get_v2ray_status():
    """Checks for the V2Ray process."""
    logging.debug("Checking for V2Ray process.")
    if not V2RAY_LOCK_FILE.exists():
        return {"connected": False, "socks_port": None}

    try:
        pid = int(V2RAY_LOCK_FILE.read_text())
        proc = psutil.Process(pid)
        # Check if the process name or command line indicates it's our V2Ray instance
        if 'v2ray' in proc.name() and f'--config={V2RAY_CONFIG_PATH}' in " ".join(proc.cmdline()):
             # To get the SOCKS port, we need to read the config file
            if V2RAY_CONFIG_PATH.exists():
                config_data = json.loads(V2RAY_CONFIG_PATH.read_text())
                socks_port = config_data.get("inbounds", [{}])[0].get("port")
                logging.info(f"Found V2Ray process with PID: {pid}. SOCKS port: {socks_port}")
                return {"connected": True, "socks_port": socks_port}
    except (psutil.NoSuchProcess, ValueError, FileNotFoundError, IndexError, KeyError):
        # PID is invalid, lock file is stale, or config is malformed. Clean up.
        V2RAY_LOCK_FILE.unlink(missing_ok=True)

    return {"connected": False, "socks_port": None}


def get_ssh_tunnel_status(ssh_command_identifier):
    """Checks for the SSH process and extracts the SOCKS port."""
    logging.debug(f"Checking for SSH process with identifier: '{ssh_command_identifier}'")
    if not ssh_command_identifier:
        logging.warning("No SSH command identifier provided.")
        return {"connected": False, "socks_port": None}

    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'username']):
        try:
            if proc.info['name'] == 'ssh' and proc.info['cmdline'] and proc.info['username'] == getpass.getuser():
                cmd_str = " ".join(proc.info['cmdline'])
                if f"ControlPath=/tmp/holocron.ssh.socket.{ssh_command_identifier}" in cmd_str:
                    logging.info(f"Found matching SSH process with PID: {proc.pid}")
                    match = re.search(r'-D\s*(\d+)', cmd_str)
                    socks_port = int(match.group(1)) if match else None
                    if socks_port:
                        logging.info(f"Extracted SOCKS port {socks_port} from command line.")
                    return {"connected": True, "socks_port": socks_port}
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return {"connected": False, "socks_port": None}

def execute_tunnel_command(command, config=None):
    """Executes the work_connect.sh script with 'start' or 'stop'."""
    if command not in ["start", "stop"]:
        return {"success": False, "message": f"Invalid command: {command}"}

    if not SHELL_SCRIPT_PATH.is_file():
        error_msg = f"Shell script not found at {SHELL_SCRIPT_PATH}"
        logging.error(error_msg)
        return {"success": False, "message": error_msg}

    try:
        cmd_list = [str(SHELL_SCRIPT_PATH), command]

        if command == "start" and config:
            # Note: The keys used here (e.g., "ssh_user") MUST match the keys sent from the JavaScript side.
            if config.get("ssh_user"):
                cmd_list.extend(["--user", config.get("ssh_user")])
            if config.get("ssh_host"):
                cmd_list.extend(["--host", config.get("ssh_host")])
            if config.get("ssh_command_id"):
                cmd_list.extend(["--identifier", config.get("ssh_command_id")])

            for ssid in config.get("wifi_ssids", []):
                if ssid:  # Ensure not empty
                    cmd_list.extend(["--ssid", ssid])

            for rule in config.get("port_forwards", []):
                if rule.get("type") == "D" and rule.get("localPort"):
                    cmd_list.extend(["-D", str(rule.get("localPort"))])
                elif rule.get("type") == "L" and all(k in rule for k in ["localPort", "remoteHost", "remotePort"]):
                    forward_str = f"{rule['localPort']}:{rule['remoteHost']}:{rule['remotePort']}"
                    cmd_list.extend(["-L", forward_str])

        logging.info(f"Executing command: {' '.join(cmd_list)}")

        # Use a longer timeout for 'start' as it may need to establish a connection and prompt for a password.
        timeout = 45 if command == "start" else 10
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False # We check the returncode manually to provide better error messages
        )
        logging.info(f"Script stdout: {result.stdout.strip()}")
        # Handle special exit code 3: Already running (this is a success case)
        if result.returncode == 3:
            message = result.stdout.strip() or "Tunnel is already running."
            logging.info(f"Script exited with code 3 (already running): {message}")
            return {"success": True, "already_running": True, "message": message}

        if result.returncode != 0:
            # Handle special exit code 2: Condition not met (e.g., not on work Wi-Fi)
            if result.returncode == 2:
                message = result.stdout.strip() or result.stderr.strip()
                logging.info(f"Script exited with code 2 (condition not met): {message}")
                # Report as a failure so the UI shows the message, but the message itself is informational.
                return {"success": False, "message": message}

            error_output = result.stderr.strip() or result.stdout.strip()
            logging.error(f"Script execution failed for command '{command}'. Exit code: {result.returncode}. Output: {error_output}")

            # Check for common sudo password errors and provide a user-friendly message.
            if "a terminal is required to read the password" in error_output or "sudo: a password is required" in error_output:
                # Provide platform-specific advice for passwordless sudo
                if platform.system() == "Darwin":
                    current_user = getpass.getuser()
                    user_friendly_error = (
                        "Sudo password required for Wi-Fi check. To enable passwordless operation, "
                        "run 'sudo visudo' and add this line at the end of the file "
                        f"(replace '{current_user}' with your actual username if needed):\n\n{current_user} ALL=(ALL) NOPASSWD: /usr/bin/wdutil"
                    )
                else:
                    # Generic message for other OSes (e.g., Linux)
                    user_friendly_error = (
                        "Sudo password required to run the connection script. "
                        "Please configure passwordless sudo for the script at: "
                        f"{SHELL_SCRIPT_PATH}"
                    )
                return {"success": False, "message": user_friendly_error}

            return {"success": False, "message": f"Failed to {command} tunnel: {error_output}"}
        return {"success": True, "message": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        logging.error(f"Script execution timed out for command '{command}'.")
        return {"success": False, "message": f"Timeout: The command '{command}' took too long to execute."}
    except Exception as e:
        logging.error(f"An unexpected error occurred during script execution: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred: {e}"}

def generate_v2ray_config(config):
    """Generates a V2Ray JSON configuration from the provided settings."""
    protocol = config.get("protocol", "vmess") # Default to vmess

    outbound_settings = {
        "vnext": [
            {
                "address": config.get("server"),
                "port": int(config.get("port")),
                "users": [
                    {
                        "id": config.get("uuid"),
                        "security": config.get("security", "auto")
                    }
                ]
            }
        ]
    }
    # VLESS has a different user structure
    if protocol == 'vless':
        outbound_settings["vnext"][0]["users"][0]["flow"] = "xtls-rprx-direct"
    else: # vmess
        outbound_settings["vnext"][0]["users"][0]["alterId"] = int(config.get("alterId", 0))

    return {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "port": int(config.get("socksPort", 1080)),
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": { "auth": "noauth", "udp": True }
            }
        ],
        "outbounds": [
            {
                "protocol": protocol,
                "settings": outbound_settings,
                "streamSettings": { "network": config.get("network", "tcp") }
            }
        ]
    }

def execute_v2ray_command(command, config=None):
    """Handles starting and stopping the V2Ray process."""
    if command == "start":
        v2ray_json = generate_v2ray_config(config)
        V2RAY_CONFIG_PATH.write_text(json.dumps(v2ray_json, indent=2))

        # Start V2Ray process
        proc = subprocess.Popen(['v2ray', '--config', str(V2RAY_CONFIG_PATH)])
        V2RAY_LOCK_FILE.write_text(str(proc.pid))
        return {"success": True, "message": f"V2Ray process started with PID {proc.pid}"}

    elif command == "stop":
        if not V2RAY_LOCK_FILE.exists():
            return {"success": True, "message": "V2Ray appears to be stopped already."}
        try:
            pid = int(V2RAY_LOCK_FILE.read_text())
            proc = psutil.Process(pid)
            proc.terminate() # or proc.kill()
            V2RAY_LOCK_FILE.unlink()
            return {"success": True, "message": f"V2Ray process {pid} stopped."}
        except (psutil.NoSuchProcess, ValueError):
            V2RAY_LOCK_FILE.unlink(missing_ok=True)
            return {"success": True, "message": "V2Ray process not found, cleaned up stale lock file."}
    return {"success": False, "message": "Invalid V2Ray command."}


def get_shadowsocks_status():
    """Checks for the Shadowsocks process and its SOCKS port from the lock file."""
    logging.debug("Checking for Shadowsocks process.")
    if not SHADOWSOCKS_LOCK_FILE.exists():
        return {"connected": False, "socks_port": None}
    try:
        pid_str, socks_port_str = SHADOWSOCKS_LOCK_FILE.read_text().strip().split(':')
        pid = int(pid_str)
        socks_port = int(socks_port_str)
        proc = psutil.Process(pid)
        if 'ss-local' in proc.name().lower():
            logging.info(f"Found Shadowsocks process with PID: {pid}. SOCKS port: {socks_port}")
            return {"connected": True, "socks_port": socks_port}
    except (psutil.NoSuchProcess, ValueError, KeyError, FileNotFoundError):
        SHADOWSOCKS_LOCK_FILE.unlink(missing_ok=True)
    return {"connected": False, "socks_port": None}


def execute_shadowsocks_command(command, config=None):
    """Handles starting and stopping the Shadowsocks ss-local process."""
    if command == "start":
        ss_config = {
            "server": config.get("server"),
            "server_port": config.get("port"),
            "password": config.get("password"),
            "method": config.get("method"),
            "local_address": "127.0.0.1",
            "local_port": config.get("socksPort", 1080)
        }
        SHADOWSOCKS_CONFIG_PATH.write_text(json.dumps(ss_config, indent=2))

        cmd = ['ss-local', '-c', str(SHADOWSOCKS_CONFIG_PATH)]
        proc = subprocess.Popen(cmd)
        SHADOWSOCKS_LOCK_FILE.write_text(f"{proc.pid}:{ss_config['local_port']}")
        return {"success": True, "message": f"Shadowsocks process started with PID {proc.pid}"}

    elif command == "stop":
        if not SHADOWSOCKS_LOCK_FILE.exists():
            return {"success": True, "message": "Shadowsocks appears to be stopped already."}
        try:
            pid = int(SHADOWSOCKS_LOCK_FILE.read_text().strip().split(':')[0])
            proc = psutil.Process(pid)
            proc.terminate()
            SHADOWSOCKS_LOCK_FILE.unlink()
            return {"success": True, "message": f"Shadowsocks process {pid} stopped."}
        except (psutil.NoSuchProcess, ValueError):
            SHADOWSOCKS_LOCK_FILE.unlink(missing_ok=True)
            return {"success": True, "message": "Cleaned up stale Shadowsocks lock file."}
    return {"success": False, "message": "Invalid Shadowsocks command."}


def main():
    """Main loop to read commands and send status."""
    while True:
        try:
            message = read_message()
            logging.debug(f"Received message: {message}")
            command = message.get("command")

            # The 'type' of the active proxy config determines the mode.
            # For start/stop, the full config is sent.
            # For getStatus, only the active config's type and relevant identifiers are sent.
            proxy_config = message.get("config", {})
            mode = proxy_config.get("type") if proxy_config else message.get("mode")


            if command == "getStatus":
                status = {}
                if mode == "ssh":
                    status = get_ssh_tunnel_status(message.get("sshCommandIdentifier"))
                elif mode == "v2ray":
                    status = get_v2ray_status()
                elif mode == "ss":
                    status = get_shadowsocks_status()

                response = { "connected": status.get("connected", False), "socks_port": status.get("socks_port") }

                if status.get("connected") and status.get("socks_port"):
                    socks_port = status["socks_port"]
                    web_latency, web_status, web_error = perform_web_check(url=message.get("webCheckUrl"), socks_port=socks_port)
                    response.update({"web_check_latency_ms": web_latency, "web_check_status": web_status, "web_check_error": web_error})
                    tcp_latency, tcp_ping_error = perform_tcp_ping(host=message.get("pingHost"), socks_port=socks_port)
                    response.update({"tcp_ping_ms": tcp_latency, "tcp_ping_error": tcp_ping_error})
                else:
                    tcp_latency, tcp_ping_error = perform_tcp_ping(host=message.get("pingHost"), socks_port=None)
                    response.update({"tcp_ping_ms": tcp_latency, "tcp_ping_error": tcp_ping_error})
                    response.update({"web_check_latency_ms": -1, "web_check_status": "N/A (Tunnel Down)", "web_check_error": None})

                send_message(response)

            elif command in ["startTunnel", "stopTunnel"]:
                action = "start" if command == "startTunnel" else "stop"
                response = {}
                if mode == "ssh":
                    response = execute_tunnel_command(action, proxy_config)
                elif mode == "v2ray":
                    response = execute_v2ray_command(action, proxy_config)
                elif mode == "ss":
                    response = execute_shadowsocks_command(action, proxy_config)
                send_message(response)

            else:
                logging.warning(f"Unknown command received: {command}")

        except Exception as e:
            logging.error(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            continue

if __name__ == '__main__':
    main()