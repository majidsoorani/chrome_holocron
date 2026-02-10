#!/bin/bash
#
# Manual ProtonVPN Setup on OpenWrt
# For testing before adding to the main application
#

set -e

# Configuration
OPENWRT_IP="192.168.1.1"
OPENWRT_USER="root"

# ProtonVPN Credentials
PROTONVPN_USERNAME="8NlTR0U3vsuJJ7nY"
PROTONVPN_PASSWORD="nv0ndA0ECPrV3aryW0Q8WZGD59HNemdS"

# Best working free server from tests
PROTONVPN_SERVER_IP="146.70.149.226"  # Spain FREE
PROTONVPN_SERVER_NAME="es-free-01.protonvpn.net"
PROTONVPN_PORT="443"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ProtonVPN Manual Setup on OpenWrt${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Router: ${YELLOW}$OPENWRT_IP${NC}"
echo -e "Server: ${YELLOW}$PROTONVPN_SERVER_NAME${NC}"
echo -e "Username: ${YELLOW}$PROTONVPN_USERNAME${NC}"
echo ""

# Function to run commands on router
run_on_router() {
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$OPENWRT_USER@$OPENWRT_IP" "$@"
}

echo -e "${YELLOW}[1/6] Checking OpenVPN installation...${NC}"
if run_on_router "opkg list-installed | grep -q openvpn-openssl"; then
    echo -e "${GREEN}✓ OpenVPN is already installed${NC}"
else
    echo -e "${YELLOW}Installing OpenVPN...${NC}"
    run_on_router "opkg update && opkg install openvpn-openssl luci-app-openvpn" || {
        echo -e "${RED}✗ Failed to install OpenVPN${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ OpenVPN installed successfully${NC}"
fi
echo ""

echo -e "${YELLOW}[2/6] Creating ProtonVPN directory...${NC}"
run_on_router "mkdir -p /etc/openvpn/protonvpn"
echo -e "${GREEN}✓ Directory created${NC}"
echo ""

echo -e "${YELLOW}[3/6] Creating OpenVPN configuration...${NC}"

# Create the config file with CA certificate embedded
cat > /tmp/protonvpn_spain.ovpn << 'EOF'
# ProtonVPN Spain Free Server - Manual Setup
client
dev tun
proto tcp
remote 146.70.149.226 443

# Retry settings
resolv-retry infinite
nobind

# TUN/TAP settings
tun-mtu 1500
mssfix 1450

# Persistence
persist-key
persist-tun

# Security settings
cipher AES-256-GCM
auth SHA512
tls-version-min 1.2
remote-cert-tls server

# Logging
verb 3
mute 20

# Authentication
auth-user-pass /etc/openvpn/protonvpn/auth.txt

# Routing - Accept all routes from server (for testing)
# Later we'll configure selective routing for Instagram only

# DNS
dhcp-option DNS 10.2.0.1

# Keep alive
keepalive 10 60

# Disable compression
allow-compression no

# ProtonVPN CA Certificate
<ca>
-----BEGIN CERTIFICATE-----
MIIFozCCA4ugAwIBAgIBATANBgkqhkiG9w0BAQ0FADBAMQswCQYDVQQGEwJDSDEV
MBMGA1UEChMMUHJvdG9uVlBOIEFHMRowGAYDVQQDExFQcm90b25WUE4gUm9vdCBD
QTAeFw0xNzAyMTUxNDM4MDBaFw0yNzAyMTUxNDM4MDBaMEAxCzAJBgNVBAYTAkNI
MRUwEwYDVQQKEwxQcm90b25WUE4gQUcxGjAYBgNVBAMTEVByb3RvblZQTiBSb290
IENBMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAt+BsSsZg7+AuqTq7
vDbPzfygtl9f8fLJqO4amsyOXlI7pquL5IsEZhpWyJIIvYybqS4s1/T7BbvHPLVE
wlrq8A5DBIXcfuXrBbKoYkmpICGc2u1KYVGOZ9A+PH9z4Tr6OXFfXRnsbZToie8t
2Xjv/dZDdUDAqeW89I/mXg3k5x08m2nfGCQDm4gCanN1r5MT7ge56z0MkY3FFGCO
qRwspIEUzu1ZqGSTkG1eQiOYIrdOF5cc7n2APyvBIcfvp/W3cpTOEmEBJ7/14RnX
nHo0fcx61Inx/6ZxzKkW8BMdGGQF3tF6u2M0FjVN0lLH9S0ul1TgoOS56yEJ34hr
JSRTqHuar3t/xdCbKFZjyXFZFNsXVvgJu34CNLrHHTGJj9jiUfFnxWQYMo9UNUd4
a3PPG1HnbG7LAjlvj5JlJ5aqO5gshdnqb9uIQeR2CdzcCJgklwRGCyDT1pm7eoiv
WV19YBd81vKulLzgPavu3kRRe83yl29It2hwQ9FMs5w6ZV/X6ciTKo3etkX9nBD9
ZzJPsGQsBUy7CzO1jK4W01+u3ItmQS+1s4xtcFxdFY8o/q1zoqBlxpe5MQIWN6Qa
lryiET74gMHE/S5WrPlsq/gehxsdgc6GDUXG4dk8vn6OUMa6wb5wRO3VXGEc67IY
m4mDFTYiPvLaFOxtndlUWuCruKcCAwEAAaOBpzCBpDAMBgNVHRMEBTADAQH/MB0G
A1UdDgQWBBSDkIaYhLVZTwyLNTetNB2qV0gkVDBoBgNVHSMEYTBfgBSDkIaYhLVZ
TwyLNTetNB2qV0gkVKFEpEIwQDELMAkGA1UEBhMCQ0gxFTATBgNVBAoTDFByb3Rv
blZQTiBBRzEaMBgGA1UEAxMRUHJvdG9uVlBOIFJvb3QgQ0GCAQEwCwYDVR0PBAQD
AgEGMA0GCSqGSIb3DQEBDQUAA4ICAQCYr7LpvnfZXBCxVIVc2ea1fjxQ6vkTj0zM
htFs3qfeXpMz92SXLfQOEfLprVoSW8RAMd/TP/BPgp+P1qKfJgFd/FhKqD8fPJM5
lVJ0CUkHWqKLWXM6WUq8Jl9xwCjv0s9pFqR9i9sCRUcQYmJz3Uq6lbC/jqYYXv94
rRSy3xqYz42vLkCbK5z7XQn5XCqNMJjOQfVqDN0Nc0oOX6iZJBmB8hD9/1OfJhyJ
+lzhfVJb6aEzVTbmJGaTnFMfUkMnC3NN8xlGo2vH3DqQCYRPd1SqvY5ZEGhvRxWj
xDuWNvLl9iPnBG8GFcQ9Qb7DmPpUnWi3vJCCVw0Mb1xCXXtQx0PJ9zN3KS7RMJBS
6HQGFHY6TKP6K0Kl4Dqn4CXnJ8HKCA8nnPqWG4dRzVYu9qCdOGZSUxBCTgmINbBo
qvLzRfQfLEQNcL5R0E7xF4EWmBPa3PbnQqBOcMpvH1TCbJhkXbGGQmqiN8eYVjZK
Fk8glR1cPQKGqDhGQT3ek8f0RpPJ+PHpqHKBLlBNH8KiCJWFXWPu4yqpSLx5RX3P
gqEk2R7HjJ0qN2X5ADbVdwZJv7x7qfYcZ2pLBBa7VTAY0fY3FvN9gBGP7qz5dZxW
+ZXAqYoSHe3CiWb7Gg+4lYWmxfgOQiSSJRp1RvGqBZpTH8FDQb9P4VNZHQv3nzGr
f6aFNJqR1w==
-----END CERTIFICATE-----
</ca>
EOF

# Upload to router using cat over ssh instead of scp
run_on_router "cat > /etc/openvpn/protonvpn/spain.conf" < /tmp/protonvpn_spain.ovpn

echo -e "${GREEN}✓ Configuration uploaded${NC}"
echo ""

echo -e "${YELLOW}[4/6] Setting up credentials...${NC}"
run_on_router "cat > /etc/openvpn/protonvpn/auth.txt << 'EOFAUTH'
$PROTONVPN_USERNAME
$PROTONVPN_PASSWORD
EOFAUTH"

run_on_router "chmod 600 /etc/openvpn/protonvpn/auth.txt"
echo -e "${GREEN}✓ Credentials saved securely${NC}"
echo ""

echo -e "${YELLOW}[5/6] Testing server connectivity...${NC}"
echo -n "Checking if ProtonVPN server is reachable... "

if run_on_router "timeout 5 nc -zv $PROTONVPN_SERVER_IP $PROTONVPN_PORT 2>&1 | grep -q succeeded"; then
    echo -e "${GREEN}✓ Server is reachable!${NC}"
else
    echo -e "${RED}✗ Server not directly reachable${NC}"
    echo -e "${YELLOW}This is normal in Iran. Testing via Passwall2 proxy...${NC}"
    
    # Test via Passwall2 SOCKS proxy
    if run_on_router "curl -x socks5h://127.0.0.1:1080 --connect-timeout 5 -s https://$PROTONVPN_SERVER_IP:$PROTONVPN_PORT 2>&1 | head -1" &>/dev/null; then
        echo -e "${GREEN}✓ Server is reachable via Passwall2 proxy!${NC}"
        echo -e "${YELLOW}Note: You'll need to configure OpenVPN to use SOCKS proxy${NC}"
    else
        echo -e "${YELLOW}⚠ Server might be blocked. Will try to connect anyway...${NC}"
    fi
fi
echo ""

echo -e "${YELLOW}[6/6] Starting ProtonVPN connection...${NC}"

# Check if already running
if run_on_router "ps | grep -v grep | grep -q 'openvpn.*spain'"; then
    echo -e "${YELLOW}ProtonVPN is already running. Stopping it first...${NC}"
    run_on_router "killall openvpn 2>/dev/null || true"
    sleep 2
fi

# Start OpenVPN
echo -e "${YELLOW}Starting OpenVPN client...${NC}"
run_on_router "openvpn --config /etc/openvpn/protonvpn/spain.conf --daemon --log /var/log/protonvpn.log"

echo -e "${YELLOW}Waiting for connection to establish...${NC}"
sleep 5

# Check if it's running
if run_on_router "ps | grep -v grep | grep -q 'openvpn.*spain'"; then
    echo -e "${GREEN}✓ OpenVPN is running!${NC}"
    echo ""
    
    # Check for TUN interface
    echo -e "${YELLOW}Checking TUN interface...${NC}"
    if run_on_router "ifconfig | grep -q tun0"; then
        echo -e "${GREEN}✓ TUN interface is up!${NC}"
        
        # Get assigned IP
        TUN_IP=$(run_on_router "ifconfig tun0 | grep 'inet addr' | awk '{print \$2}' | cut -d: -f2")
        if [ -n "$TUN_IP" ]; then
            echo -e "${GREEN}✓ VPN IP: $TUN_IP${NC}"
        fi
    else
        echo -e "${RED}✗ TUN interface not found${NC}"
    fi
    
    # Check logs for connection status
    echo ""
    echo -e "${YELLOW}Connection log (last 20 lines):${NC}"
    echo -e "${BLUE}----------------------------------------${NC}"
    run_on_router "tail -20 /var/log/protonvpn.log"
    echo -e "${BLUE}----------------------------------------${NC}"
    
    # Test internet via VPN
    echo ""
    echo -e "${YELLOW}Testing internet connectivity via VPN...${NC}"
    VPN_IP=$(run_on_router "curl --interface tun0 -s --max-time 10 ifconfig.me 2>/dev/null || echo 'FAILED'")
    
    if [ "$VPN_IP" != "FAILED" ] && [ -n "$VPN_IP" ]; then
        echo -e "${GREEN}✓ VPN is working! Public IP: $VPN_IP${NC}"
        echo -e "${GREEN}✓ Successfully connected to ProtonVPN!${NC}"
    else
        echo -e "${YELLOW}⚠ Could not verify external IP via VPN${NC}"
        echo -e "${YELLOW}Check logs above for connection status${NC}"
    fi
    
else
    echo -e "${RED}✗ OpenVPN failed to start${NC}"
    echo ""
    echo -e "${YELLOW}Error log:${NC}"
    run_on_router "cat /var/log/protonvpn.log"
    exit 1
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo ""
echo -e "Check VPN status:"
echo -e "  ${GREEN}ssh root@$OPENWRT_IP \"ps | grep openvpn\"${NC}"
echo ""
echo -e "View logs:"
echo -e "  ${GREEN}ssh root@$OPENWRT_IP \"tail -f /var/log/protonvpn.log\"${NC}"
echo ""
echo -e "Stop VPN:"
echo -e "  ${GREEN}ssh root@$OPENWRT_IP \"killall openvpn\"${NC}"
echo ""
echo -e "Restart VPN:"
echo -e "  ${GREEN}ssh root@$OPENWRT_IP \"killall openvpn && openvpn --config /etc/openvpn/protonvpn/spain.conf --daemon --log /var/log/protonvpn.log\"${NC}"
echo ""
echo -e "Test your external IP:"
echo -e "  ${GREEN}ssh root@$OPENWRT_IP \"curl --interface tun0 ifconfig.me\"${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Test if Instagram works"
echo -e "2. If it works, we'll add selective routing for Instagram only"
echo -e "3. Then integrate into the Chrome extension"
echo ""
