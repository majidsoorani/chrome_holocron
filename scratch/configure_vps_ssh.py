#!/usr/bin/env python3
import json
import subprocess
import sys

ROUTER_IP = "192.168.1.1"
SSH_USER = "root"
CONFIG_PATH = "/etc/sing-box/config.json"
INIT_PATH = "/etc/init.d/holocron_ssh"

def run_ssh_cmd(cmd_str):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", cmd_str]
    res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if res.returncode != 0:
        print(f"Error running SSH command: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return res.stdout

def main():
    print("Updating /etc/init.d/holocron_ssh on the router...")
    
    # Generate the updated service init script content
    init_script_content = """#!/bin/sh /etc/rc.common

USE_PROCD=1
START=95
STOP=10

start_service() {
    # --- Retrieve dynamic local IPs for routing & binding ---
    local_ip1=$(ip -o -4 addr show dev wan 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    local_ip2=$(ip -o -4 addr show dev lan3 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    local_ip3=$(ip -o -4 addr show dev lan1 2>/dev/null | awk '{print $4}' | cut -d/ -f1)

    # --- Setup Policy-Based Routing Rules ---
    # 1. RighTel (lan3) - Route traffic from RighTel IP via RighTel gateway
    if [ -n "$local_ip2" ]; then
        ip rule del from "$local_ip2" table 103 2>/dev/null
        ip rule add from "$local_ip2" table 103
        ip route replace default via 192.168.100.1 dev lan3 table 103
    fi

    # 2. Mobinnet (lan1) - Route traffic from Mobinnet IP via Mobinnet gateway
    if [ -n "$local_ip3" ]; then
        ip rule del from "$local_ip3" table 104 2>/dev/null
        ip rule add from "$local_ip3" table 104
        ip route replace default via 192.168.3.1 dev lan1 table 104
    fi

    # --- Existing EC2-1 SSH Tunnels (34.244.201.246) ---
    
    # Tunnel 1: Zitel (wan) -> Port 1032
    procd_open_instance "tunnel_zitel"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip1:+-o BindAddress=$local_ip1} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1032 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 2: RighTel (lan3) -> Port 1033
    procd_open_instance "tunnel_rightel"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip2:+-o BindAddress=$local_ip2} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1033 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 3: Mobinnet (lan1) -> Port 1034
    procd_open_instance "tunnel_mobinnet"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip3:+-o BindAddress=$local_ip3} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1034 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # --- New VPS SSH Tunnels (130.185.120.44 on backup port 8022) ---

    # Tunnel 4: VPS Zitel (wan) -> Port 1042
    procd_open_instance "tunnel_vps_zitel"
    procd_set_param command /usr/bin/ssh -p 8022 -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip1:+-o BindAddress=$local_ip1} -i /root/.ssh/arvan_deploy_key -D 0.0.0.0:1042 ubuntu@130.185.120.44
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 5: VPS RighTel (lan3) -> Port 1043
    procd_open_instance "tunnel_vps_rightel"
    procd_set_param command /usr/bin/ssh -p 8022 -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip2:+-o BindAddress=$local_ip2} -i /root/.ssh/arvan_deploy_key -D 0.0.0.0:1043 ubuntu@130.185.120.44
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 6: VPS Mobinnet (lan1) -> Port 1044
    procd_open_instance "tunnel_vps_mobinnet"
    procd_set_param command /usr/bin/ssh -p 8022 -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip3:+-o BindAddress=$local_ip3} -i /root/.ssh/arvan_deploy_key -D 0.0.0.0:1044 ubuntu@130.185.120.44
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}

service_started() {
    echo "Holocron SSH Tunnels started successfully."
}
"""
    
    # Upload init script to router
    ssh_write_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {INIT_PATH}"]
    subprocess.run(ssh_write_cmd, input=init_script_content, text=True, check=True)
    run_ssh_cmd(f"chmod +x {INIT_PATH}")
    
    print("Restarting holocron_ssh tunnels service on router...")
    run_ssh_cmd(f"{INIT_PATH} restart")

    print(f"Reading configuration from router ({ROUTER_IP})...")
    config_str = run_ssh_cmd(f"cat {CONFIG_PATH}")
    try:
        config = json.loads(config_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Clean existing outbounds of any remarks keys that might have survived the check failure
    outbounds = config.get("outbounds", [])
    for o in outbounds:
        if "remarks" in o:
            del o["remarks"]

    existing_tags = {o.get("tag") for o in outbounds}

    vps_tunnels = [
        {"type": "socks", "tag": "ssh-vps-zitel", "server": "127.0.0.1", "server_port": 1042},
        {"type": "socks", "tag": "ssh-vps-rightel", "server": "127.0.0.1", "server_port": 1043},
        {"type": "socks", "tag": "ssh-vps-mobinnet", "server": "127.0.0.1", "server_port": 1044}
    ]

    for tunnel in vps_tunnels:
        if tunnel["tag"] not in existing_tags:
            print(f"Adding outbound outbound for {tunnel['tag']}...")
            outbounds.append(tunnel)
    
    # Find balancer and add them to balancer outbounds
    for o in outbounds:
        if o.get("tag") == "balancer" and "outbounds" in o:
            for tunnel in vps_tunnels:
                if tunnel["tag"] not in o["outbounds"]:
                    print(f"Adding {tunnel['tag']} to balancer outbounds...")
                    o["outbounds"].append(tunnel["tag"])
            break

    config["outbounds"] = outbounds

    print("Uploading updated configuration...")
    new_config_str = json.dumps(config, indent=2)
    ssh_write_cmd2 = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", f"cat > {CONFIG_PATH}"]
    subprocess.run(ssh_write_cmd2, input=new_config_str, text=True, check=True)

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
