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
from pathlib import Path

# --- Setup Logging ---
# This will create a log file in your home directory to help with debugging.
# The log file will be located at: backends/log/holocron_native_host.log
log_dir = Path(__file__).resolve().parent.parent / "log"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "holocron_native_host.log"
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("--- Native host script started ---")

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

def get_tunnel_status(ssh_command_identifier):
    """
    Checks for the SSH process and extracts the SOCKS port.

    Returns:
        dict: {'connected': bool, 'socks_port': int|None}
    """
    logging.debug(f"Checking for SSH process with identifier: '{ssh_command_identifier}'")
    if not ssh_command_identifier:
        logging.warning("No SSH command identifier provided to get_tunnel_status.")
        return {"connected": False, "socks_port": None}

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'ssh' and proc.info['cmdline'] and any(ssh_command_identifier in s for s in proc.info['cmdline']):
                logging.info(f"Found matching SSH process with PID: {proc.pid}")
                
                # Find the SOCKS port (-D flag)
                cmd_str = " ".join(proc.info['cmdline'])
                match = re.search(r'-D\s*(\d+)', cmd_str)
                socks_port = int(match.group(1)) if match else None
                if socks_port:
                    logging.info(f"Extracted SOCKS port {socks_port} from command line.")
                else:
                    logging.warning("Found SSH process but could not extract SOCKS port from command.")

                return {"connected": True, "socks_port": socks_port}
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return {"connected": False, "socks_port": None}

def main():
    """Main loop to read commands and send status."""
    while True:
        try:
            message = read_message()
            logging.debug(f"Received message: {message}")
            if message.get("command") != "getStatus":
                continue

            ssh_command_id = message.get("sshCommand")
            status = get_tunnel_status(ssh_command_id)
            response = {
                "connected": status["connected"],
                "socks_port": status.get("socks_port") # Ensure port is always included
            }

            # If the tunnel is connected and we have a SOCKS port, perform all proxied checks.
            if status["connected"] and status.get("socks_port"):
                socks_port = status["socks_port"]

                # 1. Perform a full web check through the proxy for application-level latency.
                web_latency, web_status, web_error = perform_web_check(
                    url=message.get("webCheckUrl"),
                    socks_port=socks_port
                )
                response["web_check_latency_ms"] = web_latency
                response["web_check_status"] = web_status
                response["web_check_error"] = web_error

                # 2. Also perform a TCP ping through the proxy for network-level latency.
                tcp_latency, tcp_ping_error = perform_tcp_ping(
                    host=message.get("pingHost", "youtube.com"),
                    socks_port=socks_port
                )
                response["tcp_ping_ms"] = tcp_latency
                response["tcp_ping_error"] = tcp_ping_error
            else:
                # Tunnel is down. Perform a direct TCP ping for basic connectivity diagnostics.
                logging.info("SSH tunnel not found. Performing direct TCP ping for diagnostics.")
                
                tcp_latency, tcp_ping_error = perform_tcp_ping(
                    host=message.get("pingHost", "youtube.com"),
                    socks_port=None  # Explicitly None for a direct check
                )
                response["tcp_ping_ms"] = tcp_latency
                response["tcp_ping_error"] = tcp_ping_error

                # Set web check fields to default values for consistency in the UI
                response["web_check_latency_ms"] = -1
                response["web_check_status"] = "N/A (Tunnel Down)"
                response["web_check_error"] = None
            
            logging.debug(f"Sending response: {response}")
            send_message(response)

        except Exception as e:
            logging.error(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            sys.exit(1) # Exit with a non-zero code to indicate an error

if __name__ == '__main__':
    main()