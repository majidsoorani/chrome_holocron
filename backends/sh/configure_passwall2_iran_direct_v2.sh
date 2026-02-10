#!/bin/bash
#
# Passwall2 Iranian Direct Routing Configuration Script
# Version: 2.0
# Date: 2025-11-16
#
# PURPOSE:
# This script configures Passwall2 to route all Iranian IPs and domains directly,
# bypassing the proxy tunnels using geoip/geosite databases.
# Uses chocolate4u Iran sing-box rules for accurate Iranian IP/domain detection.

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

# Enable global mode
uci set passwall2.@global[0].enabled='1'
uci set passwall2.@global[0].tcp_proxy_mode='gfwlist'
uci set passwall2.@global[0].udp_proxy_mode='gfwlist'

# Set default TCP and UDP nodes (use one of the SSH tunnels)
SSH_NODE=\$(uci show passwall2 | grep \"remarks='SSH-Tunnel-EC2-1'\" | cut -d. -f2 | cut -d= -f1 | head -n1)
if [ -n \"\$SSH_NODE\" ]; then
    uci set passwall2.@global[0].tcp_node=\"\$SSH_NODE\"
    uci set passwall2.@global[0].udp_node=\"\$SSH_NODE\"
    echo \"INFO: Set default node to SSH-Tunnel-EC2-1 (\$SSH_NODE)\"
else
    echo \"WARNING: SSH tunnel node not found, you'll need to select it manually in the UI\"
fi

# Configure DNS settings
uci set passwall2.@global[0].direct_dns_protocol='tcp'
uci set passwall2.@global[0].remote_dns_protocol='tcp'
uci set passwall2.@global[0].remote_dns='8.8.8.8'
uci set passwall2.@global[0].direct_dns='10.202.10.202'

# Enable geoip/geosite usage
uci set passwall2.@global[0].geoip_path='/usr/share/v2ray/geoip.db'
uci set passwall2.@global[0].geosite_path='/usr/share/v2ray/geosite.db'

# Configure shunt rules for Iranian traffic
SHUNT_RULE=\$(uci show passwall2 | grep \"type='shunt'\" | cut -d. -f2 | cut -d= -f1 | head -n1)

if [ -z \"\$SHUNT_RULE\" ]; then
    SHUNT_RULE=\"shunt_iran\"
    uci set passwall2.\$SHUNT_RULE='shunt'
    echo \"INFO: Created new shunt rule: \$SHUNT_RULE\"
else
    echo \"INFO: Using existing shunt rule: \$SHUNT_RULE\"
fi

# Configure the shunt rule to use geoip:ir and geosite:ir
uci set passwall2.\$SHUNT_RULE.remarks='Iranian Direct Route (GeoIP/GeoSite)'
uci set passwall2.\$SHUNT_RULE.default_node='_default'
uci set passwall2.\$SHUNT_RULE.main_node=\"\$SSH_NODE\"

# Set Iranian geoip to go direct
uci set passwall2.\$SHUNT_RULE.geoip_direct_list='ir'

# Set Iranian geosite domains to go direct  
uci set passwall2.\$SHUNT_RULE.geosite_direct_list='ir'

# Optional: Add some common Iranian domains for fallback
mkdir -p /etc/passwall2/
cat > /etc/passwall2/direct_host << 'EOF'
# Common Iranian domains (fallback)
.ir
.ایران
EOF

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
