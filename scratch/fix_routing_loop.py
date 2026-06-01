#!/usr/bin/env python3
import json
import subprocess
import sys

ROUTER_IP = "192.168.1.1"
SSH_USER = "root"
CONFIG_PATH = "/etc/sing-box/config.json"
NFT_PATH = "/etc/sing-box/nftables.conf"

def run_ssh_cmd(cmd_str):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", cmd_str]
    res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if res.returncode != 0:
        print(f"Error running SSH command: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return res.stdout

def main():
    # 1. Update /etc/sing-box/nftables.conf on router
    print("Reading nftables.conf from router...")
    nft_content = run_ssh_cmd(f"cat {NFT_PATH}")
    
    if "meta mark 2 return" not in nft_content:
        print("Adding 'meta mark 2 return' to nftables.conf output chain...")
        # We find "meta mark 1 return" and insert "meta mark 2 return" right after it
        lines = nft_content.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if "meta mark 1 return" in line:
                # Keep indentation matching
                indent = line[:line.find("meta mark 1 return")]
                new_lines.append(f"{indent}meta mark 2 return")
        nft_content = "\n".join(new_lines) + "\n"
        
        # Upload updated nftables.conf
        print("Uploading updated nftables.conf...")
        ssh_write_nft = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {NFT_PATH}"]
        subprocess.run(ssh_write_nft, input=nft_content, text=True, check=True)
    else:
        print("nftables.conf already contains mark 2 bypass rule.")

    # 2. Update /etc/sing-box/config.json on router
    print("Reading config.json from router...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    print("Adding 'routing_mark': 2 to outbounds...")
    outbounds = config.get("outbounds", [])
    updated_count = 0
    for outbound in outbounds:
        outbound_type = outbound.get("type")
        if outbound_type in ["direct", "vless", "shadowsocks", "socks"]:
            if outbound.get("routing_mark") != 2:
                outbound["routing_mark"] = 2
                updated_count += 1
                print(f"  Added routing_mark: 2 to outbound: {outbound.get('tag')} ({outbound_type})")

    if updated_count > 0:
        new_config_str = json.dumps(config, indent=2)
        print("Uploading updated config.json...")
        ssh_write_config = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
        subprocess.run(ssh_write_config, input=new_config_str, text=True, check=True)
    else:
        print("All outbounds already have routing_mark: 2.")

    # 3. Reload nftables
    print("Reloading nftables on router...")
    run_ssh_cmd(f"nft -f {NFT_PATH}")
    print("✅ nftables reloaded successfully!")

    # 4. Restart sing-box
    print("Restarting sing-box on router...")
    run_ssh_cmd("/etc/init.d/sing-box restart")
    print("✅ sing-box restarted successfully!")

    # 5. Verify connectivity
    print("\nWaiting 3 seconds for service initialization...")
    run_ssh_cmd("sleep 3")
    
    print("Testing subscription URLs from router (unproxied/direct)...")
    
    # Multiservers
    res_multi = run_ssh_cmd("curl -s -L -m 5 -w '%{http_code}' https://multiservers.info/sub/djMsMzk5NjksMTc3OTA5MDk0MQ155e077304 -o /dev/null || echo 'Failed'")
    print(f"- Multiservers response code: {res_multi.strip()}")
    
    # Zarink
    res_zarink = run_ssh_cmd("curl -s -L -m 5 -w '%{http_code}' https://cmr.zarink.ir/sub/djMsNjY1OCwxNzc5Nzk2ODgx49d5b285c5 -o /dev/null || echo 'Failed'")
    print(f"- Zarink response code: {res_zarink.strip()}")

if __name__ == "__main__":
    main()
