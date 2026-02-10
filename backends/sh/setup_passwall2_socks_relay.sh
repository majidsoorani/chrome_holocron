#!/bin/bash
#
# Passwall2 SOCKS Relay Setup Script
# Version: 1.0
# Date: 2025-11-16
#
# PURPOSE:
# Creates a socat relay to expose Passwall2's localhost-only SOCKS proxy
# to the LAN, so the Chrome extension can connect to it.

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
LOCAL_SOCKS_PORT="1080"
PUBLIC_SOCKS_PORT="1090"

echo "INFO: Setting up SOCKS proxy relay on OpenWrt router..."
echo ""

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "
set -e

echo 'INFO: Installing socat if not present...'
if ! which socat >/dev/null 2>&1; then
    opkg update
    opkg install socat
    echo '  ✓ socat installed'
else
    echo '  ✓ socat already installed'
fi

echo ''
echo 'INFO: Creating SOCKS relay service...'

# Create relay script
cat > /usr/bin/passwall2_socks_relay.sh << 'RELAY_EOF'
#!/bin/sh
# Relay Passwall2 SOCKS proxy from 127.0.0.1:${LOCAL_SOCKS_PORT} to 0.0.0.0:${PUBLIC_SOCKS_PORT}
exec socat TCP-LISTEN:${PUBLIC_SOCKS_PORT},fork,reuseaddr TCP:127.0.0.1:${LOCAL_SOCKS_PORT}
RELAY_EOF

chmod +x /usr/bin/passwall2_socks_relay.sh

# Create procd service
cat > /etc/init.d/passwall2_socks_relay << 'SERVICE_EOF'
#!/bin/sh /etc/rc.common

START=99
STOP=10

USE_PROCD=1

start_service() {
    procd_open_instance
    procd_set_param command /usr/bin/passwall2_socks_relay.sh
    procd_set_param respawn \${respawn_threshold:-3600} \${respawn_timeout:-5} \${respawn_retry:-5}
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
SERVICE_EOF

chmod +x /etc/init.d/passwall2_socks_relay

echo '  ✓ Relay service created'

echo ''
echo 'INFO: Enabling and starting relay service...'
/etc/init.d/passwall2_socks_relay enable
/etc/init.d/passwall2_socks_relay start

sleep 2

echo ''
echo 'INFO: Checking relay status...'
if netstat -tlnp | grep ':${PUBLIC_SOCKS_PORT} '; then
    echo '  ✅ Relay is running!'
else
    echo '  ❌ Relay failed to start'
    ps w | grep socat
fi

echo ''
echo 'SUCCESS: SOCKS relay configured!'
"

echo ""
echo "=========================================="
echo "✅ SOCKS PROXY RELAY ACTIVE"
echo "=========================================="
echo ""
echo "Passwall2 SOCKS proxy is now accessible on LAN:"
echo "  • Internal: 127.0.0.1:${LOCAL_SOCKS_PORT} (Passwall2)"
echo "  • External: ${OPENWRT_HOST}:${PUBLIC_SOCKS_PORT} (Relay)"
echo ""
echo "Chrome Extension Settings:"
echo "  • Proxy Type: SOCKS5"
echo "  • Host: ${OPENWRT_HOST}"
echo "  • Port: ${PUBLIC_SOCKS_PORT}"
echo ""
echo "To test from your Mac:"
echo "  curl -x socks5h://${OPENWRT_HOST}:${PUBLIC_SOCKS_PORT} https://ipinfo.io/ip"
echo ""
echo "Service Management:"
echo "  • Start: ssh ${OPENWRT_HOST} '/etc/init.d/passwall2_socks_relay start'"
echo "  • Stop: ssh ${OPENWRT_HOST} '/etc/init.d/passwall2_socks_relay stop'"
echo "  • Status: ssh ${OPENWRT_HOST} 'netstat -tlnp | grep :${PUBLIC_SOCKS_PORT}'"
echo ""
