import { COMMANDS, STORAGE_KEYS } from './constants.js';

document.addEventListener('DOMContentLoaded', () => {
  const statusTextEl = document.getElementById('connection-status');
  const statusDotEl = document.getElementById('status-dot');
  const actionButton = document.getElementById('connection-action-button');
  const detailsGrid = document.getElementById('details_grid');
  const spinnerOverlay = document.getElementById('spinner');
  const webLatencyEl = document.getElementById('web_latency');
  const tcpPingEl = document.getElementById('tcp_ping');
  const webCheckEl = document.getElementById('web_check_status');
  const refreshButton = document.getElementById('refresh_button');
  const proxyContainer = document.getElementById('proxy-container');
  const proxyMessage = document.getElementById('proxy-message');
  const applyProxyButton = document.getElementById('apply-proxy-button');
  const revertProxyButton = document.getElementById('revert-proxy-button');

  let currentStatus = {}; // Cache the latest status object

  function formatTcpError(error) {
    if (!error) return 'Fail';
    // Provide more user-friendly error messages
    // Map Python exception names to friendlier text.
    const errorMap = {
      'gaierror': 'DNS Fail',
      'timeout': 'Timeout',
      'ProxyError': 'Proxy Fail',
      'ConnectionRefusedError': 'Refused',
      'ConnectionResetError': 'Reset',
      'NewConnectionError': 'Conn Fail',
      'MaxRetryError': 'Retry Fail',
      'SSLError': 'SSL Error',
      'OSError': 'OS Error',
    };

    if (errorMap[error]) {
      return errorMap[error];
    }

    // Fallback for unmapped errors
    return error.replace(/Error$/, '').trim();
  }
  function updateUI(status) {
    spinnerOverlay.style.display = 'none';
    detailsGrid.style.display = 'grid';

    // Update main status display
    if (status.connecting) {
        statusDotEl.dataset.status = 'in-progress';
        statusTextEl.textContent = 'Connecting...';
        actionButton.innerHTML = '⏳';
        actionButton.title = 'In Progress...';
        actionButton.disabled = true;
    } else if (status.connected) {
        statusDotEl.dataset.status = 'connected';
        statusTextEl.textContent = 'Connected';
        actionButton.innerHTML = '⏻';
        actionButton.title = 'Disconnect';
        actionButton.disabled = false;
    } else { // Disconnected
        statusDotEl.dataset.status = 'disconnected';
        statusTextEl.textContent = 'Disconnected';
        actionButton.innerHTML = '⏻';
        actionButton.title = 'Connect';
        actionButton.disabled = false;
    }

    // Update details grid
    const webLatency = status.web_check_latency_ms;
    if (webLatency === -1 || typeof webLatency === 'undefined') {
      webLatencyEl.textContent = '--';
      webLatencyEl.className = 'value bad';
    } else {
      webLatencyEl.textContent = `${webLatency}ms`;
      webLatencyEl.className = 'value good';
    }

    const tcpLatency = status.tcp_ping_ms;
    if (tcpLatency === -1 || typeof tcpLatency === 'undefined') {
      tcpPingEl.textContent = formatTcpError(status.tcp_ping_error);
      tcpPingEl.className = 'value bad';
    } else {
      tcpPingEl.textContent = `${tcpLatency}ms`;
      tcpPingEl.className = 'value good';
    }

    const webStatus = status.web_check_status;
    if (webStatus === 'OK') {
      webCheckEl.textContent = 'OK';
      webCheckEl.className = 'value good';
    } else {
      webCheckEl.textContent = webStatus || '--';
      webCheckEl.className = 'value bad';
    }

    // Update proxy controls display
    if (status.connected && status.socks_port) {
        proxyContainer.style.display = 'block';
        (async () => {
            const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
            if (isProxyManaged) {
                proxyMessage.textContent = 'Browser proxy is managed by Holocron.';
                applyProxyButton.style.display = 'none';
                revertProxyButton.style.display = 'inline-block';
            } else {
                proxyMessage.textContent = 'A proxy is available for your browser.';
                applyProxyButton.style.display = 'inline-block';
                revertProxyButton.style.display = 'none';
            }
        })();
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
    // Show spinner to give feedback that a refresh is happening
    spinnerOverlay.style.display = 'flex';
    
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
        } else {
          // Display an error message to the user if setting the proxy failed.
          const errorMessage = response ? response.message : 'An unknown error occurred.';
          proxyMessage.textContent = `Error: ${errorMessage}`;
          console.error("Holocron: Failed to apply proxy.", response);
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
      } else {
        // Display an error message to the user if reverting the proxy failed.
        const errorMessage = response ? response.message : 'An unknown error occurred.';
        proxyMessage.textContent = `Error: ${errorMessage}`;
        console.error("Holocron: Failed to revert proxy.", response);
      }
    });
  });

  actionButton.addEventListener('click', () => {
    spinnerOverlay.style.display = 'flex';
    if (currentStatus.connected) {
      statusTextEl.textContent = 'Disconnecting...';
      chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL });
    } else {
      statusTextEl.textContent = 'Connecting...';
      chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL });
    }
    // The UI will be fully updated by the status broadcast message.
  });

  // Initial status request
  requestStatusUpdate();
  refreshButton.addEventListener('click', requestStatusUpdate);
});
