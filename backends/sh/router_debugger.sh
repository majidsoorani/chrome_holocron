#!/bin/sh
# Router Diagnostic Tool
# This script runs diagnostics directly on the OpenWrt router.

echo "======================================================================"
echo " DIAGNOSTIC REPORT: $(date)"
echo "======================================================================"

echo "--- 1. CPU LOAD & UPTIME ---"
uptime
echo "Load average: $(cat /proc/loadavg)"
echo ""

echo "--- 2. MEMORY UTILIZATION ---"
free -m
echo ""

echo "--- 3. PROCESS RESOURCE USAGE (xray/sing-box) ---"
ps | grep -E '/tmp/etc/passwall2/bin/(xray|sing-box)' | grep -v grep || echo "No Passwall2 core processes running."
echo ""

echo "--- 4. MWAN3 MULTI-WAN INTERFACE STATUS ---"
if command -v mwan3 >/dev/null 2>&1; then
    mwan3 status | grep -E -A 2 "Interface .* is" || mwan3 status
else
    echo "mwan3 is not installed or not in PATH."
fi
echo ""

echo "--- 5. ACTIVE WAN ROUTING ---"
ip route show | grep default
echo ""

echo "--- 6. INTERFACE LATENCY CHECKS (Ping to 8.8.8.8) ---"
# Check latency through each modem interface if it exists and is UP
for iface in wan lan3 wl0-sta0 wl1-sta0; do
    if ip link show "$iface" 2>/dev/null | grep -q "UP"; then
        # Resolve the IPv4 address assigned to this interface
        iface_ip=$(ip -4 addr show dev "$iface" 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -n 1)
        if [ -n "$iface_ip" ]; then
            # Ping 8.8.8.8 binding to the resolved source IP
            ping_out=$(ping -I "$iface_ip" -c 2 -W 3 8.8.8.8 2>/dev/null)
            if [ $? -eq 0 ]; then
                avg_latency=$(echo "$ping_out" | tail -n 1 | awk -F'/' '{print $5}' | tr -cd '0-9.')
                echo "Interface $iface ($iface_ip): Connected (Latency: ${avg_latency}ms)"
            else
                echo "Interface $iface ($iface_ip): Connection FAILED / LOSS"
            fi
        else
            echo "Interface $iface: Link UP but no IP address assigned"
        fi
    else
        echo "Interface $iface: Link is DOWN or device not present"
    fi
done
echo ""

echo "--- 7. DNS RESOLUTION SPEED ---"
# Test DNS lookup speed using nslookup
dns_time=$( { time nslookup www.google.com >/dev/null; } 2>&1 | grep real )
echo "DNS resolution time: $dns_time"
echo "======================================================================"
