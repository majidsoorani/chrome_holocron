#!/bin/bash
#
# Holocron — Mobile Shadowsocks via Reverse SSH Tunnel
# ----------------------------------------------------
# PURPOSE
#   Give your phone (e.g. Shadowrocket on iOS) a Shadowsocks endpoint that
#   exits through your HOME Iranian ISP, even though the home router sits
#   behind CGNAT.
#
# ARCHITECTURE
#   Phone ──► VPS_PUBLIC_IP:VPS_PORT ──► (reverse SSH tunnel) ──► OpenWrt
#         (Shadowsocks client)            VPS is a dumb TCP relay         (ss-server on 127.0.0.1)
#                                                                         └─► WAN (home Iran exit)
#
#   • Shadowsocks server runs on the OpenWrt router, bound to 127.0.0.1 only
#     (never exposed directly to the internet).
#   • The router opens an outbound SSH connection to your existing VPS and
#     reverse-forwards (-R) the SS port to a public port on the VPS.
#   • The phone connects to the VPS public IP+port using normal SS creds.
#
# PREREQUISITES
#   • VPS reachable via SSH from the router using the existing tunnel key
#     (/root/.ssh/id_rsa_tunnel installed by configure_openwrt_tunnel_service.sh).
#   • VPS sshd has `GatewayPorts yes` (or `GatewayPorts clientspecified`)
#     — run setup_vps_gateway_ports.sh once on the VPS, or edit by hand.
#   • VPS firewall/security-group allows inbound TCP on VPS_PORT.
#
# USAGE
#   OPENWRT_HOST=192.168.1.1 \
#   TUNNEL_REMOTE_HOST=34.244.201.246 \
#   TUNNEL_REMOTE_USER=ubuntu \
#   VPS_PORT=18388 \
#   SS_LOCAL_PORT=8388 \
#   SS_PASSWORD='change-me-strong-password' \
#   SS_METHOD=chacha20-ietf-poly1305 \
#       bash backends/sh/setup_mobile_shadowsocks.sh
#
set -euo pipefail

# --- Configuration ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"

TUNNEL_REMOTE_USER="${TUNNEL_REMOTE_USER:-ubuntu}"
TUNNEL_REMOTE_HOST="${TUNNEL_REMOTE_HOST:-34.244.201.246}"
TUNNEL_KEY_PATH_ON_ROUTER="${TUNNEL_KEY_PATH_ON_ROUTER:-/root/.ssh/id_rsa_tunnel}"

# Shadowsocks (server-side, on the router, bound to localhost only)
SS_LOCAL_PORT="${SS_LOCAL_PORT:-8388}"
SS_METHOD="${SS_METHOD:-chacha20-ietf-poly1305}"
SS_PASSWORD="${SS_PASSWORD:-}"

# Public port on the VPS that the phone will connect to
VPS_PORT="${VPS_PORT:-18388}"

# Auto-generate a strong password if none provided
if [[ -z "${SS_PASSWORD}" ]]; then
    if command -v openssl >/dev/null 2>&1; then
        SS_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
    else
        SS_PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | cut -c1-24)"
    fi
    echo "INFO: Auto-generated SS_PASSWORD=${SS_PASSWORD}"
fi

echo "INFO: Connecting to OpenWrt router at ${OPENWRT_HOST}..."
if ! ssh -o BatchMode=yes "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Cannot SSH to ${OPENWRT_USER}@${OPENWRT_HOST}. Set up key auth first." >&2
    exit 1
fi

# Export vars for the remote heredoc
export SS_LOCAL_PORT SS_METHOD SS_PASSWORD VPS_PORT \
       TUNNEL_REMOTE_USER TUNNEL_REMOTE_HOST TUNNEL_KEY_PATH_ON_ROUTER

ssh "${OPENWRT_USER}@${OPENWRT_HOST}" \
    "SS_LOCAL_PORT='${SS_LOCAL_PORT}' \
     SS_METHOD='${SS_METHOD}' \
     SS_PASSWORD='${SS_PASSWORD}' \
     VPS_PORT='${VPS_PORT}' \
     TUNNEL_REMOTE_USER='${TUNNEL_REMOTE_USER}' \
     TUNNEL_REMOTE_HOST='${TUNNEL_REMOTE_HOST}' \
     TUNNEL_KEY_PATH_ON_ROUTER='${TUNNEL_KEY_PATH_ON_ROUTER}' \
     sh -s" <<'REMOTE_EOF'
set -eu

echo "INFO: [REMOTE] Installing shadowsocks-libev (ss-server)..."
opkg update >/dev/null 2>&1 || true
# shadowsocks-libev-ss-server is the server-only package; the meta package
# 'shadowsocks-libev-config' is not required since we ship our own JSON.
if ! command -v ss-server >/dev/null 2>&1; then
    opkg install shadowsocks-libev-ss-server || {
        echo "ERROR: Failed to install shadowsocks-libev-ss-server via opkg." >&2
        echo "       If Passwall2 is installed, ss-server may already be present" >&2
        echo "       under /usr/bin/ss-server. Check and re-run." >&2
        exit 1
    }
