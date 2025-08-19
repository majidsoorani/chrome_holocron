#!/bin/bash

# --- Configuration ---
SOCKS_PORT="10808" # Default SOCKS port

# --- Helper Functions ---
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

find_xray_executable() {
    # This function robustly finds the 'xray' executable.
    # It's necessary because the script, when launched by Chrome's native host,
    # may not inherit the user's full shell PATH environment, especially on macOS.

    # 1. Use command -v first, as it's the most common case for PATH-configured shells.
    local exec_path
    exec_path=$(command -v xray)
    if [ -n "$exec_path" ] && [ -x "$exec_path" ]; then
        echo "$exec_path"
        return 0
    fi

    # 2. Check common Homebrew paths for macOS, which are often not in the GUI app PATH.
    local common_paths=(
        "/opt/homebrew/bin/xray"  # Apple Silicon Homebrew
        "/usr/local/bin/xray"     # Intel Homebrew / other standard location
    )
    for path in "${common_paths[@]}"; do
        if [ -x "$path" ]; then
            echo "$path"
            return 0
        fi
    done

    return 1 # Not found
}

cleanup() {
    log "Cleaning up temporary files..."
    rm -f "$CONFIG_FILE" "$LOCK_FILE"
}

# --- Command Functions ---
start_tunnel() {
    local XRAY_EXEC
    XRAY_EXEC=$(find_xray_executable)
    if [ -z "$XRAY_EXEC" ]; then
        local error_msg="Error: 'xray' executable not found. Please install Xray-core and ensure it's in your PATH or a standard location (e.g., /opt/homebrew/bin)."
        echo "$error_msg"
        log "$error_msg"
        exit 1
    fi

    if [ -f "$LOCK_FILE" ]; then
        pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null; then
            echo "V2Ray tunnel is already running with PID $pid."
            log "Start command issued, but tunnel already running with PID $pid."
            exit 3 # Special exit code for "already running"
        else
            log "Found stale lock file for PID $pid. Cleaning up."
            cleanup
        fi
    fi

    log "--- Starting V2Ray Tunnel ---"
    log "Received URL: $V2RAY_URL"

    # --- Parse VLESS URL ---
    # Format: vless://<uuid>@<domain>:<port>?<params>#<remark>
    if [[ ! "$V2RAY_URL" =~ ^vless:// ]]; then
        echo "Error: Invalid VLESS URL provided."
        log "Error: Invalid VLESS URL. Must start with vless://"
        exit 1
    fi

    # Remove the "vless://" prefix
    url_body=${V2RAY_URL#vless://}

    # Extract remark (everything after #)
    REMARK=$(echo "$url_body" | awk -F'#' '{print $2}')
    log "Parsed Remark: $REMARK"

    # Extract main part (before #)
    main_part=$(echo "$url_body" | awk -F'#' '{print $1}')

    # Extract user@host:port
    user_host_port=$(echo "$main_part" | awk -F'?' '{print $1}')

    # Extract UUID
    UUID=$(echo "$user_host_port" | awk -F'@' '{print $1}')
    log "Parsed UUID: $UUID"

    # Extract domain and port
    host_port=$(echo "$user_host_port" | awk -F'@' '{print $2}')
    DOMAIN=$(echo "$host_port" | awk -F':' '{print $1}')
    PORT=$(echo "$host_port" | awk -F':' '{print $2}')
    log "Parsed Domain: $DOMAIN"
    log "Parsed Port: $PORT"

    # Extract query parameters
    query_part=$(echo "$main_part" | awk -F'?' -v N=2 '{if(NF>1) print $N}')

    # Simple parsing for required params. A more robust solution would handle all cases.
    TYPE=$(echo "$query_part" | sed -n 's/.*type=\([^&]*\).*/\1/p')
    SECURITY=$(echo "$query_part" | sed -n 's/.*security=\([^&]*\).*/\1/p')
    SNI=$(echo "$query_part" | sed -n 's/.*sni=\([^&]*\).*/\1/p')
    FP=$(echo "$query_part" | sed -n 's/.*fp=\([^&]*\).*/\1/p')
    ALPN_RAW=$(echo "$query_part" | sed -n 's/.*alpn=\([^&]*\).*/\1/p')
    ALPN=$(echo "$ALPN_RAW" | sed 's/%2C/,/g') # URL Decode for comma
    FLOW=$(echo "$query_part" | sed -n 's/.*flow=\([^&]*\).*/\1/p')

    log "Parsed Type: $TYPE"
    log "Parsed Security: $SECURITY"
    log "Parsed SNI: $SNI"
    log "Parsed Fingerprint: $FP"
    log "Parsed ALPN: $ALPN"
    log "Parsed Flow: $FLOW"

    # --- Generate Xray JSON Config ---
    log "Generating Xray config file at $CONFIG_FILE"

    # Basic validation
    if [ -z "$UUID" ] || [ -z "$DOMAIN" ] || [ -z "$PORT" ]; then
        echo "Error: Failed to parse required fields (UUID, domain, port) from URL."
        log "Error: Failed to parse required fields from URL."
        exit 1
    fi

    # --- Generate Xray JSON Config ---
    log "Generating Xray config file at $CONFIG_FILE"

    # Basic validation
    if [ -z "$UUID" ] || [ -z "$DOMAIN" ] || [ -z "$PORT" ]; then
        echo "Error: Failed to parse required fields (UUID, domain, port) from URL."
        log "Error: Failed to parse required fields from URL."
        exit 1
    fi

    # Conditionally add the "flow" field to the user object
    FLOW_JSON_LINE=""
    if [ -n "$FLOW" ]; then
        # Note the comma at the end. This is safe because "encryption" always follows.
        FLOW_JSON_LINE="\"flow\": \"$FLOW\","
    fi

    # Conditionally build the tlsSettings or xtlsSettings object as a string
    SECURITY_SETTINGS_JSON=""
    if [ "$SECURITY" = "tls" ] || [ "$SECURITY" = "xtls" ]; then
        # Note: The alpn field expects a JSON array of strings.
        # We'll construct it carefully.
        ALPN_JSON_ARRAY="\"h2\", \"http/1.1\"" # Default
        if [ -n "$ALPN" ]; then
            # If ALPN is provided, format it as a JSON array of strings
            # Use [^,][^,]* instead of [^,]+ for macOS (BSD) sed compatibility
            ALPN_JSON_ARRAY=$(echo "$ALPN" | sed 's/[^,][^,]*/"&"/g')
        fi

        SETTINGS_KEY="${SECURITY}Settings"

        SECURITY_SETTINGS_JSON=$(cat <<EOF
                "${SETTINGS_KEY}": {
                    "serverName": "${SNI:-$DOMAIN}",
                    "fingerprint": "${FP:-chrome}",
                    "alpn": [${ALPN_JSON_ARRAY}]
                }
EOF
)
    fi

    # Build the final JSON using the conditionally created parts
    cat > "$CONFIG_FILE" << EOL
{
    "log": {
        "loglevel": "warning"
    },
    "inbounds": [
        {
            "port": ${SOCKS_PORT},
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {
                "auth": "noauth",
                "udp": true
            }
        }
    ],
    "outbounds": [
        {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": "${DOMAIN}",
                        "port": ${PORT},
                        "users": [
                            {
                                "id": "${UUID}",
                                ${FLOW_JSON_LINE}
                                "encryption": "none" # VLESS encryption is handled by the underlying transport (TLS/XTLS)
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": "${TYPE:-tcp}",
                "security": "${SECURITY:-none}"$(if [ -n "$SECURITY_SETTINGS_JSON" ]; then echo ","; fi)
                ${SECURITY_SETTINGS_JSON}
            }
        }
    ]
}
EOL

    log "Config file generated. Starting Xray..."
    nohup "$XRAY_EXEC" -config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
    pid=$!

    if [ -z "$pid" ]; then
        echo "Error: Failed to start the xray process."
        log "Error: 'nohup xray' command failed to return a PID."
        cleanup
        exit 1
    fi

    echo "$pid" > "$LOCK_FILE"
    log "Xray process started with PID $pid."

    # Wait up to 5 seconds for the process to confirm it's running by checking the log file.
    # This is more reliable than a fixed sleep duration.
    local success=false
    for i in {1..10}; do # Check every 0.5s for 5s
        # If the process died, stop waiting.
        if ! ps -p "$pid" > /dev/null; then
            log "Process $pid died prematurely."
            break
        fi
        # Check for the success message in the log.
        if grep -q "proxy is listening on" "$LOG_FILE"; then
            success=true
            break
        fi
        sleep 0.5
    done

    if [ "$success" = false ]; then
        echo "Error: Xray process failed to start correctly. Check the log for details."
        log "Error: Xray process with PID $pid did not log a successful start message. It may have crashed."
        kill "$pid" 2>/dev/null # Ensure the zombie process is gone
        cleanup
        exit 1
    fi

    echo "V2Ray tunnel started successfully."
    log "Start script finished."
}

stop_tunnel() {
    log "--- Stopping V2Ray Tunnel ---"
    if [ ! -f "$LOCK_FILE" ]; then
        echo "Tunnel is not running (no lock file found)."
        log "Stop command issued, but no lock file found."
        exit 0
    fi

    pid=$(cat "$LOCK_FILE")
    if [ -z "$pid" ]; then
        log "Lock file is empty. Cleaning up."
        cleanup
        exit 0
    fi

    if ps -p "$pid" > /dev/null; then
        log "Killing process with PID $pid."
        kill "$pid"
        # Wait a moment for the process to terminate
        sleep 1
        if ps -p "$pid" > /dev/null; then
            log "Process $pid did not terminate gracefully. Forcing kill."
            kill -9 "$pid"
        fi
        log "Process $pid stopped."
    else
        log "Process with PID $pid not found. Assuming already stopped."
    fi

    cleanup
    echo "V2Ray tunnel stopped."
    log "Stop script finished."
}


# --- Main Script Logic ---
if [ "$#" -eq 0 ]; then
    echo "Usage: $0 {start|stop} --identifier <id> [--url <url>]"
    exit 1
fi

COMMAND=$1
shift

# Parse arguments
while [ "$#" -gt 0 ]; do
    case "$1" in
        --identifier)
            IDENTIFIER="$2"
            shift 2
            ;;
        --url)
            V2RAY_URL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$IDENTIFIER" ]; then
    echo "Error: --identifier is a required argument."
    exit 1
fi

# Define file paths based on the identifier
LOCK_FILE="/tmp/holocron_v2ray_${IDENTIFIER}.lock"
LOG_FILE="/tmp/holocron_v2ray_${IDENTIFIER}.log"
CONFIG_FILE="/tmp/holocron_v2ray_config_${IDENTIFIER}.json"

# Execute command
case "$COMMAND" in
    start)
        if [ -z "$V2RAY_URL" ]; then
            echo "Error: --url is required for the start command."
            exit 1
        fi
        start_tunnel
        ;;
    stop)
        stop_tunnel
        ;;
    *)
        echo "Invalid command: $COMMAND. Use 'start' or 'stop'."
        exit 1
        ;;
esac

exit 0
