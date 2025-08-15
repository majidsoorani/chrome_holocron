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

      const statusDot = li.querySelector('.status-dot');
      const latencyEl = li.querySelector('.proxy-latency');

      if (proxy.id === connectionStatus.activeProxyId && connectionStatus.connected) {
          const latency = connectionStatus.web_check_latency_ms;
          if (latency === -1) {
              statusDot.style.backgroundColor = '#ff3b30'; // red
              latencyEl.textContent = 'Error';
          } else {
              latencyEl.textContent = `${latency}ms`;
              if (latency < 300) {
                  statusDot.style.backgroundColor = '#4cd964'; // green
              } else if (latency < 1000) {
                  statusDot.style.backgroundColor = '#ff9500'; // orange
              } else {
                  statusDot.style.backgroundColor = '#ff3b30'; // red
              }
          }
      } else {
          statusDot.style.backgroundColor = '#d1d1d6'; // grey
          latencyEl.textContent = '--ms';
      }

      li.addEventListener('click', () => {
        selectedIndex = index;
        render();
      });

      // Add edit/delete buttons to each item
      const editButton = document.createElement('button');
      editButton.textContent = 'Edit';
      editButton.addEventListener('click', (e) => { e.stopPropagation(); handleEdit(index); });
      li.appendChild(editButton);

      const deleteButton = document.createElement('button');
      deleteButton.textContent = 'Delete';
      deleteButton.addEventListener('click', (e) => { e.stopPropagation(); handleDelete(index); });
      li.appendChild(deleteButton);


      proxyListElement.appendChild(item);
    });

    if (connectionStatus.connected) {
        connectButton.textContent = 'Disconnect';
    } else {
        connectButton.textContent = 'Connect';
    }
  }

  async function handleConnectClick() {
    if (connectionStatus.connected) {
      const activeProxy = proxyList.find(p => p.id === connectionStatus.activeProxyId);
      chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL, config: activeProxy });
    } else {
      if (selectedIndex !== -1) {
        const proxyToActivate = proxyList[selectedIndex];
        if (!proxyToActivate.id) { proxyToActivate.id = Date.now() + Math.random(); }
        chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: proxyToActivate });
      } else {
        alert("Please select a proxy to connect.");
      }
    }
  }

  async function loadState() {
    const result = await chrome.storage.sync.get(STORAGE_KEYS.PROXY_LIST);
    proxyList = result[STORAGE_KEYS.PROXY_LIST] || [];
    proxyList.forEach(p => { if (!p.id) p.id = Date.now() + Math.random(); });
    render();
  }

  async function saveProxyList() {
    await chrome.storage.sync.set({ [STORAGE_KEYS.PROXY_LIST]: proxyList });
  }

  // --- Modal & Form Logic ---

  // Generic handler to open a modal and clear its form
  function openModal(modal, form, onOpen) {
    form.reset();
    delete form.dataset.editIndex;
    if(onOpen) onOpen();
    modal.style.display = 'block';
  }

  // Generic handler to save proxy data
  async function saveProxy(proxyData, editIndex) {
    if (editIndex !== undefined && editIndex !== null) {
      const originalProxy = proxyList[editIndex];
      proxyData.id = originalProxy.id; // Preserve the original ID
      proxyData.isActive = originalProxy.isActive;
      proxyList[editIndex] = proxyData;
    } else {
      proxyData.isActive = false;
      proxyData.id = `proxy_${Date.now()}_${Math.random()}`;
      proxyList.push(proxyData);
    }
    await saveProxyList();
    render();
  }

  async function handleDelete(index) {
    if (confirm(`Are you sure you want to delete "${proxyList[index].remarks}"?`)) {
      proxyList.splice(index, 1);
      await saveProxyList();
      if (selectedIndex === index) {
        selectedIndex = -1;
      } else if (selectedIndex > index) {
        selectedIndex--;
      }
      render();
    }
  }

  function handleEdit(index) {
    const proxy = proxyList[index];
    const editIndex = String(index); // Use string to avoid confusion with 0
    let modal, form;

    if (proxy.type === 'ssh') {
        modal = document.getElementById('add-ssh-modal');
        form = modal.querySelector('form');
        form.querySelector('#ssh-remarks').value = proxy.remarks;
        form.querySelector('#ssh-command-id').value = proxy.ssh_command_id;
        form.querySelector('#ssh-user').value = proxy.ssh_user;
        form.querySelector('#ssh-host').value = proxy.ssh_host;
        // TODO: Populate rules and ssids
    } else if (proxy.type === 'v2ray') {
        modal = document.getElementById('add-v2ray-modal');
        form = modal.querySelector('form');
        form.querySelector('#v2ray-remarks').value = proxy.remarks;
        form.querySelector('#v2ray-protocol').value = proxy.protocol || 'vmess';
        form.querySelector('#v2ray-server').value = proxy.server;
        form.querySelector('#v2ray-port').value = proxy.port;
        form.querySelector('#v2ray-uuid').value = proxy.uuid;
        form.querySelector('#v2ray-alterid').value = proxy.alterId || 0;
        form.querySelector('#v2ray-socks-port').value = proxy.socksPort;
    } else if (proxy.type === 'ss') {
        modal = document.getElementById('add-ss-modal');
        form = modal.querySelector('form');
        form.querySelector('#ss-remarks').value = proxy.remarks;
        form.querySelector('#ss-server').value = proxy.server;
        form.querySelector('#ss-port').value = proxy.port;
        form.querySelector('#ss-method').value = proxy.method;
        form.querySelector('#ss-password').value = proxy.password;
        form.querySelector('#ss-socks-port').value = proxy.socksPort;
    }

    if(modal && form) {
      form.dataset.editIndex = editIndex;
      modal.style.display = 'block';
    }
  }

  // Add listeners for all modals
  const chooserModal = document.getElementById('add-proxy-chooser-modal');
  const sshModal = document.getElementById('add-ssh-modal');
  const v2rayModal = document.getElementById('add-v2ray-modal');
  const ssModal = document.getElementById('add-ss-modal');
  const importModal = document.getElementById('import-modal');

  // --- Button Listeners ---
  addButton.addEventListener('click', () => {
    chooserModal.style.display = 'block';
  });

  [chooserModal, sshModal, v2rayModal, ssModal, importModal].forEach(modal => {
    modal.querySelector('.close-button').addEventListener('click', () => {
      const form = modal.querySelector('form');
      if (form) {
        form.reset();
        delete form.dataset.editIndex;
      }
      modal.style.display = 'none';
    });
  });

  v2rayModal.querySelector('#v2ray-save-button').addEventListener('click', () => {
      const form = v2rayModal.querySelector('form');
      const editIndex = form.dataset.editIndex ? parseInt(form.dataset.editIndex) : null;
      const v2rayProxy = {
        type: 'v2ray',
        protocol: form.querySelector('#v2ray-protocol').value,
        remarks: form.querySelector('#v2ray-remarks').value || `${form.querySelector('#v2ray-server').value}:${form.querySelector('#v2ray-port').value}`,
        server: form.querySelector('#v2ray-server').value,
        port: parseInt(form.querySelector('#v2ray-port').value),
        uuid: form.querySelector('#v2ray-uuid').value,
        alterId: parseInt(form.querySelector('#v2ray-alterid').value),
        socksPort: parseInt(form.querySelector('#v2ray-socks-port').value),
      };
      saveProxy(v2rayProxy, editIndex);
      v2rayModal.style.display = 'none';
  });

  ssModal.querySelector('#ss-save-button').addEventListener('click', () => {
      const form = ssModal.querySelector('form');
      const editIndex = form.dataset.editIndex ? parseInt(form.dataset.editIndex) : null;
      const ssProxy = {
        type: 'ss',
        remarks: form.querySelector('#ss-remarks').value || `${form.querySelector('#ss-server').value}:${form.querySelector('#ss-port').value}`,
        server: form.querySelector('#ss-server').value,
        port: parseInt(form.querySelector('#ss-port').value),
        method: form.querySelector('#ss-method').value,
        password: form.querySelector('#ss-password').value,
        socksPort: parseInt(form.querySelector('#ss-socks-port').value),
      };
      saveProxy(ssProxy, editIndex);
      ssModal.style.display = 'none';
  });

  sshModal.querySelector('#ssh-save-button').addEventListener('click', () => {
    const form = sshModal.querySelector('form');
    const editIndex = form.dataset.editIndex ? parseInt(form.dataset.editIndex) : null;
    const sshProxy = {
        type: 'ssh',
        remarks: form.querySelector('#ssh-remarks').value || `${form.querySelector('#ssh-user').value}@${form.querySelector('#ssh-host').value}`,
        ssh_command_id: form.querySelector('#ssh-command-id').value,
        ssh_user: form.querySelector('#ssh-user').value,
        ssh_host: form.querySelector('#ssh-host').value,
        port_forwards: [], // TODO: Implement rule saving
        wifi_ssids: [], // TODO: Implement ssid saving
    };
    saveProxy(sshProxy, editIndex);
    sshModal.style.display = 'none';
  });

  const importTextarea = document.getElementById('import-textarea');
  const importConfirmButton = document.getElementById('import-confirm-button');
  const importFromClipboardButton = document.getElementById('import-from-clipboard-button');

  importFromClipboardButton.addEventListener('click', async () => {
      try {
          const text = await navigator.clipboard.readText();
          importTextarea.value = text;
      } catch (err) {
          console.error('Failed to read clipboard contents: ', err);
          alert('Failed to read from clipboard. Please paste manually.');
      }
  });

  importConfirmButton.addEventListener('click', async () => {
    const uris = importTextarea.value.split('\n').filter(uri => uri.trim() !== '');
    let newProxies = 0;
    for (const uri of uris) {
        const parsedConfig = parseUri(uri);
        if (parsedConfig) {
            proxyList.push(parsedConfig);
            newProxies++;
        }
    }

    if (newProxies > 0) {
        await saveProxyList();
        render();
    }

    importTextarea.value = '';
    importModal.style.display = 'none';
  });

  // --- Theme Switcher ---
  const themeSwitcher = document.getElementById('theme-switcher');

  async function applyTheme() {
    const result = await chrome.storage.sync.get('theme');
    const theme = result.theme || 'light';
    document.body.dataset.theme = theme;
  }

  themeSwitcher.addEventListener('click', async () => {
    const currentTheme = document.body.dataset.theme;
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.body.dataset.theme = newTheme;
    await chrome.storage.sync.set({ theme: newTheme });
  });

  // --- Initial Load ---
  loadState();
  applyTheme();
  chrome.runtime.onMessage.addListener((request) => {
    if (request.command === COMMANDS.STATUS_UPDATED) {
        connectionStatus = request.status;
        selectedIndex = proxyList.findIndex(p => p.id === connectionStatus.activeProxyId);
        render();
    }
  });
  chrome.runtime.sendMessage({ command: COMMANDS.GET_POPUP_STATUS }, (status) => {
    if (status) {
        connectionStatus = status;
        selectedIndex = proxyList.findIndex(p => p.id === connectionStatus.activeProxyId);
        render();
    }
  });
});