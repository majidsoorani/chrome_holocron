#!/bin/bash

# --- Configuration ---
# This script assumes 'xray' executable is in the system's PATH.
# You can specify a direct path if needed, e.g., XRAY_EXEC="/usr/local/bin/xray"
XRAY_EXEC=$(command -v xray)
SOCKS_PORT="10808" # Default SOCKS port

# --- Helper Functions ---
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

cleanup() {
    log "Cleaning up temporary files..."
    rm -f "$CONFIG_FILE" "$LOCK_FILE"
}

# --- Command Functions ---
start_tunnel() {
    if [ -z "$XRAY_EXEC" ]; then
        echo "Error: 'xray' executable not found. Please install Xray-core."
        log "Error: 'xray' executable not found."
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

    log "Parsed Type: $TYPE"
    log "Parsed Security: $SECURITY"
    log "Parsed SNI: $SNI"
    log "Parsed Fingerprint: $FP"
    log "Parsed ALPN: $ALPN"

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

    # Conditionally build the tlsSettings object as a string
    TLS_SETTINGS_JSON=""
    if [ "$SECURITY" = "tls" ]; then
        # Note: The alpn field expects a JSON array of strings.
        # We'll construct it carefully.
        ALPN_JSON_ARRAY="\"h2\", \"http/1.1\"" # Default
        if [ -n "$ALPN" ]; then
            # If ALPN is provided, format it as a JSON array of strings
            ALPN_JSON_ARRAY=$(echo "$ALPN" | sed 's/[^,]\+/"&"/g')
        fi

        TLS_SETTINGS_JSON=$(cat <<EOF
                ,"tlsSettings": {
                    "serverName": "${SNI:-${DOMAIN}}",
                    "fingerprint": "${FP:-chrome}",
                    "alpn": [${ALPN_JSON_ARRAY}]
                }
EOF
)
    fi

    # Build the final JSON using the conditionally created TLS part
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
                                "flow": "xtls-rprx-vision",
                                "encryption": "none"
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": "${TYPE:-tcp}",
                "security": "${SECURITY:-none}"
                ${TLS_SETTINGS_JSON}
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
    # Give it a moment to initialize before the extension checks status
    sleep 2

    # Check if the process is still alive after a short sleep
    if ! ps -p "$pid" > /dev/null; then
        echo "Error: Xray process exited immediately. Check the log for details."
        log "Error: Xray process with PID $pid exited immediately. See log above for details."
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
