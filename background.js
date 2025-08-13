// This is a background service worker for the extension.

importScripts('constants.js', 'iran_ip_ranges.js');
const NATIVE_HOST_NAME = 'com.holocron.native_host';

let lastStatus = { connected: false }; // Store the last known status
let isUpdateInProgress = false; // A flag to prevent concurrent updates.

function broadcastStatus() {
  // Send the latest status to any listeners (like the popup).
  // This allows the UI to be updated in real-time.
  chrome.runtime.sendMessage({ command: COMMANDS.STATUS_UPDATED, status: lastStatus }).catch(e => {
    // This can error if no popup is open to receive the message. We can safely ignore it.
    if (e.message !== "Could not establish connection. Receiving end does not exist.") {
      console.warn("Error broadcasting status:", e.message);
    }
  });
}

/**
 * Generates a dynamic circular icon based on ping latency.
 * The icon is a progress-style circle that goes from green (low ping) to red (high ping).
 * @param {number} ping - The latency in milliseconds.
 * @param {number} webLatency - The latency from the full web check (for the inner circle).
 * @param {number} tcpLatency - The latency from the TCP ping (for the outer circle).
 * @param {number} size - The desired icon size (e.g., 16, 32, 48).
 * @returns {ImageData} The generated icon data for the specified size.
 */
function generatePingIcon(webLatency, tcpLatency, size) {
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext('2d');

  const MIN_PING = 100; // ms, at or below this is 100% green
  const MAX_PING = 1000; // ms, at or above this is 10% red

  const calculateParams = (ping) => {
    if (ping === -1 || typeof ping === 'undefined') {
      return { percentage: 0, color: 'hsl(0, 0%, 50%)' }; // Grey for failure
    }
    let progress = 0;
    if (ping > MIN_PING) {
      progress = (Math.min(ping, MAX_PING) - MIN_PING) / (MAX_PING - MIN_PING);
    }
    const percentage = 1.0 - (progress * 0.9);
    const hue = 120 - (progress * 120);
    const color = `hsl(${hue}, 100%, 50%)`;
    return { percentage, color };
  };

  const webParams = calculateParams(webLatency);
  const tcpParams = calculateParams(tcpLatency);

  // --- Drawing ---
  const center = size / 2;
  const startAngle = -0.5 * Math.PI; // 12 o'clock

  // --- Outer Circle (Web Latency) ---
  const outerRadius = size * 0.4;
  const outerLineWidth = size * 0.18;
  // Background
  ctx.strokeStyle = 'rgba(128, 128, 128, 0.3)';
  ctx.lineWidth = outerLineWidth;
  ctx.beginPath();
  ctx.arc(center, center, outerRadius, 0, 2 * Math.PI);
  ctx.stroke();
  // Foreground
  if (webParams.percentage > 0) {
    ctx.strokeStyle = webParams.color;
    ctx.lineCap = 'round';
    ctx.beginPath();
    const webEndAngle = startAngle + (webParams.percentage * 2 * Math.PI);
    ctx.arc(center, center, outerRadius, startAngle, webEndAngle);
    ctx.stroke();
  }

  // --- Inner Circle (TCP Ping) ---
  const innerRadius = size * 0.20;
  const innerLineWidth = size * 0.15;
  // Background
  ctx.strokeStyle = 'rgba(128, 128, 128, 0.3)';
  ctx.lineWidth = innerLineWidth;
  ctx.beginPath();
  ctx.arc(center, center, innerRadius, 0, 2 * Math.PI);
  ctx.stroke();
  // Foreground
  if (tcpParams.percentage > 0) {
    ctx.strokeStyle = tcpParams.color;
    ctx.lineCap = 'round';
    ctx.beginPath();
    const tcpEndAngle = startAngle + (tcpParams.percentage * 2 * Math.PI);
    ctx.arc(center, center, innerRadius, startAngle, tcpEndAngle);
    ctx.stroke();
  }

  return ctx.getImageData(0, 0, size, size);
}

