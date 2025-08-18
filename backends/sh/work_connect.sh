#!/bin/bash

# ==============================================================================
# Holocron SSH Tunnel Manager
#
# Description:
# This script automatically starts or stops an SSH tunnel when on a designated
# work Wi-Fi network. It receives all connection parameters via command-line
# arguments and uses a lock file to manage the tunnel's state.
#
# Requirements:
# The script uses 'wdutil' to detect the network, which requires administrator
# privileges. For passwordless use, see the "Passwordless Sudo" section.
# ==============================================================================

# --- Full paths for reliability ---
SSH_PATH="/usr/bin/ssh"
WDUTIL_PATH="/usr/bin/wdutil"

# --- Helper Functions ---
status_tunnels() {
    local identifier="$2"
    if [ -z "$identifier" ]; then
        echo "Error: Identifier must be provided for status check." >&2
        return 1
    fi
    local lock_file="$HOME/.ssh/holocron_tunnel_${identifier}.lock"

    if [ ! -f "$lock_file" ]; then
        echo "Tunnel status: 🔴 Stopped (No lock file found)."
        return 1
    fi

    PID=$(cat "$lock_file")
    if [ -z "$PID" ]; then
        echo "Tunnel status: 🔴 Stopped (Lock file is empty). Cleaning up."
        rm -f "$lock_file"
        return 1
    fi

    # Check if a process with PID is an ssh command
    if ps -p "$PID" -o comm= | grep -q "ssh"; then
        echo "Tunnel status: 🟢 Running with PID $PID."
    else
        echo "Tunnel status: 🔴 Stopped (Stale lock file for non-existent PID $PID). Cleaning up."
        rm -f "$lock_file"
    fi
}

