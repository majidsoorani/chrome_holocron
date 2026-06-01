#!/usr/bin/env python3
"""
Master VPN Refresh Script for OpenWrt Passwall2 (Refined)
Automates fetching, testing, and updating interface-bound load balancers.
"""

import json
import subprocess
import re
import time
import sys
import os
import argparse
from urllib.parse import urlparse, unquote
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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

IFACE_MAP = {
    'zitel': 'wan',
    'Irancell': 'wl1-sta0',
    'RighTel': 'lan3',
    'Mobinnet': 'wwan_mobinnet'
}

IFACE_PREFIX_MAP = {
    'zitel': 'zitel',
    'Irancell': 'irancell',
    'RighTel': 'rightel',
    'Mobinnet': 'mobinnet'
}

def ssh_exec(command: str) -> Tuple[bool, str, str]:
    """Execute command via SSH"""
    try:
        result = subprocess.run(
            f"ssh {ROUTER_USER}@{ROUTER_IP} '{command}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def get_balancer_id(remarks_name: str) -> Optional[str]:
    """Find balancer ID by remarks"""
    # Exact match first
    success, stdout, _ = ssh_exec(f"uci show passwall2 | grep \"remarks='{remarks_name}'\"")
    if success and stdout:
        line = stdout.strip().split('\n')[0]
        return line.split('.')[1]
    
    # Try search
    success, stdout, _ = ssh_exec(f"uci show passwall2 | grep -i \"remarks.*{remarks_name}\"")
    if success and stdout:
        line = stdout.strip().split('\n')[0]
        return line.split('.')[1]
            
    return None

def create_vless_node_cmds(server: Dict[str, Any], node_id: str, uuid: str, interface: Optional[str] = None) -> List[str]:
    """Generate UCI commands for a VLESS node"""
    remarks = str(server['name']).replace("'", " ")
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

    if interface:
        commands.append(f"set passwall2.{node_id}.bind_local='1'")
        commands.append(f"set passwall2.{node_id}.bind_interface='{interface}'")
        
    return commands

# Manual/Static nodes that should never be deleted and always included in balancers
STATIC_NODES = ['old_kixy_node']

def main():
    print("🚀 Master VPN Refresh Started (Refined)")
    
    # 0. Parse Arguments
    parser = argparse.ArgumentParser(description="Master VPN Refresh Script for OpenWrt Passwall2")
    parser.add_argument("--test-url", help="Target URL for latency testing", default="https://www.youtube.com")
    parser.add_argument("--worker-url", help="Override Cloudflare Worker URL")
    parser.add_argument("--uuid", help="Override VPN UUID")
    args = parser.parse_args()

    # Use arguments if provided, otherwise fallback to .env/config
    active_worker_url = args.worker_url or WORKER_URL
    active_uuid = args.uuid or VPN_UUID
    
    if not active_worker_url or not active_uuid:
        print("❌ ERROR: WORKER_URL and VPN_UUID must be set via .env file or command line arguments")
        sys.exit(1)

    # Determine test target
    parsed = urlparse(args.test_url)
    test_target_host = parsed.netloc or parsed.path
    if not test_target_host:
        # If it's just an IP or hostname
        test_target_host = args.test_url
        
    print(f"🎯 Latency Test Target: {args.test_url} (Host/IP: {test_target_host})")

    print("=" * 60)

    # 1. Fetch Subscription
    sub_url = f"{active_worker_url}/{active_uuid}/sub"
    print(f"\n📡 Fetching nodes from: {sub_url}")
    try:
        result = subprocess.run(["curl", "-s", "-L", sub_url], capture_output=True, text=True, timeout=30)
        content = result.stdout.strip()
        
        if not content:
            print("❌ ERROR: Subscription content is empty!")
            print(f"Debug Info: Exit Code: {result.returncode}, Stderr: {result.stderr}")
            sys.exit(1)
            
        raw_nodes = []
        if "vless://" in content or "vmess://" in content:
            raw_nodes = content.split('\n')
        else:
            try:
                import base64
                # Standard base64 padding correction
                missing_padding = len(content) % 4
                if missing_padding:
                    content += '=' * (4 - missing_padding)
                decoded = base64.b64decode(content).decode('utf-8')
                raw_nodes = decoded.strip().split('\n')
            except Exception as e:
                print(f"⚠️  Base64 decode failed, trying raw split: {e}")
                raw_nodes = content.split('\n')
    except Exception as e:
        print(f"❌ Error fetching nodes: {e}")
        sys.exit(1)

    # 2. Parse and Filter
    nodes = []
    print(f"🔍 Found {len(raw_nodes)} raw nodes. Filtering...")
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
                        'host': WORKER_URL.split('//')[-1].split('/')[0],
                        'path': '/?ed=2048',
                        'sni': sni
                    })
            except Exception:
                continue

    print(f"✅ Found {len(nodes)} valid IPv4 nodes.")

    # 3. Test Latency
    print("\n⚡ Testing latency...")
    tested_nodes = []
    for node in nodes[:30]:
        try:
            # Use test target host if provided, otherwise use node address
            ping_target = test_target_host or node['address']
            ping = subprocess.run(["ping", "-c", "2", "-W", "2000", ping_target], capture_output=True, text=True)
            if ping.returncode == 0:
                # macOS output: round-trip min/avg/max/stddev = 93.308/103.866/114.424/10.558 ms
                match = re.search(r'min/avg/max/stddev = [0-9.]+/([0-9.]+)/', ping.stdout)
                if match:
                    node['latency'] = float(match.group(1))
                    tested_nodes.append(node)
                else:
                    # Fallback for other ping formats
                    match = re.search(r'avg = ([0-9.]+)/', ping.stdout)
                    if match:
                        node['latency'] = float(match.group(1))
                        tested_nodes.append(node)
        except Exception:
            continue

    tested_nodes.sort(key=lambda x: x.get('latency', 9999))
    top_nodes = tested_nodes[:10]
    print(f"🏆 Top {len(top_nodes)} nodes selected.")

    # 4. Update Router
    print("\n🖥️  Updating OpenWrt configuration...")
    
    # Clean up old temporary nodes (excluding manual/static nodes)
    exclude_args = " ".join([f"-v '{node}'" for node in STATIC_NODES])
    ssh_exec(f"uci show passwall2 | grep -E '^passwall2.(zitel|irancell|rightel)_node_' | cut -d. -f2 | cut -d= -f1 | grep {exclude_args} | xargs -I {{}} uci delete passwall2.{{}}")
    ssh_exec("uci commit passwall2")

    for balancer_name, interface_name in IFACE_MAP.items():
        prefix = IFACE_PREFIX_MAP[balancer_name]
        balancer_id = get_balancer_id(balancer_name)
        
        if not balancer_id:
            print(f"⚠️  SKIPPING: Balancer '{balancer_name}' not found.")
            continue
            
        print(f"   ⚙️  Configuring '{balancer_name}' (ID: {balancer_id})...")
        
        batch_cmds = []
        node_ids = []
        for i, node in enumerate(top_nodes, 1):
            node_id = f"{prefix}_node_{i}"
            batch_cmds.extend(create_vless_node_cmds(node, node_id, active_uuid, interface_name))
            node_ids.append(node_id)
        
        # Update balancer
        batch_cmds.append(f"delete passwall2.{balancer_id}.balancing_node")
        # Add fresh nodes
        for nid in node_ids:
            batch_cmds.append(f"add_list passwall2.{balancer_id}.balancing_node='{nid}'")
        # Add static nodes
        for snid in STATIC_NODES:
            batch_cmds.append(f"add_list passwall2.{balancer_id}.balancing_node='{snid}'")
        
        batch_cmds.append("commit passwall2")
        
        # Use uci batch for reliability
        batch_str = "\n".join(batch_cmds)
        # Write batch to a temp file on router and execute
        ssh_exec(f"cat <<EOF > /tmp/vpn_update.batch\n{batch_str}\nEOF")
        success, _, stderr = ssh_exec("uci batch < /tmp/vpn_update.batch")
        
        if success:
            print(f"   ✅ Balancer '{balancer_name}' updated.")
        else:
            print(f"   ❌ Error updating {balancer_name}: {stderr}")

    # 5. Restart
    print("\n🔄 Restarting Passwall2...")
    success, _, stderr = ssh_exec("/etc/init.d/passwall2 restart")
    if success:
        print("✅ VPN services refreshed!")
    else:
        print(f"❌ Failed to restart: {stderr}")

    print("\n" + "=" * 60)
    print("✨ Refresh Complete!")

if __name__ == "__main__":
    main()
