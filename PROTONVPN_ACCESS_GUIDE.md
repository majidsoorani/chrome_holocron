# ProtonVPN Access Troubleshooting Guide

## Current Situation

You've added `*.protonvpn.com` to DIRECT routing in the extension, but ProtonVPN is still not accessible in your browser.

## Root Cause

The issue is **not** with the DIRECT rule configuration. The problem is:

1. **All your proxy servers are currently unreachable** due to ISP blocking:
   - OpenVPN server (149.34.251.138:443) - TIMEOUT
   - SSH server (54.194.139.127:22) - TIMEOUT

2. **When no proxy is working**, the extension may still be trying to route traffic through a broken proxy configuration, blocking all access.

## Solutions

### Solution 1: Disable Proxy Extension (Immediate Access)

**To access ProtonVPN right now:**

1. Go to `chrome://extensions/`
2. Find "Holocron" extension
3. Toggle it **OFF** (disable it)
4. Try accessing ProtonVPN again
5. Once you're connected to ProtonVPN, you can re-enable the extension

### Solution 2: Use "Revert Proxy" Button

If you have the extension active:

1. Open the extension options page
2. Click the **"Revert Proxy"** or **"Disable PAC"** button
3. This will temporarily disable the PAC script routing
4. Access ProtonVPN
5. After connecting, you can re-apply the proxy settings

### Solution 3: Fix Your Proxy Servers First

The permanent solution is to get your proxy servers working:

#### Option A: Test with Mobile Hotspot
1. Connect your Mac to mobile hotspot
2. Test if the VPN servers become reachable
3. If yes, the problem is ISP blocking

#### Option B: Use Different Server IPs
1. Your current servers are blocked by your ISP
2. You need to set up new proxy servers on different IP addresses
3. Update your extension configurations with the new servers

#### Option C: Add ProtonVPN as External Proxy
If you can get ProtonVPN working:

1. In Holocron extension options
2. Add a new configuration
3. Type: **"External Proxy"**
4. Configure ProtonVPN's SOCKS5 proxy details
5. Enable it
6. This way Holocron will route traffic through ProtonVPN

### Solution 4: Verify DIRECT Rule is Applied

To make sure your DIRECT rule is working when proxies are active:

1. Open Holocron extension options
2. Go to **"Proxy Rules & PAC"** tab
3. Look for your `*.protonvpn.com` rule
4. Verify:
   - ✅ Rule is **enabled** (checkbox checked)
   - ✅ Domain is `*.protonvpn.com`
   - ✅ Target is set to **"DIRECT"**
5. Click **"Apply Proxy to Browser"** to reload PAC script

## Understanding DIRECT Rules

- **DIRECT** means: "Don't use any proxy for this domain"
- Even with DIRECT, you still need a working internet connection
- If your ISP blocks the domain directly, DIRECT won't help
- DIRECT only bypasses your configured proxies

## Check if ProtonVPN is Blocked by Your ISP

Run this test:

```bash
# Test if you can reach ProtonVPN servers directly
ping -c 3 protonvpn.com

# Test if DNS resolves
nslookup protonvpn.com

# Test HTTPS connectivity
curl -I https://protonvpn.com --max-time 5
```

If these fail even with the extension disabled, your ISP is blocking ProtonVPN directly.

## Next Steps

1. **Immediate**: Disable the extension to access ProtonVPN
2. **Short-term**: Connect to ProtonVPN first, then use Holocron through it
3. **Long-term**: Get working proxy servers that aren't blocked by your ISP

## Still Not Working?

If ProtonVPN is still blocked after disabling the extension:

1. **Your ISP is blocking ProtonVPN directly**
2. You'll need an alternative VPN/proxy to access ProtonVPN
3. Consider:
   - Using a different VPN service that's not blocked
   - Using Tor Browser
   - Using a mobile hotspot
   - Using DNS-over-HTTPS (DoH) - though this won't help with IP blocking

## Summary

- ✅ Your DIRECT rule for `*.protonvpn.com` is probably configured correctly
- ❌ Your proxy servers are not working (ISP blocking)
- ❌ This causes the extension to potentially block all traffic
- ✅ **Solution**: Disable extension temporarily to access ProtonVPN
