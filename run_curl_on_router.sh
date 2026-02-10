#!/bin/bash
#
# Simple script to run curl command on OpenWrt router
# Handles the "Site not reachable" error by executing the command on the router itself
#

# Configuration - UPDATE THESE VALUES
ROUTER_IP="192.168.1.1"        # Your OpenWrt router IP address
ROUTER_USER="root"              # SSH username (usually root)
ROUTER_PORT="22"                # SSH port (default is 22)

# Choose authentication method:
# Option 1: SSH Key (recommended - uncomment the line below)
SSH_KEY="$HOME/.ssh/id_rsa"
SSH_CMD="ssh -i $SSH_KEY -p $ROUTER_PORT -o StrictHostKeyChecking=no $ROUTER_USER@$ROUTER_IP"

# Option 2: Password (uncomment the lines below and comment out SSH_KEY lines above)
# ROUTER_PASSWORD="your_password_here"
# SSH_CMD="sshpass -p '$ROUTER_PASSWORD' ssh -p $ROUTER_PORT -o StrictHostKeyChecking=no $ROUTER_USER@$ROUTER_IP"

# The curl command to execute
CURL_URL="https://bit.ly/apply-cressoft"

echo "=================================================="
echo "Executing curl command on OpenWrt router"
echo "=================================================="
echo "Router: $ROUTER_USER@$ROUTER_IP:$ROUTER_PORT"
echo "URL: $CURL_URL"
echo "=================================================="
echo ""

# Check if router is reachable
echo "Testing router connectivity..."
if ! ping -c 1 -W 2 "$ROUTER_IP" > /dev/null 2>&1; then
    echo "❌ ERROR: Router at $ROUTER_IP is not reachable"
    echo "Please check:"
    echo "  1. Router IP address is correct"
    echo "  2. You are connected to the network"
    echo "  3. Router is powered on"
    exit 1
fi
echo "✅ Router is reachable"
echo ""

# Test SSH connection
echo "Testing SSH connection..."
if ! $SSH_CMD "echo 'SSH OK'" > /dev/null 2>&1; then
    echo "❌ ERROR: Cannot connect via SSH"
    echo "Please check:"
    echo "  1. SSH is enabled on the router"
    echo "  2. Username and password/key are correct"
    echo "  3. SSH port is correct (default: 22)"
    echo ""
    echo "If using SSH key, make sure:"
    echo "  - Key exists at: $SSH_KEY"
    echo "  - Key has correct permissions: chmod 600 $SSH_KEY"
    echo ""
    echo "If using password authentication, install sshpass:"
    echo "  macOS: brew install sshpass"
    exit 1
fi
echo "✅ SSH connection successful"
echo ""

# Execute the curl command on the router
echo "Executing curl command on router..."
echo "Command: curl -L $CURL_URL"
echo ""
echo "Output:"
echo "=================================================="

# Run the command and capture output
OUTPUT=$($SSH_CMD "curl -L '$CURL_URL'" 2>&1)
EXIT_CODE=$?

echo "$OUTPUT"
echo "=================================================="
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Command executed successfully!"
else
    echo "❌ Command failed with exit code: $EXIT_CODE"
    
    # Check for common errors
    if echo "$OUTPUT" | grep -q "not found"; then
        echo ""
        echo "⚠️  curl is not installed on the router"
        echo "Install it with: opkg update && opkg install curl"
    elif echo "$OUTPUT" | grep -q "Could not resolve"; then
        echo ""
        echo "⚠️  DNS resolution failed"
        echo "Check router's internet connection and DNS settings"
    elif echo "$OUTPUT" | grep -q "Connection refused\|Connection timed out"; then
        echo ""
        echo "⚠️  Cannot reach the destination server"
        echo "The router may be behind a firewall or proxy"
    fi
fi

echo ""
echo "=================================================="
echo "Done!"
echo "=================================================="
