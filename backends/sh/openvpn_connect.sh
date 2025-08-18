#!/bin/bash

# ==============================================================================
# Holocron OpenVPN Connector
#
# Description:
# This script starts or stops an OpenVPN connection using a provided
# configuration file. It manages the process using a PID lock file.
# It's designed to be called by the Holocron native host script.
#
# Requirements:
# - openvpn: The OpenVPN client binary.
# - sudo: The script requires sudo to manage network interfaces and run openvpn.
#   Passwordless sudo may be required for the user running the browser.
# ==============================================================================

# --- Configuration ---
# The lock file path should be in a location writable by the user.
# Using a directory inside $HOME/.config/ is a good practice.
CONFIG_DIR="$HOME/.config/holocron"
mkdir -p "$CONFIG_DIR" # Ensure the directory exists
LOCK_FILE="$CONFIG_DIR/openvpn.lock"
LOG_FILE="/tmp/holocron_openvpn_output.log"

# --- Full paths for reliability ---
# Common path on Linux. For macOS (e.g., via Homebrew), it might be /usr/local/sbin/openvpn
OPENVPN_PATH="/usr/sbin/openvpn"
SUDO_PATH="/usr/bin/sudo"

start_vpn() {
    # --- Pre-flight Checks ---
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if [ -n "$PID" ] && ps -p "$PID" > /dev/null; then
            echo "✅ OpenVPN is already running with PID $PID."
            return 3 # Special exit code for "already running"
        else
            echo "⚠️ Found stale lock file. Removing it."
            rm -f "$LOCK_FILE"
        fi
    fi

    # --- Argument Parsing ---
    local config_file=""
    local auth_file=""

    while (( "$#" )); do
      case "$1" in
        --config)
          config_file="$2"
          shift 2
          ;;
        --auth-file)
          auth_file="$2"
          shift 2
          ;;
        *)
          echo "Unknown argument: $1" >&2
          exit 1
          ;;
      esac
    done

    if [ -z "$config_file" ]; then
        echo "❌ Error: --config file path is required." >&2
        return 1
    fi

    # --- Start Tunnel ---
    echo "🚀 Starting OpenVPN tunnel..."
    local openvpn_args=(
        "--config" "$config_file"
        "--daemon" # Run in the background
        "--log" "$LOG_FILE" # Log to a file
        # Note: --writepid is executed by openvpn with root privileges, so it can write anywhere.
        # But for consistency, we're using a file we know we can manage.
        "--writepid" "$LOCK_FILE"
    )

    if [ -n "$auth_file" ]; then
        openvpn_args+=("--auth-user-pass" "$auth_file")
    fi

    # Check if openvpn binary exists
    if [ ! -f "$OPENVPN_PATH" ]; then
        # Fallback for Homebrew on macOS
        if [ -f "/usr/local/sbin/openvpn" ]; then
            OPENVPN_PATH="/usr/local/sbin/openvpn"
        else
            echo "❌ Error: OpenVPN binary not found at $OPENVPN_PATH or /usr/local/sbin/openvpn" >&2
            return 1
        fi
    fi

    "$SUDO_PATH" "$OPENVPN_PATH" "${openvpn_args[@]}"

    # Wait a moment for the PID file to be created by the daemon
    sleep 2

    if [ ! -f "$LOCK_FILE" ] || [ -z "$(cat "$LOCK_FILE")" ]; then
        echo "❌ Error: OpenVPN failed to start. Check the log for details:" >&2
        echo "   $LOG_FILE" >&2
        rm -f "$LOCK_FILE" # Clean up empty lock file
        return 1
    fi

    VPN_PID=$(cat "$LOCK_FILE")
    if ps -p "$VPN_PID" > /dev/null; then
        echo "✅ OpenVPN started successfully with PID $VPN_PID."
        return 0
    else
        echo "❌ Error: OpenVPN process with PID $VPN_PID exited unexpectedly." >&2
        echo "   Check the log for details: $LOG_FILE" >&2
        rm -f "$LOCK_FILE"
        return 1
    fi
}

stop_vpn() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo "ℹ️ OpenVPN appears to be stopped already."
        return 0
    fi

    PID_TO_KILL=$(cat "$LOCK_FILE")
    if [ -z "$PID_TO_KILL" ]; then
        echo "⚠️ Lock file is empty. Removing it."
        rm -f "$LOCK_FILE"
        return 1
    fi

    if ps -p "$PID_TO_KILL" > /dev/null; then
        echo "🛑 Stopping OpenVPN process with PID $PID_TO_KILL..."
        "$SUDO_PATH" kill "$PID_TO_KILL"
        # Wait a moment for the process to terminate
        sleep 2
    else
        echo "⚠️ PID $PID_TO_KILL from lock file is not a running process."
    fi

    # Clean up lock file regardless
    rm -f "$LOCK_FILE"
    echo "✅ OpenVPN stopped."
}


# --- Main Logic ---
case "$1" in
    start) start_vpn "${@:2}" ;;
    stop) stop_vpn ;;
    *)
      echo "Usage: $0 {start|stop}"
      exit 1
      ;;
esac
