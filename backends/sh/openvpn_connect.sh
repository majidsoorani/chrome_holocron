#!/bin/bash

# ==============================================================================
# Holocron OpenVPN Tunnel Manager
#
# Description:
# This script starts or stops an OpenVPN tunnel. It receives all connection
# parameters via command-line arguments and uses a lock file to manage the
# tunnel's state.
# ==============================================================================

# --- Helper Functions ---

# Function to find the openvpn executable in common locations
find_openvpn() {
    local openvpn_paths=(
        "/usr/local/sbin/openvpn" # Homebrew on macOS
        "/usr/sbin/openvpn"       # Debian/Ubuntu, CentOS
        "/opt/homebrew/sbin/openvpn" # Homebrew on Apple Silicon
    )
    for path in "${openvpn_paths[@]}"; do
        if [ -x "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    # Fallback to searching in PATH if not found in common locations
    if command -v openvpn >/dev/null 2>&1; then
        command -v openvpn
        return 0
    fi
    return 1
}

start_tunnel() {
    local identifier=""
    local ovpn_content=""

    # --- Argument Parsing ---
    while (( "$#" )); do
      case "$1" in
        --identifier)
          identifier="$2"
          shift 2
          ;;
        --ovpn-content)
          ovpn_content="$2"
          shift 2
          ;;
        *) # Should not happen
          echo "Unknown argument: $1" >&2
          shift
          ;;
      esac
    done

    # --- Pre-flight Checks ---
    if [ -z "$identifier" ]; then
        echo "Error: An identifier must be provided to start the OpenVPN tunnel." >&2
        return 1
    fi
    if [ -z "$ovpn_content" ]; then
        echo "Error: OVPN file content must be provided." >&2
        return 1
    fi

    local lock_file="/tmp/holocron_openvpn_${identifier}.lock"
    local ovpn_config_file="/tmp/holocron_openvpn_${identifier}.ovpn"
    local log_file="/tmp/holocron_openvpn_${identifier}.log"

    if [ -f "$lock_file" ]; then
        PID=$(cat "$lock_file")
        if ps -p "$PID" > /dev/null; then
            echo "✅ OpenVPN tunnel for '$identifier' is already running with PID $PID."
            return 3 # Special exit code for "already running"
        else
            echo "⚠️ Found stale lock file for PID $PID. Removing it."
            rm -f "$lock_file"
        fi
    fi

    # Find openvpn executable
    OPENVPN_PATH=$(find_openvpn)
    if [ -z "$OPENVPN_PATH" ]; then
        echo "❌ Error: 'openvpn' executable not found. Please install OpenVPN." >&2
        return 1
    fi

    # --- Start Tunnel ---
    echo "🚀 Starting OpenVPN tunnel for identifier '$identifier'..."

    # Write the .ovpn content to a temporary file
    echo "$ovpn_content" > "$ovpn_config_file"
    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to write temporary OVPN config file." >&2
        return 1
    fi

    # Start OpenVPN in the background
    # Using --daemon to run it in the background properly
    # Using --log to redirect logs
    # Using --writepid to get the PID
    "$OPENVPN_PATH" --config "$ovpn_config_file" --log "$log_file" --daemon --writepid "$lock_file"

    # Wait a moment to see if the process started correctly
    sleep 2

    if [ ! -f "$lock_file" ]; then
        echo "❌ Error: OpenVPN failed to start. Lock file was not created." >&2
        if [ -f "$log_file" ]; then
            echo "   --- OpenVPN Log ---" >&2
            sed 's/^/   | /' "$log_file" >&2
            echo "   -------------------" >&2
        fi
        rm -f "$ovpn_config_file" # Clean up config
        return 1
    fi

    VPN_PID=$(cat "$lock_file")
    if ! ps -p "$VPN_PID" > /dev/null; then
        echo "❌ Error: OpenVPN process with PID $VPN_PID exited unexpectedly." >&2
        if [ -f "$log_file" ]; then
            echo "   --- OpenVPN Log ---" >&2
            sed 's/^/   | /' "$log_file" >&2
            echo "   -------------------" >&2
        fi
        rm -f "$lock_file" "$ovpn_config_file" # Clean up
        return 1
    fi

    echo "✅ OpenVPN tunnel established successfully with PID $VPN_PID."
    return 0
}

stop_tunnel() {
    local identifier=""

    # --- Argument Parsing ---
    while (( "$#" )); do
      case "$1" in
        --identifier)
          identifier="$2"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done

    if [ -z "$identifier" ]; then
        echo "Error: Identifier must be provided to stop a specific tunnel." >&2
        return 1
    fi

    local lock_file="/tmp/holocron_openvpn_${identifier}.lock"
    local ovpn_config_file="/tmp/holocron_openvpn_${identifier}.ovpn"
    local log_file="/tmp/holocron_openvpn_${identifier}.log"

    if [ ! -f "$lock_file" ]; then
        echo "ℹ️ Tunnel for '$identifier' appears to be stopped already."
        # Clean up any orphaned files just in case
        rm -f "$ovpn_config_file" "$log_file"
        return 0
    fi

    PID_TO_KILL=$(cat "$lock_file")
    if [ -z "$PID_TO_KILL" ]; then
        echo "⚠️ Lock file is empty. Removing it and other orphaned files."
        rm -f "$lock_file" "$ovpn_config_file" "$log_file"
        return 1
    fi

    # Check if the process is actually running
    if ps -p "$PID_TO_KILL" > /dev/null; then
        echo "🛑 Stopping OpenVPN tunnel process with PID $PID_TO_KILL..."
        kill "$PID_TO_KILL"
        # Wait a moment for the process to terminate
        sleep 1
        if ps -p "$PID_TO_KILL" > /dev/null; then
           echo "⚠️ Process $PID_TO_KILL did not terminate gracefully. Forcing kill..."
           kill -9 "$PID_TO_KILL"
        fi
    else
        echo "⚠️ PID $PID_TO_KILL from lock file is not a running process. Cleaning up stale files."
    fi

    # Clean up all associated files
    rm -f "$lock_file" "$ovpn_config_file" "$log_file"
    echo "✅ Tunnel for '$identifier' stopped and resources cleaned up."
}

# --- Main Logic ---
case "$1" in
    start) start_tunnel "${@:2}" ;;
    stop) stop_tunnel "${@:2}" ;;
    *)
      echo "Usage: $0 {start|stop} --identifier <id> --ovpn-content <content>"
      exit 1
      ;;
esac
