#!/usr/bin/env python3
"""
Master VPN Refresh Script for OpenWrt Passwall2 (Refined)
Automates fetching, testing, and updating the best Cloudflare proxy.
Includes fallback logic for an Xray Socks node and modem restart.
"""

import json
import subprocess
import re
import time
import sys
import os
import argparse
import datetime
from urllib.parse import urlparse, unquote
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

STATE_FILE = Path("/tmp/vpn_status.json")
LOG_FILE = Path("/tmp/vpn_refresh.log")

def load_env(env_path: Path) -> Dict[str, str]:
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key_value = line.split('=', 1)
                    if len(key_value) == 2:
                        env_vars[key_value[0].strip()] = key_value[1].strip()
    return env_vars

ENV_PATH = Path(__file__).parent / ".env"
CONFIG = load_env(ENV_PATH)

ROUTER_IP = CONFIG.get("ROUTER_IP", "192.168.1.1")
ROUTER_USER = CONFIG.get("ROUTER_USER", "root")
WORKER_URL = CONFIG.get("WORKER_URL")
VPN_UUID = CONFIG.get("VPN_UUID")

class Logger:
    @staticmethod
    def _log(msg: str, symbol: str = ""):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{now}] {symbol} {msg}"
        print(formatted_msg)
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(formatted_msg + "\n")
        except:
            pass

    @staticmethod
    def info(msg: str):
        Logger._log(msg, "ℹ️")
    @staticmethod
    def success(msg: str):
        Logger._log(msg, "✅")
    @staticmethod
    def warning(msg: str):
        Logger._log(msg, "⚠️")
    @staticmethod
    def error(msg: str):
        Logger._log(msg, "❌")

def save_state(status: str, active_node: Optional[str] = None, latency: Optional[float] = None, node_type: str = "Unknown"):
    """Saves the current VPN state to a JSON file for SwiftBar integration."""
    state = {
        "last_refresh": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "active_node": active_node or "None",
        "latency": f"{latency:.2f}ms" if latency is not None else "N/A",
        "type": node_type
    }
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Error saving state: {e}")

logger = Logger()

