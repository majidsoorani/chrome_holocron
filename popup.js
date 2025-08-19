import { COMMANDS, STORAGE_KEYS } from './constants.js';

document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('connection_status');
  const statusIndicator = document.getElementById('status_indicator');
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
  const tunnelControls = document.getElementById('tunnel-controls');
  const tunnelMessage = document.getElementById('tunnel-message');
  const connectButton = document.getElementById('connect-button');
  const disconnectButton = document.getElementById('disconnect-button');

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
    // Hide spinner once we have a status to show
    spinnerOverlay.style.display = 'none';

    tunnelControls.style.display = 'block';
    // Handle disconnected state first
    if (!status || !status.connected) {
      statusEl.textContent = 'Disconnected';
      statusIndicator.className = 'status-indicator bad';
      detailsGrid.style.display = 'grid'; // Show grid for diagnostics

      webLatencyEl.textContent = '--';
      webLatencyEl.className = 'value';
      webCheckEl.textContent = 'N/A';
      webCheckEl.className = 'value';

      // When disconnected, show the direct TCP ping latency for basic diagnostics
      if (status && typeof status.tcp_ping_ms !== 'undefined') {
        if (status.tcp_ping_ms === -1) {
          tcpPingEl.textContent = formatTcpError(status.tcp_ping_error);
          tcpPingEl.className = 'value bad';
        } else {
          tcpPingEl.textContent = `${status.tcp_ping_ms}ms`;
          tcpPingEl.className = 'value'; // Neutral color for direct ping
        }
      } else {
        tcpPingEl.textContent = '--';
        tcpPingEl.className = 'value';
      }
      proxyContainer.style.display = 'none';

      // Configure tunnel controls for disconnected state
      connectButton.style.display = 'inline-flex';
      disconnectButton.style.display = 'none';
      tunnelMessage.textContent = 'Tunnel is disconnected.';
      return;
    }

    // Handle connected state
    statusEl.textContent = 'Connected';
    statusIndicator.className = 'status-indicator good';
    detailsGrid.style.display = 'grid';

    // Display Web Check Latency (from the full HTTP check)
    const webLatency = status.web_check_latency_ms;
    if (webLatency === -1 || typeof webLatency === 'undefined') {
      webLatencyEl.textContent = 'Fail';
      webLatencyEl.className = 'value bad';
    } else {
      webLatencyEl.textContent = `${webLatency}ms`;
      webLatencyEl.className = 'value good';
    }

    // Display TCP Ping Latency
    const tcpLatency = status.tcp_ping_ms;
    if (tcpLatency === -1 || typeof tcpLatency === 'undefined') {
      tcpPingEl.textContent = formatTcpError(status.tcp_ping_error);
      tcpPingEl.className = 'value bad';
    } else {
      tcpPingEl.textContent = `${tcpLatency}ms`;
      tcpPingEl.className = 'value good';
    }

    // Display Web Check Status
    const webStatus = status.web_check_status;
    if (webStatus) {
      if (webStatus === 'OK') {
        webCheckEl.textContent = 'OK';
        webCheckEl.className = 'value good';
      } else {
        webCheckEl.textContent = webStatus;
        webCheckEl.className = 'value bad';
      }
    } else {
      webCheckEl.textContent = '--';
      webCheckEl.className = 'value';
    }

    // Configure tunnel controls for connected state
    connectButton.style.display = 'none';
    disconnectButton.style.display = 'inline-flex';
    tunnelMessage.textContent = 'Tunnel is active.';

    // Show proxy controls only if the tunnel is connected and provides a SOCKS port.
    if (status.socks_port) {
        proxyContainer.style.display = 'block';
        // Use an async IIFE to handle the storage get call cleanly
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

  connectButton.addEventListener('click', () => {
    tunnelMessage.textContent = 'Connecting...';
    spinnerOverlay.style.display = 'flex';
    chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL }, (response) => {
      // The main UI update will come from the status refresh.
      // We only need to handle direct errors here.
      if (chrome.runtime.lastError) {
        tunnelMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
        spinnerOverlay.style.display = 'none';
        return;
      }
      if (response && !response.success) {
        const message = response.message.split('\n')[0];
        // If the message starts with an info emoji (ℹ️), treat it as an info message, not an error.
        if (message.startsWith('ℹ️')) {
          tunnelMessage.textContent = message;
        } else {
          tunnelMessage.textContent = `Error: ${message}`;
        }
        spinnerOverlay.style.display = 'none';
      }
    });
  });

  disconnectButton.addEventListener('click', () => {
    tunnelMessage.textContent = 'Disconnecting...';
    spinnerOverlay.style.display = 'flex';
    chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL }, (response) => {
      if (chrome.runtime.lastError) {
        tunnelMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
        spinnerOverlay.style.display = 'none';
      }
      // Success or failure, the subsequent status update will refresh the UI.
    });
  });

  // Initial status request
  requestStatusUpdate();
  refreshButton.addEventListener('click', requestStatusUpdate);
});
