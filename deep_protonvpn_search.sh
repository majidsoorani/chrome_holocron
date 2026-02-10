#!/bin/bash

# Deep ProtonVPN Server Discovery for Iran
# Tests multiple server locations, ports, and protocols to find accessible endpoints

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# V2Ray HTTP proxy
PROXY="http://127.0.0.1:10808"

# Create results directory
RESULTS_DIR="protonvpn_test_results"
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="$RESULTS_DIR/test_results_${TIMESTAMP}.txt"
WORKING_SERVERS_FILE="$RESULTS_DIR/working_servers_${TIMESTAMP}.txt"

echo -e "${CYAN}=========================================================${NC}"
echo -e "${CYAN}   Deep ProtonVPN Server Discovery for Iran${NC}"
echo -e "${CYAN}=========================================================${NC}"
echo ""
echo -e "Results will be saved to: ${YELLOW}$RESULTS_FILE${NC}"
echo -e "Working servers: ${YELLOW}$WORKING_SERVERS_FILE${NC}"
echo ""

# Initialize results files
echo "ProtonVPN Server Discovery Test - $(date)" > "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

echo "# Working ProtonVPN Servers from Iran" > "$WORKING_SERVERS_FILE"
echo "# Tested on: $(date)" >> "$WORKING_SERVERS_FILE"
echo "" >> "$WORKING_SERVERS_FILE"

# Counters
TOTAL_TESTS=0
SUCCESSFUL_TESTS=0

# ProtonVPN server locations (more comprehensive list)
# Format: country|hostname|ip
declare -a PROTONVPN_SERVERS=(
    # Netherlands (NL)
    "Netherlands|nl-01.protonvpn.net|185.159.157.11"
    "Netherlands|nl-02.protonvpn.net|185.159.157.12"
    "Netherlands|nl-03.protonvpn.net|185.159.157.13"
    "Netherlands|nl-04.protonvpn.net|185.159.156.27"
    "Netherlands|nl-free-01.protonvpn.net|95.215.61.163"
    "Netherlands|nl-free-02.protonvpn.net|95.215.61.164"
    
    # Switzerland (CH)
    "Switzerland|ch-01.protonvpn.net|146.70.136.2"
    "Switzerland|ch-02.protonvpn.net|146.70.136.3"
    "Switzerland|ch-03.protonvpn.net|146.70.136.4"
    "Switzerland|ch-04.protonvpn.net|146.70.198.2"
    "Switzerland|ch-ch-01.protonvpn.net|146.70.174.2"
    
    # Iceland (IS)
    "Iceland|is-01.protonvpn.net|89.22.98.178"
    "Iceland|is-02.protonvpn.net|89.22.98.179"
    "Iceland|is-free-01.protonvpn.net|89.22.98.226"
    
    # Sweden (SE)
    "Sweden|se-01.protonvpn.net|185.107.56.146"
    "Sweden|se-02.protonvpn.net|185.107.56.147"
    "Sweden|se-free-01.protonvpn.net|185.107.56.228"
    
    # United States (US)
    "USA|us-ca-01.protonvpn.net|169.150.219.196"
    "USA|us-ca-02.protonvpn.net|169.150.219.197"
    "USA|us-ny-01.protonvpn.net|209.58.128.194"
    "USA|us-ny-02.protonvpn.net|209.58.128.195"
    "USA|us-free-01.protonvpn.net|45.151.162.194"
    
    # United Kingdom (UK)
    "UK|uk-01.protonvpn.net|146.70.184.2"
    "UK|uk-02.protonvpn.net|146.70.184.3"
    "UK|uk-free-01.protonvpn.net|146.70.184.226"
    
    # Germany (DE)
    "Germany|de-01.protonvpn.net|185.181.58.2"
    "Germany|de-02.protonvpn.net|185.181.58.3"
    "Germany|de-free-01.protonvpn.net|185.181.58.242"
    
    # France (FR)
    "France|fr-01.protonvpn.net|146.70.152.2"
    "France|fr-02.protonvpn.net|146.70.152.3"
    "France|fr-free-01.protonvpn.net|146.70.152.226"
    
    # Japan (JP)
    "Japan|jp-01.protonvpn.net|146.70.27.2"
    "Japan|jp-02.protonvpn.net|146.70.27.3"
    "Japan|jp-free-01.protonvpn.net|146.70.27.226"
    
    # Singapore (SG)
    "Singapore|sg-01.protonvpn.net|37.19.220.2"
    "Singapore|sg-02.protonvpn.net|37.19.220.3"
    
    # Australia (AU)
    "Australia|au-01.protonvpn.net|146.70.130.2"
    "Australia|au-02.protonvpn.net|146.70.130.3"
    
    # Spain (ES)
    "Spain|es-01.protonvpn.net|146.70.149.2"
    "Spain|es-free-01.protonvpn.net|146.70.149.226"
    
    # Italy (IT)
    "Italy|it-01.protonvpn.net|146.70.162.2"
    "Italy|it-free-01.protonvpn.net|146.70.162.226"
    
    # Poland (PL)
    "Poland|pl-01.protonvpn.net|185.232.23.2"
    "Poland|pl-free-01.protonvpn.net|185.232.23.226"
    
    # Romania (RO)
    "Romania|ro-01.protonvpn.net|89.45.89.2"
    "Romania|ro-free-01.protonvpn.net|89.45.89.226"
)

