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

# --- Configuration ---
LOCK_FILE="$HOME/.ssh/holocron_tunnel.lock"
SSH_LOG_FILE="/tmp/holocron_ssh_output.log" # Temporary log for SSH connection errors

# --- Full paths for reliability ---
SSH_PATH="/usr/bin/ssh"
WDUTIL_PATH="/usr/bin/wdutil"

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
    # --- Pre-flight Checks ---
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if ps -p "$PID" > /dev/null; then
            echo "✅ Tunnel is already running with PID $PID. No action needed."
            return 3 # Special exit code for "already running"
        else
            echo "⚠️ Found stale lock file for PID $PID. Removing it."
            rm -f "$LOCK_FILE"
        fi
    fi

    # --- Argument Parsing ---
    local ssh_user=""
    local ssh_host=""
    local forwards=()
    local socks_port=""
    local identifier=""
    local work_ssids=()

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
        --ssid)
          work_ssids+=("$2")
          shift 2
          ;;
        -L|-D)
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

    # --- Start Tunnel ---
    echo "🚀 Starting SSH tunnel on work network '$CURRENT_SSID'..."
    local final_ssh_args=(
        -N # Do not execute a remote command.
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

    # Add dynamic forwards
    for ((i=0; i<${#forwards[@]}; i+=2)); do
        final_ssh_args+=("${forwards[i]}" "${forwards[i+1]}")
    done
    final_ssh_args+=("${ssh_user}@${ssh_host}")

    # Start SSH in the background, redirecting its output to /dev/null
    # Capture SSH output to a log file for debugging in case of failure.
    "${SSH_PATH}" "${final_ssh_args[@]}" > "$SSH_LOG_FILE" 2>&1 &
    SSH_PID=$!

    # Ensure the directory for the lock file exists before writing to it.
    mkdir -p "$(dirname "$LOCK_FILE")"
    echo "$SSH_PID" > "$LOCK_FILE"

    # Wait for the SOCKS port to become available before declaring success.
    if [ -z "$socks_port" ]; then
        rm -f "$SSH_LOG_FILE" # Clean up log on success
        echo "✅ Tunnel process started with PID $SSH_PID (no SOCKS port to check)."
        return 0
    fi

    echo "⏳ Waiting for SOCKS proxy on port $socks_port to become available..."
    for i in {1..10}; do # Wait for up to 10 seconds
        # Use nc (netcat) to check the port. -z is for zero-I/O mode (port scanning)
        if nc -z 127.0.0.1 "$socks_port" 2>/dev/null; then
            rm -f "$SSH_LOG_FILE" # Clean up log on success
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
            if [ -f "$SSH_LOG_FILE" ]; then
                echo "   --- SSH Connection Log ---" >&2
                # Indent the output for readability
                sed 's/^/   | /' "$SSH_LOG_FILE" >&2
                echo "   --------------------------" >&2
                rm -f "$SSH_LOG_FILE"
            fi
            rm -f "$LOCK_FILE"
            return 1
        fi
        sleep 1
    done

    # If the loop finishes, the port never became available. Capture the error.
    echo "❌ Error: Timed out waiting for the SOCKS proxy on port $socks_port." >&2
    echo "   The SSH process (PID $SSH_PID) is running, but the port is not responding." >&2
    if [ -f "$SSH_LOG_FILE" ]; then
        echo "   The SSH process may have printed errors. Check its log for details." >&2
        # Don't remove the log file in this case, so it can be inspected manually.
    fi
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
    sleep 1 # Give a moment for ports to be released
    start_tunnels "$@"
}

# --- Main Logic ---
case "$1" in
    start) start_tunnels "${@:2}" ;;
    stop) stop_tunnels ;;
    restart) restart_tunnels "${@:2}" ;;
    status) status_tunnels ;;
    *)
      echo "Usage: $0 {start|stop|restart|status}"
      exit 1
      ;;
esac