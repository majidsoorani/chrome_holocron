// This is a background service worker for the extension.

// --- Constants ---
const NATIVE_HOST_NAME = 'com.holocron.native_host';

const STORAGE_KEYS = {
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
  SSH_COMMAND_ID: 'sshCommandIdentifier',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
};

const COMMANDS = {
  // from other scripts to background
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  TEST_CONNECTION: 'testConnection',
  // from background to other scripts
  STATUS_UPDATED: 'statusUpdated',
  // to native host
  GET_STATUS: 'getStatus',
};

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
 * @param {number} size - The desired icon size (e.g., 16, 32, 48).
 * @returns {ImageData} The generated icon data for the specified size.
 */
function generatePingIcon(ping, size) {
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext('2d');

  const MIN_PING = 100; // ms, at or below this is 100% green
  const MAX_PING = 1000; // ms, at or above this is 10% red

  // Calculate the progress for color and percentage. Progress is 0 for MIN_PING and 1 for MAX_PING.
  let progress = 0;
  if (ping > MIN_PING) {
    progress = (Math.min(ping, MAX_PING) - MIN_PING) / (MAX_PING - MIN_PING);
  }

  // The percentage of the circle to draw, from 100% (1.0) down to 10% (0.1).
  const percentage = 1.0 - (progress * 0.9);

  // The color hue, from green (120) down to red (0).
  const hue = 120 - (progress * 120);
  const color = `hsl(${hue}, 100%, 50%)`;

  // --- Drawing ---
  const center = size / 2;
  const radius = size * 0.4; // Use 40% of the canvas size for the radius
  const lineWidth = size * 0.18; // Use 18% for line width

  // Draw a faint background circle for context
  ctx.strokeStyle = 'rgba(128, 128, 128, 0.3)';
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  ctx.arc(center, center, radius, 0, 2 * Math.PI);
  ctx.stroke();

  // Draw the colored foreground arc
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = 'round';
  ctx.beginPath();
  const startAngle = -0.5 * Math.PI; // Start at the 12 o'clock position
  const endAngle = startAngle + (percentage * 2 * Math.PI);
  ctx.arc(center, center, radius, startAngle, endAngle);
  ctx.stroke();

  return ctx.getImageData(0, 0, size, size);
}

function setActionIcon(status) {
  const badIcon = { "16": "images/icon16-bad.png", "32": "images/icon32-bad.png", "48": "images/icon48-bad.png" };
  const warnIcon = { "16": "images/icon16-warn.png", "32": "images/icon32-warn.png", "48": "images/icon48-warn.png" };

  // 1. Disconnected or critical failure (e.g., web check failed)
  if (!status || !status.connected || (status.web_check_status && status.web_check_status.includes('Failed'))) {
    chrome.action.setIcon({ path: badIcon });
    return;
  }

  // 2. Connected but ping failed (unreliable connection)
  if (status.ping_ms === -1) {
    chrome.action.setIcon({ path: warnIcon });
    return;
  }

  // 3. Connected with a valid ping: generate dynamic icon
  const imageData = {
    16: generatePingIcon(status.ping_ms, 16),
    32: generatePingIcon(status.ping_ms, 32),
    48: generatePingIcon(status.ping_ms, 48)
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
 * Connects to the native host and checks the status for a given command.
 * @param {string} sshCommand The command identifier to check.
 * @returns {Promise<object>} A promise that resolves with the status response from the native host.
 */
function checkNativeHostConnection(sshCommand, pingHost, webCheckUrl) {
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
          reject(new Error("Connection closed by native host without a response. Check native script for errors."));
        }
        // If response was received, the promise is already resolved. No action needed.
      });

      port.postMessage({
        command: COMMANDS.GET_STATUS,
        sshCommand: sshCommand,
        pingHost: pingHost,
        webCheckUrl: webCheckUrl
      });
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
    const response = await checkNativeHostConnection(sshCommandIdentifier, pingHost, webCheckUrl);
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
        // Store original settings before changing them.
        const originalSettings = await chrome.proxy.settings.get({ incognito: false });
        const config = {
          mode: "fixed_servers",
          rules: {
            singleProxy: { scheme: "socks5", host: "127.0.0.1", port: socksPort },
            bypassList: ["<local>"]
          }
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
        const response = await checkNativeHostConnection(sshCommand, pingHost, webCheckUrl);
        const message = (response && response.connected) ? `Success! IP: ${response.ip}, Country: ${response.country}` : "Host connected, but reports tunnel is down.";
        sendResponse({ success: true, message: message });
      } catch (error) {
        sendResponse({ success: false, message: error.message });
      }
    })();
    return true; // Indicate async response.
  }
  return false; // Explicitly return false for other messages.
});