def ssh_exec(command: str) -> Tuple[bool, str, str]:
    """Execute command via SSH"""
    try:
        result = subprocess.run(
            f"ssh {ROUTER_USER}@{ROUTER_IP} '{command}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def find_shunt_node() -> Optional[str]:
    """Finds the main node ID (Node switch), and returns it if it's a Shunt."""
    # First get the main node id
    success, stdout, _ = ssh_exec("uci get passwall2.@global[0].node")
    if success and stdout.strip():
        main_node_id = stdout.strip()
        # Verify if it is a shunt node
        s_success, s_stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.protocol")
        if s_success and s_stdout.strip() == '_shunt':
            return main_node_id
        return main_node_id # Even if it's not a shunt, we return the main node
    return None

def find_local_socks_node_id(port: str = "1032") -> Optional[str]:
    """Find the node ID of the local socks proxy on the router."""
    success, stdout, _ = ssh_exec("uci show passwall2")
    if success and stdout:
        for line in stdout.splitlines():
            if f".port='{port}'" in line and "group=" not in line:
                parts = line.split('.')
                if len(parts) >= 2:
                    return parts[1]
    return None

def test_local_proxy_on_router(port: str = "1032", test_url: str = "https://www.youtube.com") -> bool:
    """Tests if curl works through the specified SOCKS5 port on the router."""
    logger.info(f"Testing local proxy at 127.0.0.1:{port} on router...")
    cmd = f"curl -s --socks5-hostname 127.0.0.1:{port} -o /dev/null -w '%{{http_code}}' -m 15 {test_url}"
    success, stdout, stderr = ssh_exec(cmd)
    
    if success and stdout.strip().isdigit():
        code = int(stdout.strip())
        logger.info(f"Local proxy test returned HTTP {code}")
        # Consider 2xx and 3xx as success
        if 200 <= code < 400:
            return True
    
    logger.warning(f"Local proxy test failed. Code: {stdout.strip()} | Error: {stderr.strip()}")
    return False

def create_vless_node_cmds(server: Dict[str, Any], node_id: str, uuid: str) -> List[str]:
    """Generate UCI commands for a VLESS node"""
    remarks = str(server.get('name') or 'best_cf_proxy').replace("'", " ")
    commands = [
        f"set passwall2.{node_id}=nodes",
        f"set passwall2.{node_id}.remarks='{remarks}'",
        f"set passwall2.{node_id}.type='sing-box'",
        f"set passwall2.{node_id}.protocol='vless'",
        f"set passwall2.{node_id}.address='{server['address']}'",
        f"set passwall2.{node_id}.port='{server['port']}'",
        f"set passwall2.{node_id}.uuid='{uuid}'",
        f"set passwall2.{node_id}.encryption='none'",
    ]
    
    if server.get('security') == 'tls':
        commands.append(f"set passwall2.{node_id}.tls='1'")
        if server.get('sni'):
            commands.append(f"set passwall2.{node_id}.tls_serverName='{server['sni']}'")
    else:
        commands.append(f"set passwall2.{node_id}.tls='0'")
    
    commands.append(f"set passwall2.{node_id}.transport='{server['type']}'")
    if server['type'] == 'ws':
        commands.append(f"set passwall2.{node_id}.ws_host='{server.get('host', '')}'")
        commands.append(f"set passwall2.{node_id}.ws_path='{server.get('path', '/')}'")
        
    return commands

def check_if_node_changed(node_id: str, new_server: Dict[str, Any]) -> bool:
    """Checks if the existing node configuration differs from the new one."""
    success, stdout, _ = ssh_exec(f"uci show passwall2.{node_id}")
    if not success or not stdout.strip():
        return True # Node doesn't exist yet
    
    current = {}
    for line in stdout.splitlines():
        if '=' in line:
            parts = line.split('=', 1)
            if len(parts) == 2:
                key = parts[0].split('.')[-1]
                val = parts[1].strip("'")
                current[key] = val
                
    if current.get('address') != new_server.get('address'):
        return True
    if current.get('port') != str(new_server.get('port', '')):
        return True
    if current.get('ws_host') != new_server.get('host', ''):
        return True
        
    return False

def fetch_and_test_nodes(active_worker_url: str, active_uuid: str, test_target_host: str) -> Optional[Dict[str, Any]]:
    """Fetches nodes from Cloudflare and finds the best one."""
    sub_url = f"{active_worker_url}/{active_uuid}/sub"
    logger.info(f"Fetching nodes from: {sub_url}")
    
    try:
        result = subprocess.run(["curl", "-s", "-L", sub_url], capture_output=True, text=True, timeout=30)
        content = result.stdout.strip()
        
        if not content:
            logger.error("Subscription content is empty!")
            return None
            
        raw_nodes = []
        if "vless://" in content or "vmess://" in content:
            raw_nodes = content.split('\n')
        else:
            try:
                import base64
                missing_padding = len(content) % 4
                if missing_padding:
                    content += '=' * (4 - missing_padding)
                decoded = base64.b64decode(content).decode('utf-8')
                raw_nodes = decoded.strip().split('\n')
            except Exception as e:
                logger.warning(f"Base64 decode failed, trying raw split: {e}")
                raw_nodes = content.split('\n')
    except Exception as e:
        logger.error(f"Error fetching nodes: {e}")
        return None

    nodes = []
    for link in raw_nodes:
        if link.startswith('vless://'):
            try:
                parts = re.split(r'[@:/?#&]', link[8:])
                uuid = parts[0]
                addr = parts[1]
                port = parts[2]
                
                if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', addr):
                    name = unquote(link.split('#', 1)[1]) if '#' in link else addr
                    
                    security = 'tls' if 'security=tls' in link else 'none'
                    sni_match = re.search(r'sni=([^&]+)', link)
                    sni = sni_match.group(1) if sni_match else ""
                    
                    nodes.append({
                        'name': name,
                        'address': addr,
                        'port': port,
                        'security': security,
                        'type': 'ws' if 'type=ws' in link else 'tcp',
                        'host': active_worker_url.split('//')[-1].split('/')[0],
                        'path': '/?ed=2048',
                        'sni': sni
                    })
            except Exception:
                continue

    if not nodes:
        logger.error("No valid IPv4 VLESS nodes extracted.")
        return None

    logger.info(f"Found {len(nodes)} valid IPv4 nodes. Testing latency...")
    
    tested_nodes = []
    for node in nodes[:20]: # Limit testing to save time
        try:
            ping_target = test_target_host or node['address']
            ping_cmd = ["ping", "-c", "2", "-W", "2000", ping_target]
            
            # Using python 3.9+ timeout kwarg just in case
            ping = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=5)
            if ping.returncode == 0:
                match = re.search(r'min/avg/max/stddev = [0-9.]+/([0-9.]+)/', ping.stdout)
                if match:
                    node['latency'] = float(match.group(1))
                    tested_nodes.append(node)
                else:
                    match = re.search(r'avg = ([0-9.]+)/', ping.stdout)
                    if match:
                        node['latency'] = float(match.group(1))
                        tested_nodes.append(node)
        except Exception:
            continue

    if not tested_nodes:
        logger.error("All CF nodes failed ping test.")
        return None

    tested_nodes.sort(key=lambda x: x.get('latency', 9999))
    best_node = tested_nodes[0]
    logger.success(f"Selected best CC node: {best_node['address']} (Latency: {best_node.get('latency', 0):.2f}ms)")
    return best_node

