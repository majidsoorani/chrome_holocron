#!/bin/bash
#
# ProtonVPN via Passwall2 SOCKS Proxy
# This connects to ProtonVPN through your existing Passwall2 SOCKS proxy
# to bypass DPI/blocking
#

set -e

OPENWRT_IP="192.168.1.1"
OPENWRT_USER="root"

# ProtonVPN Credentials
PROTONVPN_USERNAME="8NlTR0U3vsuJJ7nY"
PROTONVPN_PASSWORD="nv0ndA0ECPrV3aryW0Q8WZGD59HNemdS"

# Server info
PROTONVPN_SERVER_IP="146.70.149.226"
PROTONVPN_SERVER_NAME="es-free-01.protonvpn.net"
PROTONVPN_PORT="443"

# Passwall2 SOCKS proxy (already running on your router)
SOCKS_PROXY_IP="127.0.0.1"
SOCKS_PROXY_PORT="1080"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ProtonVPN via Passwall2 Proxy${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

run_on_router() {
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$OPENWRT_USER@$OPENWRT_IP" "$@"
}

echo -e "${YELLOW}[1/4] Installing required packages...${NC}"

# Check if we need proxychains or redsocks
if ! run_on_router "opkg list-installed | grep -q redsocks"; then
    echo -e "${YELLOW}Installing redsocks (transparent proxy)...${NC}"
    run_on_router "opkg update && opkg install redsocks" || {
        echo -e "${YELLOW}⚠ redsocks not available, will try alternative method${NC}"
    }
fi

echo -e "${GREEN}✓ Packages checked${NC}"
echo ""

echo -e "${YELLOW}[2/4] Creating configuration...${NC}"

# Create config that uses socks-proxy directive
run_on_router "cat > /etc/openvpn/protonvpn/spain.conf << 'EOFCONF'
# ProtonVPN via SOCKS Proxy
client
dev tun
proto tcp
remote $PROTONVPN_SERVER_IP $PROTONVPN_PORT

# SOCKS proxy settings - this makes OpenVPN go through Passwall2
socks-proxy $SOCKS_PROXY_IP $SOCKS_PROXY_PORT

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
EOFCONF"

echo -e "${GREEN}✓ Configuration with SOCKS proxy created${NC}"
echo ""

echo -e "${YELLOW}[3/4] Verifying Passwall2 SOCKS proxy...${NC}"
if run_on_router "netstat -tlnp 2>/dev/null | grep -q ':$SOCKS_PROXY_PORT'"; then
    echo -e "${GREEN}✓ Passwall2 SOCKS proxy is running on port $SOCKS_PROXY_PORT${NC}"
else
    echo -e "${RED}✗ Passwall2 SOCKS proxy is not running!${NC}"
    echo -e "${YELLOW}Please make sure Passwall2 is started and SOCKS proxy is enabled${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}[4/4] Starting ProtonVPN...${NC}"

# Stop any existing OpenVPN
run_on_router "killall openvpn 2>/dev/null || true"
sleep 2

# Start with SOCKS proxy support
run_on_router "openvpn --config /etc/openvpn/protonvpn/spain.conf --daemon --log /var/log/protonvpn.log"

echo -e "${YELLOW}Waiting for connection...${NC}"
sleep 8

# Check status
if run_on_router "ps | grep -v grep | grep -q 'openvpn.*spain'"; then
    echo -e "${GREEN}✓ OpenVPN process is running${NC}"
    
    # Check TUN
    if run_on_router "ifconfig | grep -q tun0"; then
        echo -e "${GREEN}✓ TUN interface is UP!${NC}"
        
        # Get VPN IP
        TUN_IP=$(run_on_router "ifconfig tun0 2>/dev/null | grep 'inet addr' | awk '{print \$2}' | cut -d: -f2")
        if [ -n "$TUN_IP" ]; then
            echo -e "${GREEN}✓ VPN IP assigned: $TUN_IP${NC}"
        fi
        
        # Test external IP
        echo ""
        echo -e "${YELLOW}Testing external IP via VPN...${NC}"
        EXTERNAL_IP=$(run_on_router "curl --interface tun0 -s --max-time 10 ifconfig.me 2>/dev/null")
        
        if [ -n "$EXTERNAL_IP" ]; then
            echo -e "${GREEN}✓✓✓ SUCCESS! External IP: $EXTERNAL_IP${NC}"
            echo -e "${GREEN}✓✓✓ ProtonVPN is working!${NC}"
        else
            echo -e "${YELLOW}⚠ Could not get external IP, but connection might still work${NC}"
        fi
        
    else
        echo -e "${YELLOW}⚠ TUN interface not up yet, checking logs...${NC}"
    fi
    
    echo ""
    echo -e "${BLUE}--- Last 15 lines of log ---${NC}"
    run_on_router "tail -15 /var/log/protonvpn.log"
else
    echo -e "${RED}✗ OpenVPN failed to start${NC}"
    run_on_router "cat /var/log/protonvpn.log"
    exit 1
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Monitor connection:${NC}"
echo -e "  ssh root@$OPENWRT_IP tail -f /var/log/protonvpn.log"
echo ""
