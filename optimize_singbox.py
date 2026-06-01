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
    print("==========================================================")
    # 1. Update MTU on router using UCI
    print("[*] Setting MTU to 1280 on RighTel and Mobinnet interfaces...")
    run_ssh_cmd("uci set network.RighTel.mtu='1280'")
    run_ssh_cmd("uci set network.wwan_mobinnet.mtu='1280'")
    run_ssh_cmd("uci commit network")
    print("[*] Restarting router network service (applying MTU)...")
    run_ssh_cmd("/etc/init.d/network restart")

    # 2. Fetch and optimize sing-box config
    print("[*] Fetching config.json from router...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    print("[*] Optimizing VLESS Reality outbound dialer settings...")
    outbounds = config.get("outbounds", [])
    for outbound in outbounds:
        tag = outbound.get("tag", "")
        # Optimize all VLESS reality outbounds
        if outbound.get("type") == "vless" and tag.startswith("vless-reality-"):
            outbound["tcp_fast_open"] = True
            outbound["connect_timeout"] = "5s"
            # Ensure TLS UTLS fingerprint is set to chrome
            tls = outbound.setdefault("tls", {})
            utls = tls.setdefault("utls", {})
            utls["enabled"] = True
            utls["fingerprint"] = "chrome"

    # Write config back
    print("[*] Uploading optimized configuration...")
    new_config_str = json.dumps(config, indent=2)
    ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
    subprocess.run(ssh_write_cmd, input=new_config_str, text=True, check=True)

    # Check validity
    print("[*] Verifying config on router...")
    check_res = run_ssh_cmd("sing-box check -c /etc/sing-box/config.json 2>&1 || echo 'failed'")
    if "failed" in check_res or "error" in check_res.lower():
        print(f"❌ Configuration check failed:\n{check_res}", file=sys.stderr)
        sys.exit(1)

    # 3. Restart sing-box
    print("[*] Restarting sing-box service...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("==========================================================")
    print("✅ Optimization Completed Successfully!")
    print("==========================================================")

if __name__ == "__main__":
    main()