fi
SS_SERVER_BIN="$(command -v ss-server || echo /usr/bin/ss-server)"
echo "INFO: [REMOTE] Using ss-server at ${SS_SERVER_BIN}"

echo "INFO: [REMOTE] Writing Shadowsocks config..."
mkdir -p /etc/shadowsocks-libev
cat > /etc/shadowsocks-libev/holocron_mobile.json <<JSON
{
    "server": "127.0.0.1",
    "server_port": ${SS_LOCAL_PORT},
    "password": "${SS_PASSWORD}",
    "method": "${SS_METHOD}",
    "timeout": 300,
    "fast_open": false,
    "mode": "tcp_and_udp",
    "no_delay": true
}
JSON
chmod 600 /etc/shadowsocks-libev/holocron_mobile.json

echo "INFO: [REMOTE] Creating ss-server init script..."
cat > /etc/init.d/holocron_ss_server <<'EOM'
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=94
STOP=11

SS_BIN="/usr/bin/ss-server"
SS_CFG="/etc/shadowsocks-libev/holocron_mobile.json"

start_service() {
    [ -x "$SS_BIN" ] || SS_BIN="$(command -v ss-server || echo $SS_BIN)"
    procd_open_instance
    procd_set_param command "$SS_BIN" -c "$SS_CFG" -u
    procd_set_param respawn 3600 5 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
EOM
chmod +x /etc/init.d/holocron_ss_server

echo "INFO: [REMOTE] Creating reverse-tunnel wrapper..."
cat > /usr/bin/holocron_mobile_relay.sh <<EOM
#!/bin/sh
# Reverse-forward the local Shadowsocks port to the VPS public interface.
# 'GatewayPorts yes' must be set in the VPS sshd_config for 0.0.0.0 binding.
export AUTOSSH_GATETIME=0
export AUTOSSH_PORT=0
exec /usr/sbin/autossh -M 0 -N -T \\
    -o StrictHostKeyChecking=no \\
    -o ServerAliveInterval=30 \\
    -o ServerAliveCountMax=3 \\
    -o ExitOnForwardFailure=yes \\
    -o GatewayPorts=yes \\
    -i ${TUNNEL_KEY_PATH_ON_ROUTER} \\
    -R 0.0.0.0:${VPS_PORT}:127.0.0.1:${SS_LOCAL_PORT} \\
    ${TUNNEL_REMOTE_USER}@${TUNNEL_REMOTE_HOST}
EOM
chmod +x /usr/bin/holocron_mobile_relay.sh

echo "INFO: [REMOTE] Creating reverse-tunnel init script..."
cat > /etc/init.d/holocron_mobile_relay <<'EOM'
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=96
STOP=9

start_service() {
    procd_open_instance
    procd_set_param command /usr/bin/holocron_mobile_relay.sh
    procd_set_param respawn 3600 5 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
EOM
chmod +x /etc/init.d/holocron_mobile_relay

echo "INFO: [REMOTE] Enabling and (re)starting services..."
/etc/init.d/holocron_ss_server enable
/etc/init.d/holocron_ss_server restart
/etc/init.d/holocron_mobile_relay enable
/etc/init.d/holocron_mobile_relay restart

sleep 2
echo "INFO: [REMOTE] Status:"
pgrep -af ss-server || echo "  (ss-server not running — check logs)"
pgrep -af autossh   || echo "  (autossh not running — check logs)"
REMOTE_EOF

echo
echo "============================================================"
echo " Mobile Shadowsocks endpoint is ready."
echo "============================================================"
echo " Server (VPS):     ${TUNNEL_REMOTE_HOST}"
echo " Port:             ${VPS_PORT}"
echo " Password:         ${SS_PASSWORD}"
echo " Encryption:       ${SS_METHOD}"
echo " Mode:             tcp_and_udp"
echo
echo " iOS clients: Shadowrocket, Potatso Lite, Outline (TCP only)."
echo
echo " ss:// URI (paste into Shadowrocket → '+' → Type: Shadowsocks → 'Import from clipboard'):"
SS_USERINFO="${SS_METHOD}:${SS_PASSWORD}"
if command -v base64 >/dev/null 2>&1; then
    SS_B64=$(printf '%s' "${SS_USERINFO}" | base64 | tr -d '\n=' | tr '/+' '_-')
    echo "   ss://${SS_B64}@${TUNNEL_REMOTE_HOST}:${VPS_PORT}#Holocron-Home"
fi
echo
echo " Reminders:"
echo "   1. On the VPS, sshd_config must contain: GatewayPorts yes"
echo "      (run setup_vps_gateway_ports.sh once, or edit /etc/ssh/sshd_config)."
echo "   2. Open inbound TCP ${VPS_PORT} in the VPS firewall / cloud security group."
echo "   3. Verify from your phone (off Wi-Fi): connect via Shadowrocket and visit"
echo "      https://ifconfig.me — it should show your home Iran ISP IP."
echo "============================================================"
