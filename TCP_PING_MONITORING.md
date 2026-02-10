# TCP Ping Monitoring for All Configurations

## Overview

The extension now continuously monitors TCP ping latency for all enabled proxy configurations and displays real-time measurements in the Core Configurations section. This feature works alongside the Auto-Select Best Proxy feature to provide comprehensive performance visibility.

## Features

### 1. **Continuous Latency Monitoring**
- Automatically measures TCP ping for all enabled configurations every 2 minutes
- Tests both running tunnel-based proxies (SSH, V2Ray, OpenVPN) and external proxies
- Updates background script state with latest measurements

### 2. **Real-Time UI Display**
- Shows TCP ping latency for each configuration in the Core Configurations list
- Color-coded latency indicators:
  - **Green** (< 100ms): Excellent connection
  - **Yellow** (100-299ms): Good connection
  - **Orange** (≥ 300ms): Slow connection
  - **Red** ("Offline"): Connection failed or proxy not running
  - **Gray** ("--"): Not yet measured

### 3. **Live Updates**
- Latency values update automatically without page refresh
- Background script broadcasts latency changes to all open options pages
- Initial latency data loaded when options page opens

## How It Works

### Background Script (background.js)

1. **State Management**
   - `configLatencies` object stores current latency for each configuration ID
   - Format: `{ configId: latencyMs }` where `-1` indicates offline/error

2. **Periodic Checks**
   - `updateConfigLatencies()` function runs every 2 minutes via Chrome alarm
   - Tests all enabled configurations in parallel for efficiency
   - For tunnel-based proxies: Uses GET_STATUS command to check if running
   - For external proxies: Tests directly with tcpPing command

3. **Broadcasting**
   - `broadcastLatencies()` sends LATENCIES_UPDATED message to listeners
   - Runs after each measurement cycle completes

### Options Page (options.js)

1. **Message Listener**
   - Listens for LATENCIES_UPDATED commands from background script
   - Calls `updateLatencyDisplay()` to refresh UI

2. **Display Function**
   - `updateLatencyDisplay(latencies)` updates TCP Ping value for each config card
   - Applies color coding based on latency thresholds
   - Handles offline/error states gracefully

3. **Initial Load**
   - Sends GET_LATENCIES command when page loads
   - Populates initial latency values from background script state

## Technical Details

### New Commands (constants.js)
```javascript
COMMANDS.LATENCIES_UPDATED  // Broadcast from background to options page
COMMANDS.GET_LATENCIES      // Request current latencies from background
```

### Chrome Alarm Configuration
```javascript
chrome.alarms.create('latency-check', { periodInMinutes: 2 });
```

### Latency Measurement Logic

**For Tunnel-Based Proxies (SSH, V2Ray, OpenVPN, OpenWrt):**
1. Check if tunnel is running via GET_STATUS command
2. If not connected, set latency to `-1` (offline)
3. If connected, use TCP ping value from status response

**For External Proxies (SOCKS/HTTP):**
1. Test directly with tcpPing command
2. Use configured proxy host, port, and protocol
3. Measure latency through the proxy to ping host (default: youtube.com)

### Error Handling
- Network errors set latency to `-1`
- Invalid configurations show as "Offline"
- No latency data shows as "--" (not yet measured)
- Silent failures logged to console for debugging

## Usage

### Viewing Latencies

1. Open the extension's Options page
2. Navigate to the "Core Configurations" section
3. Each configuration card shows current TCP ping under "TCP Ping" metric
4. Values update automatically every 2 minutes

### Interpreting Results

- **Low latency (< 100ms)**: Optimal for general browsing and streaming
- **Medium latency (100-299ms)**: Acceptable for most use cases
- **High latency (≥ 300ms)**: May cause noticeable delays
- **Offline**: Proxy not running or unreachable

### Integration with Auto-Select

