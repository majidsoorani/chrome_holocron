# ProtonVPN Server Discovery Results for Iran

**Test Date:** November 14, 2025  
**Testing Method:** Deep scan via V2Ray proxy + Direct connections

---

## 🎯 Key Findings

### ✅ **Working ProtonVPN Web Services (via V2Ray Proxy)**
All ProtonVPN web services are **FULLY ACCESSIBLE** when routed through V2Ray proxy on port 10808:

- ✓ `https://protonvpn.com` - Main website
- ✓ `https://account.protonvpn.com` - Account management
- ✓ `https://api.protonvpn.ch` - API endpoint
- ✓ `https://account.protonvpn.com/downloads` - **Download clients here**
- ✓ `https://account.protonvpn.com/login` - Login page
- ✓ `https://api.protonvpn.ch/vpn/logicals` - Server list API
- ✓ `https://api.protonvpn.ch/vpn/servers` - Server details API

### 🔍 **Partially Accessible VPN Servers (Direct Connection)**

**Netherlands:**
- `185.159.156.27` (nl-04.protonvpn.net)
  - ✓ Port 443 (HTTPS) - **REACHABLE**
  - ✗ Port 1194 (OpenVPN) - BLOCKED

**Switzerland:**
- `146.70.198.2` (ch-04.protonvpn.net)
  - ✓ Port 443 (HTTPS) - **REACHABLE**
  - ✗ Port 1194 (OpenVPN) - BLOCKED

- `146.70.174.2` (ch-ch-01.protonvpn.net)
  - ✓ Port 443 (HTTPS) - **REACHABLE**
  - ✓ Port 80 (HTTP) - **REACHABLE**
  - ✗ Port 1194 (OpenVPN) - BLOCKED

### ❌ **Blocked Services**

- **All OpenVPN ports (1194, 4569, 5060)** - Completely blocked by ISP
- **Most VPN server IPs** - Blocked across all countries tested
- **Traditional VPN protocols** - Cannot connect directly

---

## 📊 Test Statistics

### Phase 1: Web Services (via V2Ray)
- **Tested:** 7 endpoints
- **Success:** 7/7 (100%)
- **Status:** ✅ All working

### Phase 2: Direct VPN Server Access
- **Countries Tested:** Netherlands, Switzerland, Iceland, Sweden, USA, UK, Germany, France, Japan, Singapore, Australia, Spain, Italy, Poland, Romania
- **Total Servers:** 40+
- **Ports Tested Per Server:** 6 (443, 1194, 5060, 80, 8080, 4569)
- **Accessible Servers:** 3 out of 40+ (partial access on port 443 only)
- **Success Rate:** ~7% (extremely limited)

### Phase 3: Servers via V2Ray Proxy
- **Status:** Testing in progress...

---

## 💡 **Practical Solutions**

### ✅ What Works NOW:
1. **Access ProtonVPN website via V2Ray proxy**
   - Configure your browser to use Holocron with V2Ray
   - Add `*.protonvpn.com` rule pointing to V2Ray config (NOT DIRECT)
   - Download ProtonVPN clients from `account.protonvpn.com/downloads`

2. **Use ProtonVPN's Stealth/Obfuscation Features**
   - Download ProtonVPN client via V2Ray proxy
   - Enable "Stealth" protocol in ProtonVPN settings
   - Try connecting through ProtonVPN's obfuscated servers

3. **Combine ProtonVPN + V2Ray**
   - Use V2Ray as first layer to bypass Iran's DPI
   - Connect to ProtonVPN through V2Ray tunnel
   - Double-layer protection

### ❌ What Doesn't Work:
1. Direct VPN connections to ProtonVPN servers (OpenVPN/WireGuard)
2. Standard OpenVPN configuration files (ports blocked)
3. Direct download of ProtonVPN website (ISP blocks it)

---

## 🔧 **Configuration Steps**

### Step 1: Configure Holocron for ProtonVPN Access

