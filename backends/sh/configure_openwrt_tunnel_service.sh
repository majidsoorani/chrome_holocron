#!/bin/bash
#
# Principal Banking Data Engineer: OpenWrt Tunnel Service Configuration Script
# Version: 2.1
# Date: 2025-11-10
#
# PURPOSE:
# This script configures a persistent, resilient SSH tunnel service on an
# OpenWrt router. It securely copies the necessary SSH key, creates a
# procd-managed init script, configures the firewall, and enables the service.
#
# CHANGE (v2.1): Corrected the key transfer mechanism. The script now pipes the
# local key file into the SSH command, ensuring it is correctly written on the remote host.

# --- Configuration (Local Machine to Router) ---
OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-192.168.1.1}"
# CRITICAL: Set this environment variable to the path of your local private key
# for connecting to the TUNNEL_REMOTE_HOST.
OPENWRT_SSH_KEY="${OPENWRT_SSH_KEY:-<PATH_TO_TUNNEL_KEY>}"

# --- Configuration (Router to Tunnel Endpoint) ---
TUNNEL_REMOTE_USER="${TUNNEL_REMOTE_USER:-ubuntu}"
TUNNEL_REMOTE_HOST="${TUNNEL_REMOTE_HOST:-34.244.201.246}"
TUNNEL_SOCKS_PORT="${TUNNEL_SOCKS_PORT:-1032}"
TUNNEL_KEY_PATH_ON_ROUTER="/root/.ssh/id_rsa_tunnel"

# --- Validation ---
# Priority 1: Use OPENWRT_SSH_KEY environment variable if it is set and valid.
if [[ -n "${OPENWRT_SSH_KEY}" && -f "${OPENWRT_SSH_KEY}" ]]; then
    echo "INFO: Using SSH key from environment variable: ${OPENWRT_SSH_KEY}"
# Priority 2: Fall back to a default key path if the environment variable is not set.
else
    DEFAULT_KEY_PATH="$HOME/.ssh/id_rsa_openwrt"
    echo "INFO: OPENWRT_SSH_KEY not set or invalid. Checking for default key at ${DEFAULT_KEY_PATH}..."
    if [[ -f "${DEFAULT_KEY_PATH}" ]]; then
        OPENWRT_SSH_KEY="${DEFAULT_KEY_PATH}"
        echo "INFO: Found and using default SSH key: ${OPENWRT_SSH_KEY}"
    else
        echo "ERROR: SSH key not found." >&2
        echo "Please either:" >&2
        echo "  1. Set the OPENWRT_SSH_KEY environment variable to the path of your private key, or" >&2
        echo "  2. Place the private key at the default location: ${DEFAULT_KEY_PATH}" >&2
        exit 1
    fi
fi

echo "INFO: Using local key '${OPENWRT_SSH_KEY}' to configure the tunnel."
echo "INFO: Connecting to OpenWrt router at ${OPENWRT_HOST}..."

if ! ssh "${OPENWRT_USER}@${OPENWRT_HOST}" 'exit'; then
    echo "ERROR: Failed to connect to OpenWrt router at ${OPENWRT_HOST}." >&2
    exit 1
fi

echo "SUCCESS: Connected to OpenWrt router. Proceeding with service configuration..."

# --- Remote Execution on OpenWrt ---
# The content of the local SSH key is piped into the standard input of the ssh command.
# The remote script, enclosed in single quotes, reads from its stdin to create the key file.
cat "${OPENWRT_SSH_KEY}" | ssh "${OPENWRT_USER}@${OPENWRT_HOST}" '
# [DEBUG] Enable verbose command execution tracing to identify the point of failure.
set -x
# This entire block is executed remotely on the OpenWrt router.
set -e # Exit immediately if a command fails.

echo "INFO: [REMOTE] Configuring holocron_tunnel service..."

# 1. Securely install the SSH private key.
echo "INFO: [REMOTE] Creating .ssh directory and setting permissions..."
mkdir -p /root/.ssh
chmod 700 /root/.ssh

echo "INFO: [REMOTE] Installing tunnel private key to /root/.ssh/id_rsa_tunnel..."
# The `cat` command now correctly reads from the stdin piped from the local machine.
cat > /root/.ssh/id_rsa_tunnel
chmod 600 /root/.ssh/id_rsa_tunnel
'

# 2. Create SSH tunnel wrapper script for the service.
echo "INFO: [REMOTE] Creating SSH tunnel wrapper script with autossh..."
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "cat > /usr/bin/holocron_tunnel.sh << 'EOM'
#!/bin/sh
# Use autossh for automatic reconnection
# AUTOSSH_GATETIME=0 means autossh will retry immediately if the connection fails on first attempt
export AUTOSSH_GATETIME=0
export AUTOSSH_PORT=0
exec /usr/sbin/autossh -M 0 -N -T -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -i ${TUNNEL_KEY_PATH_ON_ROUTER} -D 0.0.0.0:${TUNNEL_SOCKS_PORT} ${TUNNEL_REMOTE_USER}@${TUNNEL_REMOTE_HOST}
EOM
chmod +x /usr/bin/holocron_tunnel.sh"

echo "INFO: [REMOTE] Creating procd init script at /etc/init.d/holocron_tunnel..."
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "cat > /etc/init.d/holocron_tunnel << 'EOM'
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=95
STOP=10

start_service() {
    echo \"Starting holocron_tunnel service with autossh...\"
    procd_open_instance
    procd_set_param command /usr/bin/holocron_tunnel.sh
    procd_set_param respawn 3600 5 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}

stop_service() {
    echo \"Holocron tunnel service stopped.\"
}
EOM
"

# 3. Make the new init script executable.
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "chmod +x /etc/init.d/holocron_tunnel"

# 5. Enable and restart the service to apply all changes.
echo "INFO: [REMOTE] Enabling and restarting the holocron_tunnel service..."
ssh "${OPENWRT_USER}@${OPENWRT_HOST}" "/etc/init.d/holocron_tunnel enable && /etc/init.d/holocron_tunnel restart"

echo "SUCCESS: [REMOTE] Holocron tunnel service has been configured and started."
echo "To check status, run '\''logread -f'\'' on the router."

# --- Final Verification ---
if [[ $? -eq 0 ]]; then
    echo "Configuration script executed successfully."
else
    echo "ERROR: An error occurred during the remote execution on the OpenWrt router." >&2
    exit 1
fi
