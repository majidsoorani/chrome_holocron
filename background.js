// This is a background service worker for the extension.

import { COMMANDS, STORAGE_KEYS } from './constants.js';
import { IRAN_IP_RANGES_NETMASK } from './iran_ip_ranges.js';

const NATIVE_HOST_NAME = 'com.holocron.native_host';

// --- State Variables ---
let lastStatus = { connected: false }; // Store the last known status
const GEOIP_URL = 'https://cdn.jsdelivr.net/gh/chocolate4u/Iran-sing-box-rules@release/direct/iran.txt'; // For IP ranges (CIDR)
const GEOSITE_URL = 'https://cdn.jsdelivr.net/gh/chocolate4u/Iran-sing-box-rules@release/direct/iran/iran.txt'; // For domains
const GEOIP_UPDATE_COOLDOWN_HOURS = 24;

// --- State Variables ---
let isUpdateInProgress = false; // A flag to prevent concurrent updates.
let lastReconnectAttemptTimestamp = 0; // For throttling auto-reconnect attempts.
const RECONNECT_COOLDOWN_MS = 10000; // 10 seconds

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
 * Converts a CIDR string to an [IP, Netmask] pair for use with isInNet().
 * @param {string} cidr The CIDR string (e.g., "192.168.1.0/24").
 * @returns {Array<string>|null} An array [ip, netmask] or null if invalid.
 */
function cidrToIpNetmask(cidr) {
  try {
    const [ip, prefixStr] = cidr.split('/');
    const prefix = parseInt(prefixStr, 10);
    if (isNaN(prefix) || prefix < 0 || prefix > 32) {
      return null;
    }
    let mask = [];
    for (let i = 0; i < 4; i++) {
      let n = Math.min(prefix - (i * 8), 8);
      n = Math.max(n, 0);
      mask.push(256 - Math.pow(2, 8 - n));
    }
    const netmask = mask.join('.');
    // Basic validation for the IP part
    if (ip.split('.').length !== 4) return null;
    return [ip, netmask];
  } catch (e) {
    return null;
  }
}

/**
 * Fetches the latest GeoIP database for Iran, processes it, and stores it.
 * Includes a cooldown mechanism to avoid fetching too frequently.
 * @param {boolean} force - If true, ignores the cooldown and forces an update.
 */
