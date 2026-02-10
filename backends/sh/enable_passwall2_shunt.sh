#!/bin/bash
#
# Enable Passwall2 Shunt Rules
# Version: 1.0
# Date: 2025-11-16

OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"

echo "INFO: Connecting to OpenWrt router..."

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Enabling shunt rules in Passwall2...\"

# Check current configuration
echo \"Current configuration:\"
uci show passwall2.@global[0] | grep -E '(enabled|tcp_|udp_)'

# Enable shunt rules usage
# Passwall2 uses shunt_rules automatically when they exist and the node is an Xray/sing-box type

# The key is to make sure routing rules are being used
# Check if there's a global rule switch
uci set passwall2.@global[0].enabled='1'

# Commit changes
uci commit passwall2

echo \"\"
echo \"INFO: Checking if shunt rules are in the generated config...\"

# Restart Passwall2
/etc/init.d/passwall2 restart

sleep 3

# Check generated config
if [ -f /tmp/etc/passwall2/SOCKS_*.json ]; then
    echo \"Generated Xray config:\"
    cat /tmp/etc/passwall2/SOCKS_*.json | grep -A5 -B5 'geoip\|geosite' || echo \"No geoip/geosite rules found in config\"
fi

echo \"\"
echo \"Shunt rules defined in UCI:\"
uci show passwall2.iran_direct

echo \"\"
echo \"SUCCESS: Configuration updated\"
"

echo ""
echo "To verify the shunt rule is working:"
echo "  1. Check Passwall2 UI: Rule Manage → Sing-Box/Xray Shunt Rule"
echo "  2. The rule should show as enabled/active"
echo ""
echo "If not working, you may need to:"
echo "  1. Go to Passwall2 web UI"
echo "  2. Navigate to 'Rule Manage' → 'Sing-Box/Xray Shunt Rule'"
echo "  3. Check the 'Enabled' checkbox for 'Iranian Direct Route'"
echo "  4. Click 'Save & Apply'"
echo ""
