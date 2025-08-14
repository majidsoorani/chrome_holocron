document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const connectButton = document.getElementById('global-connect-button');
  const proxyListElement = document.getElementById('proxy-list');
  const proxyItemTemplate = document.getElementById('proxy-item-template');
  const addButton = document.getElementById('add-proxy-button');

  // --- State ---
  let proxyList = [];
  let selectedIndex = -1;
  let connectionStatus = { connected: false, activeProxyId: null };

  // --- Functions ---

  function render() {
    proxyListElement.innerHTML = ''; // Clear list

    if (!proxyList || proxyList.length === 0) {
        proxyListElement.innerHTML = '<li><p>No proxy configurations. Click \'+\' to add one.</p></li>';
        return;
    }

    proxyList.forEach((proxy, index) => {
      const item = proxyItemTemplate.content.cloneNode(true);
      const li = item.querySelector('.proxy-item');

      li.dataset.proxyId = proxy.id;
      li.querySelector('.proxy-name').textContent = proxy.remarks || `${proxy.server}:${proxy.port}`;
      li.querySelector('.proxy-info').textContent = proxy.type.toUpperCase();

      if (index === selectedIndex) {
        li.classList.add('selected');
      }

      if (proxy.id === connectionStatus.activeProxyId && connectionStatus.connected) {
          li.querySelector('.status-dot').style.backgroundColor = '#4cd964'; // green
      } else {
          li.querySelector('.status-dot').style.backgroundColor = '#d1d1d6'; // grey
      }

      li.addEventListener('click', () => {
        selectedIndex = index;
        render();
      });

      proxyListElement.appendChild(item);
    });

    if (connectionStatus.connected) {
        connectButton.textContent = 'Disconnect';
        connectButton.classList.add('connected');
    } else {
        connectButton.textContent = 'Connect';
        connectButton.classList.remove('connected');
    }
  }

  async function handleConnectClick() {
    if (connectionStatus.connected) {
      // Disconnect logic - send the currently active proxy config
      const activeProxy = proxyList.find(p => p.id === connectionStatus.activeProxyId);
      chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL, config: activeProxy });
    } else {
      // Connect logic
      if (selectedIndex === -1 && proxyList.length > 0) {
        selectedIndex = 0; // Default to first if none selected
      }
      if (selectedIndex !== -1) {
        const proxyToActivate = proxyList[selectedIndex];
        // Add a unique ID if it doesn't have one (for proxies imported before this change)
        if (!proxyToActivate.id) {
            proxyToActivate.id = Date.now() + Math.random();
        }
        chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: proxyToActivate });
      } else {
        alert("Please select a proxy to connect.");
      }
    }
  }

  async function loadState() {
    const result = await chrome.storage.sync.get(STORAGE_KEYS.PROXY_LIST);
    proxyList = result[STORAGE_KEYS.PROXY_LIST] || [];
    // Ensure all proxies have a unique ID for tracking
    proxyList.forEach(p => { if (!p.id) p.id = Date.now() + Math.random(); });
    render();
  }

  // Listen for status updates from the background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.command === COMMANDS.STATUS_UPDATED) {
        connectionStatus = request.status;
        // Find the selected index based on the active proxy ID from the background
        selectedIndex = proxyList.findIndex(p => p.id === connectionStatus.activeProxyId);
        render();
    }
  });

  // --- Event Listeners ---
  connectButton.addEventListener('click', handleConnectClick);
  // Add button listener will be implemented in Phase 2.

  // --- Initial Load ---
  loadState();
  // Request initial status from background script to sync UI
  chrome.runtime.sendMessage({ command: COMMANDS.GET_POPUP_STATUS }, (status) => {
    if (status) {
        connectionStatus = status;
        selectedIndex = proxyList.findIndex(p => p.id === connectionStatus.activeProxyId);
        render();
    }
  });
});