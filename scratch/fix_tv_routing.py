#!/usr/bin/env python3
import json
import subprocess
import sys

ROUTER_IP = "192.168.1.1"
SSH_USER = "root"
CONFIG_PATH = "/etc/sing-box/config.json"

def run_ssh_cmd(cmd_str):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", cmd_str]
    res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if res.returncode != 0:
        print(f"Error running SSH command: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return res.stdout

def main():
    print(f"Reading configuration from router ({ROUTER_IP})...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    old_rules = config.get("route", {}).get("rules", [])
    
    # Separate existing header rules (sniff, hijack-dns)
    header_rules = []
    direct_rules = []
    
    for rule in old_rules:
        if rule.get("action") in ["sniff", "hijack-dns"]:
            header_rules.append(rule)
        elif rule.get("outbound") == "direct" or rule.get("ip_is_private") == True:
            if rule not in direct_rules:
                direct_rules.append(rule)

    # 1. NTP rule: UDP 123 direct
    ntp_rule = {
        "port": [123],
        "network": ["udp"],
        "action": "route",
        "outbound": "direct"
    }

    # 2. QUIC rule: UDP 443 reject
    quic_rule = {
        "port": [443],
        "network": ["udp"],
        "action": "reject"
    }

    # 3. YouTube domains list (should go to tunnel-mobinnet)
    youtube_domains = [
        "youtube.com",
        "youtubei.googleapis.com",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
        "ytimg.l.google.com",
        "youtube-nocookie.com",
        "youtu.be"
    ]
    youtube_rule = {
        "domain_suffix": youtube_domains,
        "action": "route",
        "outbound": "tunnel-mobinnet"
    }

    # 4. 30nama domains list (should go to tunnel-rightel)
    nama_domains = [
        "30nama.com",
        "30nama.ts",
        "30nama.work",
        "30nama.website",
        "30nama.zone",
        "30nama.space",
        "30nama.press"
    ]
    nama_rule = {
        "domain_suffix": nama_domains,
        "action": "route",
        "outbound": "tunnel-rightel"
    }

    # Define the new rules order:
    # Header Rules -> NTP -> QUIC -> Custom Tunnels -> Direct Rules (IP/IR)
    new_rules = header_rules + [ntp_rule, quic_rule, youtube_rule, nama_rule] + direct_rules
    config["route"]["rules"] = new_rules

    print("Uploading updated configuration...")
    new_config_str = json.dumps(config, indent=2)
    ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
    subprocess.run(ssh_write_cmd, input=new_config_str, text=True, check=True)

    print("Verifying configuration validity with sing-box check...")
    check_res = run_ssh_cmd("sing-box check -c /etc/sing-box/config.json 2>&1 || echo 'failed'")
    if "failed" in check_res or "error" in check_res.lower():
        print(f"❌ Configuration check failed:\n{check_res}", file=sys.stderr)
        sys.exit(1)
    print("✅ Configuration is valid!")

    print("Restarting sing-box service...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("✅ Service restarted successfully!")

if __name__ == "__main__":
    main()