def is_node_active(node_id: str) -> bool:
    """Checks if the given node_id is currently the active routing node."""
    main_node_id = find_shunt_node()
    if not main_node_id:
        return False
        
    s_success, s_stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.protocol")
    is_shunt = s_success and s_stdout.strip() == '_shunt'
    
    if is_shunt:
        success, stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.default_node")
        return success and stdout.strip() == node_id
    else:
        success, stdout, _ = ssh_exec("uci get passwall2.@global[0].tcp_node")
        return success and stdout.strip() == node_id

def get_active_node_info() -> Tuple[Optional[str], Optional[str]]:
    """Finds the (address, node_id) of the currently active proxy node."""
    main_node_id = find_shunt_node()
    if not main_node_id:
        return None, None
        
    active_node_id = main_node_id
    # If the main node is a shunt, the actual active node is its default_node
    s_success, s_stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.protocol")
    is_shunt = s_success and s_stdout.strip() == '_shunt'
    
    if is_shunt:
        success, stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.default_node")
        if success and stdout.strip():
            active_node_id = stdout.strip()
            
    # Now get the address of this active_node_id
    success, stdout, _ = ssh_exec(f"uci get passwall2.{active_node_id}.address")
    if success and stdout.strip():
        addr = stdout.strip()
        # Ensure it looks like an IP or hostname, not a raw config string
        if len(addr) > 2:
            return addr, active_node_id
    return None, active_node_id

def apply_router_config(node_id: str):
    """Applies the identified node_id as default in passwall2 and restarts."""
    main_node_id = find_shunt_node()
    if not main_node_id:
        logger.error("Could not determine current global TCP node (shunt).")
        return False
        
    logger.info(f"Identified active routing node: passwall2.{main_node_id}")
    
    # Check if the main TCP node is a Shunt
    s_success, s_stdout, _ = ssh_exec(f"uci get passwall2.{main_node_id}.protocol")
    is_shunt = s_success and s_stdout.strip() == '_shunt'

    if is_shunt:
        ssh_exec(f"uci set passwall2.{main_node_id}.default_node='{node_id}'")
        logger.info(f"Set Shunt default_node to '{node_id}'")
    else:
        # Instead of updating the shunt, update the global TCP mode to this node directly
        ssh_exec(f"uci set passwall2.@global[0].tcp_node='{node_id}'")
        ssh_exec(f"uci set passwall2.@global[0].udp_node='{node_id}'")
        logger.info(f"Set global tcp/udp node to '{node_id}'")

    ssh_exec("uci commit passwall2")
    
    logger.info("Restarting Passwall2...")
    success, _, stderr = ssh_exec("/etc/init.d/passwall2 restart")
    if success:
        logger.success("Passwall2 restarted successfully.")
        return True
    else:
        logger.error(f"Failed to restart passwall2: {stderr}")
        return False

