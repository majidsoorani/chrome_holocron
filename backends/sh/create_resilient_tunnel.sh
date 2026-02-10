#!/bin/bash
#
# Principal Banking Data Engineer: Standardized Resilient SSH Tunnel Script
# Version: 1.0
# Date: 2025-11-09
#
# PURPOSE:
# This script establishes a persistent and resilient SSH tunnel using autossh.
# It is designed to be run as a service and incorporates modern security
# and reliability best practices.
#
# SECURITY:
# - Placeholders are used for all sensitive values.
# - It is REQUIRED to populate these variables from a secure source,
#   such as a secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager)
#   or environment variables.
# - DO NOT hardcode credentials in this script.

# --- Configuration ---
# Populate these variables from a secure source.
# The user on the remote SSH server.
REMOTE_USER="${SSH_REMOTE_USER:-ubuntu}"

# The public hostname or IP address of the remote SSH server.
REMOTE_HOST="${SSH_REMOTE_HOST:-<YOUR_REMOTE_HOST>}"

# The local port for the SOCKS5 proxy.
SOCKS_PORT="${SOCKS_PORT:-1032}"

# The full, absolute path to the SSH private key.
# IMPORTANT: This key must be configured for passwordless access on the remote host.
SSH_KEY_PATH="${SSH_KEY_PATH:-<PATH_TO_YOUR_SSH_KEY>}"

# The port on which the remote SSH daemon is running.
SSH_PORT="${SSH_REMOTE_PORT:-22}"

# --- Validation ---
if [[ "${REMOTE_HOST}" == "<YOUR_REMOTE_HOST>" ]] || [[ "${SSH_KEY_PATH}" == "<PATH_TO_YOUR_SSH_KEY>" ]]; then
    echo "ERROR: Unconfigured placeholders. Please set SSH_REMOTE_HOST and SSH_KEY_PATH." >&2
    exit 1
fi

if [[ ! -f "${SSH_KEY_PATH}" ]]; then
    echo "ERROR: SSH private key not found at specified path: ${SSH_KEY_PATH}" >&2
    exit 1
fi

# --- Autossh Execution ---
# -M 0: Disables autossh's monitoring port, relying on SSH's internal keep-alive.
# -N: Do not execute a remote command.
# -f: Go to background just before exec'ing ssh.
# -o "ServerAliveInterval=30": Sends a keep-alive message every 30 seconds.
# -o "ServerAliveCountMax=3": Exits if 3 keep-alive messages fail.
# -o "ExitOnForwardFailure=yes": Exits if the tunnel cannot be established.
# -o "ConnectTimeout=10": Timeout for establishing the connection.
# -D ${SOCKS_PORT}: Creates the dynamic SOCKS proxy on the local port.

echo "Starting resilient SSH tunnel to ${REMOTE_HOST}..."

/usr/local/bin/autossh -M 0 -N -f \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -o "ConnectTimeout=10" \
    -i "${SSH_KEY_PATH}" \
    -p "${SSH_PORT}" \
    -D "${SOCKS_PORT}" \
    "${REMOTE_USER}@${REMOTE_HOST}"

# --- Verification ---
# The 'ps' command checks if an autossh process is running for the specified port.
# Note: Due to the -f flag, the exit code of the autossh command itself is not
# immediately available. We verify by checking the process table.
if pgrep -f "autossh -M 0 -N -f.*-D ${SOCKS_PORT}" > /dev/null; then
    echo "SUCCESS: autossh process initiated."
    exit 0
else
    echo "FAILURE: autossh process did not start as expected." >&2
    exit 1
fi
