#!/bin/bash
#
# Holocron — Enable GatewayPorts on the VPS sshd
# ----------------------------------------------
# Required so that the router's `ssh -R 0.0.0.0:PORT:...` reverse-forward
# actually binds on the VPS public interface (otherwise sshd binds 127.0.0.1
# only and the phone cannot reach the port from the internet).
#
# Run this ONCE on your local machine; it edits /etc/ssh/sshd_config on the VPS.
#
# Usage:
#   VPS_USER=ubuntu VPS_HOST=34.244.201.246 bash backends/sh/setup_vps_gateway_ports.sh
#
set -euo pipefail

VPS_USER="${VPS_USER:-${TUNNEL_REMOTE_USER:-ubuntu}}"
VPS_HOST="${VPS_HOST:-${TUNNEL_REMOTE_HOST:-34.244.201.246}}"

echo "INFO: Connecting to ${VPS_USER}@${VPS_HOST} to enable GatewayPorts..."

ssh "${VPS_USER}@${VPS_HOST}" 'sudo sh -s' <<'REMOTE_EOF'
set -eu
CFG=/etc/ssh/sshd_config
BACKUP="${CFG}.holocron.bak.$(date +%Y%m%d%H%M%S)"

cp "$CFG" "$BACKUP"
echo "INFO: Backed up sshd_config to $BACKUP"

# Remove any existing GatewayPorts directives (commented or not)
sed -i -E '/^[[:space:]]*#?[[:space:]]*GatewayPorts[[:space:]]+.*/d' "$CFG"

# Append the desired setting
printf '\n# Added by Holocron setup_vps_gateway_ports.sh\nGatewayPorts yes\n' >> "$CFG"

# Validate config before restarting
if sshd -t; then
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || service ssh reload
    echo "INFO: sshd reloaded with GatewayPorts yes."
else
    echo "ERROR: sshd config test failed; restoring backup." >&2
    cp "$BACKUP" "$CFG"
    exit 1
fi
REMOTE_EOF

echo "SUCCESS: GatewayPorts is enabled on ${VPS_HOST}."
echo "Reminder: also open the chosen VPS_PORT (default 18388/tcp) in the cloud firewall."
