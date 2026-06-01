#!/bin/sh

echo "=========================================================="
echo "    Rebuilding & Starting Router Services                 "
echo "=========================================================="

# 1. Stop services
echo "[*] Stopping sing-box and holocron_ssh services..."
/etc/init.d/sing-box stop 2>/dev/null || true
/etc/init.d/holocron_ssh stop 2>/dev/null || true

# Kill any stray processes
echo "[*] Killing stray ssh or sing-box instances..."
killall -9 ssh 2>/dev/null || true
killall -9 sing-box 2>/dev/null || true
sleep 1

# 2. Check config compatibility
echo "[*] Checking config.json validity..."
sing-box check -c /etc/sing-box/config.json

# 3. Start SSH Tunnels service
echo "[*] Starting holocron_ssh tunnels..."
/etc/init.d/holocron_ssh enable
/etc/init.d/holocron_ssh restart
sleep 4

# Verify listening SOCKS ports
echo "--- Listening SSH SOCKS Ports ---"
netstat -lntp | grep -E '1032|1033|1034' || echo "No active SSH tunnels found!"
echo "--------------------------------"

# 4. Start Sing-Box service
echo "[*] Starting sing-box service..."
/etc/init.d/sing-box enable
/etc/init.d/sing-box restart
sleep 3

# Verify sing-box process
echo "--- Active Sing-Box Processes ---"
ps | grep -v grep | grep sing-box
echo "--------------------------------"

# 5. Run Verification Tests
echo "=========================================================="
echo "               Connection Diagnostics                     "
echo "=========================================================="

# Test Zitel Tunnel
echo -n "Zitel Tunnel (1032)  -> "
curl -x socks5h://127.0.0.1:1032 -I -s -m 7 -o /dev/null -w 'Status: %{http_code}, Time: %{time_total}s\n' https://www.google.com || echo "Failed"

# Test RighTel Tunnel
echo -n "RighTel Tunnel (1033) -> "
curl -x socks5h://127.0.0.1:1033 -I -s -m 7 -o /dev/null -w 'Status: %{http_code}, Time: %{time_total}s\n' https://www.google.com || echo "Failed"

# Test Mobinnet Tunnel
echo -n "Mobinnet Tunnel (1034)-> "
curl -x socks5h://127.0.0.1:1034 -I -s -m 7 -o /dev/null -w 'Status: %{http_code}, Time: %{time_total}s\n' https://www.google.com || echo "Failed"

# Test Main Balancer Proxy
echo -n "Balancer Proxy (1080) -> "
curl -x socks5h://127.0.0.1:1080 -I -s -m 7 -o /dev/null -w 'Status: %{http_code}, Time: %{time_total}s\n' https://www.google.com || echo "Failed"
echo "=========================================================="