start_tunnels() {
    # --- Pre-flight Checks ---
    # --- Argument Parsing ---
    local ssh_user=""
    local ssh_host=""
    local forwards=()
    local socks_port=""
    local identifier=""
    local work_ssids=()
    local remote_command=""

    while (( "$#" )); do
      case "$1" in
        --user)
          ssh_user="$2"
          shift 2
          ;;
        --host)
          ssh_host="$2"
          shift 2
          ;;
        --identifier)
          identifier="$2"
          shift 2
          ;;
        --remote-command)
          remote_command="$2"
          shift 2
          ;;
        --ssid)
          work_ssids+=("$2")
          shift 2
          ;;
        -L|-D|-R)
          forwards+=("$1" "$2")
          if [ "$1" == "-D" ]; then
            socks_port="$2"
          fi
          shift 2
          ;;
        *) # Should not happen if called from native host
          shift
          ;;
      esac
    done

    # --- Pre-flight Checks ---
    if [ -z "$identifier" ]; then
        echo "Error: An identifier must be provided to start a tunnel." >&2
        return 1
    fi
    local lock_file="$HOME/.ssh/holocron_tunnel_${identifier}.lock"
    if [ -f "$lock_file" ]; then
        PID=$(cat "$lock_file")
        if ps -p "$PID" > /dev/null; then
            echo "✅ Tunnel for '$identifier' is already running with PID $PID. No action needed."
            return 3 # Special exit code for "already running"
        else
            echo "⚠️ Found stale lock file for PID $PID. Removing it."
            rm -f "$lock_file"
        fi
    fi

    # --- SSID Detection (Optional) ---
    # If work SSIDs are configured, check if we are on one of them.
    # If no SSIDs are configured, the check is skipped, allowing manual connection from any network.
    if [ ${#work_ssids[@]} -gt 0 ]; then
        echo "ℹ️ Work Wi-Fi networks configured. Checking current network..."
        # Use `sudo` with `wdutil` as it requires elevated privileges.
        CURRENT_SSID=$(sudo "$WDUTIL_PATH" info 2>/dev/null | grep -w 'SSID' | awk '{print $3}')

        if [ -z "$CURRENT_SSID" ]; then
            echo "⚠️ Warning: Could not determine current Wi-Fi SSID (e.g., on a wired connection)." >&2
            echo "   Since work networks are configured, the connection will not start automatically." >&2
            return 2 # Condition not met, as we can't verify the SSID.
        fi

        is_work_network=false
        for ssid in "${work_ssids[@]}"; do
            if [[ "$ssid" == "$CURRENT_SSID" ]]; then
                is_work_network=true
                break
            fi
        done

        if ! $is_work_network; then
            echo "ℹ️ Not on a configured work Wi-Fi network ('$CURRENT_SSID'). Tunnel not started."
            return 2 # Special exit code for "condition not met"
        fi
    else
        echo "ℹ️ No work Wi-Fi networks configured. Skipping SSID check."
    fi

    # Define a per-connection log file for live logging in the UI
    local log_file="/tmp/holocron_ssh_${identifier}.log"
    # Clear previous log for this identifier to ensure a fresh log for each attempt.
    >"$log_file"

    # --- Start Tunnel ---
    echo "🚀 Starting SSH tunnel..."
    local final_ssh_args=(
        -v # Use verbose output for better logging in the UI
        -o "ServerAliveInterval=60"
        -o "ExitOnForwardFailure=yes"
    )

    # Use a unique ControlPath to tag the SSH process with the identifier.
    # This is a standard SSH option, and since ControlMaster is 'no' by default,
    # it won't create a socket but will appear in the process's command line,
    # allowing the native host to find it reliably.
    if [ -n "$identifier" ]; then
        final_ssh_args+=(-o "ControlPath=/tmp/holocron.ssh.socket.$identifier")
    fi

    # If no remote command is specified, use -N to prevent shell allocation.
    if [ -z "$remote_command" ]; then
        final_ssh_args+=(-N)
    fi

    # Add dynamic forwards
    for ((i=0; i<${#forwards[@]}; i+=2)); do
        final_ssh_args+=("${forwards[i]}" "${forwards[i+1]}")
    done
    final_ssh_args+=("${ssh_user}@${ssh_host}")

    # Start SSH in the background, redirecting its output to /dev/null
    # Capture all SSH output to the per-connection log file for live viewing.
    if [ -n "$remote_command" ]; then
        # If a remote command exists, it must be the last argument.
        "${SSH_PATH}" "${final_ssh_args[@]}" "$remote_command" > "$log_file" 2>&1 &
    else
        "${SSH_PATH}" "${final_ssh_args[@]}" > "$log_file" 2>&1 &
    fi
    SSH_PID=$!

    # Ensure the directory for the lock file exists before writing to it.
    mkdir -p "$(dirname "$LOCK_FILE")"
    echo "$SSH_PID" > "$lock_file"

    # Wait for the SOCKS port to become available before declaring success.
    if [ -z "$socks_port" ]; then
        echo "✅ Tunnel process started with PID $SSH_PID (no SOCKS port to check)."
        return 0
    fi

    echo "⏳ Waiting for SOCKS proxy on port $socks_port to become available..."
    for i in {1..10}; do # Wait for up to 10 seconds
        # Use nc (netcat) to check the port. -z is for zero-I/O mode (port scanning)
        if nc -z 127.0.0.1 "$socks_port" 2>/dev/null; then
            echo "✅ Tunnel established successfully with PID $SSH_PID."
            # List all forwards for user confirmation
            for ((i=0; i<${#forwards[@]}; i+=2)); do
                type_flag="${forwards[i]}"
                rule="${forwards[i+1]}"
                echo "   - Forward (${type_flag}): ${rule}"
            done
            return 0 # Success
        fi

        # Check if the ssh process died prematurely
        if ! ps -p "$SSH_PID" > /dev/null; then
            echo "❌ Error: SSH process with PID $SSH_PID failed to start or exited unexpectedly." >&2
            echo "   --- SSH Connection Log (from ${log_file}) ---" >&2
            # Indent the output for readability
            sed 's/^/   | /' "$log_file" >&2
            echo "   --------------------------" >&2
            rm -f "$lock_file"
            return 1
        fi
        sleep 1
    done

    # If the loop finishes, the port never became available. Capture the error.
    echo "❌ Error: Timed out waiting for the SOCKS proxy on port $socks_port." >&2
    echo "   The SSH process (PID $SSH_PID) is running, but the port is not responding." >&2
    echo "   The SSH process may have printed errors. Check its log at ${log_file} for details." >&2
    echo "   Stopping the new SSH process to clean up." >&2
    kill "$SSH_PID"
    rm -f "$lock_file"
    return 1
}

stop_tunnels() {
    local identifier=""
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
    local lock_file="$HOME/.ssh/holocron_tunnel_${identifier}.lock"

    if [ ! -f "$lock_file" ]; then
        echo "ℹ️ Tunnel for '$identifier' appears to be stopped already."
        return 0
    fi

    PID_TO_KILL=$(cat "$lock_file")
    if [ -z "$PID_TO_KILL" ]; then
        echo "⚠️ Lock file is empty. Removing it."
        rm -f "$lock_file"
        return 1
    fi

    if ps -p "$PID_TO_KILL" -o comm= | grep -q "ssh"; then
        echo "🛑 Stopping tunnel process with PID $PID_TO_KILL..."
        kill "$PID_TO_KILL"
        rm -f "$lock_file"
        echo "✅ Tunnel stopped."
    else
        echo "⚠️ PID $PID_TO_KILL from lock file is not a running SSH process. Removing stale lock file."
        rm -f "$lock_file"
    fi
}

restart_tunnels() {
    echo "🔄 Restarting tunnel..."
    stop_tunnels
    sleep 1 # Give a moment for ports to be released
    start_tunnels "$@"
}

# --- Main Logic ---
case "$1" in
    start) start_tunnels "${@:2}" ;;
    stop) stop_tunnels "${@:2}" ;;
    restart) restart_tunnels "${@:2}" ;;
    *)
      echo "Usage: $0 {start|stop|restart} --identifier <id> ..."
      exit 1
      ;;
esac