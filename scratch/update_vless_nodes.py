#!/usr/bin/env python3
import json
import subprocess
import sys

ROUTER_IP = "192.168.1.1"
SSH_USER = "root"
CONFIG_PATH = "/etc/sing-box/config.json"

NEW_SERVER = "130.185.120.44"
NEW_PUBLIC_KEY = "-Ph0bs1dPw1q2JPAp6VPNJzfXi6GBBx1rqqY2JZ_pik"
NEW_SHORT_ID = "537cc3ede9252e42"


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

    # 2. Update outbounds
    updated_count = 0
    outbounds = config.get("outbounds", [])
    for outbound in outbounds:
        tag = outbound.get("tag", "")
        # Look for VLESS Reality outbounds
        if outbound.get("type") == "vless" and tag.startswith("vless-reality-"):
            outbound["server"] = NEW_SERVER
            
            if "multiplex" in outbound:
                outbound["multiplex"] = { "enabled": False }
            
            tls = outbound.get("tls", {})
            reality = tls.get("reality", {})
            if reality:
                reality["public_key"] = NEW_PUBLIC_KEY
                # sing-box outbound config uses "short_id"
                reality["short_id"] = NEW_SHORT_ID
                updated_count += 1
                print(f"Updated outbound: {tag}")


    if updated_count == 0:
        print("No matching VLESS outbounds found to update.", file=sys.stderr)
        sys.exit(1)

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
    print("Running verification tests...")
    
    # Test through mixed-in proxy port 1080
    res_google = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w '%{http_code}' https://www.google.com || echo 'Failed'")
    print(f"- Google connection via proxy: {res_google.strip()}")

if __name__ == "__main__":
    main()
