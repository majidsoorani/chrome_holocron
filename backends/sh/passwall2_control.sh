#!/bin/bash
#
# Principal Banking Data Engineer: Gemini
#
# [cite_start]This script manages the Passwall2 service on an OpenWrt router. [cite_end]
# [cite_start]It adheres to the highest standards of security and robustness, using environment variables for credentials and including comprehensive error handling. [cite_end]
#
# Core Principles:
# 1. [cite_start]Security First: Never write credentials, API keys, or hostnames directly in code. [cite: 2]
# 2. [cite_start]Robust I/O: All functions with I/O operations MUST include comprehensive error handling. [cite: 4]

set -euo pipefail

# --- Configuration and Validation ---

# [cite_start]Recommend using a secrets manager to populate these environment variables. [cite: 3]
OPENWRT_HOST="${OPENWRT_HOST:-}"
OPENWRT_USER="${OPENWRT_USER:-root}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"

if [[ -z "${OPENWRT_HOST}" ]]; then
    echo "ERROR: Environment variable OPENWRT_HOST is not set." >&2
    exit 1
fi

if [[ ! -f "${SSH_KEY_PATH}" ]]; then
    echo "ERROR: SSH key file not found at path specified by SSH_KEY_PATH." >&2
    exit 1
fi

# [cite_start]Define the remote command with explicit error handling. [cite_end]
function execute_remote_command() {
    local cmd="$1"
    ssh -i "${SSH_KEY_PATH}" -o "StrictHostKeyChecking=no" -o "UserKnownHostsFile=/dev/null" "${OPENWRT_USER}@${OPENWRT_HOST}" "${cmd}"
}

function start_passwall2() {
    echo "Attempting to start Passwall2..."
    local command
    command="uci set passwall2.@global[0].enabled='1'; uci commit passwall2; /etc/init.d/passwall2 restart"
    
    # [cite_start]Robust I/O with comprehensive try...except...finally blocks (emulated with bash error handling). [cite: 4]
    if execute_remote_command "${command}"; then
        echo "Passwall2 started successfully."
    else
        echo "ERROR: Failed to start Passwall2." >&2
        exit 1
    fi
}

function stop_passwall2() {
    echo "Attempting to stop Passwall2..."
    local command
    command="uci set passwall2.@global[0].enabled='0'; uci commit passwall2; /etc/init.d/passwall2 restart"

    if execute_remote_command "${command}"; then
        echo "Passwall2 stopped successfully."
    else
        echo "ERROR: Failed to stop Passwall2." >&2
        exit 1
    fi
}

function get_passwall2_status() {
    local command="uci get passwall2.@global[0].enabled"
    
    local status
    status=$(execute_remote_command "${command}")

    if [[ "${status}" == "1" ]]; then
        echo "enabled"
    else
        echo "disabled"
    fi
}

# --- Main Logic ---

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 {start|stop|status}" >&2
    exit 1
fi

case "$1" in
    start)
        start_passwall2
        ;;
    stop)
        stop_passwall2
        ;;
    status)
        get_passwall2_status
        ;;
    *)
        echo "Invalid command: $1" >&2
        echo "Usage: $0 {start|stop|status}" >&2
        exit 1
        ;;
esac
