#!/bin/bash

# Quick Setup Script for ProtonVPN Access from Iran

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  ProtonVPN Quick Setup for Iran${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check if V2Ray proxy is running
echo -e "${BLUE}Step 1: Checking V2Ray proxy status...${NC}"
if nc -z -G 2 127.0.0.1 10808 &> /dev/null; then
    echo -e "${GREEN}✓ V2Ray proxy is running on port 10808${NC}"
else
    echo -e "${YELLOW}⚠ V2Ray proxy is NOT running${NC}"
    echo -e "  Please start your V2Ray connection in Holocron extension first"
    echo ""
    exit 1
fi

echo ""

# Test ProtonVPN access via proxy
echo -e "${BLUE}Step 2: Testing ProtonVPN website access...${NC}"
if curl -I -x http://127.0.0.1:10808 https://account.protonvpn.com --max-time 5 --silent | grep -q "200"; then
    echo -e "${GREEN}✓ ProtonVPN website is accessible via V2Ray${NC}"
else
    echo -e "${YELLOW}⚠ Cannot access ProtonVPN website${NC}"
    echo -e "  Check your V2Ray connection"
    echo ""
fi

echo ""

# Test top working servers
echo -e "${BLUE}Step 3: Testing discovered ProtonVPN servers...${NC}"
echo ""

echo -e "${YELLOW}Testing French servers (BEST OPTIONS):${NC}"
echo -n "  fr-01 (146.70.152.2:443) ... "
if nc -zv -G 3 146.70.152.2 443 &> /dev/null; then
    echo -e "${GREEN}✓ REACHABLE${NC}"
else
    echo -e "✗ Not reachable"
fi

echo -n "  fr-02 (146.70.152.3:443) ... "
if nc -zv -G 3 146.70.152.3 443 &> /dev/null; then
    echo -e "${GREEN}✓ REACHABLE${NC}"
else
    echo -e "✗ Not reachable"
fi

echo ""
echo -e "${YELLOW}Testing Singapore servers:${NC}"
echo -n "  sg-01 (37.19.220.2:443) ... "
if nc -zv -G 3 37.19.220.2 443 &> /dev/null; then
    echo -e "${GREEN}✓ REACHABLE${NC}"
else
    echo -e "✗ Not reachable"
fi

echo -n "  sg-02 (37.19.220.3:443) ... "
if nc -zv -G 3 37.19.220.3 443 &> /dev/null; then
    echo -e "${GREEN}✓ REACHABLE${NC}"
else
    echo -e "✗ Not reachable"
fi

echo ""

# Show instructions
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Next Steps${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

echo -e "${GREEN}1. Configure Holocron Extension:${NC}"
echo -e "   • Open Chrome → chrome://extensions"
echo -e "   • Reload Holocron extension (click reload button)"
echo -e "   • Open Holocron Options"
echo ""

echo -e "${GREEN}2. Add ProtonVPN Proxy Rule:${NC}"
echo -e "   • Go to 'Proxy Rules & PAC' tab"
echo -e "   • Add or edit rule for: ${YELLOW}*.protonvpn.com${NC}"
echo -e "   • ${YELLOW}IMPORTANT:${NC} Set target to your ${YELLOW}V2Ray config name${NC} (NOT 'DIRECT')"
echo -e "   • Click 'Apply Proxy to Browser'"
echo ""

echo -e "${GREEN}3. Download ProtonVPN:${NC}"
echo -e "   • Visit: ${YELLOW}https://account.protonvpn.com/downloads${NC}"
echo -e "   • Download ProtonVPN for macOS"
echo -e "   • Install the client"
echo ""

echo -e "${GREEN}4. Configure ProtonVPN:${NC}"
echo -e "   • Open ProtonVPN settings"
echo -e "   • Protocol → Select ${YELLOW}'Stealth'${NC} or ${YELLOW}'TCP'${NC}"
echo -e "   • Try connecting to ${YELLOW}French servers${NC} first (fr-01, fr-02)"
echo ""

echo -e "${GREEN}5. Best Servers to Try:${NC}"
echo -e "   🥇 ${YELLOW}France fr-01${NC}: 146.70.152.2 (3 open ports)"
echo -e "   🥇 ${YELLOW}France fr-02${NC}: 146.70.152.3 (3 open ports)"
echo -e "   🥈 ${YELLOW}Singapore sg-01${NC}: 37.19.220.2 (2 open ports)"
echo -e "   🥈 ${YELLOW}Singapore sg-02${NC}: 37.19.220.3 (2 open ports)"
echo ""

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Helpful Commands${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

echo -e "${BLUE}Test V2Ray proxy:${NC}"
echo -e "  curl -I -x http://127.0.0.1:10808 https://protonvpn.com"
echo ""

echo -e "${BLUE}Test direct server access:${NC}"
echo -e "  nc -zv 146.70.152.2 443"
echo ""

echo -e "${BLUE}View discovered servers:${NC}"
echo -e "  cat protonvpn_test_results/working_servers_*.txt"
echo ""

echo -e "${BLUE}Run deep search again:${NC}"
echo -e "  ./deep_protonvpn_search.sh"
echo ""

echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${GREEN}For detailed instructions, see:${NC}"
echo -e "  • ${YELLOW}WORKING_PROTONVPN_SERVERS.md${NC}"
echo -e "  • ${YELLOW}PROTONVPN_DISCOVERY_RESULTS.md${NC}"
echo ""
