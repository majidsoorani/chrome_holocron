#!/usr/bin/env python3
import sys
import json
import subprocess
import tempfile
import os

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
    if len(sys.argv) < 2:
        print("Usage: python3 add_to_bypass.py <domain_pattern>", file=sys.stderr)
        print("Example: python3 add_to_bypass.py *.iranicard.ir", file=sys.stderr)
        sys.exit(1)

    domain = sys.argv[1].strip()
    
    # 1. Read existing config.json
    print(f"Fetching config from router ({ROUTER_IP})...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Add domain to dns.rules (direct DNS lookup) and route.rules (direct routing)
    added = False
    
    # Update DNS rules domain_suffix
    dns_rules = config.get("dns", {}).get("rules", [])
    for rule in dns_rules:
        if rule.get("server") == "dns-direct" and "domain_suffix" in rule:
            suffixes = rule["domain_suffix"]
            clean_domain = domain.lstrip("*.") # sing-box domain_suffix expects just domain, e.g. iranicard.ir
            if clean_domain not in suffixes:
                suffixes.append(clean_domain)
                print(f"Added {clean_domain} to direct DNS suffix rules.")
                added = True
            break
            
    # Update Route rules domain_suffix
    route_rules = config.get("route", {}).get("rules", [])
    for rule in route_rules:
        if rule.get("outbound") == "direct" and "domain_suffix" in rule:
            suffixes = rule["domain_suffix"]
            clean_domain = domain.lstrip("*.")
            if clean_domain not in suffixes:
                suffixes.append(clean_domain)
                print(f"Added {clean_domain} to direct routing suffix rules.")
                added = True
            break

    if not added:
        print(f"Domain '{domain}' already exists in direct bypass rules.")
        sys.exit(0)

    # 3. Upload new config to router
    print("Uploading updated configuration to router...")
    new_config_str = json.dumps(config, indent=2)
    try:
        ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
        subprocess.run(ssh_write_cmd, input=new_config_str, text=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"Failed to upload config: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Restart sing-box
    print("Restarting sing-box service on the router...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("✅ Configuration updated and service restarted successfully!")

    # 5. Verify the route
    print("\nRunning verification test...")
    test_host = domain.lstrip("*.")
    # Check DNS resolution detour or routing on the router
    test_cmd = f"curl -I -s -m 5 -w '%{{http_code}}' -o /dev/null https://{test_host}"
    try:
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", test_cmd]
        res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        code = res.stdout.strip()
        print(f"Test connection to https://{test_host} status code: {code}")
        if code in ["200", "301", "302", "403", "404"]:
            print("🎉 Success! The site is reachable directly from the router.")
        else:
            print("⚠️ Host returned an unexpected or empty status. Check connectivity.")
    except Exception as e:
        print(f"Verification test failed: {e}")

if __name__ == "__main__":
    main()
