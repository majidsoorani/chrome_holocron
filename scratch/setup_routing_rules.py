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

    # 2. Re-construct route rules cleanly
    old_rules = config.get("route", {}).get("rules", [])
    
    # Header rules
    header_rules = []
    # Footer rules (direct routes)
    footer_rules = []
    
    for rule in old_rules:
        # Check if it is a header rule (sniff or hijack-dns)
        if rule.get("action") in ["sniff", "hijack-dns"]:
            header_rules.append(rule)
        # Check if it is a direct routing rule
        elif rule.get("outbound") == "direct" or rule.get("ip_is_private") == True:
            # Avoid duplicate direct rules if they match
            if rule not in footer_rules:
                footer_rules.append(rule)

    # Define our custom routing rules
    rightel_domains = [
        "instagram.com",
        "cdninstagram.com",
        "fbcdn.net",
        "github.com",
        "githubusercontent.com",
        "github.io",
        "30nama.com",
        "30nama.ts",
        "30nama.work"
    ]
    
    mobinnet_domains = [
        "youtube.com",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
        "google.com",
        "gmail.com",
        "googleapis.com",
        "gstatic.com"
    ]

    rightel_rule = {
        "domain_suffix": rightel_domains,
        "action": "route",
        "outbound": "vless-reality-rightel"
    }
    
    mobinnet_rule = {
        "domain_suffix": mobinnet_domains,
        "action": "route",
        "outbound": "vless-reality-mobinnet"
    }

    # Combine them in order: Header -> Custom Rules -> Footer (direct bypass)
    new_rules = header_rules + [rightel_rule, mobinnet_rule] + footer_rules
    config["route"]["rules"] = new_rules
    
    # Set fallback to Zitel
    config["route"]["final"] = "vless-reality-zitel"
    
    # Detour remote DNS through Zitel
    dns_servers = config.get("dns", {}).get("servers", [])
    for server in dns_servers:
        if server.get("tag") == "dns-remote":
            server["detour"] = "vless-reality-zitel"
            break

    # 3. Upload new config to router
    print("Uploading updated configuration...")
    new_config_str = json.dumps(config, indent=2)
    ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
    subprocess.run(ssh_write_cmd, input=new_config_str, text=True, check=True)

    # 4. Check configuration validity on router
    print("Verifying configuration validity with sing-box check...")
    check_res = run_ssh_cmd("sing-box check -c /etc/sing-box/config.json 2>&1 || echo 'failed'")
    if "failed" in check_res or "error" in check_res.lower():
        print(f"❌ Configuration check failed:\n{check_res}", file=sys.stderr)
        sys.exit(1)
    print("✅ Configuration is valid!")

    # 5. Restart sing-box
    print("Restarting sing-box service...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("✅ Service restarted successfully!")

    # 6. Verification tests
    print("\nWaiting 3 seconds for service initialization...")
    run_ssh_cmd("sleep 3")
    print("Running verification tests through respective interfaces...")
    
    # Test RighTel domain
    print("Testing Instagram routing (should detour via RighTel)...")
    res_insta = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w '%{http_code}' https://www.instagram.com || echo 'Failed'")
    print(f"- Instagram response code: {res_insta.strip()}")
    
    # Test Mobinnet domain
    print("Testing YouTube routing (should detour via Mobinnet)...")
    res_yt = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w '%{http_code}' https://www.youtube.com || echo 'Failed'")
    print(f"- YouTube response code: {res_yt.strip()}")
    
    # Test default fallback Zitel
    print("Testing general domain routing (should fallback to Zitel)...")
    res_wiki = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w '%{http_code}' https://www.wikipedia.org || echo 'Failed'")
    print(f"- Wikipedia response code: {res_wiki.strip()}")

if __name__ == "__main__":
    main()
