#!/bin/sh

echo "=========================================================="
echo "    Deploying Lightweight SSH Tunnels & config.json Fix    "
echo "=========================================================="

# 1. Stop sing-box service during deployment
echo "[*] Stopping sing-box service..."
/etc/init.d/sing-box stop 2>/dev/null || true

# 2. Update /etc/sing-box/config.json to revert SSH outbounds back to SOCKS
echo "[*] Restoring SOCKS tunnel outbounds in config.json..."
python3 -c '
import json
config_path = "/etc/sing-box/config.json"
try:
    with open(config_path, "r") as f:
        config = json.load(f)
    
    tunnels = {
        "tunnel-zitel": {"type": "socks", "tag": "tunnel-zitel", "server": "127.0.0.1", "server_port": 1032},
        "tunnel-rightel": {"type": "socks", "tag": "tunnel-rightel", "server": "127.0.0.1", "server_port": 1033},
        "tunnel-mobinnet": {"type": "socks", "tag": "tunnel-mobinnet", "server": "127.0.0.1", "server_port": 1034}
    }
    
    new_outbounds = []
    for o in config.get("outbounds", []):
        tag = o.get("tag")
        if tag in tunnels:
            new_outbounds.append(tunnels[tag])
        else:
            new_outbounds.append(o)
    config["outbounds"] = new_outbounds
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("    Successfully updated config.json outbounds to SOCKS")
except Exception as e:
    print("    Error updating config.json: " + str(e))
'

# 3. Create the /etc/init.d/holocron_ssh service script
echo "[*] Writing /etc/init.d/holocron_ssh service script..."
cat << 'EOF' > /etc/init.d/holocron_ssh
#!/bin/sh /etc/rc.common

USE_PROCD=1
START=95
STOP=10

start_service() {
    # Tunnel 1: Zitel (wan) -> Port 1032
    local_ip1=$(ip -o -4 addr show dev wan 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    procd_open_instance "tunnel_zitel"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip1:+-o BindAddress=$local_ip1} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1032 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 2: RighTel (lan3) -> Port 1033
    local_ip2=$(ip -o -4 addr show dev lan3 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    procd_open_instance "tunnel_rightel"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip2:+-o BindAddress=$local_ip2} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1033 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance

    # Tunnel 3: Mobinnet (lan1) -> Port 1034
    local_ip3=$(ip -o -4 addr show dev lan1 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    procd_open_instance "tunnel_mobinnet"
    procd_set_param command /usr/bin/ssh -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes ${local_ip3:+-o BindAddress=$local_ip3} -i /root/.ssh/id_rsa_tunnel -D 0.0.0.0:1034 ubuntu@34.244.201.246
    procd_set_param respawn 3600 10 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}

service_started() {
    echo "Holocron SSH Tunnels started successfully."
}
EOF

# 4. Make the init script executable
chmod +x /etc/init.d/holocron_ssh

# 5. Enable and start the new SSH service
echo "[*] Enabling and starting holocron_ssh service..."
/etc/init.d/holocron_ssh enable
/etc/init.d/holocron_ssh restart

# 6. Verify config.json compatibility
echo "[*] Checking config compatibility with sing-box..."
sing-box check -c /etc/sing-box/config.json

# 7. Start sing-box service
echo "[*] Starting sing-box service..."
/etc/init.d/sing-box start

echo "[*] Checking running services..."
sleep 2
echo "--- Running SSH clients ---"
ps | grep -v grep | grep ssh
echo "---------------------------"
echo "--- Uptime and load average ---"
uptime
echo "---------------------------"
echo "Deployment completed!"