# Ports to test
PORTS=(
    "443:TCP/HTTPS"
    "1194:TCP/OpenVPN"
    "5060:UDP/OpenVPN"
    "80:HTTP"
    "8080:HTTP-Alt"
    "4569:OpenVPN"
)

# Test functions
test_http_via_proxy() {
    local url=$1
    local timeout=5
    
    response=$(curl -I -x "$PROXY" "$url" --max-time $timeout --connect-timeout $timeout --silent --show-error 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        http_code=$(echo "$response" | head -n 1 | awk '{print $2}')
        echo "$http_code"
        return 0
    else
        echo "FAILED"
        return 1
    fi
}

test_tcp_port() {
    local host=$1
    local port=$2
    local timeout=3
    
    if command -v nc &> /dev/null; then
        nc -zv -G $timeout "$host" "$port" &> /dev/null
        return $?
    else
        timeout $timeout bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null
        return $?
    fi
}

test_tcp_port_via_proxy() {
    local host=$1
    local port=$2
    local timeout=5
    
    # Use curl to test TCP connection through proxy
    response=$(curl -x "$PROXY" --connect-timeout $timeout -s "http://$host:$port" 2>&1)
    exit_code=$?
    
    # Exit code 52 means empty reply (connection successful but no HTTP)
    # Exit code 0 means success
    if [ $exit_code -eq 0 ] || [ $exit_code -eq 52 ] || [ $exit_code -eq 56 ]; then
        return 0
    else
        return 1
    fi
}

# Test ProtonVPN API and web endpoints via proxy
echo -e "${MAGENTA}========== Phase 1: Testing ProtonVPN Web Services ==========${NC}"
echo ""

WEB_ENDPOINTS=(
    "https://protonvpn.com"
    "https://account.protonvpn.com"
    "https://api.protonvpn.ch"
    "https://account.protonvpn.com/downloads"
    "https://account.protonvpn.com/login"
    "https://api.protonvpn.ch/vpn/logicals"
    "https://api.protonvpn.ch/vpn/servers"
)

for endpoint in "${WEB_ENDPOINTS[@]}"; do
    ((TOTAL_TESTS++))
    echo -n "Testing $endpoint ... "
    result=$(test_http_via_proxy "$endpoint")
    
    if [ "$result" != "FAILED" ]; then
        echo -e "${GREEN}✓ SUCCESS${NC} (HTTP $result)"
        echo "[✓] $endpoint - HTTP $result" >> "$RESULTS_FILE"
        echo "$endpoint" >> "$WORKING_SERVERS_FILE"
        ((SUCCESSFUL_TESTS++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "[✗] $endpoint - FAILED" >> "$RESULTS_FILE"
    fi
done

echo "" | tee -a "$RESULTS_FILE"

# Test direct server connectivity (without proxy)
echo -e "${MAGENTA}========== Phase 2: Testing Direct Server Access (No Proxy) ==========${NC}"
echo "" | tee -a "$RESULTS_FILE"

for server_info in "${PROTONVPN_SERVERS[@]}"; do
    IFS='|' read -r country hostname ip <<< "$server_info"
    
    echo -e "${BLUE}Testing $country - $hostname ($ip)${NC}"
    echo "Server: $country - $hostname ($ip)" >> "$RESULTS_FILE"
    
    server_reachable=false
    
    for port_info in "${PORTS[@]}"; do
        IFS=':' read -r port protocol <<< "$port_info"
        ((TOTAL_TESTS++))
        
        echo -n "  Port $port ($protocol) ... "
        
        if test_tcp_port "$ip" "$port"; then
            echo -e "${GREEN}✓ REACHABLE${NC}"
            echo "  [✓] Port $port ($protocol) - REACHABLE" >> "$RESULTS_FILE"
            echo "$ip:$port # $country - $hostname ($protocol)" >> "$WORKING_SERVERS_FILE"
            server_reachable=true
            ((SUCCESSFUL_TESTS++))
        else
            echo -e "${RED}✗ BLOCKED${NC}"
            echo "  [✗] Port $port ($protocol) - BLOCKED" >> "$RESULTS_FILE"
        fi
    done
    
    if [ "$server_reachable" = true ]; then
        echo -e "  ${GREEN}Server has accessible ports!${NC}"
    fi
    
    echo "" >> "$RESULTS_FILE"
    sleep 0.5  # Small delay to avoid rate limiting
done

echo ""

# Test server connectivity via V2Ray proxy
echo -e "${MAGENTA}========== Phase 3: Testing Server Access via V2Ray Proxy ==========${NC}"
echo "" | tee -a "$RESULTS_FILE"

for server_info in "${PROTONVPN_SERVERS[@]}"; do
    IFS='|' read -r country hostname ip <<< "$server_info"
    
    echo -e "${BLUE}Testing $country - $hostname via proxy${NC}"
    echo "Server (via proxy): $country - $hostname ($ip)" >> "$RESULTS_FILE"
    
    # Test HTTPS (443)
    ((TOTAL_TESTS++))
    echo -n "  HTTPS (443) ... "
    if test_tcp_port_via_proxy "$ip" "443"; then
        echo -e "${GREEN}✓ REACHABLE${NC}"
        echo "  [✓] HTTPS (443) - REACHABLE via proxy" >> "$RESULTS_FILE"
        echo "# Via V2Ray: $ip:443 # $country - $hostname" >> "$WORKING_SERVERS_FILE"
        ((SUCCESSFUL_TESTS++))
    else
        echo -e "${RED}✗ BLOCKED${NC}"
        echo "  [✗] HTTPS (443) - BLOCKED" >> "$RESULTS_FILE"
    fi
    
    echo "" >> "$RESULTS_FILE"
    sleep 0.5
done

echo ""

# Fetch ProtonVPN server list from API if accessible
echo -e "${MAGENTA}========== Phase 4: Fetching Live Server List from API ==========${NC}"
echo ""

API_RESPONSE=$(curl -x "$PROXY" -s --max-time 10 "https://api.protonvpn.ch/vpn/logicals" 2>&1)

if [ $? -eq 0 ] && [ ! -z "$API_RESPONSE" ]; then
    echo -e "${GREEN}✓ Successfully fetched server list from API${NC}"
    echo "$API_RESPONSE" > "$RESULTS_DIR/api_servers_${TIMESTAMP}.json"
    echo -e "Saved to: ${YELLOW}$RESULTS_DIR/api_servers_${TIMESTAMP}.json${NC}"
    
    # Extract and test servers from API response
    if command -v jq &> /dev/null; then
        echo ""
        echo -e "${CYAN}Parsing server data...${NC}"
        
        # Extract server IPs and test them
        SERVER_IPS=$(echo "$API_RESPONSE" | jq -r '.LogicalServers[]? | .Servers[]? | .EntryIP' 2>/dev/null | sort -u)
        
        if [ ! -z "$SERVER_IPS" ]; then
            echo "Found $(echo "$SERVER_IPS" | wc -l) unique server IPs from API"
            echo ""
            echo "Testing sample of API servers..."
            
            count=0
            while IFS= read -r server_ip; do
                ((count++))
                if [ $count -gt 10 ]; then  # Test only first 10 to save time
                    break
                fi
                
                echo -n "Testing $server_ip:443 via proxy ... "
                if test_tcp_port_via_proxy "$server_ip" "443"; then
                    echo -e "${GREEN}✓ REACHABLE${NC}"
                    echo "# API Server: $server_ip:443" >> "$WORKING_SERVERS_FILE"
                else
                    echo -e "${RED}✗ BLOCKED${NC}"
                fi
            done <<< "$SERVER_IPS"
        fi
    else
        echo -e "${YELLOW}⚠ jq not installed, cannot parse JSON. Install with: brew install jq${NC}"
    fi
else
    echo -e "${RED}✗ Failed to fetch server list from API${NC}"
fi

echo ""

# Summary
echo -e "${CYAN}=========================================================${NC}"
echo -e "${CYAN}   Test Summary${NC}"
echo -e "${CYAN}=========================================================${NC}"
echo ""
echo -e "Total tests performed: ${YELLOW}$TOTAL_TESTS${NC}"
echo -e "Successful connections: ${GREEN}$SUCCESSFUL_TESTS${NC}"
echo -e "Failed connections: ${RED}$((TOTAL_TESTS - SUCCESSFUL_TESTS))${NC}"
echo -e "Success rate: ${YELLOW}$(awk "BEGIN {printf \"%.1f\", ($SUCCESSFUL_TESTS/$TOTAL_TESTS)*100}")%${NC}"
echo ""

# Summary to file
echo "" >> "$RESULTS_FILE"
echo "========== SUMMARY ==========" >> "$RESULTS_FILE"
echo "Total tests: $TOTAL_TESTS" >> "$RESULTS_FILE"
echo "Successful: $SUCCESSFUL_TESTS" >> "$RESULTS_FILE"
echo "Failed: $((TOTAL_TESTS - SUCCESSFUL_TESTS))" >> "$RESULTS_FILE"
echo "Success rate: $(awk "BEGIN {printf \"%.1f\", ($SUCCESSFUL_TESTS/$TOTAL_TESTS)*100}")%" >> "$RESULTS_FILE"

echo -e "${GREEN}Results saved to:${NC}"
echo -e "  ${YELLOW}$RESULTS_FILE${NC}"
echo -e "  ${YELLOW}$WORKING_SERVERS_FILE${NC}"
echo ""

# Show working servers
if [ -s "$WORKING_SERVERS_FILE" ]; then
    working_count=$(grep -v '^#' "$WORKING_SERVERS_FILE" | grep -v '^$' | wc -l)
    if [ $working_count -gt 0 ]; then
        echo -e "${GREEN}========== Working Servers/Endpoints ===========${NC}"
        cat "$WORKING_SERVERS_FILE"
        echo ""
    fi
fi

echo -e "${CYAN}=========================================================${NC}"
echo ""
echo -e "${YELLOW}Recommendations:${NC}"
echo -e "1. ProtonVPN web services (account, downloads) work via V2Ray proxy"
echo -e "2. Direct VPN server connections are likely blocked by ISP"
echo -e "3. Use V2Ray proxy to access ProtonVPN website and download clients"
echo -e "4. For VPN connection, you may need to use ProtonVPN's Secure Core"
echo -e "   or their obfuscation/stealth features"
echo ""
