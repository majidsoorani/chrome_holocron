#!/bin/bash
#
# Passwall2 SSH Tunnel Integration Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# This script adds the SSH tunnel (running via autossh) as a SOCKS5 node in Passwall2.
# This allows Passwall2 to use the SSH tunnel alongside other proxy methods.

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
TUNNEL_SOCKS_PORT="${TUNNEL_SOCKS_PORT:-1032}"
NODE_REMARKS="${NODE_REMARKS:-SSH-Tunnel-EC2}"

echo "INFO: Connecting to OpenWrt router at ${OPENWRT_HOST}..."

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

echo "SUCCESS: Connected to OpenWrt router."
echo "INFO: Adding SSH tunnel as SOCKS5 node to Passwall2..."

# Add SSH tunnel as a SOCKS5 node in Passwall2
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
# Generate a unique node ID
NODE_ID=\"ssh_\$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 8)\"

# Add the SOCKS5 node configuration
uci set passwall2.\${NODE_ID}=nodes
uci set passwall2.\${NODE_ID}.type='Socks'
uci set passwall2.\${NODE_ID}.protocol='socks'
uci set passwall2.\${NODE_ID}.remarks='${NODE_REMARKS}'
uci set passwall2.\${NODE_ID}.address='127.0.0.1'
uci set passwall2.\${NODE_ID}.port='${TUNNEL_SOCKS_PORT}'
uci set passwall2.\${NODE_ID}.username=''
uci set passwall2.\${NODE_ID}.password=''

# Commit the changes
uci commit passwall2

echo \"Node ID: \${NODE_ID}\"
echo \"INFO: SSH tunnel SOCKS5 node added to Passwall2.\"
echo \"INFO: You can now select '${NODE_REMARKS}' in Passwall2 web interface.\"
"

echo ""
echo "✅ SUCCESS: SSH tunnel has been added to Passwall2 as a SOCKS5 node!"
echo ""
echo "Next steps:"
echo "1. Open Passwall2 web interface: http://192.168.1.1/cgi-bin/luci/admin/services/passwall2"
echo "2. Go to 'Node List' and you'll see '${NODE_REMARKS}'"
echo "3. Select it as your active node or use it in ACL rules"
echo ""
echo "To verify the tunnel is running:"
echo "  ssh ${OPENWRT_HOST} 'ps w | grep autossh'"
echo ""
