#!/bin/bash
#
# Fix Passwall2 Shunt Rule - Create proper routing rule
# Version: 1.0
# Date: 2025-11-16

OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"

echo "INFO: Connecting to OpenWrt router..."

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Removing incorrect shunt node...\"
# Remove the wrong shunt_iran node
uci delete passwall2.shunt_iran 2>/dev/null || true

# Reset tcp/udp nodes to SSH tunnel
SSH_NODE=\$(uci show passwall2 | grep \"remarks='SSH-Tunnel-EC2-1'\" | cut -d. -f2 | cut -d= -f1 | head -n1)

if [ -n \"\$SSH_NODE\" ]; then
    uci set passwall2.@global[0].tcp_node=\"\$SSH_NODE\"
    uci set passwall2.@global[0].udp_node=\"\$SSH_NODE\"
    echo \"INFO: Reset main node to: \$SSH_NODE\"
fi

echo \"INFO: Creating proper shunt_rules for Iranian direct routing...\"

# Create Iranian direct routing rule
IRAN_SHUNT=\"iran_direct\"
uci set passwall2.\${IRAN_SHUNT}=shunt_rules
uci set passwall2.\${IRAN_SHUNT}.remarks='Iranian Direct Route'
uci set passwall2.\${IRAN_SHUNT}.network='tcp,udp'
uci set passwall2.\${IRAN_SHUNT}.domain_list='geosite:ir,geosite:category-ir'
uci set passwall2.\${IRAN_SHUNT}.ip_list='geoip:ir'
uci set passwall2.\${IRAN_SHUNT}.node_type='_direct'

echo \"INFO: Shunt rule 'iran_direct' created\"

# Commit changes
uci commit passwall2

echo \"INFO: Restarting Passwall2...\"
/etc/init.d/passwall2 restart

echo \"SUCCESS: Proper shunt rule configured!\"
echo \"\"
echo \"Configuration:\"
echo \"  - Rule name: iran_direct\"
echo \"  - Iranian IPs (geoip:ir): Direct\"
echo \"  - Iranian domains (geosite:ir): Direct\"
echo \"  - All other traffic: Via \$SSH_NODE\"
"

echo ""
echo "=========================================="
echo "✅ SHUNT RULE FIXED!"
echo "=========================================="
echo ""
echo "The rule is now visible in:"
echo "  Passwall2 → Rule Manage → Sing-Box/Xray Shunt Rule"
echo ""
echo "Verify with:"
echo "  ssh ${OPENWRT_HOST} 'uci show passwall2.iran_direct'"
echo ""