def refresh_cycle(active_worker_url: str, active_uuid: str, test_url: str):
    logger.info("Starting refresh cycle...")
    
    parsed = urlparse(test_url)
    test_target_host = parsed.netloc or parsed.path
    if not test_target_host:
        test_target_host = test_url

    # Early exit optimization: check current node latency first
    current_addr, current_id = get_active_node_info()
    if current_addr and current_addr != '127.0.0.1':
        logger.info(f"Checking latency of currently active node: {current_addr}")
        try:
            ping_cmd = ["ping", "-c", "2", "-W", "2000", current_addr]
            ping = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=5)
            if ping.returncode == 0:
                match = re.search(r'min/avg/max/stddev = [0-9.]+/([0-9.]+)/', ping.stdout)
                latency = None
                if match:
                    latency = float(match.group(1))
                else:
                    match = re.search(r'avg = ([0-9.]+)/', ping.stdout)
                    if match:
                        latency = float(match.group(1))
                        
                if latency is not None and latency < 400.0:
                    logger.success(f"Current active node ({current_addr}) is still fast enough ({latency:.2f}ms). Skipping refresh.")
                    label = "Cloudflare" if current_id == "best_cf_node" else "Kixy SSH"
                    save_state("Connected", active_node=current_addr, latency=latency, node_type=label)
                    return
                elif latency is not None:
                     logger.warning(f"Current active node ({current_addr}) is slow ({latency:.2f}ms). Searching for a better one...")
                     save_state("Refreshing", active_node=current_addr, latency=latency, node_type="Slow")
            else:
                 logger.warning(f"Current active node ({current_addr}) is unreachable. Searching for a better one...")
                 save_state("Refreshing", active_node=current_addr, node_type="Disconnected")
        except Exception as e:
            logger.warning(f"Failed to ping current active node: {e}")
            save_state("Error", node_type="Ping Failed")

    save_state("Fetching Nodes")
    best_node = fetch_and_test_nodes(active_worker_url, active_uuid, test_target_host)
    
    if best_node:
        node_id = "best_cf_node"
        
        # Determine if we even need to update
        if is_node_active(node_id) and not check_if_node_changed(node_id, best_node):
            logger.success(f"Best CF node ({best_node['address']}) is already the active default. Skipping restart to avoid network interruption.")
            save_state("Connected", active_node=best_node['address'], latency=best_node['latency'], node_type="Cloudflare")
            return
            
        logger.info("Applying new best CF node to router...")
        save_state("Updating Router", active_node=best_node['address'], node_type="Cloudflare")
        
        batch_cmds = []
        batch_cmds.extend(create_vless_node_cmds(best_node, node_id, active_uuid))
        batch_cmds.append("commit passwall2")
        
        batch_str = "\n".join(batch_cmds)
        ssh_exec(f"cat <<EOF > /tmp/cf_update.batch\n{batch_str}\nEOF")
        ssh_exec("uci batch < /tmp/cf_update.batch")
        
        if apply_router_config(node_id):
            save_state("Connected", active_node=best_node['address'], latency=best_node.get('latency'), node_type="Cloudflare")
    else:
        # Fallback 1: Test 127.0.0.1:1032 on the router
        logger.warning("No Cloudflare nodes available. Falling back to local node 127.0.0.1:1032...")
        save_state("Fallback", node_type="Initiating Local SOCKS")
        
        if test_local_proxy_on_router(port="1032", test_url=test_url):
            logger.success("Fallback local proxy works! Setting it as default.")
            local_node_id = find_local_socks_node_id("1032")
            if local_node_id:
                # Check if it was already the active fallback
                if is_node_active(local_node_id) and not check_if_node_changed(local_node_id, {'address': '127.0.0.1', 'port': '1032'}):
                     logger.success("Fallback node is already active. Skipping restart.")
                     save_state("Connected", active_node="127.0.0.1:1032", node_type="Local SOCKS")
                else:    
                     if apply_router_config(local_node_id):
                         save_state("Connected", active_node="127.0.0.1:1032", node_type="Local SOCKS")
            else:
                logger.error("Could not find Passwall2 node ID for port 1032.")
                save_state("Error", node_type="Local SOCKS ID Missing")
        else:
            # Fallback 2: Restart the modem/router
            logger.error("Fallback local proxy also failed. Restarting the router/modem...")
            save_state("Rebooting Modem", node_type="Critical")
            ssh_exec("reboot")

def main():
    parser = argparse.ArgumentParser(description="Auto Refresh Proxy Script for OpenWrt")
    parser.add_argument("--test-url", help="Target URL for latency testing", default="https://www.youtube.com")
    parser.add_argument("--worker-url", help="Override Cloudflare Worker URL")
    parser.add_argument("--uuid", help="Override VPN UUID")
    parser.add_argument("--run-once", help="Run once and exit", action="store_true")
    args = parser.parse_args()

    active_worker_url = args.worker_url or WORKER_URL
    active_uuid = args.uuid or VPN_UUID
    
    if not active_worker_url or not active_uuid:
        logger.error("WORKER_URL and VPN_UUID must be set via .env file or arguments.")
        sys.exit(1)

    if args.run_once:
        refresh_cycle(active_worker_url, active_uuid, args.test_url)
        return

    logger.info("🟢 Starting Continuous Proxy Auto-Refresh Daemon (interval: 5 seconds)")
    try:
        while True:
            refresh_cycle(active_worker_url, active_uuid, args.test_url)
            logger.info("Sleeping for 5 seconds...")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Daemon gracefully stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