When "Auto-Select Best Proxy" is enabled:
1. Background script uses `configLatencies` data
2. Only tests proxies that are already running (preserves port mappings)
3. Selects proxy with lowest latency
4. Continuous monitoring ensures up-to-date selection criteria

## Configuration

### Adjusting Check Frequency

Edit `background.js` alarm creation:
```javascript
// Default: every 2 minutes
chrome.alarms.create('latency-check', { periodInMinutes: 2 });

// More frequent: every 1 minute
chrome.alarms.create('latency-check', { periodInMinutes: 1 });

// Less frequent: every 5 minutes
chrome.alarms.create('latency-check', { periodInMinutes: 5 });
```

### Changing Color Thresholds

Edit `options.js` in `updateLatencyDisplay()`:
```javascript
// Current thresholds
if (latency < 100) {
  tcpPingValueElement.style.color = '#28a745'; // Green
} else if (latency < 300) {
  tcpPingValueElement.style.color = '#ffc107'; // Yellow
} else {
  tcpPingValueElement.style.color = '#fd7e14'; // Orange
}
```

## Performance Considerations

### Resource Usage
- **CPU**: Minimal - runs every 2 minutes
- **Network**: Lightweight TCP ping packets only
- **Memory**: Stores one latency value per enabled configuration

### Optimization Features
- Parallel testing of all configurations
- Only tests enabled configurations
- Reuses existing GET_STATUS calls for tunnel-based proxies
- Silent error handling prevents UI freezing

## Troubleshooting

### Latencies Show as "--"
- **Cause**: Background script hasn't run initial check yet
- **Solution**: Wait 2 minutes or reload extension

### Latencies Show as "Offline" for Running Proxy
- **Cause**: TCP ping failing through proxy
- **Check**:
  1. Verify ping host is accessible (default: youtube.com)
  2. Check proxy is actually connected (try manual test)
  3. Review native host logs for errors

### Latencies Not Updating
- **Cause**: Message channel broken or options page not receiving updates
- **Solution**:
  1. Close and reopen options page
  2. Check browser console for errors
  3. Reload extension

### High Latency on All Proxies
- **Cause**: Network congestion or ping host issues
- **Check**:
  1. Test with different ping host
  2. Check your internet connection
  3. Try manual test button for comparison

## Files Modified

### New Files
- `TCP_PING_MONITORING.md` - This documentation

### Modified Files
- `background.js`:
  - Added `configLatencies` state variable
  - Added `updateConfigLatencies()` function
  - Added `broadcastLatencies()` function
  - Added GET_LATENCIES message handler
  - Modified onStartup to trigger initial check
  - Added latency-check alarm
  - Added alarm handler for latency checks

- `options.js`:
  - Added `updateLatencyDisplay()` function
  - Modified message listener to handle LATENCIES_UPDATED
  - Added GET_LATENCIES request on page load

- `constants.js`:
  - Added `LATENCIES_UPDATED` command
  - Added `GET_LATENCIES` command

## Future Enhancements

Potential improvements for future versions:

1. **User-Configurable Check Interval**
   - Add setting in options page
   - Store in chrome.storage.sync
   - Allow 1-10 minute intervals

2. **Latency History Graph**
   - Track latency over time per configuration
   - Display trends in Connection Health History section
   - Show min/max/average values

3. **Alert Thresholds**
   - Notify when latency exceeds threshold
   - Auto-disable slow proxies
   - Badge indicator for degraded performance

4. **Manual Refresh Button**
   - Trigger immediate latency check
   - Show loading indicator during test
   - Useful for troubleshooting

5. **Latency-Based Sorting**
   - Sort configurations by speed
   - Quick access to fastest proxy
   - Visual ranking indicators

## Related Documentation

- [AUTO_SELECT_BEST_PROXY.md](./AUTO_SELECT_BEST_PROXY.md) - Auto-selection feature
- [README.md](./README.md) - Main extension documentation
- [BUSINESS_GUIDE.md](./BUSINESS_GUIDE.md) - Business logic overview
