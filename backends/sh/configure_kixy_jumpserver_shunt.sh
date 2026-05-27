#!/bin/sh
#
# configure_kixy_jumpserver_shunt.sh
#
# Pins *.kixy.com traffic on the OpenWrt router (Passwall2) to the AWS bastion
# / "jumpserver" SSH node, regardless of which exit node the rest of the
# traffic uses.
#
# The bastion is reached via the router's SSH SOCKS tunnel that
# configure_openwrt_tunnel_service_multi.sh creates on port 1032
# (Passwall2 node id: ssh_7Hd5rcr0 by default).
#
# Usage:
#   ./configure_kixy_jumpserver_shunt.sh [router_host]
#
# Environment overrides:
#   OPENWRT_USER   (default: root)
#   OPENWRT_HOST   (default: 192.168.1.1, or first CLI arg)
#   JUMP_NODE_ID   (default: ssh_7Hd5rcr0) -- Passwall2 UCI section name of
#                  the SSH node pointing at the bastion (port 1032 SOCKS).
#   SHUNT_RULE_ID  (default: iran_shunt_node) -- existing shunt node that
#                  this script attaches the kixy rule to.
#   DOMAIN_LIST    (default: domain:.kixy.com) -- Passwall2 domain_list value.

set -e

OPENWRT_USER="${OPENWRT_USER:-root}"
OPENWRT_HOST="${OPENWRT_HOST:-${1:-192.168.1.1}}"
JUMP_NODE_ID="${JUMP_NODE_ID:-ssh_7Hd5rcr0}"
SHUNT_RULE_ID="${SHUNT_RULE_ID:-iran_shunt_node}"
DOMAIN_LIST="${DOMAIN_LIST:-domain:.kixy.com}"
COMPANY_SITES_ID="company_sites"

echo "INFO: Connecting to ${OPENWRT_USER}@${OPENWRT_HOST}..."
echo "INFO: Pinning ${DOMAIN_LIST} -> Passwall2 node '${JUMP_NODE_ID}'"

ssh -o BatchMode=yes -o ConnectTimeout=10 \
    "${OPENWRT_USER}@${OPENWRT_HOST}" \
    JUMP_NODE_ID="${JUMP_NODE_ID}" \
    SHUNT_RULE_ID="${SHUNT_RULE_ID}" \
    DOMAIN_LIST="${DOMAIN_LIST}" \
    COMPANY_SITES_ID="${COMPANY_SITES_ID}" \
    'sh -s' <<'REMOTE'
set -e

# --- 1. Sanity checks -------------------------------------------------------
if ! command -v uci >/dev/null 2>&1; then
    echo "ERROR: uci not found on router. Is this OpenWrt?" >&2
    exit 1
fi

if ! uci -q get passwall2.@global[0] >/dev/null; then
    echo "ERROR: Passwall2 not installed (no passwall2.@global[0])." >&2
    exit 1
fi

if ! uci -q get "passwall2.${JUMP_NODE_ID}" >/dev/null; then
    echo "ERROR: Jumpserver node 'passwall2.${JUMP_NODE_ID}' does not exist." >&2
    echo "       Run configure_openwrt_tunnel_service_multi.sh first to create the SSH-to-bastion tunnel." >&2
    exit 1
fi

if ! uci -q get "passwall2.${SHUNT_RULE_ID}" >/dev/null; then
    echo "ERROR: Shunt node 'passwall2.${SHUNT_RULE_ID}' does not exist." >&2
    echo "       Run add_passwall2_shunt.sh first." >&2
    exit 1
fi

echo "INFO: All prerequisites OK."

# --- 2. Ensure the company_sites shunt rule exists --------------------------
if ! uci -q get "passwall2.${COMPANY_SITES_ID}" >/dev/null; then
    echo "INFO: Creating shunt rule '${COMPANY_SITES_ID}'..."
    uci set "passwall2.${COMPANY_SITES_ID}=shunt_rules"
    uci set "passwall2.${COMPANY_SITES_ID}.remarks=Company Sites (Kixy via jumpserver)"
else
    echo "INFO: Shunt rule '${COMPANY_SITES_ID}' already exists, updating in place."
fi

uci set "passwall2.${COMPANY_SITES_ID}.domain_list=${DOMAIN_LIST}"
uci set "passwall2.${COMPANY_SITES_ID}.node=${JUMP_NODE_ID}"
uci set "passwall2.${COMPANY_SITES_ID}.enabled=1"

# --- 3. Attach the rule to the active shunt node ----------------------------
# Passwall2 shunt nodes reference rules by `<rule_id>=<node_id>` UCI option.
echo "INFO: Attaching '${COMPANY_SITES_ID}' to shunt node '${SHUNT_RULE_ID}'..."
uci set "passwall2.${SHUNT_RULE_ID}.${COMPANY_SITES_ID}=${JUMP_NODE_ID}"

uci commit passwall2

# --- 4. Apply ---------------------------------------------------------------
echo "INFO: Restarting Passwall2..."
/etc/init.d/passwall2 restart >/dev/null 2>&1 || /etc/init.d/passwall2 reload >/dev/null 2>&1 || true

# --- 5. Verify --------------------------------------------------------------
echo ""
echo "=== Verification ==="
echo "Shunt rule:"
uci show "passwall2.${COMPANY_SITES_ID}" 2>/dev/null | sed 's/^/  /'
echo ""
echo "Shunt node attachment:"
uci show "passwall2.${SHUNT_RULE_ID}.${COMPANY_SITES_ID}" 2>/dev/null | sed 's/^/  /'
echo ""
echo "Jump node summary:"
uci -q get "passwall2.${JUMP_NODE_ID}.remarks" | sed 's/^/  remarks: /'
uci -q get "passwall2.${JUMP_NODE_ID}.address" | sed 's/^/  address: /'
uci -q get "passwall2.${JUMP_NODE_ID}.port"    | sed 's/^/  port:    /'

echo ""
echo "SUCCESS: *.kixy.com is now pinned to the jumpserver."
REMOTE

cat <<EOM

✅ Done.

Test from the router:
  ssh ${OPENWRT_USER}@${OPENWRT_HOST} "curl -sS -o /dev/null -w '%{http_code}\\n' \\
    --resolve noc.kixy.com:443:\$(dig +short noc.kixy.com | head -1) \\
    https://noc.kixy.com"

Test from your Mac (Holocron native host test_node):
  Kixy URLs in test_node are now automatically routed through '${JUMP_NODE_ID}'
  regardless of which node you select in the Holocron UI.
EOM
