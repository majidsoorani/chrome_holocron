# Auto-Select Best Proxy Feature

## Overview
This feature allows Holocron to automatically test multiple enabled proxies using TCP ping and connect to the one with the lowest latency. This ensures you always get the fastest available connection when multiple proxy options are configured.

## How It Works

### 1. Configuration
- Navigate to the **Connections & Health** tab in the options page
- Enable the **"Auto-Select Best Proxy"** checkbox under "Automatic Connection"
- Ensure you have **multiple proxy configurations enabled**

### 2. Proxy Testing Process
When you click connect (or auto-reconnect triggers), the following happens:

1. **Detection**: If more than one proxy is enabled and auto-select is on, the system tests all enabled proxies
2. **Running Check**: For tunnel-based proxies (SSH, V2Ray, OpenVPN), only tests those that are **already running**
3. **TCP Ping**: Each running proxy is tested with a TCP ping to the configured ping host (default: youtube.com)
4. **Selection**: The proxy with the lowest latency is selected
5. **Connection**: If a better proxy is found, switches to it; otherwise keeps current connection
6. **Fallback**: If no running proxy responds, falls back to sequential connection attempts

### Important: Port Mapping Preservation

**The auto-select feature only tests proxies that are ALREADY RUNNING.** This means:
- Your WiFi SSID-to-port mappings remain unchanged
- If you configured a specific proxy for a WiFi network, that proxy must be running first
- The feature won't start new tunnels, it only selects among active ones
- External proxies are always tested (they don't need to be "started")

### 3. Supported Proxy Types

#### External Proxies
- Tested directly without needing to start a tunnel
- Tests the configured proxy host and port

#### SSH Proxies
- Tests the SOCKS port from Dynamic port forwarding (-D) rules
- Must have at least one -D rule configured

#### V2Ray Proxies
- Tests the default SOCKS port (10808)
- No additional configuration needed

#### OpenVPN/Other Types
- Currently not testable without starting the tunnel
- Will use sequential connection method

### 4. Performance Benefits

- **Faster Initial Connection**: Automatically finds the fastest proxy without manual testing
- **Better Performance**: Always uses the lowest-latency proxy available
- **Automatic Failover**: If the fastest proxy fails, tries the next best option

## Technical Details

### Background Script Enhancement
The `tryToConnectToEnabledConfigs()` function in `background.js` was enhanced to:
- Check the `AUTO_SELECT_BEST_PROXY` setting
- Call `selectBestProxy()` when multiple proxies are enabled
- Test all proxies in parallel for speed
- Sort by latency and select the best one

### New Function: `selectBestProxy()`
```javascript
async function selectBestProxy(configs, pingHost)
```
- Takes an array of enabled proxy configurations
- Tests each proxy via TCP ping
- Returns the configuration with the lowest latency
- Returns null if no proxy responds

### Native Host Support
The native host already supports the `tcpPing` command with the following parameters:
- `host`: The target host to ping
- `proxy_port`: The SOCKS proxy port
- `proxy_host`: The proxy host (default: 127.0.0.1)
- `proxy_protocol`: The protocol (SOCKS5, SOCKS4, HTTP)

### Storage Key
A new storage key was added to `constants.js`:
```javascript
AUTO_SELECT_BEST_PROXY: 'autoSelectBestProxy'
```

## User Interface

### Options Page
Location: **Connections & Health** > **Automatic Connection**

New checkbox:
```
☐ Auto-Select Best Proxy
  When multiple proxies are enabled, test TCP ping and connect to the fastest one.
```

### Behavior
- Default: **Disabled** (preserves existing behavior)
- When enabled: Tests all proxies and selects the fastest
- When disabled: Uses sequential connection (first enabled proxy that works)

## Usage Examples

### Example 1: Multiple External Proxies
1. Configure 3 external SOCKS5 proxies in different locations
2. Enable all 3 proxies
3. Enable "Auto-Select Best Proxy"
4. Click connect
5. Result: Automatically connects to the fastest server

### Example 2: Mixed Proxy Types
1. Configure 2 SSH tunnels with -D rules
2. Configure 1 external proxy
3. Enable all 3
4. Enable "Auto-Select Best Proxy"
5. Click connect
6. Result: Tests all 3 and connects to the fastest

### Example 3: Fallback Behavior
1. Configure 3 proxies, but 2 are offline
2. Enable "Auto-Select Best Proxy"
3. Click connect
4. Result: Detects only 1 proxy responds, uses that one

## Limitations

1. **OpenVPN/Passwall2**: Cannot be tested without starting the tunnel
2. **Network Overhead**: Testing multiple proxies adds a small delay before connection
3. **Single Ping**: Uses only one TCP ping test (could add averaging in future)

## Future Enhancements

Potential improvements:
- **Continuous Monitoring**: Periodically test and switch to faster proxies
- **Multiple Ping Averaging**: Test each proxy multiple times for accuracy
- **Custom Test Endpoints**: Allow different hosts for different proxy types
- **Latency Thresholds**: Set minimum acceptable latency values
- **Connection Health Scoring**: Combine TCP ping, web check, and historical data

## Troubleshooting

### Auto-select not working
1. Verify multiple proxies are enabled
2. Check that proxies have SOCKS ports configured
3. Look at browser console for error messages

### All proxies showing high latency
1. Check your internet connection
2. Verify ping host is accessible
3. Try a different ping host in settings

### Connects to wrong proxy
1. Disable auto-select temporarily
2. Manually test each proxy to verify latencies
3. Check if proxy configurations are correct

## Configuration Tips

1. **Use reliable ping hosts**: Choose hosts that are always available (e.g., google.com, cloudflare.com)
2. **Enable only working proxies**: Disable broken configurations to speed up testing
3. **Mix proxy types**: Combine external and SSH proxies for best availability
4. **Monitor latency charts**: Use the built-in charts to track proxy performance over time

## Code References

- **Background Script**: `background.js` - lines containing `selectBestProxy()`
- **Options UI**: `options.html` - "Auto-Select Best Proxy" checkbox
- **Options Logic**: `options.js` - loading/saving the setting
- **Constants**: `constants.js` - `AUTO_SELECT_BEST_PROXY` key
- **Native Host**: `holocron_native_host.py` - `tcpPing` command handler
