// --- Constants ---
// NOTE: In a larger project, these would be in a shared file.
const STORAGE_KEYS = {
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
};

const COMMANDS = {
  // to background
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  // from background
  STATUS_UPDATED: 'statusUpdated',
};
// --- End Constants ---

document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('connection_status');
  const ipEl = document.getElementById('ip_address');
  const countryEl = document.getElementById('country');
  const pingEl = document.getElementById('ping');
  const webCheckEl = document.getElementById('web_check_status');
  const refreshButton = document.getElementById('refresh_button');
  const proxyContainer = document.getElementById('proxy-container');
  const proxyMessage = document.getElementById('proxy-message');
  const applyProxyButton = document.getElementById('apply-proxy-button');
  const revertProxyButton = document.getElementById('revert-proxy-button');

  let currentStatus = {}; // Cache the latest status object

  function updateUI(status) {
    if (status && status.connected) {
      statusEl.textContent = 'Connected'; 
      statusEl.className = 'status good';
      ipEl.textContent = status.ip || 'N/A';
      countryEl.textContent = status.country || 'N/A';

      if (status.ping_ms === -1) {
        pingEl.textContent = 'Fail';
        pingEl.className = 'detail bad';
      } else {
        pingEl.textContent = `${status.ping_ms}ms`;
        pingEl.className = 'detail good';
      }

      // Update Web Check status
      if (status.web_check_status) {
        if (status.web_check_status === 'OK') {
          webCheckEl.textContent = 'OK';
          webCheckEl.className = 'detail good';
        } else {
          webCheckEl.textContent = status.web_check_status;
          webCheckEl.className = 'detail bad';
        }
      }
    } else {
      statusEl.textContent = 'Disconnected';
      statusEl.className = 'status bad';
      ipEl.textContent = 'N/A';
      countryEl.textContent = 'N/A';
      pingEl.textContent = 'N/A';
      pingEl.className = 'detail';
      webCheckEl.textContent = 'N/A';
      proxyContainer.style.display = 'none';
      return; // Exit early if disconnected
    }

    // Show proxy controls only if the tunnel is connected and provides a SOCKS port.
    if (status.socks_port) {
      proxyContainer.style.display = 'block';
      chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED, ({ [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManagedByHolocron }) => {
          if (isProxyManagedByHolocron) {
            proxyMessage.textContent = 'Browser proxy is active.';
            applyProxyButton.style.display = 'none';
            revertProxyButton.style.display = 'inline-block';
          } else {
            proxyMessage.textContent = 'A proxy is available for your browser.';
            applyProxyButton.style.display = 'inline-block';
            revertProxyButton.style.display = 'none';
          }
      });
    } else {
      proxyContainer.style.display = 'none';
    }
  }

  // Listen for broadcasted updates from the background script.
  // This allows the popup to reflect the latest status in real-time.
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.command === COMMANDS.STATUS_UPDATED) {
      currentStatus = request.status; // Cache the latest status
      updateUI(request.status);
    }
  });

  function requestStatusUpdate() {
    // Visually reset the status to give feedback that a refresh is happening
    statusEl.textContent = 'Loading...';
    statusEl.className = 'status';
    
    // Ask the background script for the latest status and to trigger a refresh.
    // The initial response will be the cached status. A "statusUpdated"
    // message will arrive later with the fresh results.
    chrome.runtime.sendMessage({ command: COMMANDS.GET_POPUP_STATUS }, (response) => {
      if (chrome.runtime.lastError) {
        // Handle cases where the background script might be inactive
        console.error(chrome.runtime.lastError.message);
        updateUI({ connected: false });
      } else {
        currentStatus = response; // Cache the latest status
        // Update with the cached status immediately.
        updateUI(response);
      }
    });
  }

  applyProxyButton.addEventListener('click', () => {
    if (currentStatus && currentStatus.socks_port) {
      chrome.runtime.sendMessage({ command: COMMANDS.SET_BROWSER_PROXY, socksPort: currentStatus.socks_port }, (response) => {
        if (response && response.success) {
          requestStatusUpdate(); // Refresh UI to show the new state
        }
      });
    } else {
      proxyMessage.textContent = 'Error: SOCKS port not found. Cannot apply proxy.';
      console.error("Holocron: Attempted to apply proxy, but SOCKS port is missing from status object.", currentStatus);
    }
  });

  revertProxyButton.addEventListener('click', () => {
    chrome.runtime.sendMessage({ command: COMMANDS.CLEAR_BROWSER_PROXY }, (response) => {
      if (response && response.success) {
        requestStatusUpdate(); // Refresh UI
      }
    });
  });

  // Initial status request
  requestStatusUpdate();
  refreshButton.addEventListener('click', requestStatusUpdate);
});
