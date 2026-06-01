#!/usr/bin/env python3
import os
import sys
import re
import json
import base64
import subprocess
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Load environment configuration
def load_env(env_path):
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

ENV_PATH = Path(__file__).parent / ".env"
CONFIG = load_env(ENV_PATH)

ROUTER_IP = CONFIG.get("ROUTER_IP", "192.168.1.1")
ROUTER_USER = CONFIG.get("ROUTER_USER", "root")
WORKER_URL = CONFIG.get("WORKER_URL", "https://cloudflaresoorani.soorani.workers.dev")
VPN_UUID = CONFIG.get("VPN_UUID", "c0686cb1-515d-4fe3-8f22-508746811ef3")

# Default subscription URLs to try
DEFAULT_SUBSCRIPTIONS = [
    f"{WORKER_URL}/{VPN_UUID}/sub",
    "https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304",
    "https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5",
    "https://multiservers.info/sub/djMsMzk6NTIsMTc3OTA5NzA0NQ2db88860a2#EXC5Q",
    "https://multiservers.info/sub/djMsMzQ3MzcsMTc3ODk2Nzk0MAa2bf94679b#QK8QF"
]

def decode_base64(data):
    """Safely decode base64 string with padding adjustment."""
    data = data.strip().replace("\r", "").replace("\n", "")
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode('utf-8', errors='ignore')
    except Exception:
        return ""

def parse_proxy_link(link):
    """Parse SS, VLESS, VMESS, or Trojan links into a standard dictionary format."""
    link = link.strip()
    if not link:
        return None
        
    try:
        name = ""
        if "#" in link:
            link, name_part = link.split("#", 1)
            name = urllib.parse.unquote(name_part)
            
        if link.startswith("ss://"):
            # shadowsocks link parsing
            # Format: ss://base64(method:password)@host:port
            # Or: ss://base64(method:password@host:port)
            content = link[5:]
            if "@" in content:
                userinfo, hostport = content.split("@", 1)
                decoded_user = decode_base64(userinfo)
                method, password = decoded_user.split(":", 1)
                host, port = hostport.split(":", 1)
            else:
                decoded = decode_base64(content)
                if "@" in decoded:
                    userinfo, hostport = decoded.split("@", 1)
                    method, password = userinfo.split(":", 1)
                    host, port = hostport.split(":", 1)
                else:
                    return None
            return {
                "type": "Shadowsocks",
                "name": name or f"SS-{host}",
                "server": host,
                "port": int(port),
                "method": method,
                "password": password,
                "raw": link
            }
            
        elif link.startswith("vless://"):
            # vless://uuid@host:port?query#name
            content = link[8:]
            uuid, remain = content.split("@", 1)
            hostport, *query_parts = remain.split("?", 1)
            host, port = hostport.split(":", 1)
            
            query = query_parts[0] if query_parts else ""
            params = urllib.parse.parse_qs(query)
            
            return {
                "type": "VLESS",
                "name": name or f"VLESS-{host}",
                "server": host,
                "port": int(port),
                "uuid": uuid,
                "tls": "1" if params.get("security", [""])[0] == "tls" else "0",
                "sni": params.get("sni", [""])[0],
                "transport": params.get("type", ["tcp"])[0],
                "ws_host": params.get("host", [""])[0],
                "ws_path": params.get("path", ["/"])[0],
                "raw": link
            }
            
        elif link.startswith("vmess://"):
            # vmess://base64(json)
            content = link[8:]
            decoded = decode_base64(content)
            data = json.loads(decoded)
            return {
                "type": "VMESS",
                "name": name or data.get("ps", f"VMESS-{data.get('add')}"),
                "server": data.get("add"),
                "port": int(data.get("port", 443)),
                "uuid": data.get("id"),
                "alterId": int(data.get("aid", 0)),
                "security": data.get("scy", "auto"),
                "transport": data.get("net", "tcp"),
                "ws_host": data.get("host", ""),
                "ws_path": data.get("path", "/"),
                "tls": "1" if data.get("tls") == "tls" else "0",
                "raw": link
            }
            
        elif link.startswith("trojan://"):
            # trojan://password@host:port?query
            content = link[9:]
            password, remain = content.split("@", 1)
            hostport, *query_parts = remain.split("?", 1)
            host, port = hostport.split(":", 1)
            return {
                "type": "Trojan",
                "name": name or f"Trojan-{host}",
                "server": host,
                "port": int(port),
                "password": password,
                "raw": link
            }
    except Exception as e:
        # Silently skip malformed links
        pass
    return None

def fetch_subscription(url):
    """Fetch nodes from a subscription URL and decode them."""
    print(f"Fetching nodes from: {url} ...")
    try:
        cmd = ["curl", "-s", "-L", "-m", "10", "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", url]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        content = proc.stdout.strip()
            
        if not content:
            return []
            
        # Check if the content is base64 encoded
        if "vless://" not in content and "vmess://" not in content and "ss://" not in content and "trojan://" not in content:
            content = decode_base64(content)
            
        links = [line.strip() for line in content.splitlines() if line.strip()]
        nodes = []
        for l in links:
            node = parse_proxy_link(l)
            if node:
                nodes.append(node)
        return nodes
    except Exception as e:
        print(f"⚠️ Failed to fetch {url}: {e}")
        return []

def local_ping(host):
    """Run local ping on the Mac to get latency."""
    try:
        cmd = ["ping", "-c", "1", "-W", "1000", host]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        if proc.returncode == 0:
            match = re.search(r"time=([0-9.]+) ms", proc.stdout)
            if match:
                return f"{float(match.group(1)):.1f}ms"
    except Exception:
        pass
    return "timeout"