function setActionIcon(status) {
  const badIcon = { "16": "images/icon16-bad.png", "32": "images/icon32-bad.png", "48": "images/icon48-bad.png" };
  const warnIcon = { "16": "images/icon16-warn.png", "32": "images/icon32-warn.png", "48": "images/icon48-warn.png" };

  // 1. Disconnected or critical failure (e.g., web check status reports failure)
  if (!status || !status.connected || (status.web_check_status && status.web_check_status.includes('Failed'))) {
    chrome.action.setIcon({ path: badIcon });
    return;
  }

  // 2. Connected but one of the latency checks failed (unreliable connection)
  if (status.web_check_latency_ms === -1 || status.tcp_ping_ms === -1) {
    chrome.action.setIcon({ path: warnIcon });
    return;
  }

  // 3. Connected with valid latencies: generate dynamic icon
  const imageData = {
    16: generatePingIcon(status.web_check_latency_ms, status.tcp_ping_ms, 16),
    32: generatePingIcon(status.web_check_latency_ms, status.tcp_ping_ms, 32),
    48: generatePingIcon(status.web_check_latency_ms, status.tcp_ping_ms, 48)
  };
  chrome.action.setIcon({ imageData: imageData });
}

/**
 * Centralized function to update the extension's state, icon, and broadcast to listeners.
 * @param {object} newStatus - The new status object, e.g., { connected: false }.
 * @param {string|null} errorMessage - An optional error message to log for debugging.
 */
async function updateStateAndBroadcast(newStatus, errorMessage = null) {
  if (errorMessage) {
    // Use console.error for actual errors, console.log for informational messages.
    newStatus.connected ? console.log(errorMessage) : console.error(errorMessage);
  }
  lastStatus = newStatus;

  // Automatically clear the browser proxy if the tunnel disconnects while managed.
  const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManagedByHolocron } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
  if (isProxyManagedByHolocron && !newStatus.connected) {
    console.log("Tunnel disconnected. Automatically clearing browser proxy.");
    const { [STORAGE_KEYS.ORIGINAL_PROXY]: originalProxySettings } = await chrome.storage.local.get(STORAGE_KEYS.ORIGINAL_PROXY);
    if (originalProxySettings) {
      await chrome.proxy.settings.set({ value: originalProxySettings, scope: 'regular' });
    } else {
      // Fallback to clearing if no original settings were found.
      await chrome.proxy.settings.clear({ scope: 'regular' });
    }
    await chrome.storage.local.remove([STORAGE_KEYS.ORIGINAL_PROXY, STORAGE_KEYS.IS_PROXY_MANAGED]);
    console.log("Browser proxy restored to original settings.");
    // Add the cleared status to the broadcast so the UI can update.
    lastStatus.proxyCleared = true;
  }

  setActionIcon(newStatus);
  broadcastStatus();
}

/**
 * Sends a message to the native host and returns its response.
 * This is a centralized function for all native host communication.
 * @param {object} message The message object to send to the native host.
 * @returns {Promise<object>} A promise that resolves with the response.
 */
function communicateWithNativeHost(message) {
  return new Promise((resolve, reject) => {
    try {
      const port = chrome.runtime.connectNative(NATIVE_HOST_NAME);
      let responseReceived = false;
 
      port.onMessage.addListener((response) => {
        responseReceived = true;
        resolve(response);
        port.disconnect();
      });
 
      port.onDisconnect.addListener(() => {
        if (chrome.runtime.lastError) {
          reject(new Error(`Native host disconnected: ${chrome.runtime.lastError.message}`));
        } else if (!responseReceived) {
          reject(new Error("Connection closed by native host without a response. Check native script logs for errors."));
        }
      });
 
      port.postMessage(message);
    } catch (e) {
      reject(new Error(`Failed to connect to native host: ${e.message}`));
    }
  });
}

