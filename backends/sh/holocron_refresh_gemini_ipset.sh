#!/bin/sh

TABLE="${TABLE:-passwall2}"
FAMILY="${FAMILY:-inet}"
SET4="${SET4:-passwall2_xGJBvT4N_gemini}"
SET6="${SET6:-passwall2_xGJBvT4N_gemini6}"
TIMEOUT="${TIMEOUT:-2h}"
LOCK_DIR="${LOCK_DIR:-/tmp/holocron_gemini_ipset.lock}"

DOMAINS="${DOMAINS:-gemini.google.com bard.google.com notebooklm.google.com notebooklm-pa.clients6.google.com generativelanguage.googleapis.com content-push.googleapis.com ogads-pa.googleapis.com alkalicore-pa.clients6.google.com alkalimakersuite-pa.clients6.google.com aistudio.google.com ai.google.dev makersuite.google.com}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if ! command -v nft >/dev/null 2>&1 || ! command -v nslookup >/dev/null 2>&1; then
    exit 0
fi

have_set() {
    nft list set "$FAMILY" "$TABLE" "$1" >/dev/null 2>&1
}

add_ipv4() {
    ip="$1"
    [ -n "$ip" ] || return 0
    have_set "$SET4" || return 0
    nft delete element "$FAMILY" "$TABLE" "$SET4" "{ $ip }" 2>/dev/null || true
    nft add element "$FAMILY" "$TABLE" "$SET4" "{ $ip timeout $TIMEOUT }" 2>/dev/null || \
        nft add element "$FAMILY" "$TABLE" "$SET4" "{ $ip }" 2>/dev/null || true
}

add_ipv6() {
    ip="$1"
    [ -n "$ip" ] || return 0
    have_set "$SET6" || return 0
    nft delete element "$FAMILY" "$TABLE" "$SET6" "{ $ip }" 2>/dev/null || true
    nft add element "$FAMILY" "$TABLE" "$SET6" "{ $ip timeout $TIMEOUT }" 2>/dev/null || \
        nft add element "$FAMILY" "$TABLE" "$SET6" "{ $ip }" 2>/dev/null || true
}

resolve_domain() {
    domain="$1"
    nslookup "$domain" 2>/dev/null | awk '
        /^Address: / { print $2 }
        /^Address [0-9]+: / { print $3 }
    '
}

for domain in $DOMAINS; do
    resolve_domain "$domain" | while IFS= read -r ip; do
        case "$ip" in
            ""|127.*|0.*|192.168.*|10.*|172.16.*|172.17.*|172.18.*|172.19.*|172.2[0-9].*|172.3[0-1].*)
                ;;
            *.*:*)
                ;;
            *.*)
                add_ipv4 "$ip"
                ;;
            *:*)
                add_ipv6 "$ip"
                ;;
        esac
    done
done
