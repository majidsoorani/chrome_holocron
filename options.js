document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  // General
  const connectionTypeSshRadio = document.getElementById('conn-type-ssh');
  const connectionTypeOvpnRadio = document.getElementById('conn-type-ovpn');
  const sshSettingsSection = document.getElementById('ssh-settings-section');
  const openvpnSettingsSection = document.getElementById('openvpn-settings-section');
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');
  const autoReconnectCheckbox = document.getElementById('auto-reconnect-enabled');
  const geoIpBypassCheckbox = document.getElementById('geoip-bypass-enabled');
  const saveButton = document.getElementById('save-button');
  const testButton = document.getElementById('test-button');
  const statusMessage = document.getElementById('status-message');

  // SSH
  const commandInput = document.getElementById('ssh-command');
  const sshUserInput = document.getElementById('ssh-user');
  const sshHostInput = document.getElementById('ssh-host');
  const rulesContainer = document.getElementById('port-forwarding-rules');
  const addRuleButton = document.getElementById('add-rule-button');
  const wifiListContainer = document.getElementById('wifi-networks-list');
  const addWifiButton = document.getElementById('add-wifi-button');
  const ruleTemplate = document.getElementById('port-forward-rule-template');
  const wifiTemplate = document.getElementById('wifi-network-template');

  // OpenVPN
  const ovpnConfigListContainer = document.getElementById('ovpn-configs-list');
  const ovpnFileUploadInput = document.getElementById('ovpn-file-upload');
  const ovpnUserInput = document.getElementById('ovpn-user');
  const ovpnPassInput = document.getElementById('ovpn-pass');
  const ovpnConfigTemplate = document.getElementById('ovpn-config-template');

  // --- Functions ---
  function toggleSettingsSections() {
    const isSsh = connectionTypeSshRadio.checked;
    sshSettingsSection.style.display = isSsh ? 'block' : 'none';
    openvpnSettingsSection.style.display = isSsh ? 'none' : 'block';
  }

  // --- Port Forwarding Rule Management ---

  function createRuleElement(rule = {}) {
    const content = ruleTemplate.content.cloneNode(true);
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
      ruleElement.querySelectorAll('.rule-colon').forEach(el => {
        el.style.display = isDynamic ? 'none' : 'inline-block';
      });
    };

    typeSelect.addEventListener('change', toggleInputs);
    removeButton.addEventListener('click', () => ruleElement.remove());

    rulesContainer.appendChild(ruleElement);
    toggleInputs(); // Initial setup
  }

  // --- OpenVPN Config Management ---
  function createOvpnConfigElement(config, activeConfigName) {
    const content = ovpnConfigTemplate.content.cloneNode(true);
    const configElement = content.querySelector('.ovpn-item');
    const radioInput = configElement.querySelector('input[type="radio"]');
    const nameSpan = configElement.querySelector('.ovpn-name');
    const removeButton = configElement.querySelector('.remove-rule-button');

    nameSpan.textContent = config.name;
    radioInput.value = config.name;
    radioInput.checked = config.name === activeConfigName;

    removeButton.addEventListener('click', () => {
        // Find the config in storage and remove it
        chrome.storage.sync.get(STORAGE_KEYS.OVPN_CONFIGS, (result) => {
            let configs = result[STORAGE_KEYS.OVPN_CONFIGS] || [];
            configs = configs.filter(c => c.name !== config.name);
            chrome.storage.sync.set({ [STORAGE_KEYS.OVPN_CONFIGS]: configs }, () => {
                configElement.remove();
                // If the removed config was the active one, clear the active setting
                if (radioInput.checked) {
                    chrome.storage.sync.remove(STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME);
                }
            });
        });
    });

    ovpnConfigListContainer.appendChild(configElement);
  }


  // --- Wi-Fi SSID Management ---

  function createWifiElement(ssid = '') {
    const content = wifiTemplate.content.cloneNode(true);
    const ruleElement = content.querySelector('.rule-item');
    const ssidInput = ruleElement.querySelector('.wifi-ssid-input');
    const removeButton = ruleElement.querySelector('.remove-rule-button');

    ssidInput.value = ssid;
    removeButton.addEventListener('click', () => ruleElement.remove());
    wifiListContainer.appendChild(ruleElement);
  }

  function loadSettings() {
    chrome.storage.sync.get(Object.values(STORAGE_KEYS), (result) => {
      // General settings
      const connType = result[STORAGE_KEYS.CONNECTION_TYPE] || 'ssh';
      if (connType === 'openvpn') {
        connectionTypeOvpnRadio.checked = true;
      } else {
        connectionTypeSshRadio.checked = true;
      }
      toggleSettingsSections();

      pingHostInput.value = result[STORAGE_KEYS.PING_HOST] || 'youtube.com';
      webCheckUrlInput.value = result[STORAGE_KEYS.WEB_CHECK_URL] || 'https://gemini.google.com/app';
      autoReconnectCheckbox.checked = result[STORAGE_KEYS.AUTO_RECONNECT_ENABLED] !== false; // Default to true
      geoIpBypassCheckbox.checked = result[STORAGE_KEYS.GEOIP_BYPASS_ENABLED] !== false; // Default to true

      // SSH settings
      commandInput.value = result[STORAGE_KEYS.SSH_COMMAND_ID] || 'holocron-tunnel';
      sshUserInput.value = result[STORAGE_KEYS.SSH_USER] || '';
      sshHostInput.value = result[STORAGE_KEYS.SSH_HOST] || '';

      rulesContainer.innerHTML = ''; // Clear existing port forwarding rules
      const portForwards = result[STORAGE_KEYS.PORT_FORWARDS] || [];
      if (portForwards.length === 0) {
        createRuleElement({ type: 'D', localPort: '1031' });
        createRuleElement({ type: 'L', localPort: '5434', remoteHost: 'database.example.com', remotePort: '5432' });
      } else {
        portForwards.forEach(createRuleElement);
      }

      wifiListContainer.innerHTML = ''; // Clear existing Wi-Fi networks
      const wifiSsids = result[STORAGE_KEYS.WIFI_SSIDS] || [];
      if (wifiSsids.length === 0) {
        createWifiElement('MyWorkWifi-5G'); // Add a default example
      } else {
        wifiSsids.forEach(createWifiElement);
      }

      // OpenVPN settings
      ovpnConfigListContainer.innerHTML = '';
      const ovpnConfigs = result[STORAGE_KEYS.OVPN_CONFIGS] || [];
      const activeOvpnConfig = result[STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME];
      ovpnConfigs.forEach(config => createOvpnConfigElement(config, activeOvpnConfig));

      ovpnUserInput.value = result[STORAGE_KEYS.OVPN_USER] || '';
      ovpnPassInput.value = result[STORAGE_KEYS.OVPN_PASS] || '';
    });
  }

  function validateSettings() {
    let isValid = true;
    let inputsToValidate = [];
    const connectionType = connectionTypeSshRadio.checked ? 'ssh' : 'openvpn';

    if (connectionType === 'ssh') {
        inputsToValidate = [
            commandInput,
            pingHostInput,
            webCheckUrlInput,
            sshUserInput,
            sshHostInput,
        ];
    } else { // openvpn
        inputsToValidate = [
            pingHostInput,
            webCheckUrlInput,
        ];
    }

    // --- Reset all previous error states ---
    document.querySelectorAll('.invalid').forEach(el => el.classList.remove('invalid'));
    document.querySelectorAll('.error-message').forEach(el => el.remove());

    const showError = (input, message) => {
      isValid = false;
      input.classList.add('invalid');
      const errorEl = document.createElement('small');
      errorEl.className = 'error-message';
      errorEl.textContent = message;
      // Insert error message after the input's description, if it exists, otherwise after the input
      const description = input.parentElement.querySelector('small:not(.error-message)');
      if (description) {
        description.insertAdjacentElement('afterend', errorEl);
      } else {
        input.insertAdjacentElement('afterend', errorEl);
      }
    };

    // 1. Validate that required text fields are not empty
    inputsToValidate.forEach(input => {
      if (!input.value.trim()) {
        showError(input, 'This field cannot be empty.');
      }
    });

    // 2. Validate URL format
    try {
      new URL(webCheckUrlInput.value);
    } catch (_) {
      if (webCheckUrlInput.value.trim()) { // Only show error if not already caught by the empty check
        showError(webCheckUrlInput, 'Please enter a valid URL (e.g., https://example.com).');
      }
    }

    // 3. Validate port forwarding rules
    document.querySelectorAll('#port-forwarding-rules .rule-item').forEach((ruleEl) => {
      const type = ruleEl.querySelector('.rule-type').value;
      const localPortInput = ruleEl.querySelector('.rule-local-port');
      const remoteHostInput = ruleEl.querySelector('.rule-remote-host');
      const remotePortInput = ruleEl.querySelector('.rule-remote-port');

      const localPort = localPortInput.value.trim();
      if (!localPort) {
        showError(localPortInput, 'Local port is required.');
      } else if (!/^\d+$/.test(localPort) || +localPort < 1 || +localPort > 65535) {
        showError(localPortInput, 'Port must be a number from 1-65535.');
      }

      if (type === 'L') {
        if (!remoteHostInput.value.trim()) {
          showError(remoteHostInput, 'Remote host is required for Local forward.');
        }
        const remotePort = remotePortInput.value.trim();
        if (!remotePort) {
          showError(remotePortInput, 'Remote port is required.');
        } else if (!/^\d+$/.test(remotePort) || +remotePort < 1 || +remotePort > 65535) {
          showError(remotePortInput, 'Port must be a number from 1-65535.');
        }
      }
    });

    // 4. Validate Wi-Fi SSIDs
    if (connectionType === 'ssh') {
        document.querySelectorAll('#wifi-networks-list .rule-item').forEach((ruleEl) => {
          const ssidInput = ruleEl.querySelector('.wifi-ssid-input');
          if (!ssidInput.value.trim()) {
            showError(ssidInput, 'SSID cannot be empty.');
          }
        });
    }


    // 5. Validate OpenVPN settings
    if (connectionType === 'openvpn') {
        const activeConfig = document.querySelector('input[name="active-ovpn-config"]:checked');
        if (!activeConfig) {
            isValid = false;
            // Find the container and show an error message
            const container = document.getElementById('ovpn-configs-list');
            showError(container, 'Please upload and select a VPN profile.');
        }
    }

    return isValid;
  }

  function saveSettings() {
    statusMessage.textContent = ''; // Clear previous messages
    statusMessage.className = '';

    if (!validateSettings()) {
      statusMessage.textContent = 'Please fix the errors before saving.';
      statusMessage.className = 'error';
      return;
    }

    const portForwardRules = [];
    document.querySelectorAll('#port-forwarding-rules .rule-item').forEach(el => {
      const type = el.querySelector('.rule-type').value;
      const localPort = el.querySelector('.rule-local-port').value;
      const remoteHost = el.querySelector('.rule-remote-host').value;
      const remotePort = el.querySelector('.rule-remote-port').value;

      if (localPort) { // Only save rules with a local port
        const rule = { type, localPort };
        if (type === 'L') {
          rule.remoteHost = remoteHost;
          rule.remotePort = remotePort;
        }
        portForwardRules.push(rule);
      }
    });

    const wifiSsids = [];
    document.querySelectorAll('#wifi-networks-list .rule-item .wifi-ssid-input').forEach(input => {
      if (input.value.trim()) {
        wifiSsids.push(input.value.trim());
      }
    });

    const connectionType = connectionTypeSshRadio.checked ? 'ssh' : 'openvpn';

    const settings = {
      // General
      [STORAGE_KEYS.CONNECTION_TYPE]: connectionType,
      [STORAGE_KEYS.PING_HOST]: pingHostInput.value,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrlInput.value,
      [STORAGE_KEYS.GEOIP_BYPASS_ENABLED]: geoIpBypassCheckbox.checked,
      [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: autoReconnectCheckbox.checked,

      // SSH
      [STORAGE_KEYS.SSH_COMMAND_ID]: commandInput.value,
      [STORAGE_KEYS.SSH_USER]: sshUserInput.value,
      [STORAGE_KEYS.SSH_HOST]: sshHostInput.value,
      [STORAGE_KEYS.PORT_FORWARDS]: portForwardRules,
      [STORAGE_KEYS.WIFI_SSIDS]: wifiSsids,

      // OpenVPN
      [STORAGE_KEYS.OVPN_USER]: ovpnUserInput.value,
      [STORAGE_KEYS.OVPN_PASS]: ovpnPassInput.value,
      // OVPN_CONFIGS is saved dynamically on upload/delete
    };

    const activeOvpnConfig = document.querySelector('input[name="active-ovpn-config"]:checked');
    if (activeOvpnConfig) {
        settings[STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME] = activeOvpnConfig.value;
    } else {
        // Ensure the key is set to null if nothing is selected
        settings[STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME] = null;
    }


    chrome.storage.sync.set(settings, () => {
      statusMessage.textContent = 'Settings saved!';
      statusMessage.className = 'success';
      setTimeout(() => {
        statusMessage.textContent = '';
        statusMessage.className = '';
      }, 2000);
    });
  }

  // --- Event Listeners ---
  ovpnFileUploadInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) {
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target.result;
      const requiresAuth = /^\s*auth-user-pass\s*$/m.test(content);
      const newConfig = {
        name: file.name,
        content: content,
        requires_auth: requiresAuth,
      };

      chrome.storage.sync.get([STORAGE_KEYS.OVPN_CONFIGS, STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME], (result) => {
        let configs = result[STORAGE_KEYS.OVPN_CONFIGS] || [];
        // Prevent duplicates
        if (configs.some(c => c.name === newConfig.name)) {
            statusMessage.textContent = 'A profile with this name already exists.';
            statusMessage.className = 'error';
            return;
        }
        configs.push(newConfig);
        chrome.storage.sync.set({ [STORAGE_KEYS.OVPN_CONFIGS]: configs }, () => {
          createOvpnConfigElement(newConfig, result[STORAGE_KEYS.ACTIVE_OVPN_CONFIG_NAME]);
          ovpnFileUploadInput.value = ''; // Reset file input
        });
      });
    };
    reader.readAsText(file);
  });

  connectionTypeSshRadio.addEventListener('change', toggleSettingsSections);
  connectionTypeOvpnRadio.addEventListener('change', toggleSettingsSections);
  addRuleButton.addEventListener('click', () => createRuleElement());
  addWifiButton.addEventListener('click', () => createWifiElement());
  saveButton.addEventListener('click', saveSettings); // This now calls the version with validation

  testButton.addEventListener('click', () => {
    // Note: We don't save before testing. The test uses the values currently on screen.
    const sshIdentifier = commandInput.value;
    const pingHost = pingHostInput.value;
    const webCheckUrl = webCheckUrlInput.value;
    statusMessage.textContent = 'Testing...';
    statusMessage.className = 'info';

    const request = {
      command: COMMANDS.TEST_CONNECTION,
      sshCommand: sshIdentifier,
      pingHost: pingHost,
      webCheckUrl: webCheckUrl
    };

    chrome.runtime.sendMessage(request, (response) => {
      if (chrome.runtime.lastError) {
        statusMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
        statusMessage.className = 'error';
        return;
      }

      statusMessage.textContent = response.message;
      statusMessage.className = response.success ? 'success' : 'error';
    });
  });

  // --- Initial Load ---
  loadSettings();
  toggleSettingsSections();
});