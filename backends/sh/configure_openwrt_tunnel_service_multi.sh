#!/bin/bash
#
# Principal Banking Data Engineer: OpenWrt Multi-Tunnel Service Configuration Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# This script configures multiple persistent, resilient SSH tunnel services on an
# OpenWrt router. It securely copies the necessary SSH key, creates procd-managed
# init scripts for each tunnel, and enables the services.
#
# TUNNELS:
# - Tunnel 1: 34.244.201.246 on SOCKS port 1032
# - Tunnel 2: 52.209.91.248 on SOCKS port 1033

# --- Configuration (Local Machine to Router) ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
# CRITICAL: Set this environment variable to the path of your local private key
OPENWRT_SSH_KEY="${OPENWRT_SSH_KEY:-<PATH_TO_TUNNEL_KEY>}"

# --- Configuration (Router to Tunnel Endpoints) ---
TUNNEL_REMOTE_USER="${TUNNEL_REMOTE_USER:-ubuntu}"
TUNNEL_KEY_PATH_ON_ROUTER="/root/.ssh/id_rsa_tunnel"

# Define tunnel configurations (simple arrays for compatibility)
TUNNEL1_HOST="34.244.201.246"
TUNNEL1_PORT="1032"
TUNNEL1_NAME="tunnel1"
TUNNEL1_REMARKS="SSH-Tunnel-EC2-1"

TUNNEL2_HOST="52.209.91.248"
TUNNEL2_PORT="1033"
TUNNEL2_NAME="tunnel2"
TUNNEL2_REMARKS="SSH-Tunnel-EC2-2"

# --- Validation ---
if [[ -n "${OPENWRT_SSH_KEY}" && -f "${OPENWRT_SSH_KEY}" ]]; then
    echo "INFO: Using SSH key from environment variable: ${OPENWRT_SSH_KEY}"
else
    DEFAULT_KEY_PATH="$HOME/.ssh/id_ed25519"
    echo "INFO: OPENWRT_SSH_KEY not set or invalid. Checking for default key at ${DEFAULT_KEY_PATH}..."
    if [[ -f "${DEFAULT_KEY_PATH}" ]]; then
        OPENWRT_SSH_KEY="${DEFAULT_KEY_PATH}"
        echo "INFO: Found and using default SSH key: ${OPENWRT_SSH_KEY}"
    else
        echo "ERROR: SSH key not found." >&2
        echo "Please either:" >&2
        echo "  1. Set the OPENWRT_SSH_KEY environment variable to the path of your private key, or" >&2
        echo "  2. Place the private key at the default location: ${DEFAULT_KEY_PATH}" >&2
        exit 1
    fi
fi

echo "INFO: Using local key '${OPENWRT_SSH_KEY}' to configure the tunnels."
echo "INFO: Connecting to OpenWrt router at ${OPENWRT_HOST}..."

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

echo "SUCCESS: Connected to OpenWrt router. Proceeding with service configuration..."

# --- Install SSH Key (Once) ---
echo "INFO: Installing SSH key on router..."
cat "${OPENWRT_SSH_KEY}" | ssh "${OPENWRT_USER}@${OPENWRT_HOST}" '
set -e
echo "INFO: [REMOTE] Creating .ssh directory and setting permissions..."
mkdir -p /root/.ssh
chmod 700 /root/.ssh

echo "INFO: [REMOTE] Installing tunnel private key to /root/.ssh/id_rsa_tunnel..."
cat > /root/.ssh/id_rsa_tunnel
chmod 600 /root/.ssh/id_rsa_tunnel
'

