#!/bin/bash
#
# Principal Banking Data Engineer Standard:
# File: openwrt_connect.sh
# Directive: Securely connect to the OpenWRT router and execute a command.
# Security: This script uses placeholders for connection details.
#           It is STRONGLY recommended to manage these using a secrets manager
#           or a secure, non-version-controlled environment file.
# Robustness: Includes comprehensive error handling and argument parsing.

# --- Configuration ---
# [Security First] Use placeholders. Do not hardcode credentials.
ROUTER_HOST="${OPENWRT_HOST:-192.168.1.1}"
ROUTER_USER="${OPENWRT_USER:-root}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"

# --- Argument Parsing ---
# If arguments are passed to the script, use them as the command.
# Otherwise, default to 'uname -a' for a simple connection test.
if [ "$#" -gt 0 ]; then
    REMOTE_COMMAND="$@"
    echo "[INFO] Preparing to execute remote command: ${REMOTE_COMMAND}"
else
    REMOTE_COMMAND="uname -a"
    echo "[INFO] No command provided. Performing standard connection test."
fi

echo "[INFO] Connecting to ${ROUTER_USER}@${ROUTER_HOST}..."

# --- Validation ---
if ! [ -f "${SSH_KEY_PATH}" ]; then
    echo "[ERROR] SSH private key not found at: ${SSH_KEY_PATH}" >&2
    echo "[FATAL] Cannot proceed without a valid SSH key. Please configure SSH_KEY_PATH." >&2
    exit 1
fi

echo "[INFO] Using SSH key: ${SSH_KEY_PATH}"

# --- Connection and Execution with Robust I/O ---
# This block functions as a try/catch mechanism.
if ssh -i "${SSH_KEY_PATH}" -o ConnectTimeout=5 -o StrictHostKeyChecking=no "${ROUTER_USER}@${ROUTER_HOST}" "${REMOTE_COMMAND}"; then
    # Success block
    echo "[SUCCESS] Remote command executed successfully."
else
    # Failure block
    echo "[ERROR] SSH command failed for ${ROUTER_USER}@${ROUTER_HOST}." >&2
    echo "[FATAL] Please check network connectivity, SSH key permissions, and router status." >&2
    exit 1
fi

# The 'finally' block is implicit; the script will exit after this point.
exit 0
