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
    # 1. Fetch current configuration
    print(f"Reading configuration from router ({ROUTER_IP})...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Clean custom rules (remove the RighTel and Mobinnet rule blocks)
    old_rules = config.get("route", {}).get("rules", [])
    new_rules = []
    
    for rule in old_rules:
        # Filter out custom rules targeting rightel/mobinnet specifically
        if rule.get("outbound") in ["vless-reality-rightel", "vless-reality-mobinnet", "tunnel-rightel", "tunnel-mobinnet"]:
            continue
        new_rules.append(rule)
        
    config["route"]["rules"] = new_rules
    
    # 3. Restore final and DNS detour back to "balancer"
    config["route"]["final"] = "balancer"
    
    dns_servers = config.get("dns", {}).get("servers", [])
    for server in dns_servers:
        if server.get("tag") == "dns-remote":
            server["detour"] = "balancer"
            break

    # 4. Upload configuration
    print("Uploading reverted configuration...")
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

    # 7. Verification test
    print("\nWaiting 3 seconds for service initialization...")
    run_ssh_cmd("sleep 3")
    print("Running verification test...")
    res_google = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w '%{http_code}' https://www.google.com || echo 'Failed'")
    print(f"- Google connection via balancer proxy: {res_google.strip()}")

if __name__ == "__main__":
    main()
