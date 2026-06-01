#!/bin/sh

# Mac watchdog for OpenWrt Passwall2.
# 1) Restarts passwall2 if it is not running.
# 2) Beeps when internet is down.

# Load environment variables from .env file if it exists
ENV_FILE="/Users/majidsoorani/chrome_holocron/.env"
if [ -f "$ENV_FILE" ]; then
    # Sourcing key-value pairs ignoring comments and empty lines
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            \#*|""|*[[:space:]]#*) continue ;;
        esac
        eval "export $line" >/dev/null 2>&1 || true
    done < "$ENV_FILE"
fi

ROUTER_HOST="${OPENWRT_HOST:-${ROUTER_IP:-192.168.1.1}}"
ROUTER_USER="${OPENWRT_USER:-root}"
ROUTER_SSH_PORT="${OPENWRT_SSH_PORT:-22}"
SSH_KEY_PATH="${SSH_KEY_PATH:-/Users/majidsoorani/.ssh/id_ed25519}"

INTERNET_TEST_URL="${INTERNET_TEST_URL:-https://www.gstatic.com/generate_204}"
BEEP_SOUND="${BEEP_SOUND:-/System/Library/Sounds/Glass.aiff}"
BEEP_REPEAT_WHILE_DOWN="${BEEP_REPEAT_WHILE_DOWN:-0}"

LOG_FILE="${WATCHDOG_LOG_FILE:-/Users/majidsoorani/chrome_holocron/backends/log/passwall2_watchdog.log}"
STATE_FILE="${WATCHDOG_STATE_FILE:-/tmp/holocron_internet_down.state}"

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

beep_alert() {
    if [ -f "$BEEP_SOUND" ]; then
        afplay "$BEEP_SOUND" >/dev/null 2>&1 || printf '\a'
    else
        printf '\a'
    fi
}

notify_mac() {
    local title="$1"
    local msg="$2"
    osascript -e "display notification \"$msg\" with title \"$title\"" >/dev/null 2>&1 || true
}

if [ ! -f "$SSH_KEY_PATH" ]; then
    log "ERROR: SSH key not found at $SSH_KEY_PATH"
    exit 1
fi

SSH_BASE=(
    ssh
    -i "$SSH_KEY_PATH"
    -o BatchMode=yes
    -o ConnectTimeout=8
    -o StrictHostKeyChecking=no
    -p "$ROUTER_SSH_PORT"
    "$ROUTER_USER@$ROUTER_HOST"
)

# Check if passwall2 exists. If not, run Sing-Box emulation!
is_passwall2_present=0
if "${SSH_BASE[@]}" "[ -f /etc/init.d/passwall2 ]" >/dev/null 2>&1; then
    is_passwall2_present=1
fi

if [ "$is_passwall2_present" = "1" ]; then
    core_check_cmd="pgrep -f '/tmp/etc/passwall2/bin/xray|/tmp/etc/passwall2/bin/sing-box' >/dev/null 2>&1"
    restart_cmd="/etc/init.d/passwall2 start >/dev/null 2>&1 || /etc/init.d/passwall2 restart >/dev/null 2>&1"
    lock_restart_cmd="/etc/init.d/passwall2 restart >/dev/null 2>&1"
    PROXY_PORT=1090
    service_name="Passwall2"
else
    core_check_cmd="pgrep -f 'sing-box run -c /etc/sing-box/config.json' >/dev/null 2>&1"
    restart_cmd="/etc/init.d/sing-box start >/dev/null 2>&1 || /etc/init.d/sing-box restart >/dev/null 2>&1"
    lock_restart_cmd="/etc/init.d/sing-box restart >/dev/null 2>&1"
    PROXY_PORT=1080
    service_name="Sing-Box"
fi

if ! "${SSH_BASE[@]}" "$core_check_cmd"; then
    log "WARN: $service_name core process not found. Trying to start."
    notify_mac "Watchdog" "$service_name stopped! Restarting immediately..."

    restart_out="$(${SSH_BASE[@]} sh -c "$restart_cmd" 2>&1)"

    if "${SSH_BASE[@]}" "$core_check_cmd"; then
        log "INFO: $service_name started successfully. output=[$restart_out]"
        notify_mac "Watchdog" "$service_name restarted successfully."
    else
        log "ERROR: $service_name start/restart failed. output=[$restart_out]"
        notify_mac "Watchdog" "Error: Failed to restart $service_name!"
    fi
fi

# Check proxy connection (urltest)
PROXY_ADDR="socks5h://${ROUTER_HOST}:${PROXY_PORT}"
proxy_ok=0
if curl -fsS --max-time 10 -x "$PROXY_ADDR" "$INTERNET_TEST_URL" >/dev/null 2>&1; then
    proxy_ok=1
fi

if [ "$proxy_ok" = "1" ]; then
    if [ -f "$STATE_FILE" ]; then
        rm -f "$STATE_FILE"
        log "INFO: Proxy internet restored."
        notify_mac "Watchdog" "Proxy connection restored."
    fi
else
    # Proxy is down/locked.
    log "WARN: Proxy URL test failed for $INTERNET_TEST_URL (SOCKS5 port ${PROXY_PORT})"
    
    # Check if direct internet is working to see if the issue is just the proxy/lock
    direct_ok=0
    if curl -fsS --max-time 5 "$INTERNET_TEST_URL" >/dev/null 2>&1; then
        direct_ok=1
    fi
    
    if [ "$direct_ok" = "1" ]; then
        log "WARN: Direct internet is UP but proxy is DOWN. Service is locked! Restarting $service_name..."
        notify_mac "Watchdog" "Proxy service is locked/blocked! Restarting $service_name..."
        
        restart_out="$(${SSH_BASE[@]} sh -c "$lock_restart_cmd" 2>&1)"
        log "INFO: $service_name restart initiated due to lock. output=[$restart_out]"
    else
        log "WARN: Both proxy and direct internet are down. Network or interface issue."
    fi

    should_beep=0
    if [ ! -f "$STATE_FILE" ]; then
        touch "$STATE_FILE"
        should_beep=1
    elif [ "$BEEP_REPEAT_WHILE_DOWN" = "1" ]; then
        should_beep=1
    fi

    if [ "$should_beep" = "1" ]; then
        beep_alert
    fi
fi

# Run remote router hardware and connection diagnostics on every run (approx every 10 seconds)
DEBUG_LOG_FILE="/Users/majidsoorani/chrome_holocron/backends/log/router_hardware_debug.log"
{
    # Test if router SSH is accessible
    if "${SSH_BASE[@]}" "true" >/dev/null 2>&1; then
        echo "INFO: Logging router diagnostics"
        "${SSH_BASE[@]}" "sh -s" < "/Users/majidsoorani/chrome_holocron/backends/sh/router_debugger.sh"
    else
        log "ERROR: Router unreachable during diagnostics"
    fi
} >> "$DEBUG_LOG_FILE" 2>&1

exit 0