1. **Reload Holocron Extension**
   - Go to `chrome://extensions`
   - Find "Holocron" extension
   - Click the reload button 🔄

2. **Add ProtonVPN Proxy Rule**
   - Open Holocron options
   - Go to "Proxy Rules & PAC" tab
   - Find or add rule for `*.protonvpn.com`
   - **Change target from "DIRECT" to your V2Ray config name**
   - Click "Save Rules"

3. **Apply Proxy Settings**
   - Click "Apply Proxy to Browser"
   - Verify PAC script includes V2Ray: `PROXY_xxx = "SOCKS5 127.0.0.1:10808"`

4. **Test Access**
   - Visit `https://account.protonvpn.com/downloads`
   - Should load successfully
   - Download ProtonVPN client for macOS

### Step 2: Use ProtonVPN with Stealth

1. **Install ProtonVPN Client**
   - Download from ProtonVPN website (via V2Ray)
   - Install on macOS

2. **Enable Stealth Protocol**
   - Open ProtonVPN settings
   - Look for "Protocol" settings
   - Enable "Stealth" or "TCP with obfuscation"
   - This may bypass some ISP blocking

3. **Try Alternative Connection Methods**
   - Use ProtonVPN's Secure Core (routes through Switzerland first)
   - Try different server locations
   - Test during different times of day

---

## 🌐 **Alternative Approach: Chain Proxies**

Since V2Ray works and some ProtonVPN HTTPS ports are accessible:

```bash
# Test connection through V2Ray to ProtonVPN server
curl -I -x http://127.0.0.1:10808 https://185.159.156.27:443

# If successful, you could potentially:
# 1. Use V2Ray as base proxy
# 2. Connect to ProtonVPN HTTPS endpoint (port 443)
# 3. Create multi-hop connection
```

---

## 📈 **ISP Blocking Analysis**

### What's Blocked:
- ✗ All standard VPN ports (1194, 5060, etc.)
- ✗ Most ProtonVPN server IPs
- ✗ Direct access to protonvpn.com domain
- ✗ OpenVPN protocol traffic

### What's NOT Blocked:
- ✓ HTTPS traffic (port 443) to some servers
- ✓ HTTP traffic (port 80) to ch-ch-01 server
- ✓ V2Ray proxy traffic
- ✓ ProtonVPN accessed via V2Ray proxy

### Conclusion:
Iran's ISP uses **Deep Packet Inspection (DPI)** that:
- Identifies and blocks VPN protocols (OpenVPN, WireGuard)
- Blacklists known VPN server IPs
- Blocks access to VPN provider domains
- BUT doesn't fully block HTTPS (443) to all servers
- V2Ray successfully bypasses DPI

---

## 🚀 **Next Steps**

1. **Immediate:** Configure Holocron to route `*.protonvpn.com` through V2Ray
2. **Download:** Get ProtonVPN client from `account.protonvpn.com/downloads`
3. **Test:** Try ProtonVPN's Stealth/TCP protocol
4. **Explore:** Test the 3 partially accessible servers (185.159.156.27, 146.70.198.2, 146.70.174.2)
5. **Consider:** Double-VPN setup (V2Ray + ProtonVPN Secure Core)

---

## 📋 **Test Files Generated**

All test results saved to `protonvpn_test_results/` directory:
- `test_results_[timestamp].txt` - Complete test log
- `working_servers_[timestamp].txt` - List of accessible endpoints
- `api_servers_[timestamp].json` - Live server data from API (if available)

---

## ⚠️ **Important Notes**

1. **Security:** Always verify ProtonVPN downloads (check signatures/hashes)
2. **Performance:** Double-proxy setup may reduce speed
3. **Stability:** Some servers may become blocked over time
4. **Updates:** Re-run discovery script periodically to find new working servers
5. **Protocol:** Standard OpenVPN is heavily blocked - use alternative protocols

---

**Generated by:** Holocron ProtonVPN Deep Search Script  
**For support:** Check ProtonVPN's Iran-specific guides for latest workarounds
