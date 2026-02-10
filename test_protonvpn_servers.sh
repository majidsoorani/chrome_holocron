#!/bin/bash

# ProtonVPN Server Reachability Test Script
# This script tests connectivity to ProtonVPN servers and downloads page

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   ProtonVPN Server Reachability Test${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# V2Ray HTTP proxy on port 10808
PROXY="http://127.0.0.1:10808"

# Common ProtonVPN domains and servers to test
DOMAINS=(
    "protonvpn.com"
    "account.protonvpn.com"
    "api.protonvpn.ch"
    "vpn.protonvpn.com"
)

# ProtonVPN server IPs (examples - you can add more)
# These are common ProtonVPN server locations
SERVERS=(
    # Netherlands
    "185.159.157.11"
    "185.159.157.12"
    "185.159.157.13"
    # Switzerland
    "146.70.136.2"
    "146.70.136.3"
    "146.70.136.4"
    # Iceland
    "89.22.98.178"
    "89.22.98.179"
    # Sweden
    "185.107.56.146"
    "185.107.56.147"
    # United States
    "169.150.219.196"
    "169.150.219.197"
)

echo -e "${YELLOW}Testing connectivity with V2Ray proxy on port 10808...${NC}"
echo ""

# Function to test HTTP/HTTPS connectivity via proxy
test_http() {
    local url=$1
    local timeout=5
    
    echo -n "Testing $url ... "
    
    response=$(curl -I -x "$PROXY" "$url" --max-time $timeout --silent --show-error 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        http_code=$(echo "$response" | head -n 1 | awk '{print $2}')
        echo -e "${GREEN}✓ SUCCESS${NC} (HTTP $http_code)"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (Exit code: $exit_code)"
        return 1
    fi
}

# Function to test TCP connectivity (ping equivalent for TCP)
test_tcp_ping() {
    local host=$1
    local port=$2
    local timeout=3
    
    echo -n "TCP ping $host:$port ... "
    
    # Use nc (netcat) with timeout
    if command -v nc &> /dev/null; then
        nc -zv -G $timeout "$host" "$port" &> /dev/null
        exit_code=$?
        
        if [ $exit_code -eq 0 ]; then
            echo -e "${GREEN}✓ REACHABLE${NC}"
            return 0
        else
            echo -e "${RED}✗ UNREACHABLE${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠ nc not available${NC}"
        return 2
    fi
}

# Test ProtonVPN domains via proxy
echo -e "${BLUE}--- Testing ProtonVPN Domains (via V2Ray Proxy) ---${NC}"
success_count=0
for domain in "${DOMAINS[@]}"; do
    if test_http "https://$domain"; then
        ((success_count++))
    fi
done
echo -e "\nDomains reachable: ${GREEN}$success_count/${#DOMAINS[@]}${NC}"
echo ""

# Test downloads page specifically
echo -e "${BLUE}--- Testing ProtonVPN Downloads Page ---${NC}"
test_http "https://account.protonvpn.com/downloads"
echo ""

# Test direct server connectivity (TCP ping on common VPN ports)
echo -e "${BLUE}--- Testing Direct Server Connectivity (no proxy) ---${NC}"
echo -e "${YELLOW}Testing OpenVPN ports (UDP 1194, TCP 443)${NC}"
vpn_reachable=0

for server in "${SERVERS[@]}"; do
    echo -e "\n${BLUE}Server: $server${NC}"
    
    # Test TCP 443 (HTTPS/OpenVPN)
    if test_tcp_ping "$server" 443; then
        ((vpn_reachable++))
    fi
    
    # Test TCP 1194 (OpenVPN)
    test_tcp_ping "$server" 1194
    
    # Test UDP 1194 would require different tool
done

echo ""
echo -e "VPN servers reachable: ${GREEN}$vpn_reachable/${#SERVERS[@]}${NC}"
echo ""

# Additional diagnostic: Check if V2Ray proxy itself is running
echo -e "${BLUE}--- V2Ray Proxy Status ---${NC}"
echo -n "Checking if V2Ray proxy is running on 127.0.0.1:10808 ... "
if nc -z -G 2 127.0.0.1 10808 &> /dev/null; then
    echo -e "${GREEN}✓ RUNNING${NC}"
else
    echo -e "${RED}✗ NOT RUNNING${NC}"
    echo -e "${YELLOW}⚠ Make sure V2Ray is connected in the Holocron extension${NC}"
fi
echo ""

# Test a known working site via proxy
echo -e "${BLUE}--- Testing V2Ray Proxy Functionality ---${NC}"
test_http "https://www.google.com"
echo ""

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Test Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. ${GREEN}Reload the Holocron extension${NC} to apply the V2Ray PAC fix"
echo -e "2. ${GREEN}Go to Proxy Rules & PAC tab${NC}"
echo -e "3. ${GREEN}Add *.protonvpn.com rule${NC} with target = your V2Ray config"
echo -e "4. ${GREEN}Click 'Apply Proxy to Browser'${NC}"
echo ""
