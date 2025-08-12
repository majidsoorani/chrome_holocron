#!/bin/bash

# ==============================================================================
# SSH Tunnel Manager for Work Networks
#
# Description:
# This script automatically starts or stops an SSH tunnel when on a designated
# work Wi-Fi network. It creates a lock file to manage the tunnel's state.
#
# Requirements:
# The script uses 'wdutil' to detect the network, which requires administrator
# privileges. You will be prompted for your password via `sudo` when starting.
# For automated/passwordless use, see the "Advanced Usage" section below.
#
# Usage:
# ./tunnel.sh {start|stop|restart|status}
# ==============================================================================

# --- Configuration ---
# Add ALL your work Wi-Fi network names (SSIDs) inside the parentheses.
WORK_SSIDS=("X28P-5G-AFC960" "X28-5G-AFC960" "X28-2.4G-552360" "X28-5G-552360" "X28P-2.4G-AFC960" "<redacted>") # <-- EDIT THIS LINE
LOCK_FILE="$HOME/.ssh/holocron_tunnel.lock"

# --- SSH Connection Details (Use environment variables for secrets) ---
# For security best practices, set these in your shell profile (~/.zshrc, etc.)
# Example:
#   export SSH_USER="ubuntu"
#   export SSH_HOST="bastion.example.com"
#   export DB_HOST="your-rds-instance.rds.amazonaws.com"
SSH_USER="${SSH_USER:-ubuntu}"
SSH_HOST="${SSH_HOST:-34.244.201.246}"
DB_HOST="${DB_HOST:-warehouse.cluster-cpmkv4ljjrvu.eu-west-1.rds.amazonaws.com}"

# --- Full paths for reliability ---
SSH_PATH="/usr/bin/ssh"
WDUTIL_PATH="/usr/bin/wdutil"

# --- Advanced Usage: Passwordless Sudo (for automation) ---
# To run this script from an automated service (like launchd) without a password
# prompt, you can allow your user to run wdutil without a password.
# 1. Open the sudoers file by running: `sudo visudo`
# 2. Add this line at the end, replacing 'your_username' with your macOS username:
#    your_username ALL=(ALL) NOPASSWD: /usr/bin/wdutil
# 3. Save and exit. This is a powerful change; be certain of the security implications.

# --- Helper Functions ---
status_tunnels() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo "Tunnel status: 🔴 Stopped (No lock file found)."
        return 1
    fi

    PID=$(cat "$LOCK_FILE")
    if [ -z "$PID" ]; then
        echo "Tunnel status: 🔴 Stopped (Lock file is empty). Cleaning up."
        rm -f "$LOCK_FILE"
        return 1
    fi

    # Check if a process with PID is an ssh command
    if ps -p "$PID" -o comm= | grep -q "ssh"; then
        echo "Tunnel status: 🟢 Running with PID $PID."
    else
        echo "Tunnel status: 🔴 Stopped (Stale lock file for non-existent PID $PID). Cleaning up."
        rm -f "$LOCK_FILE"
    fi
}

