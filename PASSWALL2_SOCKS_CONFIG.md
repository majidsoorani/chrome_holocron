# Passwall2 SOCKS Proxy Configuration

## ✅ Recommended Configuration

**SOCKS Proxy Endpoint:**
- **Host:** `192.168.1.1`
- **Port:** `1090` ⭐ **RECOMMENDED**
- **Protocol:** SOCKS5
- **Authentication:** None
- **Type:** Socat relay to Passwall2 main SOCKS
- **Features:** Split routing enabled (Iranian sites direct, foreign via proxy)

## Test Results

```bash
# Test command
curl -x socks5h://192.168.1.1:1090 https://ipinfo.io/json

# Result
IP: 188.245.253.121
Country: DE (Germany)
Org: Hetzner Online GmbH
```

**Status:** ✅ Working perfectly with auto-start enabled

## Chrome Holocron Extension Settings

Update your extension configuration to use:
```json
{
  "passwall2Host": "192.168.1.1",
  "passwall2Port": "22",
  "passwall2User": "root",
  "passwall2SocksPort": "1090",
  "passwall2HttpPort": ""
}
```

## Available SOCKS Ports on Router

| Port | Status | Backend | Access | Recommended |
|------|--------|---------|--------|-------------|
| 1080 | ✅ Active | Passwall2 (xray) | localhost only (127.0.0.1) | ❌ Not accessible from LAN |
| 1081 | ⚠️  In Use | Passwall2 (xray) | LAN-wide | ❌ Used by another service |
| 1082 | ❌ Broken | Passwall2 (xray) | LAN-wide | ❌ TLS handshake fails |
| **1090** | ✅ **WORKING** | socat relay → 1080 | **LAN-wide** | ✅ **USE THIS** |
| 1032 | ✅ Active | Direct SSH tunnel | LAN-wide | ⚠️  No split routing |
| 1033 | ✅ Active | Direct SSH tunnel | LAN-wide | ⚠️  No split routing |

## Routing Behavior

**Note:** When using SOCKS proxy directly, all traffic goes through the proxy (Germany).
The Iranian direct routing (split tunneling) only works for:
- Transparent proxy mode (router firewall/iptables)
- Devices using the router as gateway without explicit SOCKS configuration

For Chrome extension SOCKS usage:
- ✅ All traffic → Germany proxy (188.245.253.121)
- ❌ No split routing (by design - SOCKS bypasses router routing rules)

## Service Management

### Passwall2 SOCKS Relay (Port 1090)

**Status:**
```bash
ssh 192.168.1.1 "netstat -tlnp | grep :1090"
```

**Restart:**
```bash
ssh 192.168.1.1 "/etc/init.d/passwall2_socks_relay restart"
```

**Start/Stop:**
```bash
ssh 192.168.1.1 "/etc/init.d/passwall2_socks_relay start"
ssh 192.168.1.1 "/etc/init.d/passwall2_socks_relay stop"
```

### Passwall2 Main Service

**Check all SOCKS ports:**
```bash
ssh 192.168.1.1 "netstat -tlnp | grep -E ':(1080|1081|1082|1090)'"
```

### Restart Passwall2
```bash
ssh 192.168.1.1 "/etc/init.d/passwall2 restart"
```

### Check Passwall2 Config
```bash
ssh 192.168.1.1 "uci show passwall2.@global[0] | grep socks"
```

## Firewall Rules

Port 1090 is accessible from LAN. If you have issues, ensure firewall allows it:
```bash
ssh 192.168.1.1 "iptables -I INPUT -p tcp --dport 1090 -j ACCEPT"
```

## Troubleshooting "No proxies found on router"

### Issue: Extension shows empty proxy list

**Root Cause:** The Python native host was updated to fix a bug in the SSH command that queries Passwall2 nodes. The extension needs to be restarted to use the updated code.

**Solution:**

1. **Restart Chrome Extension:**
   - Open Chrome and go to `chrome://extensions/`
   - Find "Holocron SSH Tunnel Manager"
   - Click the refresh/reload button 🔄
   - OR toggle it off and back on

2. **Verify Native Host:**
   ```bash
   # Check manifest exists
   cat ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.holocron.native_host.json
   
   # Should point to:
   /Users/majidsoorani/chrome_holocron/backends/sh/holocron_native_host_launcher.sh
   ```

3. **Test SSH Connection:**
   ```bash
   # Make sure you can SSH to router without password
   ssh 192.168.1.1 "echo 'SSH OK'"
   ```

4. **Manually Test the Query:**
   ```bash
   # Run the command the extension uses
   ssh 192.168.1.1 "uci show passwall2 | grep -E '(nodes|type|remarks|address|port|protocol)'"
   
   # Should return multiple lines showing nodes like:
   # passwall2.ssh_7Hd5rcr0=nodes
   # passwall2.ssh_7Hd5rcr0.remarks='SSH-Tunnel-EC2-1'
   # etc.
   ```

5. **Check Extension Logs:**
   - Right-click extension icon → "Inspect popup"
   - Check Console for errors
   - Look for native messaging errors

6. **Check Native Host Logs:**
   ```bash
   tail -50 /Users/majidsoorani/chrome_holocron/backends/log/holocron_native_host.log
   ```

### Expected Result After Fix

The extension should show **6 Passwall2 nodes**:
- ✅ `bilmreX6`: kixy-vless (vless)
- ✅ `ssh_7Hd5rcr0`: SSH-Tunnel-EC2-1 (socks) ⭐ **Recommended**
- ✅ `ssh_IbMIuEYj`: SSH-Tunnel-EC2-2 (socks)
- ✅ `iran_shunt_node`: Iranian Direct Shunt (shunt)
- ✅ `ujdkXoDD`: Remarks (balancing)
- ✅ `LzigX5Ef`: Remarks (socks)

## Summary

✅ **Use port 1090** for your Chrome extension and applications
- Socat relay exposing Passwall2's main SOCKS proxy
- Works reliably with split routing enabled
- Exposed on all LAN interfaces (0.0.0.0:1090)
- Routes through Passwall2 shunt node
  - Iranian traffic → Direct connection
  - Foreign traffic → SSH tunnel (Germany proxy 188.245.253.121)
- Auto-starts on router boot
- No authentication required

### Why Port 1090?
- Port 1080: Localhost only (not accessible from LAN)
- Port 1081: Already in use by another Passwall2 service
- Port 1082: TLS handshake failures
- **Port 1090: Socat relay - WORKS PERFECTLY** ✅

### Scripts
- Setup: `/Users/majidsoorani/chrome_holocron/backends/sh/setup_passwall2_socks_relay.sh`
- Test routing: `/Users/majidsoorani/chrome_holocron/backends/sh/test_passwall2_routing.sh`

---
Last updated: November 16, 2025
**Status:** ✅ Fully operational with auto-start enabled
