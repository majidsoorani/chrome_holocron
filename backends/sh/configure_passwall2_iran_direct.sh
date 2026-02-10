#!/bin/bash
#
# Passwall2 Iranian Direct Routing Configuration Script
# Version: 3.0
# Date: 2025-11-16
#
# PURPOSE:
# This script configures Passwall2 to route all Iranian IPs and domains directly,
# bypassing the proxy tunnels using geoip/geosite databases.
# Uses chocolate4u Iran sing-box rules for accurate Iranian IP/domain detection.
# Creates a shunt node that uses the iranian direct shunt rule.

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
GEOIP_URL="https://cdn.jsdelivr.net/gh/chocolate4u/Iran-sing-box-rules@release/geoip.db"
GEOSITE_URL="https://cdn.jsdelivr.net/gh/chocolate4u/Iran-sing-box-rules@release/geosite.db"

echo "INFO: Connecting to OpenWrt router at ${OPENWRT_HOST}..."

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

echo "SUCCESS: Connected to OpenWrt router."
echo "INFO: Configuring Passwall2 for Iranian direct routing..."

# Configure Passwall2
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Checking for geoip/geosite database files...\"

# Check if geoip.db and geosite.db exist
if [ ! -f /usr/share/v2ray/geoip.db ] || [ ! -f /usr/share/v2ray/geosite.db ]; then
    echo \"INFO: Downloading Iranian geoip/geosite databases...\"
    mkdir -p /usr/share/v2ray/
    
    # Download geoip.db
    if [ ! -f /usr/share/v2ray/geoip.db ]; then
        echo \"INFO: Downloading geoip.db...\"
        wget -O /usr/share/v2ray/geoip.db '${GEOIP_URL}' 2>&1 | grep -E '(saved|Downloaded)'
    else
        echo \"INFO: geoip.db already exists\"
    fi
    
    # Download geosite.db
    if [ ! -f /usr/share/v2ray/geosite.db ]; then
        echo \"INFO: Downloading geosite.db...\"
        wget -O /usr/share/v2ray/geosite.db '${GEOSITE_URL}' 2>&1 | grep -E '(saved|Downloaded)'
    else
        echo \"INFO: geosite.db already exists\"
    fi
else
    echo \"INFO: geoip.db and geosite.db already exist at /usr/share/v2ray/\"
fi

# Verify files were created
if [ -f /usr/share/v2ray/geoip.db ] && [ -f /usr/share/v2ray/geosite.db ]; then
    echo \"INFO: Database files ready:\"
    ls -lh /usr/share/v2ray/*.db
else
    echo \"ERROR: Failed to download database files\"
    exit 1
fi

echo \"INFO: Configuring Passwall2...\"

# Find the SSH tunnel node
SSH_NODE=\$(uci show passwall2 | grep \"remarks='SSH-Tunnel-EC2-1'\" | cut -d. -f2 | cut -d= -f1 | head -n1)
if [ -z \"\$SSH_NODE\" ]; then
    echo \"ERROR: SSH tunnel node not found. Please run configure_passwall2_ssh.sh first.\"
    exit 1
fi
echo \"INFO: Found SSH tunnel node: \$SSH_NODE\"

# Create Iranian direct routing shunt rule
echo \"INFO: Creating Iranian direct shunt rule...\"
IRAN_SHUNT=\"iran_direct\"

# Delete if exists
uci delete passwall2.\${IRAN_SHUNT} 2>/dev/null || true

# Create shunt_rules (not nodes)
uci set passwall2.\${IRAN_SHUNT}=shunt_rules
uci set passwall2.\${IRAN_SHUNT}.remarks='Iranian Direct Route'
uci set passwall2.\${IRAN_SHUNT}.network='tcp,udp'
uci set passwall2.\${IRAN_SHUNT}.domain_list='geosite:ir,geosite:category-ir'
uci set passwall2.\${IRAN_SHUNT}.ip_list='geoip:ir'
uci set passwall2.\${IRAN_SHUNT}.node_type='_direct'
uci set passwall2.\${IRAN_SHUNT}.enabled='1'

echo \"INFO: Shunt rule 'iran_direct' created and enabled\"

# Create shunt node that uses the shunt rule
echo \"INFO: Creating shunt node...\"
SHUNT_NODE=\"iran_shunt_node\"

# Delete if exists
uci delete passwall2.\${SHUNT_NODE} 2>/dev/null || true

# Create shunt node
uci set passwall2.\${SHUNT_NODE}=nodes
uci set passwall2.\${SHUNT_NODE}.type='sing-box'
uci set passwall2.\${SHUNT_NODE}.protocol='_shunt'
uci set passwall2.\${SHUNT_NODE}.remarks='Iranian Direct Shunt'
uci set passwall2.\${SHUNT_NODE}.iran_direct='iran_direct'
uci set passwall2.\${SHUNT_NODE}.default_node=\"\$SSH_NODE\"

echo \"INFO: Shunt node 'iran_shunt_node' created\"

# Enable global mode and set shunt node as main node
uci set passwall2.@global[0].enabled='1'
uci set passwall2.@global[0].tcp_proxy_mode='global'
uci set passwall2.@global[0].udp_proxy_mode='global'
uci set passwall2.@global[0].tcp_node=\"\${SHUNT_NODE}\"
uci set passwall2.@global[0].udp_node=\"\${SHUNT_NODE}\"

# Configure DNS settings
uci set passwall2.@global[0].direct_dns_protocol='tcp'
uci set passwall2.@global[0].remote_dns_protocol='tcp'
uci set passwall2.@global[0].remote_dns='8.8.8.8'
uci set passwall2.@global[0].direct_dns='10.202.10.202'

# Enable geoip/geosite usage
uci set passwall2.@global[0].geoip_path='/usr/share/v2ray/geoip.db'
uci set passwall2.@global[0].geosite_path='/usr/share/v2ray/geosite.db'

# Commit all changes
uci commit passwall2

echo \"INFO: Passwall2 configured with GeoIP/GeoSite Iranian routing\"
echo \"INFO: Restarting Passwall2...\"

# Restart Passwall2
/etc/init.d/passwall2 restart

echo \"SUCCESS: Configuration complete!\"
"

echo ""
echo "=========================================="
echo "✅ PASSWALL2 CONFIGURED SUCCESSFULLY!"
echo "=========================================="
echo ""
echo "Configuration Summary:"
echo "  • Iranian IPs: Direct connection (using geoip:ir)"
echo "  • Iranian domains: Direct connection (using geosite:ir)"
echo "  • All other traffic: Routed through SSH tunnel proxy"
echo ""
echo "Database files:"
echo "  • GeoIP: /usr/share/v2ray/geoip.db"
echo "  • GeoSite: /usr/share/v2ray/geosite.db"
echo "  • Source: https://github.com/chocolate4u/Iran-sing-box-rules"
echo ""
echo "To manage Passwall2:"
echo "  Web UI: http://192.168.1.1/cgi-bin/luci/admin/services/passwall2"
echo ""
echo "To verify database files:"
echo "  ssh ${OPENWRT_HOST} 'ls -lh /usr/share/v2ray/*.db'"
echo ""
echo "To test routing:"
echo "  Iranian site: curl -v http://digikala.com"
echo "  Foreign site: curl https://ipinfo.io/ip"
echo ""