def test_nodes_on_router(nodes):
    """Upload a batch ping script to the router and test all nodes in parallel."""
    if not nodes:
        return {}
        
    servers = list(set(node["server"] for node in nodes))
    servers_str = " ".join(servers)
    
    # We create a shell script to run on the router that pings targets in parallel
    router_script = f"""#!/bin/sh
# Multi-WAN ping tester
targets="{servers_str}"
for target in $targets; do
    (
        # Ping Zitel (wan)
        z_rtt=$(ping -c 1 -W 1 -I wan "$target" 2>/dev/null | grep 'time=' | sed -E 's/.*time=([0-9.]+).*/\\1/')
        [ -z "$z_rtt" ] && z_rtt="timeout"
        
        # Ping RighTel (lan3)
        r_rtt=$(ping -c 1 -W 1 -I lan3 "$target" 2>/dev/null | grep 'time=' | sed -E 's/.*time=([0-9.]+).*/\\1/')
        [ -z "$r_rtt" ] && r_rtt="timeout"
        
        # Ping Mobinnet (lan1)
        m_rtt=$(ping -c 1 -W 1 -I lan1 "$target" 2>/dev/null | grep 'time=' | sed -E 's/.*time=([0-9.]+).*/\\1/')
        [ -z "$m_rtt" ] && m_rtt="timeout"
        
        echo "$target:$z_rtt:$r_rtt:$m_rtt"
    ) &
done
wait
"""
    
    # Write temp router script
    temp_script_path = "/tmp/ndtest.sh"
    try:
        # Write local copy first
        with open("/tmp/ndtest.sh", "w") as f:
            f.write(router_script)
            
        # Copy to router using ssh redirection (since scp is unsupported without sftp-server)
        subprocess.run(
            f"ssh {ROUTER_USER}@{ROUTER_IP} 'cat > /tmp/ndtest.sh' < /tmp/ndtest.sh",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        # Execute on router
        cmd = f"ssh {ROUTER_USER}@{ROUTER_IP} 'chmod +x /tmp/ndtest.sh && /tmp/ndtest.sh && rm -f /tmp/ndtest.sh'"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        
        results = {}
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line and ":" in line:
                parts = line.split(":")
                if len(parts) == 4:
                    host, z_rtt, r_rtt, m_rtt = parts
                    results[host] = {
                        "zitel": f"{float(z_rtt):.1f}ms" if z_rtt != "timeout" else "timeout",
                        "rightel": f"{float(r_rtt):.1f}ms" if r_rtt != "timeout" else "timeout",
                        "mobinnet": f"{float(m_rtt):.1f}ms" if m_rtt != "timeout" else "timeout",
                    }
        return results
    except Exception as e:
        print(f"⚠️ Error running tests on router via SSH: {e}")
        return {}

def main():
    print("========================================")
    print("      Holocron Proxy Node Manager       ")
    print("========================================")
    
    # Gather nodes from all subscriptions
    all_nodes = []
    for url in DEFAULT_SUBSCRIPTIONS:
        nodes = fetch_subscription(url)
        all_nodes.extend(nodes)
        
    if not all_nodes:
        print("❌ No nodes fetched from subscriptions!")
        sys.exit(1)
        
    # Remove duplicates based on type + server + port
    seen = set()
    unique_nodes = []
    for n in all_nodes:
        key = (n["type"], n["server"], n["port"])
        if key not in seen:
            seen.add(key)
            unique_nodes.append(n)
            
    print(f"Successfully loaded {len(unique_nodes)} unique nodes.")
    print("Running parallel latency tests (local Mac and Router interfaces)...")
    
    # Test router latency in parallel on router
    router_latencies = test_nodes_on_router(unique_nodes)
    
    # Test local Mac latency in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        local_hosts = [n["server"] for n in unique_nodes]
        local_results = list(executor.map(local_ping, local_hosts))
        
    for idx, node in enumerate(unique_nodes):
        node["local_rtt"] = local_results[idx]
        router_res = router_latencies.get(node["server"], {"zitel": "timeout", "rightel": "timeout", "mobinnet": "timeout"})
        node["zitel_rtt"] = router_res["zitel"]
        node["rightel_rtt"] = router_res["rightel"]
        node["mobinnet_rtt"] = router_res["mobinnet"]
        
    # Render table
    print("\n" + "=" * 115)
    print(f"{'Idx':<4} | {'Name':<30} | {'Type':<10} | {'Port':<6} | {'Mac Ping':<9} | {'Zitel (wan)':<12} | {'RighTel (lan3)':<14} | {'Mobinnet (lan1)'}")
    print("-" * 115)
    
    for idx, node in enumerate(unique_nodes):
        name = node["name"]
        if len(name) > 30:
            name = name[:27] + "..."
        print(f"{idx:<4} | {name:<30} | {node['type']:<10} | {node['port']:<6} | {node['local_rtt']:<9} | {node['zitel_rtt']:<12} | {node['rightel_rtt']:<14} | {node['mobinnet_rtt']}")
        
    print("=" * 115)
    
    print("\nOptions:")
    print("1. Select a node to print raw URI link")
    print("2. Exit")
    
    try:
        choice = input("\nEnter choice [1-2]: ").strip()
        if choice == "1":
            node_idx = int(input(f"Enter node index [0-{len(unique_nodes)-1}]: ").strip())
            if 0 <= node_idx < len(unique_nodes):
                selected = unique_nodes[node_idx]
                print("\nSelected Node Configuration details:")
                for k, v in selected.items():
                    if k != "raw":
                        print(f"  {k}: {v}")
                print(f"\nRaw URI:\n{selected['raw']}\n")
            else:
                print("Invalid index.")
    except KeyboardInterrupt:
        print("\nExited.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