async function updateStatus() {
  if (isUpdateInProgress) {
    console.log("Update check already in progress. Skipping.");
    return;
  }
  isUpdateInProgress = true;

  const {
    [STORAGE_KEYS.SSH_COMMAND_ID]: sshCommandIdentifier,
    [STORAGE_KEYS.PING_HOST]: pingHost,
    [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrl
  } = await chrome.storage.sync.get({
    [STORAGE_KEYS.SSH_COMMAND_ID]: '',
    [STORAGE_KEYS.PING_HOST]: 'youtube.com', // Default value
    [STORAGE_KEYS.WEB_CHECK_URL]: 'https://gemini.google.com/app'
  });

  if (!sshCommandIdentifier) {
    console.log("SSH command identifier not set. Please configure it in the options.");
    updateStateAndBroadcast({ connected: false });
    isUpdateInProgress = false;
    return;
  }

  try {
    const response = await communicateWithNativeHost({
      command: COMMANDS.GET_STATUS,
      sshCommandIdentifier,
      pingHost,
      webCheckUrl
    });
    updateStateAndBroadcast(response && response.connected ? response : { connected: false });
  } catch (error) {
    const errorMessage = `Error during status update for command "${sshCommandIdentifier}": ${error.message}`;
    updateStateAndBroadcast({ connected: false }, errorMessage);
  } finally {
    isUpdateInProgress = false;
  }
}

// Perform an initial check on browser startup.
chrome.runtime.onStartup.addListener(updateStatus);

// Set up the alarm and perform an initial check when the extension is installed.
chrome.runtime.onInstalled.addListener((details) => {
  chrome.alarms.create('status-check', { periodInMinutes: 1 });

  // On first install, open the options page to prompt the user for configuration.
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    chrome.runtime.openOptionsPage();
  }
  updateStatus();
});

// Listen for the alarm to trigger subsequent checks.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'status-check') {
    updateStatus();
  }
});

