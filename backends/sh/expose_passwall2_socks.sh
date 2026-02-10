#!/bin/bash
#
# Expose Passwall2 SOCKS Proxy Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# This script configures Passwall2 to expose its SOCKS proxy on all interfaces
# (not just localhost) so clients on the LAN can use it.
# Also sets up the correct port for the Chrome Holocron extension.

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
SOCKS_PORT="${SOCKS_PORT:-1080}"

echo "INFO: Configuring Passwall2 SOCKS proxy exposure..."
echo ""

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo \"INFO: Current SOCKS configuration:\"
echo \"  Port: \$(uci get passwall2.@global[0].node_socks_port)\"
echo \"  Enabled: \$(uci get passwall2.@global[0].socks_enabled)\"

echo \"\"
echo \"INFO: Updating SOCKS configuration...\"

# Set SOCKS port
uci set passwall2.@global[0].node_socks_port='${SOCKS_PORT}'

# Enable SOCKS
uci set passwall2.@global[0].socks_enabled='1'

# Allow LAN access (bind to 0.0.0.0 instead of 127.0.0.1)
uci set passwall2.@global[0].localhost_proxy='0'

# Enable client proxy mode
uci set passwall2.@global[0].client_proxy='1'

# Commit changes
uci commit passwall2

echo \"\"
echo \"INFO: New SOCKS configuration:\"
echo \"  Port: \$(uci get passwall2.@global[0].node_socks_port)\"
echo \"  Localhost only: \$(uci get passwall2.@global[0].localhost_proxy)\"
echo \"  Client proxy: \$(uci get passwall2.@global[0].client_proxy)\"

echo \"\"
echo \"INFO: Restarting Passwall2...\"
/etc/init.d/passwall2 restart

echo \"\"
echo \"Waiting for service to start...\"
sleep 5

echo \"\"
echo \"INFO: Checking SOCKS proxy status...\"
netstat -tlnp | grep ':${SOCKS_PORT} ' || echo 'WARNING: Port ${SOCKS_PORT} not listening yet'

echo \"\"
echo \"SUCCESS: SOCKS proxy configured!\"
"

echo ""
echo "=========================================="
echo "✅ PASSWALL2 SOCKS PROXY EXPOSED"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  • SOCKS Proxy: ${OPENWRT_HOST}:${SOCKS_PORT}"
echo "  • Access: LAN-wide (not localhost only)"
echo "  • Protocol: SOCKS5"
echo ""
echo "Chrome Extension Settings:"
echo "  • Proxy Type: SOCKS5"
echo "  • Host: ${OPENWRT_HOST}"
echo "  • Port: ${SOCKS_PORT}"
echo ""
echo "To test from your Mac:"
echo "  curl -x socks5h://${OPENWRT_HOST}:${SOCKS_PORT} https://ipinfo.io/ip"
echo ""
echo "To verify proxy is listening:"
echo "  ssh ${OPENWRT_HOST} \"netstat -tlnp | grep :${SOCKS_PORT}\""
echo ""
