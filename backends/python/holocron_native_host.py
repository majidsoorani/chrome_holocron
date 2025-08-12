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

def perform_web_check(url, socks_port, timeout=5):
    """
    Performs an HTTP HEAD request through a SOCKS5 proxy.

    Returns:
        str: A status string, e.g., "OK", "Failed (403 Forbidden)".
    """
    if not url or not url.startswith(('http://', 'https://')):
        return None

    proxies = {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }
    headers = {'User-Agent': 'HolocronStatusCheck/1.0'}

    try:
        response = requests.head(url, proxies=proxies, timeout=timeout, headers=headers)
        if 200 <= response.status_code < 400:
            logging.debug(f"Web check for {url} successful with status {response.status_code}.")
            return "OK"
        else:
            logging.warning(f"Web check for {url} failed with status {response.status_code}.")
            return f"Failed (Status {response.status_code})"
    except requests.exceptions.RequestException as e:
        logging.error(f"Web check for {url} failed with exception: {e}")
        if "SOCKSHTTPSConnectionPool" in str(e):
            return "Failed (Proxy Error)"
        return "Failed (Connection Error)"

def _get_ip_details(proxies=None, timeout=5):
    """
    Fetches public IP details, optionally through a proxy, with fallbacks.

    Args:
        proxies (dict, optional): Dictionary of proxies for requests. Defaults to None.
        timeout (int): Request timeout in seconds.

    Returns:
        tuple[str, str]: A tuple of (ip_address, country). Defaults to ("N/A", "N/A") on failure.
    """
    api_endpoints = [
        ("https://ip-api.com/json", "query", "country"),
        ("https://ipinfo.io/json", "ip", "country"),
        ("https://ifconfig.me/json", "ip_addr", "country")
    ]

    for url, ip_key, country_key in api_endpoints:
        try:
            logging.debug(f"Attempting to fetch IP details from {url}" + (" with proxy" if proxies else " (direct)"))
            response = requests.get(url, proxies=proxies, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            ip, country = data.get(ip_key, "N/A"), data.get(country_key, "N/A")
            logging.info(f"Successfully fetched IP details from {url}: {ip} ({country})")
            return ip, country
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logging.warning(f"Failed to fetch IP info from {url}: {e}")
            continue  # Try the next endpoint

    logging.error("All IP lookup services failed.")
    return "N/A", "N/A"

def get_proxied_ip_details(socks_port, timeout=5):
    """
    Fetches public IP details through the specified SOCKS proxy, with fallbacks.
    This ensures that the IP address reported is that of the tunnel's exit node.

    Args:
        socks_port (int): The local SOCKS5 proxy port.
        timeout (int): Request timeout in seconds.

    Returns:
        tuple[str, str]: A tuple of (ip_address, country). Defaults to ("N/A", "N/A") on failure.
    """
    if not socks_port:
        logging.warning("Cannot get proxied IP details without a SOCKS port.")
        return "N/A", "N/A"

    proxies = {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }
    return _get_ip_details(proxies=proxies, timeout=timeout)

def get_direct_ip_details(timeout=5):
    """
    Fetches public IP details using a direct connection, with fallbacks.
    Used for diagnostics when the SSH tunnel is not active.

    Args:
        timeout (int): Request timeout in seconds.

    Returns:
        tuple[str, str]: A tuple of (ip_address, country). Defaults to ("N/A", "N/A") on failure.
    """
    return _get_ip_details(proxies=None, timeout=timeout)

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

                # 1. Get IP details through the proxy.
                ip, country = get_proxied_ip_details(socks_port)
                response["ip"] = ip
                response["country"] = country

                # 2. Perform TCP ping through the proxy.
                latency, ping_error = perform_tcp_ping(
                    host=message.get("pingHost", "youtube.com"),
                    socks_port=socks_port
                )
                response["ping_ms"] = latency
                response["ping_error"] = ping_error

                # 3. Perform web check through the proxy.
                response["web_check_status"] = perform_web_check(message.get("webCheckUrl"), socks_port)
            else:
                # Tunnel is down. Perform direct checks for diagnostics.
                logging.info("SSH tunnel not found. Performing direct connection checks for diagnostics.")
                
                # 1. Get direct IP details.
                ip, country = get_direct_ip_details()
                response["ip"] = ip
                response["country"] = country

                # 2. Perform direct TCP ping.
                latency, ping_error = perform_tcp_ping(
                    host=message.get("pingHost", "youtube.com"),
                    socks_port=None  # Explicitly None for a direct check
                )
                response["ping_ms"] = latency
                response["ping_error"] = ping_error
                response["web_check_status"] = "N/A (Tunnel Down)"
            
            logging.debug(f"Sending response: {response}")
            send_message(response)

        except Exception as e:
            logging.error(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            sys.exit(1) # Exit with a non-zero code to indicate an error

if __name__ == '__main__':
    main()