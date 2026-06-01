#!/usr/bin/env python3
import subprocess
import sys

ROUTER_IP = "192.168.1.1"
SSH_USER = "root"

def run_ssh_cmd(cmd_str):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{SSH_USER}@{ROUTER_IP}", cmd_str]
    res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if res.returncode != 0:
        print(f"Error running SSH command: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return res.stdout

def main():
    print("Disabling IPv6 on Router LAN interface...")
    
    # Disable IPv6 assignment on LAN network interface
    run_ssh_cmd("uci set network.lan.ip6assign=''")
    
    # Disable DHCPv6 and Router Advertisements (RA) on LAN
    run_ssh_cmd("uci set dhcp.lan.dhcpv6='disabled'")
    run_ssh_cmd("uci set dhcp.lan.ra='disabled'")
    
    # Delete ndp config if present
    run_ssh_cmd("uci delete dhcp.lan.ndp || true")
    
    # Commit network and dhcp changes
    run_ssh_cmd("uci commit network")
    run_ssh_cmd("uci commit dhcp")
    
    print("Restarting network and dhcp/dns services on OpenWrt...")
    run_ssh_cmd("/etc/init.d/network restart")
    run_ssh_cmd("/etc/init.d/odhcpd restart")
    run_ssh_cmd("/etc/init.d/dnsmasq restart")
    
    print("✅ IPv6 successfully disabled on router LAN interface!")

if __name__ == "__main__":
    main()
