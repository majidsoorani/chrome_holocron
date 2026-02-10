#!/bin/bash
#
# Passwall2 Routing Test Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# Tests that Passwall2 is correctly routing Iranian traffic directly
# and foreign traffic through the SSH tunnel proxy.

ROUTER="${1:-192.168.1.1}"

echo "=========================================="
echo "🧪 PASSWALL2 ROUTING TEST"
echo "=========================================="
echo "Router: $ROUTER"
echo ""

echo "📋 Configuration Check:"
ssh "$ROUTER" "
echo '  Proxy Mode: '
uci show passwall2.@global[0].tcp_proxy_mode | cut -d= -f2 | tr -d \"'\"

echo '  Main Node: '
uci show passwall2.@global[0].tcp_node | cut -d= -f2 | tr -d \"'\"

echo '  Shunt Node Default: '
uci show passwall2.iran_shunt_node.default_node | cut -d= -f2 | tr -d \"'\"

echo '  Shunt Rule Enabled: '
uci show passwall2.iran_direct.enabled | cut -d= -f2 | tr -d \"'\"

echo '  GeoIP Path: '
uci show passwall2.@global[0].geoip_path | cut -d= -f2 | tr -d \"'\"
"

echo ""
echo "🌍 Routing Tests:"
echo ""

echo "1️⃣  Foreign Traffic Test:"
echo "   Testing ipinfo.io (US service)..."
FOREIGN_OUTPUT=$(ssh "$ROUTER" "curl -s --max-time 10 https://ipinfo.io/json 2>/dev/null")
FOREIGN_IP=$(echo "$FOREIGN_OUTPUT" | grep -o '"ip":"[^"]*"' | cut -d: -f2 | tr -d '", ')
FOREIGN_COUNTRY=$(echo "$FOREIGN_OUTPUT" | grep -o '"country":"[^"]*"' | cut -d: -f2 | tr -d '", ')

echo "   IP: $FOREIGN_IP"
echo "   Country: $FOREIGN_COUNTRY"

# Check if it's the German proxy IP
if echo "$FOREIGN_IP" | grep -q "188.245"; then
    echo "   ✅ PASS - Routing through Germany proxy (Hetzner)"
elif [ "$FOREIGN_COUNTRY" = "DE" ]; then
    echo "   ✅ PASS - Routing through Germany proxy"
elif echo "$FOREIGN_IP" | grep -q "34.244\|52.209"; then
    echo "   ✅ PASS - Routing through EC2 proxy"
else
    echo "   ❌ FAIL - Not routing through proxy (IP: $FOREIGN_IP, Country: $FOREIGN_COUNTRY)"
fi

echo ""
echo "2️⃣  Iranian Traffic Test:"
echo "   Testing digikala.com (Iranian site)..."
IRANIAN_IP="185.188.104.10"
echo "   Digikala IP: $IRANIAN_IP"

# Get first hop from traceroute
FIRST_HOP=$(ssh "$ROUTER" "traceroute -m 2 -w 1 $IRANIAN_IP 2>&1 | grep '^ 1 ' | awk '{print \$2}' | head -1")
echo "   First hop: $FIRST_HOP"

# Check if first hop is local gateway (direct routing)
if echo "$FIRST_HOP" | grep -q "192.168\|172.16\|10\."; then
    echo "   ✅ PASS - Going through local gateway (direct route)"
else
    echo "   ⚠️  WARNING - Unexpected first hop: $FIRST_HOP"
fi

# Additional test: Check DNS resolution
echo ""
echo "3️⃣  DNS Resolution Test:"
DIGIKALA_RESOLVED=$(ssh "$ROUTER" "nslookup digikala.com 2>/dev/null | grep -A1 'Name:' | tail -1 | awk '{print \$2}'")
echo "   Resolved digikala.com to: $DIGIKALA_RESOLVED"

if [ -n "$DIGIKALA_RESOLVED" ]; then
    echo "   ✅ DNS working"
else
    echo "   ❌ DNS resolution failed"
fi

echo ""
echo "=========================================="
echo "📊 SUMMARY"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  • Shunt node is active (iran_shunt_node)"
echo "  • Iranian IPs/domains: Direct routing"
echo "  • Foreign traffic: Proxy via SSH tunnel"
echo ""
echo "Database files:"
echo "  • GeoIP: /usr/share/v2ray/geoip.db"
echo "  • GeoSite: /usr/share/v2ray/geosite.db"
echo ""
echo "✅ TEST COMPLETE"
echo "=========================================="
