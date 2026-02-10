#!/bin/bash
#
# Passwall2 Add Shunt Rule for Iranian Direct Routing
# Version: 1.0
# Date: 2025-11-16

OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"

echo "INFO: Connecting to OpenWrt router..."

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Creating shunt rule for Iranian traffic...\"

# Get the SSH tunnel node
SSH_NODE=\$(uci show passwall2 | grep \"remarks='SSH-Tunnel-EC2-1'\" | cut -d. -f2 | cut -d= -f1 | head -n1)

if [ -z \"\$SSH_NODE\" ]; then
    echo \"ERROR: SSH tunnel node not found!\"
    exit 1
fi

echo \"INFO: Using SSH node: \$SSH_NODE\"

# Create a new shunt node
SHUNT_ID=\"shunt_iran\"

# Add the shunt node
uci set passwall2.\${SHUNT_ID}=nodes
uci set passwall2.\${SHUNT_ID}.type='Xray'
uci set passwall2.\${SHUNT_ID}.protocol='_shunt'
uci set passwall2.\${SHUNT_ID}.remarks='Iran Direct Shunt'

# Configure shunt rules
# Direct: Iranian IPs and domains
uci set passwall2.\${SHUNT_ID}.geoip_direct_list='ir'
uci set passwall2.\${SHUNT_ID}.geosite_direct_list='ir,category-ir'

# Proxy: Everything else goes through default node
uci set passwall2.\${SHUNT_ID}.default_node=\"\$SSH_NODE\"

# Commit changes
uci commit passwall2

echo \"INFO: Shunt rule created: \$SHUNT_ID\"

# Set this shunt rule as the main TCP/UDP node
uci set passwall2.@global[0].tcp_node=\"\$SHUNT_ID\"
uci set passwall2.@global[0].udp_node=\"\$SHUNT_ID\"

uci commit passwall2

echo \"INFO: Set shunt rule as main routing node\"
echo \"INFO: Restarting Passwall2...\"

/etc/init.d/passwall2 restart

echo \"SUCCESS: Shunt rule configured!\"
echo \"\"
echo \"Configuration:\"
echo \"  - Iranian IPs/Domains: Direct connection\"
echo \"  - Foreign traffic: Via SSH-Tunnel-EC2-1\"
"

echo ""
echo "✅ Shunt rule created and activated!"
echo ""
echo "Verify with:"
echo "  ssh ${OPENWRT_HOST} 'uci show passwall2.shunt_iran'"
echo ""