start_tunnels() {
    # --- Sudo Pre-check ---
    # Refresh sudo credentials upfront so the password prompt doesn't appear later.
    echo "ℹ️ This script requires admin privileges to check the Wi-Fi network."
    sudo -v
    if [ $? -ne 0 ]; then
      echo "❌ Sudo credentials not provided or incorrect. Aborting." >&2
      return 1
    fi

    # --- Pre-flight Checks ---
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if ps -p "$PID" > /dev/null; then
            echo "✅ Tunnel is already running with PID $PID. No action needed."
            return 0
        else
            echo "⚠️ Found stale lock file for PID $PID. Removing it."
            rm -f "$LOCK_FILE"
        fi
    fi

    # --- SSID Detection ---
    # Use `sudo` with `wdutil` as it requires elevated privileges.
    CURRENT_SSID=$(sudo "$WDUTIL_PATH" info 2>/dev/null | grep -w 'SSID' | awk '{print $3}')

    if [ -z "$CURRENT_SSID" ]; then
        echo "❌ Error: Could not determine current Wi-Fi SSID." >&2
        echo "   Please ensure you are connected to a Wi-Fi network." >&2
        return 1
    fi

    is_work_network=false
    for ssid in "${WORK_SSIDS[@]}"; do
        if [[ "$ssid" == "$CURRENT_SSID" ]]; then
            is_work_network=true
            break
        fi
    done

    if ! $is_work_network; then
        echo "ℹ️ Not on a work Wi-Fi network ('$CURRENT_SSID'). Tunnel not started."
        return 1
    fi

    # --- Start Tunnel ---
    echo "🚀 Starting SSH tunnel on work network '$CURRENT_SSID'..."
    SSH_ARGS=(
        -N # Do not execute a remote command.
        -o "ServerAliveInterval=60"
        -o "ExitOnForwardFailure=yes"
        -L "5434:${DB_HOST}:5432"
        -D "1031"
        "${SSH_USER}@${SSH_HOST}"
    )

    # Start SSH in the background, redirecting its output to /dev/null
    "${SSH_PATH}" "${SSH_ARGS[@]}" > /dev/null 2>&1 &
    SSH_PID=$!

    # Ensure the directory for the lock file exists before writing to it.
    mkdir -p "$(dirname "$LOCK_FILE")"
    echo "$SSH_PID" > "$LOCK_FILE"

    # Wait for the SOCKS port to become available before declaring success.
    # This avoids race conditions where the script finishes before the tunnel is ready.
    echo "⏳ Waiting for SOCKS proxy on port 1031 to become available..."
    for i in {1..10}; do # Wait for up to 10 seconds
        # Use nc (netcat) to check the port. -z is for zero-I/O mode (port scanning)
        if nc -z 127.0.0.1 1031 2>/dev/null; then
            echo "✅ Tunnel established successfully with PID $SSH_PID."
            echo "   - SOCKS Proxy: 127.0.0.1:1031"
            echo "   - DB Tunnel:   localhost:5434 -> ${DB_HOST}:5432"
            return 0 # Success
        fi

        # Check if the ssh process died prematurely
        if ! ps -p "$SSH_PID" > /dev/null; then
            echo "❌ Error: SSH process with PID $SSH_PID failed to start or exited unexpectedly." >&2
            rm -f "$LOCK_FILE"
            return 1
        fi
        sleep 1
    done

    # If the loop finishes, the port never became available.
    echo "❌ Error: Timed out waiting for the SOCKS proxy on port 1031." >&2
    echo "   The SSH process (PID $SSH_PID) is running, but the port is not responding." >&2
    echo "   Stopping the new SSH process to clean up." >&2
    kill "$SSH_PID"
    rm -f "$LOCK_FILE"
    return 1
}

stop_tunnels() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo "ℹ️ Tunnel appears to be stopped already."
        return 0
    fi

    PID_TO_KILL=$(cat "$LOCK_FILE")
    if [ -z "$PID_TO_KILL" ]; then
        echo "⚠️ Lock file is empty. Removing it."
        rm -f "$LOCK_FILE"
        return 1
    fi

    if ps -p "$PID_TO_KILL" -o comm= | grep -q "ssh"; then
        echo "🛑 Stopping tunnel process with PID $PID_TO_KILL..."
        kill "$PID_TO_KILL"
        rm -f "$LOCK_FILE"
        echo "✅ Tunnel stopped."
    else
        echo "⚠️ PID $PID_TO_KILL from lock file is not a running SSH process. Removing stale lock file."
        rm -f "$LOCK_FILE"
    fi
}

restart_tunnels() {
    echo "🔄 Restarting tunnel..."
    stop_tunnels
    sleep 1 # Give a moment for ports to be released.
    start_tunnels
}

# --- Main Logic ---
case "$1" in
    start) start_tunnels ;;
    stop) stop_tunnels ;;
    restart) restart_tunnels ;;
    status) status_tunnels ;;
    *)
      echo "Usage: $0 {start|stop|restart|status}"
      exit 1
      ;;
esac