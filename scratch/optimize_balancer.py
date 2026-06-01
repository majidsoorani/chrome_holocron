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

    # 2. Optimize the balancer outbound
    outbounds = config.get("outbounds", [])
    optimized = False
    for outbound in outbounds:
        if outbound.get("tag") == "balancer":
            # Keep ONLY the active native VLESS outbounds
            outbound["outbounds"] = [
                "vless-reality-zitel",
                "vless-reality-rightel",
                "vless-reality-mobinnet"
            ]
            # Speed up the test interval to 1 minute to adapt faster
            outbound["interval"] = "1m"
            # Tighten tolerance to 30ms to choose the absolute best modem
            outbound["tolerance"] = 30
            outbound["interrupt_exist_connections"] = True
            optimized = True
            print("Optimized the 'balancer' outbound pool and test settings.")
            break

    if not optimized:
        print("Could not find the 'balancer' outbound in config.", file=sys.stderr)
        sys.exit(1)

    # 3. Upload configuration
    print("Uploading optimized configuration...")
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
    print("✅ Service restarted successfully and optimized!")

    # 6. Run verification test
    print("\nWaiting 3 seconds for service initialization...")
    run_ssh_cmd("sleep 3")
    print("Running verification test...")
    res_google = run_ssh_cmd("curl -x socks5h://127.0.0.1:1080 -I -s -m 8 -o /dev/null -w 'HTTP Code: %{http_code}, Total Connect Time: %{time_total}s\n' https://www.google.com || echo 'Failed'")
    print(f"- Google connection via optimized balancer: {res_google.strip()}")

if __name__ == "__main__":
    main()