# --- Function to Configure a Tunnel ---
configure_tunnel() {
    local tunnel_host="$1"
    local tunnel_port="$2"
    local tunnel_name="$3"
    local tunnel_remarks="$4"
    
    echo ""
    echo "=========================================="
    echo "Configuring ${tunnel_name}: ${tunnel_host}:${tunnel_port}"
    echo "=========================================="
    
    # Create wrapper script
    echo "INFO: Creating wrapper script for ${tunnel_name}..."
    ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "cat > /usr/bin/holocron_${tunnel_name}.sh << 'EOM'
#!/bin/sh
# Use autossh for automatic reconnection
export AUTOSSH_GATETIME=0
export AUTOSSH_PORT=0
exec /usr/sbin/autossh -M 0 -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes -i ${TUNNEL_KEY_PATH_ON_ROUTER} -D 0.0.0.0:${tunnel_port} ${TUNNEL_REMOTE_USER}@${tunnel_host}
EOM
chmod +x /usr/bin/holocron_${tunnel_name}.sh"

    # Create init script
    echo "INFO: Creating init script for ${tunnel_name}..."
    ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "cat > /etc/init.d/holocron_${tunnel_name} << 'EOM'
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=95
STOP=10

start_service() {
    echo \"Starting holocron_${tunnel_name} service with autossh...\"
    procd_open_instance
    procd_set_param command /usr/bin/holocron_${tunnel_name}.sh
    procd_set_param respawn 3600 5 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}

stop_service() {
    echo \"Holocron ${tunnel_name} service stopped.\"
}
EOM
chmod +x /etc/init.d/holocron_${tunnel_name}"

    # Enable and start service
    echo "INFO: Enabling and starting ${tunnel_name} service..."
    ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "/etc/init.d/holocron_${tunnel_name} enable && /etc/init.d/holocron_${tunnel_name} restart"
    
    # Add to Passwall2
    echo "INFO: Adding ${tunnel_name} to Passwall2..."
    ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
    NODE_ID=\"ssh_\$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 8)\"
    uci set passwall2.\${NODE_ID}=nodes
    uci set passwall2.\${NODE_ID}.type='Socks'
    uci set passwall2.\${NODE_ID}.protocol='socks'
    uci set passwall2.\${NODE_ID}.remarks='${tunnel_remarks}'
    uci set passwall2.\${NODE_ID}.address='127.0.0.1'
    uci set passwall2.\${NODE_ID}.port='${tunnel_port}'
    uci set passwall2.\${NODE_ID}.username=''
    uci set passwall2.\${NODE_ID}.password=''
    uci commit passwall2
    echo \"Added Passwall2 node: ${tunnel_remarks} (ID: \${NODE_ID})\"
    "
    
    echo "✅ SUCCESS: ${tunnel_name} configured on port ${tunnel_port}"
}

# --- Configure All Tunnels ---
configure_tunnel "$TUNNEL1_HOST" "$TUNNEL1_PORT" "$TUNNEL1_NAME" "$TUNNEL1_REMARKS"
configure_tunnel "$TUNNEL2_HOST" "$TUNNEL2_PORT" "$TUNNEL2_NAME" "$TUNNEL2_REMARKS"

echo ""
echo "=========================================="
echo "✅ ALL TUNNELS CONFIGURED SUCCESSFULLY!"
echo "=========================================="
echo ""
echo "Tunnel Summary:"
echo "  • Tunnel 1: ${TUNNEL1_HOST} → SOCKS port ${TUNNEL1_PORT}"
echo "  • Tunnel 2: ${TUNNEL2_HOST} → SOCKS port ${TUNNEL2_PORT}"
echo ""
echo "Passwall2 Nodes:"
echo "  • ${TUNNEL1_REMARKS} (127.0.0.1:${TUNNEL1_PORT})"
echo "  • ${TUNNEL2_REMARKS} (127.0.0.1:${TUNNEL2_PORT})"
echo ""
echo "Verify tunnels are running:"
echo "  ssh ${OPENWRT_HOST} 'ps w | grep autossh'"
echo ""
echo "Check logs:"
echo "  ssh ${OPENWRT_HOST} 'logread -f | grep holocron'"
echo ""
echo "Test tunnels:"
echo "  curl -x socks5://192.168.1.1:${TUNNEL1_PORT} https://ipinfo.io/ip"
echo "  curl -x socks5://192.168.1.1:${TUNNEL2_PORT} https://ipinfo.io/ip"
echo ""