async function updateGeoIpDatabase(force = false) {
  const { [STORAGE_KEYS.GEOIP_LAST_UPDATE]: lastUpdate } = await chrome.storage.local.get(STORAGE_KEYS.GEOIP_LAST_UPDATE);
  const now = Date.now();

  if (!force && lastUpdate && (now - lastUpdate < GEOIP_UPDATE_COOLDOWN_HOURS * 60 * 60 * 1000)) {
    console.log(`GeoIP database update skipped. Last update was less than ${GEOIP_UPDATE_COOLDOWN_HOURS} hours ago.`);
    return;
  }

  console.log("Fetching updated GeoIP database for Iran from:", GEOIP_URL);
  try {
    const response = await fetch(GEOIP_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

    const text = await response.text();
    const cidrList = text.split('\n').map(line => line.trim()).filter(Boolean);
    const ranges = cidrList.map(cidrToIpNetmask).filter(Boolean);

    await chrome.storage.local.set({ [STORAGE_KEYS.GEOIP_RANGES]: ranges, [STORAGE_KEYS.GEOIP_LAST_UPDATE]: now });
    console.log(`Successfully updated and cached GeoIP database with ${ranges.length} ranges.`);
  } catch (error) {
    console.error("Failed to update GeoIP database:", error.message);
  }
}

/**
 * Fetches the latest GeoSite database for Iran (list of domains) and stores it.
 * @param {boolean} force - If true, ignores the cooldown and forces an update.
 */
async function updateGeoSiteDatabase(force = false) {
  const { [STORAGE_KEYS.GEOSITE_LAST_UPDATE]: lastUpdate } = await chrome.storage.local.get(STORAGE_KEYS.GEOSITE_LAST_UPDATE);
  const now = Date.now();

  if (!force && lastUpdate && (now - lastUpdate < GEOIP_UPDATE_COOLDOWN_HOURS * 60 * 60 * 1000)) {
    console.log(`GeoSite database update skipped. Last update was less than ${GEOIP_UPDATE_COOLDOWN_HOURS} hours ago.`);
    return;
  }

  console.log("Fetching updated GeoSite database for Iran from:", GEOSITE_URL);
  try {
    const response = await fetch(GEOSITE_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

    const text = await response.text();
    const domains = text.split('\n').map(line => line.trim()).filter(Boolean);

    await chrome.storage.local.set({ [STORAGE_KEYS.GEOSITE_DOMAINS]: domains, [STORAGE_KEYS.GEOSITE_LAST_UPDATE]: now });
    console.log(`Successfully updated and cached GeoSite database with ${domains.length} domains.`);
  } catch (error) {
    console.error("Failed to update GeoSite database:", error.message);
  }
}

/**
 * Retrieves the currently connected core SSH configuration from storage.
 * @returns {Promise<object|null>} A promise that resolves with the active configuration object, or null if not found.
 */
async function getCurrentlyConnectedConfig() {
  const {
    [STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID]: activeId
  } = await chrome.storage.local.get(STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID);
  if (!activeId) return null;

  const {
    [STORAGE_KEYS.CORE_CONFIGURATIONS]: configs
  } = await chrome.storage.sync.get(STORAGE_KEYS.CORE_CONFIGURATIONS);
  if (!configs || configs.length === 0) {
    return null;
  }
  return configs.find(c => c.id === activeId) || null;
}

/**
 * Generates a stable, filesystem-safe identifier from a configuration object.
 * This is used for lock files and process identification.
 * @param {object} config The configuration object, must contain `sshHost`.
 * @returns {string|null} A safe identifier or null.
 */
function getIdentifierForConfig(config) {
  if (!config || !config.sshHost) return null;
  // Use the SSH host as the basis for a unique, stable identifier.
  return config.sshHost.replace(/[^a-zA-Z0-9.-]/g, '_');
}
/**
 * Attempts to start a tunnel for a single, specific configuration.
 * @param {object} config The configuration object to connect with.
 * @param {Array<string>} [wifiSsidList=[]] Optional list of SSIDs for condition check.
 * @returns {Promise<object>} A promise that resolves with the response from the native host.
 */
async function attemptConnection(config, wifiSsidList = []) {
    console.log(`Attempting to connect with configuration: "${config.name}"`);
    const identifier = getIdentifierForConfig(config);

    if (!identifier) {
        const message = `Skipping configuration "${config.name}" because it has an invalid or empty SSH Host.`;
        console.warn(message);
        return { success: false, message: message };
    }

    const configPayload = {
        // Use legacy keys because the python script expects them.
        id: config.id, // Pass the ID for state management
        sshUser: config.sshUser,
        sshHost: config.sshHost,
        sshCommandIdentifier: identifier,
        sshRemoteCommand: config.sshRemoteCommand,
        portForwards: config.portForwards || [],
        wifiSsidList: wifiSsidList,
    };

    const response = await communicateWithNativeHost({ command: COMMANDS.START_TUNNEL, config: configPayload });
    if (response.success) {
        console.log(`Successfully connected with configuration: "${config.name}"`);
        await chrome.storage.local.set({ [STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID]: config.id });
    }
    return response;
}


/**
 * Iterates through enabled configurations and attempts to start a tunnel,
 * stopping at the first successful connection.
 * @returns {Promise<object>} A promise that resolves with the response from the native host.
 */
async function tryToConnectToEnabledConfigs() {
    const { [STORAGE_KEYS.CORE_CONFIGURATIONS]: configs } = await chrome.storage.sync.get(STORAGE_KEYS.CORE_CONFIGURATIONS);
    if (!configs || configs.length === 0) {
        return { success: false, message: "No configurations defined." };
    }

    const enabledConfigs = configs.filter(c => c.enabled);
    if (enabledConfigs.length === 0) {
        return { success: false, message: "No configurations are enabled." };
    }

    const { [STORAGE_KEYS.WIFI_SSIDS]: wifiSsidList } = await chrome.storage.sync.get(STORAGE_KEYS.WIFI_SSIDS);

    for (const config of enabledConfigs) {
        const response = await attemptConnection(config, wifiSsidList);
        if (response.success) {
            return response; // Return the first successful response
        }
        console.warn(`Failed to connect with "${config.name}": ${response.message}. Trying next configuration.`);
    }

    // If the loop finishes, no connection was successful
    return { success: false, message: "Failed to connect using any of the enabled configurations." };
}

/**
 * Attempts to automatically restart the SSH tunnel.
 * This is triggered when the connection drops and the user has enabled the feature.
 * It includes a cooldown mechanism to prevent rapid-fire reconnection attempts.
 */
async function attemptAutoReconnect() {
  const now = Date.now();
  if (now - lastReconnectAttemptTimestamp < RECONNECT_COOLDOWN_MS) {
    console.log(`Auto-reconnect throttled. Last attempt was less than ${RECONNECT_COOLDOWN_MS / 1000}s ago.`);
    return;
  }
  lastReconnectAttemptTimestamp = now;

  console.log("Attempting to automatically reconnect the tunnel...");
  try {
    const response = await tryToConnectToEnabledConfigs();
    if (response.success) {
      console.log("Auto-reconnect command sent successfully.");
      // A small delay gives the SSH process time to start before we check.
      setTimeout(updateStatus, 1500);
    } else {
      console.error("Auto-reconnect failed:", response.message);
    }
  } catch (error) {
    console.error("Error during auto-reconnect attempt:", error.message);
  }
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

  const wasConnected = lastStatus.connected;
  lastStatus = newStatus;

  // --- Store latency history if connected ---
  if (newStatus.connected && typeof newStatus.web_check_latency_ms !== 'undefined' && typeof newStatus.tcp_ping_ms !== 'undefined') {
    // Only store valid readings (greater than -1)
    if (newStatus.web_check_latency_ms > -1 && newStatus.tcp_ping_ms > -1) {
      const newHistoryPoint = {
        timestamp: Date.now(),
        web: newStatus.web_check_latency_ms,
        tcp: newStatus.tcp_ping_ms,
      };
      // Use an async IIFE to avoid holding up the broadcast
      (async () => {
        const { [STORAGE_KEYS.LATENCY_HISTORY]: history = [] } = await chrome.storage.local.get(STORAGE_KEYS.LATENCY_HISTORY);
        history.push(newHistoryPoint);
        // Keep the history to a reasonable size, e.g., last 200 points
        if (history.length > 200) {
          history.shift();
        }
        await chrome.storage.local.set({ [STORAGE_KEYS.LATENCY_HISTORY]: history });
      })();
    }
  }
  // --- Handle state transitions ---
  // Check if the tunnel has just disconnected.
  const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManagedByHolocron } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
  if (wasConnected && !newStatus.connected) {
    console.log("Tunnel has disconnected. Initiating disconnect sequence.");

    // 1. First, clear the browser proxy if we were managing it.
    // This is critical to restore the user's internet access immediately.
    if (isProxyManagedByHolocron) {
      console.log("Automatically clearing browser proxy.");
      const { [STORAGE_KEYS.ORIGINAL_PROXY]: originalProxySettings } = await chrome.storage.local.get(STORAGE_KEYS.ORIGINAL_PROXY);
      if (originalProxySettings) {
        await chrome.proxy.settings.set({ value: originalProxySettings, scope: 'regular' });
      } else {
        await chrome.proxy.settings.clear({ scope: 'regular' });
      }
      await chrome.storage.local.remove([STORAGE_KEYS.ORIGINAL_PROXY, STORAGE_KEYS.IS_PROXY_MANAGED]);
      console.log("Browser proxy restored to original settings.");
      lastStatus.proxyCleared = true; // For UI feedback
    }

    // 2. Second, check if we should attempt to reconnect.
    const { [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: autoReconnectEnabled } = await chrome.storage.sync.get({
      [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: true // Default to true
    });

    if (autoReconnectEnabled) {
      // Use a timeout to let other state updates settle before reconnecting.
      setTimeout(attemptAutoReconnect, 1000);
    }
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
  try {
    const connectedConfig = await getCurrentlyConnectedConfig();
    if (!connectedConfig) {
      // If we think we are disconnected, report it.
      // The updateStateAndBroadcast function will handle the transition and trigger an auto-reconnect if needed.
      // Pass null for the activeConfigId.
      updateStateAndBroadcast({ connected: false, activeConfigId: null });
      return; // The 'finally' block will still execute.
    }

    const {
      [STORAGE_KEYS.PING_HOST]: pingHost,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrl
    } = await chrome.storage.sync.get({
      [STORAGE_KEYS.PING_HOST]: 'youtube.com', // Default value
      [STORAGE_KEYS.WEB_CHECK_URL]: 'https://gemini.google.com/app'
    });

    try {
      const response = await communicateWithNativeHost({
        command: COMMANDS.GET_STATUS,
        // Pass the identifier from the active configuration
        sshCommandIdentifier: getIdentifierForConfig(connectedConfig),
        pingHost,
        webCheckUrl
      });
      response.activeConfigId = connectedConfig.id; // Add the active ID to the status object
      if (response && response.connected) {
        updateStateAndBroadcast(response);
      } else {
        // The currently "active" config is no longer connected.
        console.log(`Configuration "${connectedConfig.name}" is no longer connected.`);
        await chrome.storage.local.remove(STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID);
        // The updateStateAndBroadcast will see the state change from connected to disconnected and trigger auto-reconnect if enabled
        updateStateAndBroadcast({ connected: false, activeConfigId: null });
      }
    } catch (error) {
      const errorMessage = `Error during status update for config "${connectedConfig.name}": ${error.message}`;
      updateStateAndBroadcast({ connected: false, activeConfigId: null }, errorMessage);
    }
  } finally {
    isUpdateInProgress = false;
  }
}

// Perform an initial check on browser startup.
chrome.runtime.onStartup.addListener(() => {
  updateStatus();
  updateGeoIpDatabase();
  updateGeoSiteDatabase();
});

// Set up the alarm and perform an initial check when the extension is installed.
chrome.runtime.onInstalled.addListener((details) => {
  chrome.alarms.create('status-check', { periodInMinutes: 1 });
  // Add a new alarm for daily GeoIP updates.
  chrome.alarms.create('database-update', { periodInMinutes: 60 * 24 }); // 24 hours

  // On first install, open the options page to prompt the user for configuration.
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    chrome.runtime.openOptionsPage();
  }
  updateStatus();
  updateGeoIpDatabase();
  updateGeoSiteDatabase();
});

// Listen for the alarm to trigger subsequent checks.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'status-check') {
    updateStatus();
  } else if (alarm.name === 'database-update') {
    updateGeoIpDatabase();
    updateGeoSiteDatabase();
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
        // --- Get all necessary data from storage ---
        const {
            [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs = [],
            [STORAGE_KEYS.PROXY_BYPASS_RULES]: customRules = [],
            [STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED]: geoIpBypassEnabled = true,
            [STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED]: geoSiteBypassEnabled = true,
        } = await chrome.storage.sync.get([
            STORAGE_KEYS.CORE_CONFIGURATIONS,
            STORAGE_KEYS.PROXY_BYPASS_RULES,
            STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED,
            STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED,
        ]);

        const {
          [STORAGE_KEYS.GEOIP_RANGES]: storedRanges,
          [STORAGE_KEYS.GEOSITE_DOMAINS]: storedDomains,
          [STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID]: activeConfigId,
        } = await chrome.storage.local.get([
            STORAGE_KEYS.GEOIP_RANGES,
            STORAGE_KEYS.GEOSITE_DOMAINS,
            STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID
        ]);

        if (!activeConfigId) {
            sendResponse({ success: false, message: "Cannot apply proxy, no active configuration is set." });
            return;
        }

        // Store original settings before changing them.
        const originalSettings = await chrome.proxy.settings.get({ incognito: false });

        // --- Create a PAC script for advanced routing ---
        let pacScript = `/**
 * Holocron PAC (Proxy Auto-Configuration) Script
 * Generated: ${new Date().toISOString()}
 * Active Configuration ID: ${activeConfigId}
 */
function FindProxyForURL(url, host) {
    // --- Proxy Definitions ---
    // These are defined based on your Core Configurations that have a Dynamic (-D) port forward.
`;
        const proxyDefinitions = [];
        coreConfigs.forEach(config => {
            if (config.portForwards && config.portForwards.length > 0) {
                config.portForwards.forEach(rule => {
                    if (rule.type === 'D' && rule.localPort) {
                        const proxyVar = `PROXY_${config.id.replace(/-/g, '_')}`;
                        pacScript += `    const ${proxyVar} = "SOCKS5 127.0.0.1:${rule.localPort}"; // For "${config.name}"\n`;
                        proxyDefinitions.push({ id: config.id, variable: proxyVar });
                    }
                });
            }
        });

        pacScript += `
    const DIRECT = "DIRECT";

    // Determine the default proxy to use. This will be the proxy of the
    // currently active configuration.
`;
        let activeProxyVar = 'DIRECT'; // Fallback
        const activeProxyDef = proxyDefinitions.find(p => p.id === activeConfigId);
        if (activeProxyDef) {
            activeProxyVar = activeProxyDef.variable;
        } else {
            // If the active config has no SOCKS proxy, but one was passed (e.g. from a legacy setup), create a generic one.
            // This maintains backward compatibility.
            pacScript += `    // NOTE: Active config has no SOCKS proxy defined. Using generic port.\n`;
            activeProxyVar = `"SOCKS5 127.0.0.1:${socksPort}"`;
        }
        pacScript += `    const PROXY = ${activeProxyVar};\n`;

        pacScript += `
    // --- Standard Bypasses (always active) ---
    // Bypass for local, non-qualified, and common internal domains.
    if (isPlainHostName(host) ||
      shExpMatch(host, "localhost") ||
      shExpMatch(host, "*.local") ||
      shExpMatch(host, "*.ir")) {
    return DIRECT;
    }
    try {
        const ip = dnsResolve(host);
        if (ip && (isInNet(ip, "10.0.0.0", "255.0.0.0") ||
                   isInNet(ip, "172.16.0.0", "255.240.0.0") ||
                   isInNet(ip, "192.168.0.0", "255.255.0.0") ||
                   isInNet(ip, "127.0.0.0", "255.0.0.0"))) {
            return DIRECT;
        }
    } catch (e) { /* dnsResolve can fail, fall through */ }
`;

        // --- Custom User-Defined Rules ---
        if (customRules.length > 0) {
            pacScript += `
    // --- Custom Bypass & Routing Rules ---
    // Rules you have defined to route specific domains.
    const customRules = ${JSON.stringify(customRules, null, 4)};

    for (let i = 0; i < customRules.length; i++) {
        const rule = customRules[i];
        if (shExpMatch(host, rule.domain)) {
            // Rule target is "DIRECT" -> bypass the proxy.
            if (rule.target === "DIRECT") {
                return DIRECT;
            }
            // Find the proxy variable for the targeted configuration.
`;
            proxyDefinitions.forEach(def => {
                pacScript += `            if (rule.target === "${def.id}") { return ${def.variable}; }\n`;
            });
            pacScript += `
            // If the rule targets a configuration that doesn't have a SOCKS proxy
            // or is otherwise unhandled, bypass it for safety.
            return DIRECT;
        }
    }
`;
        }

        // --- GeoSite Bypass ---
        if (geoSiteBypassEnabled && storedDomains && storedDomains.length > 0) {
          pacScript += `
    // --- GeoSite Bypass for Iran (domain list) ---
    const domains = ${JSON.stringify(storedDomains)};
    for (let i = 0; i < domains.length; i++) {
        if (shExpMatch(host, domains[i])) {
            return DIRECT;
        }
    }
`;
        }

        // --- GeoIP Bypass ---
        if (geoIpBypassEnabled) {
          // Use dynamically fetched ranges if available, otherwise fall back to the hardcoded list.
          const rangesToUse = (storedRanges && storedRanges.length > 0) ? storedRanges : IRAN_IP_RANGES_NETMASK;
          pacScript += `
    // --- GeoIP Bypass for Iran (IP ranges) ---
    try {
        const ip = dnsResolve(host);
        if (ip) {
            const ranges = ${JSON.stringify(rangesToUse)};
            for (let i = 0; i < ranges.length; i++) {
                if (isInNet(ip, ranges[i][0], ranges[i][1])) {
                    return DIRECT;
                }
            }
        }
    } catch (e) { /* dnsResolve can fail, fall through */ }
`;
        }

        pacScript += `
    // --- Default Action ---
    // If no specific rules matched, use the default active proxy.
    return PROXY;
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
        sendResponse({ success: true, message: "Browser proxy set with advanced PAC script." });
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

  if (request.command === COMMANDS.MANUAL_DB_UPDATE) {
    (async () => {
      try {
        console.log("Manual database update triggered.");
        await Promise.all([
          updateGeoIpDatabase(true), // force update
          updateGeoSiteDatabase(true) // force update
        ]);
        console.log("Manual database update complete.");
        sendResponse({ success: true, message: "Databases updated successfully." });
      } catch (error) {
        console.error("Manual database update failed:", error);
        sendResponse({ success: false, message: `Update failed: ${error.message}` });
      }
    })();
    return true;
  }
  // Listener for the new test connection feature from the options page.
  if (request.command === COMMANDS.TEST_CONNECTION) {
    (async () => {
      const { sshCommand, pingHost, webCheckUrl, sshHost } = request;
      if (!pingHost) {
        sendResponse({ success: false, message: "Ping Host cannot be empty." });
        return;
      }
      if (!sshHost) {
        sendResponse({ success: false, message: "SSH Host cannot be empty." });
        return; // sshCommand from options.js is the same as sshHost, so this check is sufficient.
      }
      try {
        const response = await communicateWithNativeHost({
          command: COMMANDS.TEST_CONNECTION,
          sshCommandIdentifier: sshHost, // The identifier is the host.
          sshHost: sshHost, // The host itself is also needed for the direct ping test.
          pingHost,
          webCheckUrl
        });
        let message;
        if (response && response.connected) {
          message = `Success! Web Latency: ${response.web_check_latency_ms}ms, TCP Ping: ${response.tcp_ping_ms}ms. Site Status: ${response.web_check_status}`;
        } else if (response && response.ssh_host_ping_ms !== undefined) {
          const hostStatus = response.ssh_host_ping_ms > -1
            ? `Host '${response.ssh_host_name}' is reachable (ping: ${response.ssh_host_ping_ms}ms).`
            : `Host '${response.ssh_host_name}' is UNREACHABLE (${response.ssh_host_ping_error || 'Error'}).`;
          message = `Tunnel is down. Diagnostic: ${hostStatus}`;
        } else {
          message = "Could not get a detailed status. Check native host logs for errors.";
        }
        sendResponse({ success: response.success, message: message });
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
        let response;
        if (request.command === COMMANDS.START_TUNNEL) {
            if (request.config) { // A specific config is being targeted from options page
                // For a specific connection attempt, we don't care about the saved Wi-Fi SSIDs.
                // The user is forcing it, so we pass an empty list.
                response = await attemptConnection(request.config, []);
            } else { // No specific config, use the enabled ones (from popup or auto-reconnect)
                response = await tryToConnectToEnabledConfigs();
            }
        } else { // STOP_TUNNEL
          const connectedConfig = await getCurrentlyConnectedConfig();
          if (!connectedConfig) {
            sendResponse({ success: true, message: "No active tunnel to stop." });
            return;
          }
          response = await communicateWithNativeHost({
            command: request.command,
            config: { sshCommandIdentifier: getIdentifierForConfig(connectedConfig) }
          });
          if (response.success) {
            await chrome.storage.local.remove(STORAGE_KEYS.CURRENTLY_ACTIVE_CONFIG_ID);
          }
        }
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

  if (request.command === COMMANDS.GET_LOGS) {
    (async () => {
      try {
        // This command is a simple pass-through to the native host
        const response = await communicateWithNativeHost({ command: COMMANDS.GET_LOGS });
        sendResponse(response);
      } catch (error) {
        sendResponse({ success: false, message: `Failed to get logs: ${error.message}` });
      }
    })();
    return true; // Indicate async response
  }

  if (request.command === COMMANDS.CLEAR_LOGS) {
    (async () => {
      try {
        const response = await communicateWithNativeHost({ command: COMMANDS.CLEAR_LOGS });
        sendResponse(response);
      } catch (error) {
        sendResponse({ success: false, message: `Failed to clear logs: ${error.message}` });
      }
    })();
    return true; // Indicate async response
  }
  return false; // Explicitly return false for other messages.
});