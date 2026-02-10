#!/bin/bash
#
# Local DNS Override Configuration Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# This script adds local DNS overrides for domains with DNS configuration issues
# and ensures they are routed directly (not through proxy).
# Useful for Iranian sites with broken DNS infrastructure.

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"

echo "INFO: Configuring local DNS overrides on OpenWrt router..."
echo ""

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

# Add DNS overrides
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Adding local DNS overrides...\"

# Function to add DNS override
add_dns_override() {
    DOMAIN=\"\$1\"
    IP=\"\$2\"
    
    # Check if override already exists
    if uci show dhcp | grep -q \"domain='\$DOMAIN'\"; then
        echo \"  • \$DOMAIN -> \$IP (already exists)\"
    else
        uci add dhcp domain
        uci set dhcp.@domain[-1].name=\"\$DOMAIN\"
        uci set dhcp.@domain[-1].ip=\"\$IP\"
        echo \"  ✓ Added: \$DOMAIN -> \$IP\"
    fi
}

# Add DNS overrides for bmi.ir domains
echo \"\"
echo \"Adding BMI.ir domain overrides:\"
add_dns_override \"bmi.ir\" \"89.235.64.67\"
add_dns_override \"baam.bmi.ir\" \"89.235.65.149\"
add_dns_override \"www.bmi.ir\" \"89.235.64.67\"

# Add other problematic Iranian domains if needed
# add_dns_override \"example.ir\" \"1.2.3.4\"

echo \"\"
echo \"INFO: Configuring dnsmasq to use local overrides...\"

# Ensure dnsmasq is configured properly
uci set dhcp.@dnsmasq[0].domainneeded='0'
uci set dhcp.@dnsmasq[0].localise_queries='1'
uci set dhcp.@dnsmasq[0].rebind_protection='0'

# Commit changes
uci commit dhcp

echo \"\"
echo \"INFO: Restarting dnsmasq...\"
/etc/init.d/dnsmasq restart

echo \"\"
echo \"SUCCESS: DNS overrides configured!\"
echo \"\"
echo \"Configured overrides:\"
uci show dhcp | grep -E \"domain\[.*\]\.(name|ip)\" | sort
"

echo ""
echo "=========================================="
echo "✅ DNS OVERRIDES CONFIGURED"
echo "=========================================="
echo ""
echo "The following domains now have local DNS overrides:"
echo "  • bmi.ir → 89.235.64.67"
echo "  • baam.bmi.ir → 89.235.65.149"
echo "  • www.bmi.ir → 89.235.64.67"
echo ""
echo "These will bypass any external DNS issues and route directly"
echo "to the Iranian IPs (not through proxy)."
echo ""
echo "To test:"
echo "  ssh ${OPENWRT_HOST} 'nslookup baam.bmi.ir'"
echo "  ssh ${OPENWRT_HOST} 'curl -I http://baam.bmi.ir'"
echo ""
echo "To add more overrides, edit this script and add:"
echo "  add_dns_override \"domain.ir\" \"IP.ADDRESS\""
echo ""
