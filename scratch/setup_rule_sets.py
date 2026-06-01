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

    print("Configuring modern sing-box Rule Sets (geosite-ir, geoip-ir)...")

    # 1. Add rule_set configuration to route
    config["route"]["rule_set"] = [
        {
            "type": "remote",
            "tag": "geosite-ir",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs"
        },
        {
            "type": "remote",
            "tag": "geoip-ir",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs"
        }
    ]

    # 2. Update dns servers to use 127.0.0.1 (dnsmasq) for direct resolution
    dns_servers = config.setdefault("dns", {}).setdefault("servers", [])
    for server in dns_servers:
        if server.get("tag") == "dns-direct":
            server["server"] = "127.0.0.1"
            server["type"] = "udp"  # Ensure it is standard UDP

    # 3. Update dns rules to use geosite-ir and .ir suffix separately
    config["dns"]["rules"] = [
        {
            "rule_set": ["geosite-ir"],
            "server": "dns-direct"
        },
        {
            "domain_suffix": ["ir", "xn--mgba3a4f16a"],
            "server": "dns-direct"
        }
    ]

    # 3. Rebuild routing rules cleanly
    old_rules = config.get("route", {}).get("rules", [])
    
    # We keep header rules, NTP, QUIC, and specific custom tunnels, but discard old IP CIDR and domain suffix rules
    new_rules = []
    for rule in old_rules:
        # Keep sniff, hijack-dns, NTP, QUIC, YouTube, 30nama
        if (rule.get("action") in ["sniff", "hijack-dns"] or 
            rule.get("port") == [123] or 
            rule.get("port") == [443] or
            "youtube.com" in rule.get("domain_suffix", []) or
            "30nama.com" in rule.get("domain_suffix", [])):
            new_rules.append(rule)
        elif rule.get("ip_is_private") == True:
            # Keep private IP bypass rule
            new_rules.append(rule)

    # Add the direct routing rules using the new rule_sets and the basic .ir suffix fallback separately
    ruleset_direct_rule = {
        "rule_set": ["geosite-ir", "geoip-ir"],
        "action": "route",
        "outbound": "direct"
    }
    suffix_direct_rule = {
        "domain_suffix": ["ir", "xn--mgba3a4f16a"],
        "action": "route",
        "outbound": "direct"
    }
    
    new_rules.append(ruleset_direct_rule)
    new_rules.append(suffix_direct_rule)
    config["route"]["rules"] = new_rules

    # 4. Upload updated configuration
    print("Uploading updated configuration to router...")
    new_config_str = json.dumps(config, indent=2)
    ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
    subprocess.run(ssh_write_cmd, input=new_config_str, text=True, check=True)

    # 5. Check configuration validity on router
    print("Verifying configuration validity with sing-box check...")
    check_res = run_ssh_cmd("sing-box check -c /etc/sing-box/config.json 2>&1 || echo 'failed'")
    if "failed" in check_res or "error" in check_res.lower():
        print(f"❌ Configuration check failed:\n{check_res}", file=sys.stderr)
        sys.exit(1)
    print("✅ Configuration is valid!")

    # 6. Restart sing-box
    print("Restarting sing-box service...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("✅ Service restarted successfully!")

if __name__ == "__main__":
    main()
