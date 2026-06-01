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
  const refreshButton = document.getElementById('refresh-button');
  const proxyContainer = document.getElementById('proxy-container');
  const proxyMessage = document.getElementById('proxy-message');
  const applyProxyButton = document.getElementById('apply-proxy-button');
  const revertProxyButton = document.getElementById('revert-proxy-button');
  const passwall2Container = document.getElementById('passwall2-container');
  const passwall2Message = document.getElementById('passwall2-message');
  const startPasswall2Button = document.getElementById('start-passwall2-button');
  const restartPasswall2Button = document.getElementById('restart-passwall2-button');
  const stopPasswall2Button = document.getElementById('stop-passwall2-button');
  const passwall2NodesContainer = document.getElementById('passwall2-nodes-container');
  const passwall2NodesList = document.getElementById('passwall2-nodes-list');
  const refreshPasswall2NodesBtn = document.getElementById('refresh-passwall2-nodes');
  const updateBalanceNodesBtn = document.getElementById('update-balance-nodes');
  const updateSubscriptionBtn = document.getElementById('update-subscription');
  const optimizeBalanceNodesBtn = document.getElementById('optimize-balance-nodes');

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
      let displayText = `${tcpLatency}ms`;
      if (status.connection_type === 'direct') {
        displayText += ' (Direct)';
      }
      tcpPingEl.textContent = displayText;
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
    if (status.activeConfig && status.activeConfig.type === 'openwrt_passwall2') {
        proxyContainer.style.display = 'none';
        passwall2Container.style.display = 'block';
        passwall2NodesContainer.style.display = status.connected ? 'block' : 'none';
        getPasswall2Status();
        if (status.connected) loadPasswall2Nodes();
    } else if (status.connected && status.socks_port) {
        passwall2Container.style.display = 'none';
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
      passwall2Container.style.display = 'none';
      passwall2NodesContainer.style.display = 'none';
    }

    // Current Site Bypass controls
    updateCurrentSiteBypassUI();
  }

  async function updateCurrentSiteBypassUI() {
    const bypassContainer = document.getElementById('direct-bypass-container');
    const bypassMessage = document.getElementById('direct-bypass-message');
    const bypassBtn = document.getElementById('direct-bypass-toggle-btn');
    if (!bypassContainer || !bypassMessage || !bypassBtn) return;

    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs || tabs.length === 0 || !tabs[0].url) {
        bypassContainer.style.display = 'none';
        return;
      }

      const urlStr = tabs[0].url;
      if (!urlStr.startsWith('http://') && !urlStr.startsWith('https://')) {
        bypassContainer.style.display = 'none';
        return;
      }

      const parsedUrl = new URL(urlStr);
      const host = parsedUrl.hostname;
      
      const { [STORAGE_KEYS.PROXY_BYPASS_RULES]: bypassRules = [] } = await chrome.storage.sync.get(STORAGE_KEYS.PROXY_BYPASS_RULES);
      
      // Match exactly or via wildcard pattern (e.g. *.google.com)
      const existingRuleIndex = bypassRules.findIndex(r => {
        if (r.domain === host) return true;
        if (r.domain.startsWith('*.')) {
          const rootDomain = r.domain.substring(2);
          if (host === rootDomain || host.endsWith('.' + rootDomain)) return true;
        }
        return false;
      });

      bypassContainer.style.display = 'block';
      if (existingRuleIndex >= 0) {
        const matchedRule = bypassRules[existingRuleIndex];
        if (matchedRule.target === 'DIRECT' && matchedRule.enabled !== false) {
          bypassMessage.innerHTML = `Site <strong>${host}</strong> is connecting <strong>DIRECT</strong>.`;
          bypassBtn.textContent = 'Remove Direct Bypass';
          bypassBtn.style.backgroundColor = 'var(--bad-color)';
          bypassBtn.style.color = 'white';
          bypassBtn.onclick = async () => {
            const updatedRules = bypassRules.filter((_, idx) => idx !== existingRuleIndex);
            await chrome.storage.sync.set({ [STORAGE_KEYS.PROXY_BYPASS_RULES]: updatedRules });
            // Re-apply proxy settings so PAC changes immediately
            const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
            if (currentStatus.socks_port) {
              await chrome.runtime.sendMessage({ command: COMMANDS.SET_BROWSER_PROXY, socksPort: currentStatus.socks_port });
            }
            updateCurrentSiteBypassUI();
          };
          return;
        }
      }

      bypassMessage.innerHTML = `Site <strong>${host}</strong> is routed via proxy.`;
      bypassBtn.textContent = 'Add Direct Bypass';
      bypassBtn.style.backgroundColor = 'var(--good-color)';
      bypassBtn.style.color = '#1f2329';
      bypassBtn.onclick = async () => {
        const newRule = { domain: '*.' + host.replace(/^www\./, ''), target: 'DIRECT', enabled: true };
        const updatedRules = [...bypassRules, newRule];
        await chrome.storage.sync.set({ [STORAGE_KEYS.PROXY_BYPASS_RULES]: updatedRules });
        // Re-apply proxy settings so PAC changes immediately
        const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
        if (currentStatus.socks_port) {
          await chrome.runtime.sendMessage({ command: COMMANDS.SET_BROWSER_PROXY, socksPort: currentStatus.socks_port });
        }
        updateCurrentSiteBypassUI();
      };

    } catch (e) {
      console.error('Error loading current site details:', e);
      bypassContainer.style.display = 'none';
    }
  }

  function getPasswall2Status() {
    chrome.runtime.sendMessage({ command: COMMANDS.PASSWALL2, action: 'status', config: currentStatus.activeConfig }, (response) => {
      if (response && response.success) {
        passwall2Message.textContent = `Passwall2 is ${response.status}.`;
        if (response.status === 'enabled') {
          startPasswall2Button.disabled = true;
          stopPasswall2Button.disabled = false;
          if (restartPasswall2Button) restartPasswall2Button.disabled = false;
        } else {
          startPasswall2Button.disabled = false;
          stopPasswall2Button.disabled = true;
          if (restartPasswall2Button) restartPasswall2Button.disabled = true;
        }
      } else {
        passwall2Message.textContent = 'Could not get Passwall2 status.';
      }
    });
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  function renderPasswall2Nodes(proxies, activeId) {
    if (!proxies || proxies.length === 0) {
      passwall2NodesList.innerHTML = '<div class="nodes-empty">No nodes found.</div>';
      return;
    }
    passwall2NodesList.innerHTML = proxies.map(p => {
      const isActive = p.is_active || (activeId && p.id === activeId);
      const name = escapeHtml(p.remarks || p.name || p.id);
      const id = escapeHtml(p.id);
      const btnClass = isActive ? 'node-use-btn active-btn' : 'node-use-btn';
      const btnLabel = isActive ? 'In Use' : 'Use';
      return `<div class="node-row${isActive ? ' active' : ''}">
        <span class="node-name" title="${name}">${name}</span>
        <button class="${btnClass}" data-node-id="${id}" ${isActive ? 'disabled' : ''}>${btnLabel}</button>
      </div>`;
    }).join('');

    passwall2NodesList.querySelectorAll('.node-use-btn').forEach(btn => {
      if (btn.disabled) return;
      btn.addEventListener('click', () => useNode(btn.dataset.nodeId, btn));
    });
  }

  function loadPasswall2Nodes() {
    if (!currentStatus.activeConfig) return;
    passwall2NodesList.innerHTML = '<div class="nodes-empty">Loading…</div>';
    chrome.runtime.sendMessage(
      { command: COMMANDS.PASSWALL2, action: 'list_proxies', config: currentStatus.activeConfig },
      (response) => {
        if (response && response.success && Array.isArray(response.proxies)) {
          renderPasswall2Nodes(response.proxies, response.active_node_id);
        } else {
          const msg = (response && response.message) || (response && response.error) || 'Failed to load nodes.';
          passwall2NodesList.innerHTML = `<div class="nodes-empty">${escapeHtml(msg)}</div>`;
        }
      }
    );
  }

  function useNode(nodeId, btn) {
    if (!nodeId) return;
    const originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Switching…';
    chrome.runtime.sendMessage(
      { command: COMMANDS.PASSWALL2, action: 'use_proxy', config: currentStatus.activeConfig, proxyId: nodeId },
      (response) => {
        if (response && response.success) {
          loadPasswall2Nodes();
        } else {
          btn.disabled = false;
          btn.textContent = originalLabel;
          const msg = (response && response.message) || 'Failed to switch node.';
          passwall2Message.textContent = msg;
        }
      }
    );
  }

  if (refreshPasswall2NodesBtn) {
    refreshPasswall2NodesBtn.addEventListener('click', () => loadPasswall2Nodes());
  }

  if (optimizeBalanceNodesBtn) {
    optimizeBalanceNodesBtn.addEventListener('click', () => {
      if (!currentStatus.activeConfig) return;
      const original = optimizeBalanceNodesBtn.textContent;
      optimizeBalanceNodesBtn.disabled = true;
      optimizeBalanceNodesBtn.textContent = '⏳';
      passwall2Message.textContent = 'Optimizing balance nodes…';
      chrome.runtime.sendMessage(
        { command: COMMANDS.PASSWALL2, action: 'optimize_balance_nodes', config: currentStatus.activeConfig },
        (response) => {
          optimizeBalanceNodesBtn.disabled = false;
          optimizeBalanceNodesBtn.textContent = original;
          if (response && response.success) {
            passwall2Message.textContent = 'Balance groups optimized.';
            loadPasswall2Nodes();
          } else {
            const msg = (response && response.message) || 'Failed to optimize balance groups.';
            passwall2Message.textContent = msg;
          }
        }
      );
    });
  }

  if (updateSubscriptionBtn) {
    updateSubscriptionBtn.addEventListener('click', () => {
      if (!currentStatus.activeConfig) return;
      const original = updateSubscriptionBtn.textContent;
      updateSubscriptionBtn.disabled = true;
      updateSubscriptionBtn.textContent = '⏳';
      passwall2Message.textContent = 'Updating subscription…';
      chrome.runtime.sendMessage(
        { command: COMMANDS.PASSWALL2, action: 'update_subscription', config: currentStatus.activeConfig },
        (response) => {
          updateSubscriptionBtn.disabled = false;
          updateSubscriptionBtn.textContent = original;
          if (response && response.success) {
            passwall2Message.textContent = 'Subscription updated.';
            loadPasswall2Nodes();
          } else {
            const msg = (response && response.message) || 'Failed to update subscription.';
            passwall2Message.textContent = msg;
          }
        }
      );
    });
  }

  if (updateBalanceNodesBtn) {
    updateBalanceNodesBtn.addEventListener('click', () => {
      if (!currentStatus.activeConfig) return;
      const original = updateBalanceNodesBtn.textContent;
      updateBalanceNodesBtn.disabled = true;
      updateBalanceNodesBtn.textContent = '⏳';
      passwall2Message.textContent = 'Updating balance nodes…';
      chrome.runtime.sendMessage(
        { command: COMMANDS.PASSWALL2, action: 'update_balance_nodes', config: currentStatus.activeConfig },
        (response) => {
          updateBalanceNodesBtn.disabled = false;
          updateBalanceNodesBtn.textContent = original;
          if (response && response.success) {
            passwall2Message.textContent = 'Balance nodes updated.';
            loadPasswall2Nodes();
          } else {
            const msg = (response && response.message) || 'Failed to update balance nodes.';
            passwall2Message.textContent = msg;
          }
        }
      );
    });
  }

  startPasswall2Button.addEventListener('click', () => {
    passwall2Message.textContent = 'Starting Passwall2...';
    chrome.runtime.sendMessage({ command: COMMANDS.PASSWALL2, action: 'start_service', config: currentStatus.activeConfig }, (response) => {
      if (response && response.success) {
        passwall2Message.textContent = 'Passwall2 started.';
        getPasswall2Status();
      } else {
        passwall2Message.textContent = 'Failed to start Passwall2.';
      }
    });
  });

  if (restartPasswall2Button) {
    restartPasswall2Button.addEventListener('click', () => {
      passwall2Message.textContent = 'Restarting Passwall2...';
      chrome.runtime.sendMessage({ command: COMMANDS.PASSWALL2, action: 'restart_service', config: currentStatus.activeConfig }, (response) => {
        if (response && response.success) {
          passwall2Message.textContent = 'Passwall2 restarted.';
          getPasswall2Status();
          setTimeout(() => loadPasswall2Nodes(), 2000);
        } else {
          passwall2Message.textContent = 'Failed to restart Passwall2.';
        }
      });
    });
  }

  stopPasswall2Button.addEventListener('click', () => {
    passwall2Message.textContent = 'Stopping Passwall2...';
    chrome.runtime.sendMessage({ command: COMMANDS.PASSWALL2, action: 'stop_service', config: currentStatus.activeConfig }, (response) => {
      if (response && response.success) {
        passwall2Message.textContent = 'Passwall2 stopped.';
        getPasswall2Status();
      } else {
        passwall2Message.textContent = 'Failed to stop Passwall2.';
      }
    });
  });


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