// Listen for requests from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.command === COMMANDS.GET_POPUP_STATUS) {
    sendResponse(lastStatus);
    updateStatus();
    return true; // Keep message channel open for an async response.
  }

  if (request.command === COMMANDS.SET_BROWSER_PROXY) {
    (async () => {
      const { socksPort } = request;
      if (!socksPort) {
        sendResponse({ success: false, message: "SOCKS port not provided." });
        return;
      }
      try {
        // Get user setting for GeoIP bypass
        const { [STORAGE_KEYS.GEOIP_BYPASS_ENABLED]: geoIpBypassEnabled } = await chrome.storage.sync.get({
          [STORAGE_KEYS.GEOIP_BYPASS_ENABLED]: true // Default to enabled
        });

        // Store original settings before changing them.
        const originalSettings = await chrome.proxy.settings.get({ incognito: false });

        // --- Create a PAC script for advanced routing ---
        // This allows for conditional proxying, such as bypassing specific domains.
        let pacScript = `
function FindProxyForURL(url, host) {
  // 1. Bypass requests to Iranian top-level domains (.ir)
  if (shExpMatch(host, "*.ir")) {
    return "DIRECT";
  }

  // 2. Bypass localhost and other local addresses
  if (isPlainHostName(host) || shExpMatch(host, "localhost") || shExpMatch(host, "127.0.0.1")) {
    return "DIRECT";
  }
`;

        if (geoIpBypassEnabled) {
          // Inject the GeoIP check logic and the IP ranges into the PAC script
          pacScript += `
  // 3. GeoIP check for Iran. This may introduce a small latency for DNS resolution.
  try {
    const ip = dnsResolve(host);
    if (ip) {
      const ranges = ${JSON.stringify(IRAN_IP_RANGES_NETMASK)};
      for (let i = 0; i < ranges.length; i++) {
        if (isInNet(ip, ranges[i][0], ranges[i][1])) {
          return "DIRECT";
        }
      }
    }
  } catch (e) {
    // dnsResolve can fail for some hosts, fall through to proxy.
  }
`;
        }

        pacScript += `
  // Final step: For all other traffic, use the SOCKS proxy.
  return "SOCKS5 127.0.0.1:${socksPort}";
}`;

        const config = {
          mode: "pac_script",
          pacScript: { data: pacScript }
        };

        await chrome.proxy.settings.set({ value: config, scope: 'regular' });
        // Set flag and store original settings AFTER successfully setting the new proxy.
        await chrome.storage.local.set({
          [STORAGE_KEYS.IS_PROXY_MANAGED]: true,
          [STORAGE_KEYS.ORIGINAL_PROXY]: originalSettings.value
        });
        sendResponse({ success: true, message: "Browser proxy set." });
      } catch (e) {
        sendResponse({ success: false, message: `Failed to set proxy: ${e.message}` });
      }
    })();
    return true;
  }

  if (request.command === COMMANDS.CLEAR_BROWSER_PROXY) {
    (async () => {
      try {
        const { [STORAGE_KEYS.ORIGINAL_PROXY]: originalProxySettings } = await chrome.storage.local.get(STORAGE_KEYS.ORIGINAL_PROXY);
        await chrome.proxy.settings.set({ value: originalProxySettings || { mode: "direct" }, scope: 'regular' });
        await chrome.storage.local.remove([STORAGE_KEYS.ORIGINAL_PROXY, STORAGE_KEYS.IS_PROXY_MANAGED]);
        sendResponse({ success: true, message: "Browser proxy restored." });
      } catch (e) {
        sendResponse({ success: false, message: `Failed to clear proxy: ${e.message}` });
      }
    })();
    return true;
  }

  // Listener for the new test connection feature from the options page.
  if (request.command === COMMANDS.TEST_CONNECTION) {
    (async () => {
      const { sshCommand, pingHost, webCheckUrl } = request;
      if (!sshCommand) {
        sendResponse({ success: false, message: "SSH Command Identifier cannot be empty." });
        return;
      }
      if (!pingHost) {
        sendResponse({ success: false, message: "Ping Host cannot be empty." });
        return;
      }
      try {
        const response = await communicateWithNativeHost({
          command: COMMANDS.GET_STATUS,
          sshCommandIdentifier: sshCommand, // Map from options page key
          pingHost,
          webCheckUrl
        });
        let message;
        if (response && response.connected) {
          message = `Success! Web Latency: ${response.web_check_latency_ms}ms, TCP Ping: ${response.tcp_ping_ms}ms. Site Status: ${response.web_check_status}`;
        } else if (response) {
          message = `Host connected, but tunnel is down. Direct TCP Ping: ${response.tcp_ping_ms}ms.`;
        } else {
          message = "Host connected, but reports tunnel is down.";
        }
        sendResponse({ success: true, message: message });
      } catch (error) {
        sendResponse({ success: false, message: error.message });
      }
    })();
    return true; // Indicate async response.
  }

  // Listeners for tunnel control
  if (request.command === COMMANDS.START_TUNNEL || request.command === COMMANDS.STOP_TUNNEL) {
    (async () => {
      try {
        let config = null;
        // Only fetch and send config for the 'start' command
        if (request.command === COMMANDS.START_TUNNEL) {
          const settings = await chrome.storage.sync.get([
            STORAGE_KEYS.SSH_USER,
            STORAGE_KEYS.SSH_HOST,
            STORAGE_KEYS.PORT_FORWARDS,
            STORAGE_KEYS.SSH_COMMAND_ID,
            STORAGE_KEYS.WIFI_SSIDS
          ]);
          config = settings;
        }

        const response = await communicateWithNativeHost({
          command: request.command,
          config: config
        });

        sendResponse(response);

        // After a start/stop attempt, trigger a status update to refresh the UI.
        if (response.success && response.already_running) {
          // If it was already running, we can update the status immediately.
          updateStatus();
        } else {
          // Otherwise, a small delay gives the SSH process time to start/stop before we check.
          setTimeout(updateStatus, 1500);
        }
      } catch (error) {
        sendResponse({ success: false, message: error.message });
      }
    })();
    return true; // Indicate async response.
  }
  return false; // Explicitly return false for other messages.
});