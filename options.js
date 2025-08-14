document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const importButton = document.getElementById('import-button');
  const proxyListContainer = document.getElementById('proxy-list-container');
  const proxyItemTemplate = document.getElementById('proxy-item-template');
  const statusMessage = document.getElementById('status-message');

  // Global Settings
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');
  const autoReconnectCheckbox = document.getElementById('auto-reconnect-enabled');
  const saveGlobalSettingsButton = document.getElementById('save-global-settings-button');

  let currentProxyList = [];

  // --- Functions ---

  function renderProxyList() {
    proxyListContainer.innerHTML = ''; // Clear existing list

    if (currentProxyList.length === 0) {
        proxyListContainer.innerHTML = '<p>No proxy configurations. Click "Import" to add one.</p>';
        return;
    }

    currentProxyList.forEach((proxy, index) => {
      const content = proxyItemTemplate.content.cloneNode(true);
      const proxyItem = content.querySelector('.proxy-item');

      proxyItem.dataset.index = index;
      proxyItem.querySelector('.proxy-type-badge').textContent = proxy.type.toUpperCase();
      proxyItem.querySelector('.proxy-type-badge').classList.add(`badge-${proxy.type}`);
      proxyItem.querySelector('.proxy-name').textContent = proxy.remarks || `${proxy.server}:${proxy.port}`;

      const activateButton = proxyItem.querySelector('.button-activate');
      if (proxy.isActive) {
        proxyItem.classList.add('active');
        activateButton.textContent = 'Active';
        activateButton.disabled = true;
      } else {
        activateButton.addEventListener('click', () => handleActivate(index));
      }

      proxyItem.querySelector('.button-delete').addEventListener('click', () => handleDelete(index));
      proxyItem.querySelector('.button-edit').addEventListener('click', () => handleEdit(index));

      proxyListContainer.appendChild(proxyItem);
    });
  }

  async function handleActivate(index) {
    currentProxyList.forEach((proxy, i) => {
        proxy.isActive = (i === index);
    });
    await saveProxyList();
    renderProxyList();
    // It might be good to trigger a connection restart here, but for now, we just set the state.
  }

  async function handleDelete(index) {
    if (confirm('Are you sure you want to delete this proxy configuration?')) {
        currentProxyList.splice(index, 1);
        await saveProxyList();
        renderProxyList();
    }
  }

  async function saveProxyList() {
    await chrome.storage.sync.set({ [STORAGE_KEYS.PROXY_LIST]: currentProxyList });
    statusMessage.textContent = 'Proxy list updated!';
    statusMessage.className = 'success';
    setTimeout(() => { statusMessage.textContent = ''; }, 2000);
  }

  async function loadSettings() {
    const result = await chrome.storage.sync.get(Object.values(STORAGE_KEYS));
    currentProxyList = result[STORAGE_KEYS.PROXY_LIST] || [];

    // Load global settings
    pingHostInput.value = result[STORAGE_KEYS.PING_HOST] || 'youtube.com';
    webCheckUrlInput.value = result[STORAGE_KEYS.WEB_CHECK_URL] || 'https://gemini.google.com/app';
    autoReconnectCheckbox.checked = result[STORAGE_KEYS.AUTO_RECONNECT_ENABLED] !== false;

    renderProxyList();
  }

  async function saveGlobalSettings() {
    const settings = {
        [STORAGE_KEYS.PING_HOST]: pingHostInput.value.trim(),
        [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrlInput.value.trim(),
        [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: autoReconnectCheckbox.checked
    };
    await chrome.storage.sync.set(settings);
    statusMessage.textContent = 'Global settings saved!';
    statusMessage.className = 'success';
    setTimeout(() => { statusMessage.textContent = ''; }, 2000);
  }

  // --- Event Listeners ---
  saveGlobalSettingsButton.addEventListener('click', saveGlobalSettings);

  const importModal = document.getElementById('import-modal');
  const importTextarea = document.getElementById('import-textarea');
  const importConfirmButton = document.getElementById('import-confirm-button');
  const closeModalButton = importModal.querySelector('.close-button');

  // SSH Modal Elements
  const addSshButton = document.getElementById('add-ssh-button');
  const addSshModal = document.getElementById('add-ssh-modal');
  const closeSshModalButton = addSshModal.querySelector('.close-button');
  const sshSaveButton = document.getElementById('ssh-save-button');

  importButton.addEventListener('click', () => {
    importModal.style.display = 'block';
  });

  closeModalButton.addEventListener('click', () => {
    importModal.style.display = 'none';
  });

  addSshButton.addEventListener('click', () => {
    // Clear form for adding a new proxy
    addSshModal.querySelector('form').reset();
    sshRulesContainer.innerHTML = '';
    sshWifiListContainer.innerHTML = '';
    createSshRuleElement({ type: 'D', localPort: '1080' }); // Default SOCKS
    delete sshSaveButton.dataset.editIndex;
    addSshModal.style.display = 'block';
  });

  closeSshModalButton.addEventListener('click', () => {
    addSshModal.style.display = 'none';
  });

  importConfirmButton.addEventListener('click', async () => {
    const uris = importTextarea.value.split('\n').filter(uri => uri.trim() !== '');
    let newProxies = 0;
    for (const uri of uris) {
        const parsedConfig = parseUri(uri);
        if (parsedConfig) {
            currentProxyList.push(parsedConfig);
            newProxies++;
        }
    }

    if (newProxies > 0) {
        await saveProxyList();
        renderProxyList();
    }

    importTextarea.value = '';
    importModal.style.display = 'none';
    statusMessage.textContent = `Successfully imported ${newProxies} new configurations.`;
    statusMessage.className = 'success';
    setTimeout(() => { statusMessage.textContent = ''; }, 2000);
  });


  function handleEdit(index) {
    const proxy = currentProxyList[index];
    if (proxy.type === 'ssh') {
        document.getElementById('ssh-remarks').value = proxy.remarks;
        document.getElementById('ssh-command-id').value = proxy.ssh_command_id;
        document.getElementById('ssh-user').value = proxy.ssh_user;
        document.getElementById('ssh-host').value = proxy.ssh_host;

        sshRulesContainer.innerHTML = '';
        (proxy.port_forwards || []).forEach(createSshRuleElement);

        sshWifiListContainer.innerHTML = '';
        (proxy.wifi_ssids || []).forEach(createSshWifiElement);

        sshSaveButton.dataset.editIndex = index; // Store index for saving
        addSshModal.style.display = 'block';
    } else {
        alert(`Editing for proxy type '${proxy.type}' is not yet implemented.`);
    }
  }

  // --- SSH Modal Logic ---
  const sshRulesContainer = document.getElementById('ssh-port-forwarding-rules');
  const sshRuleTemplate = document.getElementById('ssh-port-forward-rule-template');
  const addSshRuleButton = document.getElementById('ssh-add-rule-button');
  const sshWifiListContainer = document.getElementById('ssh-wifi-networks-list');
  const sshWifiTemplate = document.getElementById('ssh-wifi-network-template');
  const addSshWifiButton = document.getElementById('ssh-add-wifi-button');

  function createSshWifiElement(ssid = '') {
    const content = sshWifiTemplate.content.cloneNode(true);
    const wifiItem = content.querySelector('.rule-item');
    wifiItem.querySelector('.wifi-ssid-input').value = ssid;
    wifiItem.querySelector('.remove-rule-button').addEventListener('click', () => wifiItem.remove());
    sshWifiListContainer.appendChild(wifiItem);
  }

  function createSshRuleElement(rule = {}) {
    const content = sshRuleTemplate.content.cloneNode(true);
    const ruleElement = content.querySelector('.rule-item');
    const typeSelect = ruleElement.querySelector('.rule-type');
    const localPortInput = ruleElement.querySelector('.rule-local-port');
    const remoteHostInput = ruleElement.querySelector('.rule-remote-host');
    const remotePortInput = ruleElement.querySelector('.rule-remote-port');
    const removeButton = ruleElement.querySelector('.remove-rule-button');

    typeSelect.value = rule.type || 'L';
    localPortInput.value = rule.localPort || '';
    remoteHostInput.value = rule.remoteHost || '';
    remotePortInput.value = rule.remotePort || '';

    const toggleInputs = () => {
      const isDynamic = typeSelect.value === 'D';
      remoteHostInput.style.display = isDynamic ? 'none' : 'inline-block';
      remotePortInput.style.display = isDynamic ? 'none' : 'inline-block';
    };

    typeSelect.addEventListener('change', toggleInputs);
    removeButton.addEventListener('click', () => ruleElement.remove());
    sshRulesContainer.appendChild(ruleElement);
    toggleInputs();
  }

  addSshRuleButton.addEventListener('click', () => createSshRuleElement());
  addSshWifiButton.addEventListener('click', () => createSshWifiElement());

  sshSaveButton.addEventListener('click', async () => {
    const portForwards = [];
    sshRulesContainer.querySelectorAll('.rule-item').forEach(el => {
        const type = el.querySelector('.rule-type').value;
        const localPort = el.querySelector('.rule-local-port').value;
        const remoteHost = el.querySelector('.rule-remote-host').value;
        const remotePort = el.querySelector('.rule-remote-port').value;
        if (localPort) {
            const rule = { type, localPort };
            if (type === 'L') {
                rule.remoteHost = remoteHost;
                rule.remotePort = remotePort;
            }
            portForwards.push(rule);
        }
    });

    const wifiSsids = [];
    sshWifiListContainer.querySelectorAll('.wifi-ssid-input').forEach(input => {
        if (input.value.trim()) {
            wifiSsids.push(input.value.trim());
        }
    });

    const sshProxy = {
        type: 'ssh',
        remarks: document.getElementById('ssh-remarks').value.trim(),
        ssh_command_id: document.getElementById('ssh-command-id').value.trim(),
        ssh_user: document.getElementById('ssh-user').value.trim(),
        ssh_host: document.getElementById('ssh-host').value.trim(),
        port_forwards: portForwards,
        wifi_ssids: wifiSsids
    };

    // Basic validation
    if (!sshProxy.remarks || !sshProxy.ssh_command_id || !sshProxy.ssh_user || !sshProxy.ssh_host) {
        alert('Please fill out all SSH fields.');
        return;
    }

    const editIndex = sshSaveButton.dataset.editIndex;
    if (editIndex) {
        // Update existing proxy
        const originalProxy = currentProxyList[editIndex];
        sshProxy.isActive = originalProxy.isActive; // Preserve active state
        currentProxyList[editIndex] = sshProxy;
    } else {
        // Add new proxy
        sshProxy.isActive = false; // New proxies are not active by default
        currentProxyList.push(sshProxy);
    }

    await saveProxyList();
    renderProxyList();
    addSshModal.style.display = 'none'; // Close modal on save
  });


  // --- Initial Load ---
  loadSettings();
});