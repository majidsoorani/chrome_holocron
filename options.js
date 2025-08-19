import { COMMANDS, STORAGE_KEYS } from './constants.js';

document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');
  const coreConfigListContainer = document.getElementById('core-configurations-list');
  const addConfigButton = document.getElementById('add-config-button');
  const coreConfigTemplate = document.getElementById('core-configuration-template');
  const proxyBypassRuleTemplate = document.getElementById('proxy-bypass-rule-template');
  const addProxyRuleButton = document.getElementById('add-proxy-rule-button');
  const autoReconnectCheckbox = document.getElementById('auto-reconnect-enabled');
  const wifiListContainer = document.getElementById('wifi-networks-list');
  const addWifiButton = document.getElementById('add-wifi-button');
  const ruleTemplate = document.getElementById('port-forward-rule-template');
  const wifiTemplate = document.getElementById('wifi-network-template');
  const saveButton = document.getElementById('save-button');
  const discardButton = document.getElementById('discard-button');
  const testButton = document.getElementById('test-button');
  const statusMessage = document.getElementById('status-message');
  const geoipStatusDiv = document.getElementById('geoip-status');
  const geositeStatusDiv = document.getElementById('geosite-status');
  const updateDbButton = document.getElementById('update-db-button');
  const connectionStatusIndicator = document.getElementById('connection-status-indicator');
  const connectionStatusText = document.getElementById('connection-status-text');
  const disconnectTunnelButton = document.getElementById('disconnect-tunnel-button');
  const reconnectNowContainer = document.getElementById('manual-reconnect-container');
  const reconnectNowButton = document.getElementById('reconnect-now-button');
  const applyProxyButton = document.getElementById('apply-proxy-button');
  const revertProxyButton = document.getElementById('revert-proxy-button');
  const webLatencyChartCanvas = document.getElementById('web-latency-chart');
  const tcpPingChartCanvas = document.getElementById('tcp-ping-chart');
    const refreshWebLatencyChartButton = document.getElementById('refresh-web-latency-chart');
    const refreshTcpPingChartButton = document.getElementById('refresh-tcp-ping-chart');
  const globalGeoIpBypassCheckbox = document.getElementById('global-geoip-bypass');
  const globalGeoSiteBypassCheckbox = document.getElementById('global-geosite-bypass');
  const proxyBypassRulesList = document.getElementById('proxy-bypass-rules-list');
  const pacScriptPreviewContainer = document.getElementById('pac-script-preview-container');
  const logViewerContent = document.getElementById('log-viewer-content');
  const clearLogButton = document.getElementById('clear-log-button');
  const aiSuggestRuleButton = document.getElementById('ai-suggest-rule-button');
  const openrouterModelInput = document.getElementById('openrouter-model');
  const openrouterSystemMessageInput = document.getElementById('openrouter-system-message');
  const aiLiveLogContainer = document.getElementById('ai-live-log-container');
  const aiLiveLogContent = document.getElementById('ai-live-log-content');

  // --- Tabbed Interface Logic ---
  const tabsNav = document.querySelector('.tabs-nav');
  const tabPanels = document.querySelectorAll('.tab-panel');
  const tabButtons = document.querySelectorAll('.tab-button');

  if (tabsNav) {
    tabsNav.addEventListener('click', (e) => {
        const clickedButton = e.target.closest('.tab-button');
        if (!clickedButton) return;

        // Remove active state from all
        tabButtons.forEach(button => button.classList.remove('active'));
        tabPanels.forEach(panel => panel.classList.remove('active'));

        // Apply active state to the clicked tab and its panel
        const tabId = clickedButton.dataset.tab;
        const targetPanel = document.getElementById(`panel-${tabId}`);

        clickedButton.classList.add('active');
        if (targetPanel) {
          targetPanel.classList.add('active');
        }
    });
  }

  // --- State ---
  let isDirty = false;
  let currentStatus = {}; // Cache the latest status object
  let webLatencyChart = null;
  let tcpPingChart = null;
  let coreConfigsForSelect = []; // Cache configs for dropdowns
  const MAX_CHART_POINTS = 60; // Show last 60 data points
  let configLogPollIntervals = {}; // To hold setInterval IDs for config-specific log polling.
  let logPollInterval = null; // To hold the setInterval ID for log polling
  let mainLogPollInterval = null; // For the main log viewer

  const ICONS = {
    EDIT: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>`,
    DONE: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  };

  // --- Functions ---

  function setDirty(dirtyState) {
    if (isDirty === dirtyState) return; // No change
    isDirty = dirtyState;
    updateActionButtonsState();
  }

  function updateActionButtonsState() {
    const actionButtons = [
        testButton,
        disconnectTunnelButton,
        reconnectNowButton,
        applyProxyButton,
        revertProxyButton,
        updateDbButton,
        clearLogButton,
        aiSuggestRuleButton,
        ...document.querySelectorAll('.connect-config-button'),
        ...document.querySelectorAll('.disconnect-config-button'),
    ];

    if (isDirty) {
        actionButtons.forEach(btn => {
            btn.disabled = true;
            btn.title = 'Save or discard changes to enable this action.';
        });
        discardButton.style.display = 'inline-block';
        saveButton.classList.add('pulse');
        statusMessage.textContent = 'You have unsaved changes.';
        statusMessage.className = 'info';
    } else {
        actionButtons.forEach(btn => {
            btn.disabled = false;
            btn.title = ''; // Reset title
        });
        discardButton.style.display = 'none';
        saveButton.classList.remove('pulse');
    }
  }

  // --- Core Configuration Management ---
  function createConfigElement(config = {}, activeConfigId, startInEditMode = false) {
    const content = coreConfigTemplate.content.cloneNode(true);
    const configItem = content.querySelector('.config-item');
    const details = configItem.querySelector('.config-details');
    const checkbox = configItem.querySelector('.config-enabled-checkbox');
    const nameDisplay = configItem.querySelector('.config-name');
    const userHostDisplay = configItem.querySelector('.config-user-host');
    const editButton = configItem.querySelector('.edit-config-button');
    const deleteButton = configItem.querySelector('.delete-config-button');
    const connectButton = configItem.querySelector('.connect-config-button');
    const disconnectButton = configItem.querySelector('.disconnect-config-button');
    const duplicateButton = configItem.querySelector('.duplicate-config-button');

    // Inputs inside details
    const nameInput = details.querySelector('.config-input-name');
    const typeSelect = details.querySelector('.config-type-select');

    // SSH settings
    const sshSettings = details.querySelector('.ssh-settings');
    const sshUserInput = sshSettings.querySelector('.config-input-ssh-user');
    const sshHostInput = sshSettings.querySelector('.config-input-ssh-host');
    const sshRemoteCommandInput = sshSettings.querySelector('.config-input-ssh-remote-command');
    const portForwardingList = sshSettings.querySelector('.port-forwarding-rules-list');
    const addPortForwardRuleButton = sshSettings.querySelector('.add-port-forward-rule-button');

    // OpenVPN settings
    const openvpnSettings = details.querySelector('.openvpn-settings');
    const ovpnProfileNameInput = openvpnSettings.querySelector('.ovpn-profile-name');
    const ovpnFileUpload = openvpnSettings.querySelector('.ovpn-file-upload');
    const ovpnFileStatus = openvpnSettings.querySelector('.ovpn-file-status');
    const ovpnFileContent = openvpnSettings.querySelector('.ovpn-file-content');
    const ovpnAuthContainer = openvpnSettings.querySelector('.ovpn-auth-container');
    const ovpnAuthUser = openvpnSettings.querySelector('.ovpn-auth-user');
    const ovpnAuthPass = openvpnSettings.querySelector('.ovpn-auth-pass');

    // V2Ray settings
    const v2raySettings = details.querySelector('.v2ray-settings');
    const v2rayUrlInput = v2raySettings.querySelector('.config-input-v2ray-url');
    const v2rayDetectedParams = v2raySettings.querySelector('.v2ray-detected-params');
    const v2rayParamsList = v2raySettings.querySelector('.v2ray-params-list');

    // Live Log viewer
    const liveLogContainer = details.querySelector('.config-live-log-container');
    const liveLogContent = details.querySelector('.config-live-log-content');

    const configId = config.id || crypto.randomUUID();
    configItem.dataset.id = configId;

    // --- Helper to check if OVPN profile needs auth ---
    const checkOvpnForAuth = (content) => {
        // Show auth fields if 'auth-user-pass' is present and *not* followed by a filename,
        // which implies interactive prompt is needed.
        const needsAuth = /^\s*auth-user-pass\s*$/m.test(content || '');
        ovpnAuthContainer.style.display = needsAuth ? 'flex' : 'none';
        return needsAuth;
    };

    // --- Type Switching ---
    const toggleSettingsVisibility = () => {
        const type = typeSelect.value;
        sshSettings.style.display = 'none';
        openvpnSettings.style.display = 'none';
        v2raySettings.style.display = 'none';

        if (type === 'ssh') {
            sshSettings.style.display = 'block';
        } else if (type === 'openvpn') {
            openvpnSettings.style.display = 'block';
        } else if (type === 'v2ray') {
            v2raySettings.style.display = 'block';
        }
        updateUserHostDisplay(); // Update summary on type change
    };

    typeSelect.addEventListener('change', () => {
        toggleSettingsVisibility();
        setDirty(true);
    });

    // Populate fields
    nameInput.value = config.name || '';
    typeSelect.value = config.type || 'ssh';

    // SSH fields
    sshUserInput.value = config.sshUser || '';
    sshHostInput.value = config.sshHost || '';
    sshRemoteCommandInput.value = config.sshRemoteCommand || '';

    // OpenVPN fields
    ovpnProfileNameInput.value = config.ovpnProfileName || '';
    ovpnFileContent.value = config.ovpnFileContent || '';
    ovpnAuthUser.value = config.ovpnUser || '';
    ovpnAuthPass.value = config.ovpnPass || '';
    if (config.ovpnFileContent) {
        ovpnFileStatus.textContent = `Saved profile loaded. Upload a new file to replace it.`;
    }
    checkOvpnForAuth(config.ovpnFileContent); // Check on initial load

    // V2Ray fields
    v2rayUrlInput.value = config.v2rayUrl || '';

    // Listen for changes to the enabled state to update the PAC script preview
    checkbox.addEventListener('change', () => {
      updateAllProxyRuleDropdownsAndPreview();
      setDirty(true);
    });

    checkbox.checked = config.enabled === true; // Default to false if undefined

    nameDisplay.textContent = config.name || 'New Configuration';

    const updateUserHostDisplay = () => {
        const type = typeSelect.value;
        let summary = '';
        if (type === 'ssh') {
            const user = sshUserInput.value.trim();
            const host = sshHostInput.value.trim();
            summary = (user && host) ? `${user}@${host}` : 'SSH connection details missing';
        } else if (type === 'openvpn') {
            const profileName = ovpnProfileNameInput.value.trim();
            summary = profileName ? `OpenVPN: ${profileName}` : 'OpenVPN profile details missing';
        } else if (type === 'v2ray') {
            const url = v2rayUrlInput.value.trim();
            // Try to parse out the remark from the URL, e.g., vless://...@...#My-Server
            const remarkMatch = url.match(/#(.+)$/);
            if (remarkMatch && remarkMatch[1]) {
                summary = `V2Ray: ${decodeURIComponent(remarkMatch[1])}`;
            } else if (url) {
                summary = 'V2Ray connection';
            } else {
                summary = 'V2Ray URL missing';
            }
        }
      userHostDisplay.textContent = summary;
    };

    // Initial population
    updateUserHostDisplay();
    toggleSettingsVisibility(); // Set initial visibility based on loaded config

    // Event Listeners
    editButton.addEventListener('click', () => {
      const isEditing = details.style.display === 'block';
      details.style.display = isEditing ? 'none' : 'block';
      editButton.innerHTML = isEditing ? ICONS.EDIT : ICONS.DONE;
      editButton.title = isEditing ? 'Edit configuration' : 'Done editing';
      if (!isEditing) nameInput.focus();
    });

    deleteButton.addEventListener('click', () => {
      if (confirm(`Are you sure you want to delete the "${nameDisplay.textContent}" configuration?`)) {
        configItem.remove();
        updateAllProxyRuleDropdownsAndPreview();
        setDirty(true);
      }
    });

    duplicateButton.addEventListener('click', () => {
      const newConfig = {
        id: crypto.randomUUID(),
        name: `${nameInput.value.trim()} (copy)`,
        type: typeSelect.value,
        enabled: checkbox.checked,
        sshUser: sshUserInput.value.trim(),
        sshHost: sshHostInput.value.trim(),
        sshRemoteCommand: sshRemoteCommandInput.value.trim(),
        ovpnProfileName: ovpnProfileNameInput.value.trim(),
        ovpnFileContent: ovpnFileContent.value,
        v2rayUrl: v2rayUrlInput.value.trim(),
        // Note: Passwords are not persisted to sync storage for security.
        portForwards: (config.portForwards || []).map(p => ({...p})), // Deep copy
      };
      const newElement = createConfigElement(newConfig, null, true);
      configItem.after(newElement);
      updateAllProxyRuleDropdownsAndPreview();
      setDirty(true);
    });

    // OVPN File handling
    ovpnFileUpload.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            ovpnFileContent.value = e.target.result;
            ovpnFileStatus.textContent = `File selected: ${file.name}`;
            checkOvpnForAuth(e.target.result);
            setDirty(true);
        };
        reader.readAsText(file);
    });


    nameInput.addEventListener('input', () => {
      nameDisplay.textContent = nameInput.value || 'New Configuration';
      updateAllProxyRuleDropdownsAndPreview();
      setDirty(true);
    });
    sshUserInput.addEventListener('input', () => { updateUserHostDisplay(); setDirty(true); });
    sshHostInput.addEventListener('input', () => { updateUserHostDisplay(); setDirty(true); });
    sshRemoteCommandInput.addEventListener('input', () => setDirty(true));
    ovpnProfileNameInput.addEventListener('input', () => { updateUserHostDisplay(); setDirty(true); });
    ovpnAuthUser.addEventListener('input', () => setDirty(true));
    ovpnAuthPass.addEventListener('input', () => setDirty(true));
    v2rayUrlInput.addEventListener('input', () => {
        updateUserHostDisplay();
        parseAndDisplayV2RayUrl(v2rayUrlInput.value);
        setDirty(true);
    });

    const parseAndDisplayV2RayUrl = (url) => {
        if (!url || !url.startsWith('vless://')) {
            v2rayDetectedParams.style.display = 'none';
            return;
        }

        try {
            const urlObject = new URL(url);
            v2rayParamsList.innerHTML = ''; // Clear previous
            let hasParams = false;

            const remark = urlObject.hash.substring(1);
            if (remark) {
                const li = document.createElement('li');
                li.innerHTML = `• <strong>Remark:</strong> ${decodeURIComponent(remark)}`;
                v2rayParamsList.appendChild(li);
                hasParams = true;
            }

            const address = `${urlObject.hostname}:${urlObject.port}`;
            if (address) {
                const li = document.createElement('li');
                li.innerHTML = `• <strong>Address:</strong> ${address}`;
                v2rayParamsList.appendChild(li);
                hasParams = true;
            }

            const protocol = urlObject.protocol.replace(':', '');
            if (protocol) {
                const li = document.createElement('li');
                li.innerHTML = `• <strong>Protocol:</strong> ${protocol}`;
                v2rayParamsList.appendChild(li);
                hasParams = true;
            }

            v2rayDetectedParams.style.display = hasParams ? 'block' : 'none';
        } catch (e) {
            v2rayDetectedParams.style.display = 'none';
        }
    };


    connectButton.addEventListener('click', () => {
        const type = typeSelect.value;

        // --- Live Log ---
        if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);
        liveLogContainer.style.display = 'block';
        liveLogContent.textContent = 'Initiating connection...';

        const pollConfigLogs = () => {
            // Stop polling if the element is no longer in the DOM or visible
            if (!document.body.contains(configItem) || liveLogContainer.style.display === 'none') {
                if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);
                delete configLogPollIntervals[configId];
                return;
            }
            chrome.runtime.sendMessage(
                { command: COMMANDS.GET_LOGS, identifier: configId, conn_type: type },
                (response) => {
                    if (!configLogPollIntervals[configId]) return; // Stop if interval has been cleared elsewhere
                    if (chrome.runtime.lastError) {
                        liveLogContent.textContent = `Error polling logs: ${chrome.runtime.lastError.message}`;
                        clearInterval(configLogPollIntervals[configId]);
                        delete configLogPollIntervals[configId];
                    } else if (response && response.success) {
                        liveLogContent.textContent = response.log_content || 'Waiting for log output...';
                        liveLogContainer.scrollTop = liveLogContainer.scrollHeight;
                    }
                }
            );
        };
        // Scrape data from this specific config item's inputs to send to the background script.
        const configPayload = {
            id: configId,
            name: nameInput.value.trim(),
            enabled: checkbox.checked,
            type: type,
        };

        if (type === 'ssh') {
            Object.assign(configPayload, {
                sshUser: sshUserInput.value.trim(),
                sshHost: sshHostInput.value.trim(),
                sshRemoteCommand: sshRemoteCommandInput.value.trim(),
                portForwards: Array.from(
                    portForwardingList.querySelectorAll('.rule-item')
                ).map(el => {
                    const type = el.querySelector('.rule-type').value;
                    const localPort = el.querySelector('.rule-local-port').value;
                    const remoteHost = el.querySelector('.rule-remote-host').value;
                    const remotePort = el.querySelector('.rule-remote-port').value;
                    if (!localPort) return null;
                    const rule = { type, localPort };
                    if (type === 'L' || type === 'R') {
                        rule.remoteHost = remoteHost;
                        rule.remotePort = remotePort;
                    }
                    return rule;
                }).filter(Boolean),
            });
        } else if (type === 'openvpn') {
            Object.assign(configPayload, {
                ovpnProfileName: ovpnProfileNameInput.value.trim(),
                ovpnFileContent: ovpnFileContent.value,
                ovpnUser: ovpnAuthUser.value, // Pass credentials
                ovpnPass: ovpnAuthPass.value,
            });
        } else if (type === 'v2ray') {
            Object.assign(configPayload, {
                v2rayUrl: v2rayUrlInput.value.trim(),
            });
        }


        statusMessage.textContent = `Connecting with "${configPayload.name}"...`;
        statusMessage.className = 'info';
        connectButton.disabled = true;
        pollConfigLogs(); // Initial call
        configLogPollIntervals[configId] = setInterval(pollConfigLogs, 1500);

        chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: configPayload }, (response) => {
            // The main UI update will come from the broadcasted status message.
            // But if the command fails immediately, we should stop polling.
            if (response && !response.success) {
                if (configLogPollIntervals[configId]) {
                    clearInterval(configLogPollIntervals[configId]);
                    delete configLogPollIntervals[configId];
                }
                statusMessage.textContent = `Failed to connect: ${response.message}`;
                statusMessage.className = 'error';
                // Keep the log viewer open on failure for debugging.
                // If it's a clear authentication failure, help the user correct it.
                if (type === 'openvpn' && response.message.includes("Authentication failed")) {
                    ovpnAuthPass.value = ''; // Clear password field for re-entry
                    ovpnAuthPass.focus();
                }
            }
            // On success, the status update broadcast will eventually clear the pollers when the connection state changes.
        });
    });

    disconnectButton.addEventListener('click', () => {
        liveLogContainer.style.display = 'none';
        if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);
        delete configLogPollIntervals[configId];
        statusMessage.textContent = `Disconnecting...`;
        statusMessage.className = 'info';
        chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL });
    });

    // --- Port Forwarding Management ---
    (config.portForwards || []).forEach(rule => {
      portForwardingList.appendChild(createRuleElement(rule));
    });

    addPortForwardRuleButton.addEventListener('click', (e) => {
      e.preventDefault(); // Prevent form submission if it's inside a form
      const newRuleEl = createRuleElement();
      portForwardingList.appendChild(newRuleEl);
      setDirty(true);
    });

    if (startInEditMode) {
      details.style.display = 'block';
      editButton.innerHTML = ICONS.DONE;
      editButton.title = 'Done editing';
    } else {
      // The default is already in the template, but this ensures it if the template were to change.
      editButton.innerHTML = ICONS.EDIT;
      editButton.title = 'Edit configuration';
    }

    return configItem;
  }

  function createProxyBypassRuleElement(rule = {}) {
    const content = proxyBypassRuleTemplate.content.cloneNode(true);
    const ruleElement = content.querySelector('.rule-item');
    const domainInput = ruleElement.querySelector('.bypass-domain-input');
    const targetSelect = ruleElement.querySelector('.bypass-target-select');
    const removeButton = ruleElement.querySelector('.remove-rule-button');

    domainInput.value = rule.domain || '';

    // Populate the select dropdown from the cached list of configs
    coreConfigsForSelect.forEach(config => {
        const option = document.createElement('option');
        option.value = config.id;
        option.textContent = `Proxy via: ${config.name}`;
        targetSelect.appendChild(option);
    });

    targetSelect.value = rule.target || 'DIRECT';

    domainInput.addEventListener('input', () => {
      updatePacScriptPreview();
      setDirty(true);
    });
    targetSelect.addEventListener('change', () => {
      updatePacScriptPreview();
      setDirty(true);
    });
    removeButton.addEventListener('click', () => {
      ruleElement.remove();
      updatePacScriptPreview();
      setDirty(true);
    });
    return ruleElement;
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
      const isRemote = typeSelect.value === 'R';

      // Set visibility
      remoteHostInput.style.display = isDynamic ? 'none' : 'inline-block';
      remotePortInput.style.display = isDynamic ? 'none' : 'inline-block';
      ruleElement.querySelectorAll('.rule-colon').forEach(el => {
        el.style.display = isDynamic ? 'none' : 'inline-block';
      });

      // Set placeholders based on rule type for clarity
      localPortInput.placeholder = isRemote ? 'Remote Port' : 'Local Port';
      remoteHostInput.placeholder = isRemote ? 'Local Host' : 'Remote Host';
      remotePortInput.placeholder = isRemote ? 'Local Port' : 'Remote Port';
    };

    typeSelect.addEventListener('change', () => { toggleInputs(); setDirty(true); });
    removeButton.addEventListener('click', () => { ruleElement.remove(); setDirty(true); });

    // Add listeners to inputs
    localPortInput.addEventListener('input', () => setDirty(true));
    remoteHostInput.addEventListener('input', () => setDirty(true));
    remotePortInput.addEventListener('input', () => setDirty(true));

    toggleInputs(); // Initial setup
    return ruleElement;
  }

  // --- Wi-Fi SSID Management ---

  function createWifiElement(ssid = '') {
    const content = wifiTemplate.content.cloneNode(true);
    const ruleElement = content.querySelector('.rule-item');
    const ssidInput = ruleElement.querySelector('.wifi-ssid-input');
    const removeButton = ruleElement.querySelector('.remove-rule-button');

    ssidInput.value = ssid;
    ssidInput.addEventListener('input', () => setDirty(true));
    removeButton.addEventListener('click', () => { ruleElement.remove(); setDirty(true); });
    wifiListContainer.appendChild(ruleElement);
  }

  // --- Connection & Proxy UI Management ---

  async function updateConnectionUI(status) {
    currentStatus = status; // Cache the status

    if (!status || !status.connected) {
      // --- DISCONNECTED STATE ---
      connectionStatusIndicator.className = 'status-indicator bad';
      connectionStatusText.textContent = 'Tunnel Disconnected';
      disconnectTunnelButton.style.display = 'none';
      applyProxyButton.style.display = 'none';
      revertProxyButton.style.display = 'none';
      reconnectNowContainer.style.display = 'block';

      // Stop all config log polling if disconnected
      if (Object.keys(configLogPollIntervals).length > 0) {
        Object.values(configLogPollIntervals).forEach(clearInterval);
        configLogPollIntervals = {};
        document.querySelectorAll('.config-live-log-container').forEach(el => el.style.display = 'none');
      }
    } else {
      // --- CONNECTED STATE ---
      connectionStatusIndicator.className = 'status-indicator good';
      connectionStatusText.textContent = 'Tunnel Connected';
      disconnectTunnelButton.style.display = 'inline-block';

      // Check proxy status only if connected and SOCKS port is available
      if (status.socks_port) {
        const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
        if (isProxyManaged) {
          connectionStatusText.textContent = 'Tunnel Connected (Proxy Applied)';
          applyProxyButton.style.display = 'none';
          revertProxyButton.style.display = 'inline-block';
        } else {
          connectionStatusText.textContent = 'Tunnel Connected (Proxy Ready)';
          applyProxyButton.style.display = 'inline-block';
          revertProxyButton.style.display = 'none';
        }
      } else {
        // Connected but no SOCKS port, can't apply proxy
        applyProxyButton.style.display = 'none';
        revertProxyButton.style.display = 'none';
      }
      reconnectNowContainer.style.display = 'none';
    }
    // --- Per-Configuration Button State ---
    const activeConfigId = status ? status.activeConfigId : null;
    document.querySelectorAll('#core-configurations-list .config-item').forEach(item => {
        const connectBtn = item.querySelector('.connect-config-button');
        const disconnectBtn = item.querySelector('.disconnect-config-button');
        const configId = item.dataset.id;

        if (status && status.connected) {
            if (configId === activeConfigId) {
                // This is the active one
                connectBtn.style.display = 'none';
                disconnectBtn.style.display = 'inline-block';
                disconnectBtn.disabled = isDirty; // Respect dirty state
            } else {
                // Another one is active, so disable connecting this one
                connectBtn.style.display = 'inline-block';
                connectBtn.disabled = true;
                connectBtn.title = 'Disconnect the active tunnel before connecting another.';
                disconnectBtn.style.display = 'none';
            }
        } else {
            // Nothing is connected, all are available to connect
            connectBtn.style.display = 'inline-block';
            connectBtn.disabled = isDirty; // Respect dirty state
            connectBtn.title = 'Connect using this configuration';
            disconnectBtn.style.display = 'none';
        }
    });

    updateActionButtonsState(); // Re-evaluate button states after UI changes
  }

  function updatePacScriptPreview() {
    const geoIpBypassEnabled = globalGeoIpBypassCheckbox.checked;
    const geoSiteBypassEnabled = globalGeoSiteBypassCheckbox.checked;

    const customRules = Array.from(
      document.querySelectorAll('#proxy-bypass-rules-list .rule-item')
    ).map(el => {
      const domain = el.querySelector('.bypass-domain-input').value.trim();
      const target = el.querySelector('.bypass-target-select').value;
      if (!domain) return null;
      return { domain, target };
    }).filter(Boolean);

    let pacScript = `/**
 * Holocron PAC (Proxy Auto-Configuration) Script
 * Generated: ${new Date().toISOString()}
 */
function FindProxyForURL(url, host) {
    // --- Proxy Definitions ---
    // These are defined based on your Core Configurations that have a Dynamic (-D) port forward.
`;

    const proxyDefinitions = [];
    document.querySelectorAll('#core-configurations-list .config-item').forEach(item => {
      const configId = item.dataset.id;
      const configType = item.querySelector('.config-type-select').value;
      const configName = item.querySelector('.config-input-name').value.trim() || 'Untitled';
      const portForwardingList = item.querySelector('.port-forwarding-rules-list');

      // For SSH configs, check port forwarding rules
      portForwardingList.querySelectorAll('.rule-item').forEach(ruleEl => {
        const type = ruleEl.querySelector('.rule-type').value;
        if (type === 'D') {
          const port = ruleEl.querySelector('.rule-local-port').value;
          if (port) {
            const proxyVar = `PROXY_${configId.replace(/-/g, '_')}`;
            pacScript += `    const ${proxyVar} = "SOCKS5 127.0.0.1:${port}"; // For "${configName}"\n`;
            proxyDefinitions.push({ id: configId, variable: proxyVar });
          }
        }
      });

      // For V2Ray configs, add the hardcoded SOCKS port
      if (configType === 'v2ray') {
          const port = '10808'; // The default SOCKS port for V2Ray in this system
          const proxyVar = `PROXY_${configId.replace(/-/g, '_')}`;
          pacScript += `    const ${proxyVar} = "SOCKS5 127.0.0.1:${port}"; // For "${configName}"\n`;
          proxyDefinitions.push({ id: configId, variable: proxyVar });
      }
    });

    pacScript += `
    const DIRECT = "DIRECT";

    // Determine the default proxy to use. This will be the proxy of the
    // first *enabled* configuration found with a SOCKS proxy.
`;

    const firstEnabledConfig = Array.from(document.querySelectorAll('#core-configurations-list .config-item'))
      .find(item => item.querySelector('.config-enabled-checkbox').checked);

    let activeProxyVar = 'DIRECT'; // Default to DIRECT if no enabled proxy is found
    if (firstEnabledConfig) {
      const activeConfigId = firstEnabledConfig.dataset.id;
      const activeProxyDef = proxyDefinitions.find(p => p.id === activeConfigId);
      if (activeProxyDef) {
        activeProxyVar = activeProxyDef.variable;
      }
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

    if (geoSiteBypassEnabled) {
      pacScript += `
    // --- GeoSite Bypass for Iran (domain list) ---
    // (Preview uses a placeholder list; actual list is loaded from database)
    const domains = ["*.ir", "example.ir", "another-example.ir", "..."];
    for (let i = 0; i < domains.length; i++) {
        if (shExpMatch(host, domains[i])) {
            return DIRECT;
        }
    }
`;
    }

    if (geoIpBypassEnabled) {
      pacScript += `
    // --- GeoIP Bypass for Iran (IP ranges) ---
    // (Preview uses a placeholder list; actual list is loaded from database)
    try {
        const ip = dnsResolve(host);
        if (ip) {
            const ranges = [["2.176.0.0", "255.248.0.0"], ["5.52.192.0", "255.255.240.0"], ["..."]];
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

    const codeElement = pacScriptPreviewContainer.querySelector('code');
    if (codeElement) {
        codeElement.textContent = pacScript.trim();
    }
  }

  function updateAllProxyRuleDropdownsAndPreview() {
    // 1. Rebuild the cache of core configs from the current state of the DOM
    coreConfigsForSelect = [];
    document.querySelectorAll('#core-configurations-list .config-item').forEach(item => {
        const id = item.dataset.id;
        const name = item.querySelector('.config-input-name').value.trim();
        if (id && name) {
            coreConfigsForSelect.push({ id, name });
        }
    });

    // 2. Update all existing dropdowns in the proxy rules
    document.querySelectorAll('#proxy-bypass-rules-list .bypass-target-select').forEach(select => {
        const currentValue = select.value;
        // Clear all but the first 'DIRECT' option
        while (select.options.length > 1) {
            select.remove(1);
        }
        // Repopulate with the latest list of configs
        coreConfigsForSelect.forEach(config => {
            const option = document.createElement('option');
            option.value = config.id;
            option.textContent = `Proxy via: ${config.name}`;
            select.appendChild(option);
        });
        // Try to restore the previously selected value
        select.value = currentValue;
    });

    // 3. Finally, update the PAC script preview with the new state
    updatePacScriptPreview();
  }

  // --- Chart Management ---

  function initializeCharts(history = []) {
    // Slice the history to only show the most recent points, matching the real-time behavior.
    const recentHistory = history.slice(-MAX_CHART_POINTS);

    const chartData = {
      labels: recentHistory.map(p => new Date(p.timestamp).toLocaleTimeString()),
      webData: recentHistory.map(p => p.web),
      tcpData: recentHistory.map(p => p.tcp),
    };

    const computedStyle = getComputedStyle(document.documentElement);

    const chartOptions = {
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: function(value) {
              return value + 'ms';
            },
            color: computedStyle.getPropertyValue('--text-color-secondary').trim()
          }
        },
        x: {
          ticks: {
            maxRotation: 0,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 10
          },
          color: computedStyle.getPropertyValue('--text-color-secondary').trim()
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
        },
      },
      animation: { duration: 250 },
      maintainAspectRatio: false,
      elements: { line: { tension: 0.3 } }
    };

    if (webLatencyChart) webLatencyChart.destroy();
    webLatencyChart = new Chart(webLatencyChartCanvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Web Latency',
          data: chartData.webData,
          borderColor: computedStyle.getPropertyValue('--chart-web-color').trim() || 'rgb(75, 192, 192)',
          backgroundColor: computedStyle.getPropertyValue('--chart-web-bg').trim() || 'rgba(75, 192, 192, 0.2)',
          fill: true,
        }]
      },
      options: chartOptions
    });

    if (tcpPingChart) tcpPingChart.destroy();
    tcpPingChart = new Chart(tcpPingChartCanvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'TCP Ping',
          data: chartData.tcpData,
          borderColor: computedStyle.getPropertyValue('--chart-tcp-color').trim() || 'rgb(54, 162, 235)',
          backgroundColor: computedStyle.getPropertyValue('--chart-tcp-bg').trim() || 'rgba(54, 162, 235, 0.2)',
          fill: true,
        }]
      },
      options: chartOptions
    });
  }

  function updateCharts(status) {
    if (!webLatencyChart || !tcpPingChart || !status.connected || status.web_check_latency_ms <= -1 || status.tcp_ping_ms <= -1) {
      return; // Don't update if charts aren't ready, tunnel is down, or data is invalid
    }
    [webLatencyChart, tcpPingChart].forEach((chart, index) => {
      const newData = index === 0 ? status.web_check_latency_ms : status.tcp_ping_ms;
      chart.data.labels.push(new Date().toLocaleTimeString());
      chart.data.datasets[0].data.push(newData);
      if (chart.data.labels.length > MAX_CHART_POINTS) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
      }
      chart.update();
    });
  }

  // --- Live Log Polling for AI Assistant ---
  function pollLogs() {
    // Stop polling if the container has been hidden
    if (aiLiveLogContainer.style.display === 'none') {
      if (logPollInterval) clearInterval(logPollInterval);
      return;
    }
    chrome.runtime.sendMessage({ command: COMMANDS.GET_LOGS }, (response) => {
      if (chrome.runtime.lastError) {
        aiLiveLogContent.textContent = `Error polling logs: ${chrome.runtime.lastError.message}`;
      } else if (response && response.success) {
        aiLiveLogContent.textContent = response.log_content || 'Waiting for log output...';
        aiLiveLogContainer.scrollTop = aiLiveLogContainer.scrollHeight; // Auto-scroll
      } else {
        aiLiveLogContent.textContent = `Failed to load log: ${response.message || 'Unknown error.'}`;
      }
    });
  }

  // --- Live Log Polling for Main Log Viewer ---
  function pollMainLogs() {
    // Don't poll if the page is hidden
    if (document.hidden) {
        if (mainLogPollInterval) {
            clearInterval(mainLogPollInterval);
            mainLogPollInterval = null;
        }
        return;
    }
    chrome.runtime.sendMessage({ command: COMMANDS.GET_LOGS }, (response) => {
        if (chrome.runtime.lastError) {
            logViewerContent.textContent = `Error polling logs: ${chrome.runtime.lastError.message}`;
        } else if (response && response.success) {
            const currentContent = logViewerContent.textContent;
            const newContent = response.log_content || 'Waiting for log entries...';
            // Only update DOM if content has changed to prevent flicker/reflow
            if (currentContent !== newContent) {
                logViewerContent.textContent = newContent;
                // Auto-scroll only if user is already near the bottom
                const container = logViewerContent.parentElement;
                const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 1;
                if (isScrolledToBottom) {
                    container.scrollTop = container.scrollHeight;
                }
            }
        } else {
            logViewerContent.textContent = `Failed to load log: ${response.message || 'Unknown error.'}`;
        }
    });
  }

  function handleVisibilityChange() {
      if (document.hidden) {
          if (mainLogPollInterval) clearInterval(mainLogPollInterval);
          mainLogPollInterval = null;
      } else {
          // Start polling immediately when tab becomes visible
          if (!mainLogPollInterval) {
              pollMainLogs(); // Initial call
              mainLogPollInterval = setInterval(pollMainLogs, 2000); // Poll every 2 seconds
          }
      }
  }

  // --- Settings Load/Save ---

  function loadSettings() {
    // Define the keys we expect to find in sync storage. This is more robust
    // than using Object.values(STORAGE_KEYS), which might contain local keys or
    const syncKeysToGet = [
      // New keys
      STORAGE_KEYS.CORE_CONFIGURATIONS,
      STORAGE_KEYS.PROXY_BYPASS_RULES,
      STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED,
      STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED,
      STORAGE_KEYS.OPENROUTER_API_KEY,
      STORAGE_KEYS.OPENROUTER_MODEL,
      STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE,
      // Legacy keys for migration
      STORAGE_KEYS.PING_HOST,
      STORAGE_KEYS.WEB_CHECK_URL,
      STORAGE_KEYS.AUTO_RECONNECT_ENABLED,
      STORAGE_KEYS.LEGACY_PORT_FORWARDS,
      STORAGE_KEYS.WIFI_SSIDS,
    ];

    chrome.storage.sync.get(syncKeysToGet, (result) => {
      if (chrome.runtime.lastError) {
        console.error(`Error loading settings from chrome.storage.sync: ${chrome.runtime.lastError.message}`);
        statusMessage.textContent = 'Error loading settings. Check the extension console for details.';
        statusMessage.className = 'error';
        return;
      }

      let coreConfigs = result[STORAGE_KEYS.CORE_CONFIGURATIONS];

      // --- Migration from old single-config format ---
      if (!coreConfigs && result[STORAGE_KEYS.LEGACY_SSH_HOST]) {
        console.log("Migrating old settings to new multi-configuration format.");
        const newId = crypto.randomUUID();
        const migratedConfig = {
          id: newId,
          name: 'Default Migrated Config',
          sshUser: result[STORAGE_KEYS.LEGACY_SSH_USER] || '',
          sshHost: result[STORAGE_KEYS.LEGACY_SSH_HOST] || '',
          sshRemoteCommand: result[STORAGE_KEYS.LEGACY_SSH_REMOTE_COMMAND] || '',
        };
        coreConfigs = [migratedConfig];

        const keysToRemove = [
          STORAGE_KEYS.LEGACY_SSH_COMMAND_ID,
          STORAGE_KEYS.LEGACY_SSH_USER,
          STORAGE_KEYS.LEGACY_SSH_HOST,
          STORAGE_KEYS.LEGACY_SSH_REMOTE_COMMAND,
        ];
        // Don't save yet, check for other legacy keys first
        chrome.storage.sync.remove(keysToRemove);
      }

      // --- Migration for active ID to enabled flag ---
      const legacyActiveId = result[STORAGE_KEYS.LEGACY_ACTIVE_CONFIGURATION_ID];
      if (legacyActiveId && coreConfigs) {
        console.log("Migrating active configuration ID to 'enabled' flag.");
        let found = false;
        coreConfigs.forEach(config => {
          if (config.id === legacyActiveId) {
            config.enabled = true;
            found = true;
          } else {
            config.enabled = false; // Explicitly disable others
          }
        });
        if (found) {
          // Save the updated configs and remove the old key
          chrome.storage.sync.set({ [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs });
          chrome.storage.sync.remove(STORAGE_KEYS.LEGACY_ACTIVE_CONFIGURATION_ID);
        }
      }

      // --- Migration for port forwarding rules ---
      const legacyPortForwards = result[STORAGE_KEYS.LEGACY_PORT_FORWARDS];
      if (legacyPortForwards && coreConfigs && coreConfigs.length > 0) {
        console.log("Migrating global port forwarding rules to active configuration.");
        // Find the active config, or fall back to the first one.
        const targetConfig = coreConfigs.find(c => c.enabled) || coreConfigs[0];
        if (typeof targetConfig.portForwards === 'undefined') {
          targetConfig.portForwards = legacyPortForwards;
        }
        // Save the updated configs and remove the old global key
        chrome.storage.sync.set({ [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs });
        chrome.storage.sync.remove(STORAGE_KEYS.LEGACY_PORT_FORWARDS);
      }

      pingHostInput.value = result[STORAGE_KEYS.PING_HOST] || 'youtube.com';
      webCheckUrlInput.value = result[STORAGE_KEYS.WEB_CHECK_URL] || 'https://gemini.google.com/app';
      autoReconnectCheckbox.checked = result[STORAGE_KEYS.AUTO_RECONNECT_ENABLED] !== false; // Default to true

      wifiListContainer.innerHTML = ''; // Clear existing Wi-Fi networks
      const wifiSsids = result[STORAGE_KEYS.WIFI_SSIDS] || [];
      if (wifiSsids.length === 0) {
      } else {
        wifiSsids.forEach(createWifiElement);
      }

      openrouterApiKeyInput.value = result[STORAGE_KEYS.OPENROUTER_API_KEY] || '';
      openrouterModelInput.value = result[STORAGE_KEYS.OPENROUTER_MODEL] || 'z-ai/glm-4.5-air:free';
      const defaultSystemMessage = `You are a network configuration assistant for a browser extension named Holocron. A user will describe a service, and you must suggest a proxy routing rule for it. The user has a list of available proxy configurations. Your task is to determine if the service should be accessed 'DIRECT' (bypassing the proxy, typically for local or national services) or through one of the available proxy configuration IDs (for international or blocked services). Respond ONLY with a single, valid JSON object in the format: {"domain": "domain.pattern.com", "target": "proxy_id_or_DIRECT"}. Do not include any other text, explanation, or markdown formatting. Example for a user trying to access an Iranian service like "Digikala": {"domain": "*.digikala.com", "target": "DIRECT"}. Example for a user trying to access a service that needs a proxy like "YouTube": {"domain": "*.youtube.com", "target": "some-uuid-for-a-proxy"}.`;
      openrouterSystemMessageInput.value = result[STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE] || defaultSystemMessage;

      // --- Populate Core Configurations UI ---
      coreConfigListContainer.innerHTML = ''; // Clear existing
      coreConfigsForSelect = []; // Reset cache
      if (coreConfigs && coreConfigs.length > 0) {
        coreConfigs.forEach(config => {
          // Cache for dropdowns in other sections
          coreConfigsForSelect.push({ id: config.id, name: config.name });
          const el = createConfigElement(config, null);
          coreConfigListContainer.appendChild(el);
        });
      } else {
        coreConfigListContainer.appendChild(createConfigElement({}, null, true)); // Add a blank one for new users, in edit mode
      }

      // --- Populate Global Proxy Bypass Rules ---
      globalGeoIpBypassCheckbox.checked = result[STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED] !== false; // Default true
      globalGeoSiteBypassCheckbox.checked = result[STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED] !== false; // Default true

      proxyBypassRulesList.innerHTML = '';
      const bypassRules = result[STORAGE_KEYS.PROXY_BYPASS_RULES] || [];
      if (bypassRules.length > 0) {
        bypassRules.forEach(rule => {
            proxyBypassRulesList.appendChild(createProxyBypassRuleElement(rule));
        });
      }

      updateAllProxyRuleDropdownsAndPreview(); // Initial generation
      setDirty(false); // Set initial state to clean
    });

    // Load and display database statuses from local storage
    chrome.storage.local.get([
      STORAGE_KEYS.GEOIP_RANGES,
      STORAGE_KEYS.GEOIP_LAST_UPDATE,
      STORAGE_KEYS.GEOSITE_DOMAINS,
      STORAGE_KEYS.GEOSITE_LAST_UPDATE,
      STORAGE_KEYS.LATENCY_HISTORY
    ], (result) => {
      // GeoIP Status
      const ipRanges = result[STORAGE_KEYS.GEOIP_RANGES];
      const ipLastUpdate = result[STORAGE_KEYS.GEOIP_LAST_UPDATE];
      if (ipLastUpdate) {
        const date = new Date(ipLastUpdate).toLocaleString();
        const count = ipRanges ? ipRanges.length : 0;
        geoipStatusDiv.innerHTML = `<strong>GeoIP:</strong> ${count} IP ranges loaded (Updated: ${date})`;
      } else {
        geoipStatusDiv.textContent = 'GeoIP: Database has not been updated yet.';
      }

      // GeoSite Status
      const domains = result[STORAGE_KEYS.GEOSITE_DOMAINS];
      const siteLastUpdate = result[STORAGE_KEYS.GEOSITE_LAST_UPDATE];
      if (siteLastUpdate) {
        const date = new Date(siteLastUpdate).toLocaleString();
        const count = domains ? domains.length : 0;
        geositeStatusDiv.innerHTML = `<strong>GeoSite:</strong> ${count} domains loaded (Updated: ${date})`;
      } else {
        geositeStatusDiv.textContent = 'GeoSite: Database has not been updated yet.';
      }

      // Initialize latency charts with historical data
      const history = result[STORAGE_KEYS.LATENCY_HISTORY] || [];
      initializeCharts(history);
    });
  }

  function validateSettings() {
    let isValid = true;

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

    // 1. Validate other text fields
    if (!pingHostInput.value.trim()) showError(pingHostInput, 'This field cannot be empty.');
    if (!webCheckUrlInput.value.trim()) showError(webCheckUrlInput, 'This field cannot be empty.');


    // 2. Validate URL format
    try {
      new URL(webCheckUrlInput.value);
    } catch (_) {
      if (webCheckUrlInput.value.trim()) { // Only show error if not already caught by the empty check
        showError(webCheckUrlInput, 'Please enter a valid URL (e.g., https://example.com).');
      }
    }

    // 3. Validate Core Configurations
    document.querySelectorAll('#core-configurations-list .config-item').forEach((item) => {
      const nameInput = item.querySelector('.config-input-name');
      if (!nameInput.value.trim()) showError(nameInput, 'Configuration name cannot be empty.');

      const type = item.querySelector('.config-type-select').value;
      if (type === 'ssh') {
        const sshUserInput = item.querySelector('.config-input-ssh-user');
        const sshHostInput = item.querySelector('.config-input-ssh-host');
        if (!sshUserInput.value.trim()) showError(sshUserInput, 'SSH User cannot be empty.');
        if (!sshHostInput.value.trim()) showError(sshHostInput, 'SSH Host cannot be empty.');

        // Validate port forwarding rules
        item.querySelectorAll('.port-forwarding-rules-list .rule-item').forEach((ruleEl) => {
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

            if (type === 'L' || type === 'R') {
              if (!remoteHostInput.value.trim()) {
                showError(remoteHostInput, 'This field is required for this forward type.');
              }
              const remotePort = remotePortInput.value.trim();
              if (!remotePort) {
                showError(remotePortInput, 'Remote port is required.');
              } else if (!/^\d+$/.test(remotePort) || +remotePort < 1 || +remotePort > 65535) {
                showError(remotePortInput, 'Port must be a number from 1-65535.');
              }
            }
        });
      } else if (type === 'openvpn') {
        const ovpnProfileNameInput = item.querySelector('.ovpn-profile-name');
        const ovpnFileContent = item.querySelector('.ovpn-file-content');
        if (!ovpnProfileNameInput.value.trim()) showError(ovpnProfileNameInput, 'Profile Name cannot be empty.');
        if (!ovpnFileContent.value.trim()) showError(item.querySelector('.ovpn-file-upload'), 'An .ovpn file must be uploaded.');
      } else if (type === 'v2ray') {
        const v2rayUrlInput = item.querySelector('.config-input-v2ray-url');
        const url = v2rayUrlInput.value.trim();
        if (!url) {
            showError(v2rayUrlInput, 'V2Ray URL cannot be empty.');
        } else if (!url.startsWith('vless://')) {
            showError(v2rayUrlInput, 'URL must start with vless://');
        }
      }
    });

    // Validate new proxy bypass rules
    document.querySelectorAll('#proxy-bypass-rules-list .rule-item').forEach((ruleEl) => {
        const domainInput = ruleEl.querySelector('.bypass-domain-input');
        if (!domainInput.value.trim()) {
            showError(domainInput, 'Domain pattern cannot be empty.');
        }
    });

    // 5. Validate Wi-Fi SSIDs
    document.querySelectorAll('#wifi-networks-list .rule-item').forEach((ruleEl) => {
      const ssidInput = ruleEl.querySelector('.wifi-ssid-input');
      if (!ssidInput.value.trim()) {
        showError(ssidInput, 'SSID cannot be empty.');
      }
    });

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

    const coreConfigs = [];

    document.querySelectorAll('#core-configurations-list .config-item').forEach(item => {
      const id = item.dataset.id;
      const type = item.querySelector('.config-type-select').value;

      const config = {
        id: id,
        enabled: item.querySelector('.config-enabled-checkbox').checked,
        name: item.querySelector('.config-input-name').value.trim(),
        type: type,
      };

      if (type === 'ssh') {
          Object.assign(config, {
            sshUser: item.querySelector('.config-input-ssh-user').value.trim(),
            sshHost: item.querySelector('.config-input-ssh-host').value.trim(),
            sshRemoteCommand: item.querySelector('.config-input-ssh-remote-command').value.trim(),
            portForwards: Array.from(
              item.querySelectorAll('.port-forwarding-rules-list .rule-item')
            ).map(el => {
              const type = el.querySelector('.rule-type').value;
              const localPort = el.querySelector('.rule-local-port').value;
              const remoteHost = el.querySelector('.rule-remote-host').value;
              const remotePort = el.querySelector('.rule-remote-port').value;
              if (!localPort) return null;
              const rule = { type, localPort };
              if (type === 'L' || type === 'R') {
                rule.remoteHost = remoteHost;
                rule.remotePort = remotePort;
              }
              return rule;
            }).filter(Boolean), // Filter out nulls from empty rules
          });
      } else if (type === 'openvpn') {
          Object.assign(config, {
              ovpnProfileName: item.querySelector('.ovpn-profile-name').value.trim(),
              ovpnFileContent: item.querySelector('.ovpn-file-content').value,
              // Do not save credentials to sync storage. They are only held in memory
              // in the input fields for the duration of the session.
              ovpnUser: item.querySelector('.ovpn-auth-user').value,
              ovpnPass: item.querySelector('.ovpn-auth-pass').value,
          });
      } else if (type === 'v2ray') {
          Object.assign(config, {
              v2rayUrl: item.querySelector('.config-input-v2ray-url').value.trim(),
          });
      }
      coreConfigs.push(config);
    });

    const proxyBypassRules = Array.from(
        document.querySelectorAll('#proxy-bypass-rules-list .rule-item')
    ).map(el => {
        const domain = el.querySelector('.bypass-domain-input').value.trim();
        const target = el.querySelector('.bypass-target-select').value;
        if (!domain) return null;
        return { domain, target };
    }).filter(Boolean);

    const wifiSsids = [];
    document.querySelectorAll('#wifi-networks-list .rule-item .wifi-ssid-input').forEach(input => {
      if (input.value.trim()) {
        wifiSsids.push(input.value.trim());
      }
    });

    // Create a copy of settings for storage, omitting sensitive data like passwords.
    const settingsToStore = JSON.parse(JSON.stringify(coreConfigs));
    settingsToStore.forEach(config => {
        if (config.type === 'openvpn') {
            delete config.ovpnUser;
            delete config.ovpnPass;
        }
    });

    const settings = {
      [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs,
      [STORAGE_KEYS.PING_HOST]: pingHostInput.value,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrlInput.value,
      [STORAGE_KEYS.WIFI_SSIDS]: wifiSsids,
      [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: autoReconnectCheckbox.checked,
      [STORAGE_KEYS.PROXY_BYPASS_RULES]: proxyBypassRules,
      [STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED]: globalGeoIpBypassCheckbox.checked,
      [STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED]: globalGeoSiteBypassCheckbox.checked,
      [STORAGE_KEYS.OPENROUTER_API_KEY]: openrouterApiKeyInput.value.trim(),
      [STORAGE_KEYS.OPENROUTER_MODEL]: openrouterModelInput.value.trim(),
      [STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE]: openrouterSystemMessageInput.value.trim(),
    };

    // Replace coreConfigs with the sanitized version for storage.
    settings[STORAGE_KEYS.CORE_CONFIGURATIONS] = settingsToStore;

    chrome.storage.sync.set(settings, () => {
      statusMessage.textContent = 'Settings saved!';
      statusMessage.className = 'success';
      setDirty(false); // Reset dirty state after successful save
      setTimeout(() => {
          if (statusMessage.textContent === 'Settings saved!')
        statusMessage.textContent = '';
        statusMessage.className = '';
      }, 3000);
    });
  }


  function requestStatusUpdate() {
    connectionStatusText.textContent = 'Checking...';
    connectionStatusIndicator.className = 'status-indicator'; // Reset to default
    chrome.runtime.sendMessage({ command: COMMANDS.GET_POPUP_STATUS }, (response) => {
      if (chrome.runtime.lastError) {
        console.error(`Error requesting status: ${chrome.runtime.lastError.message}`);
        updateConnectionUI({ connected: false }); // Assume disconnected on error
      } else {
        updateConnectionUI(response);
      }
    });
  }


  // --- Event Listeners ---
  addConfigButton.addEventListener('click', () => {
    const newEl = createConfigElement({}, null, true);
    coreConfigListContainer.appendChild(newEl);
    updateAllProxyRuleDropdownsAndPreview();
    setDirty(true);
  });
  addWifiButton.addEventListener('click', () => { createWifiElement(); setDirty(true); });
  addProxyRuleButton.addEventListener('click', () => {
      const newRuleEl = createProxyBypassRuleElement();
      proxyBypassRulesList.appendChild(newRuleEl);
      newRuleEl.querySelector('input').focus();
      updatePacScriptPreview();
      setDirty(true);
  });

  const openrouterApiKeyInput = document.getElementById('openrouter-api-key');
  const proxyActionsBar = document.querySelector('.proxy-actions-bar');

  proxyActionsBar.insertAdjacentElement('afterend', aiLiveLogContainer);
  aiLiveLogContainer.style.marginTop = '1em';

  aiSuggestRuleButton.addEventListener('click', async () => {
    const apiKey = openrouterApiKeyInput.value.trim();

    if (!apiKey) {
        alert('Please enter your OpenRouter API key in the AI Assistant section to use this feature.');
        openrouterApiKeyInput.focus();
        return;
    }

    const serviceName = prompt('What website or service are you trying to configure a rule for?\n(e.g., "Netflix", "Iranian news site", "my-company.internal.net")');
    if (!serviceName) {
        return; // User cancelled
    }

    // Show loading state
    const originalButtonText = aiSuggestRuleButton.textContent;
    aiSuggestRuleButton.textContent = 'Thinking...';
    aiSuggestRuleButton.disabled = true;
    statusMessage.textContent = 'Asking AI for a suggestion...';
    statusMessage.className = 'info';

    // Start live log
    aiLiveLogContainer.style.display = 'none';
    aiLiveLogContent.textContent = 'Initializing live log...';
    pollLogs();
    logPollInterval = setInterval(pollLogs, 1500);

    const maxRetries = 3;
    let lastError = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const availableProxies = coreConfigsForSelect.map(c => `ID: ${c.id}, Name: "${c.name}"`).join('; ') || 'None';

         aiLiveLogContent.textContent += `\n\nAttempt ${attempt}: Asking AI for a rule suggestion...`;
         aiLiveLogContainer.scrollTop = aiLiveLogContainer.scrollHeight;


        const userPrompt = `The user wants a rule for the service: "${serviceName}". The available proxy configurations are: [${availableProxies}].`;

        const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`,
            'HTTP-Referer': 'https://github.com/majid-soorani/holocron',
            'X-Title': 'Holocron',
          },
          body: JSON.stringify({
            model: openrouterModelInput.value.trim() || 'z-ai/glm-4.5-air:free',
            messages: [
              { role: 'system', content: openrouterSystemMessageInput.value.trim() },
              { role: 'user', content: userPrompt }
            ],
            temperature: 0.2,
            max_tokens: 350, // Increased from 150 to prevent 'length' finish_reason
          })
        });

        if (response.ok) {
          const data = await response.json();
          const choice = data.choices && data.choices[0];

          // 1. Check for a valid choice object from the API
          if (!choice) {
            const errorMessage = "AI response did not contain any choices.";
            console.error(errorMessage, "Full response object:", data);
            aiLiveLogContent.textContent += `\n\nERROR: ${errorMessage}\n${JSON.stringify(data, null, 2)}`;
                         aiLiveLogContainer.scrollTop = aiLiveLogContainer.scrollHeight;

            throw new Error('Invalid AI response structure. See AI log panel for details.');
          }

          const suggestionText = (choice.message && choice.message.content) ? choice.message.content.trim() : '';
          const finishReason = choice.finish_reason;

          // 2. Check for empty content with a specific failure reason (e.g., content filter)
          if (!suggestionText && finishReason && finishReason !== 'stop') {
              let reasonMessage = `AI failed to generate a suggestion. Reason: ${finishReason}.`;
              if (finishReason === 'length') {
                  reasonMessage = 'AI response was cut short (max_tokens reached). Try a model with a larger context window or a more specific request.';
              }
              console.error(reasonMessage, "Full response object:", data);
              aiLiveLogContent.textContent += `\n\nERROR: ${reasonMessage}\n${JSON.stringify(data, null, 2)}`;
                         aiLiveLogContainer.scrollTop = aiLiveLogContainer.scrollHeight;
              throw new Error(reasonMessage); // Throw the more specific message
          }

          const jsonMatch = suggestionText.match(/\{.*\}/s);

          if (!jsonMatch) {
            const errorMessage = "AI response did not contain valid JSON.";
            const rawResponseForLog = `--- RAW AI RESPONSE ---\n${suggestionText || '(empty response)'}\n\n--- FULL RESPONSE OBJECT ---\n${JSON.stringify(data, null, 2)}`;
            console.error(errorMessage, "Raw response from model:", suggestionText, "Full object:", data);
            aiLiveLogContent.textContent += `\n\nERROR: ${errorMessage}\n${rawResponseForLog}`;
                         aiLiveLogContainer.scrollTop = aiLiveLogContainer.scrollHeight; // Auto-scroll to show the error
            throw new Error('Invalid AI response format. See AI log panel for details.');
          }

          const suggestedRule = JSON.parse(jsonMatch[0]);
          if (!suggestedRule.domain || !suggestedRule.target) { throw new Error('AI response was missing "domain" or "target" fields.'); }

          const newRuleEl = createProxyBypassRuleElement(suggestedRule);
          proxyBypassRulesList.appendChild(newRuleEl);
          updatePacScriptPreview();
          setDirty(true);
          statusMessage.textContent = 'AI suggestion added! Remember to save your settings.';
          statusMessage.className = 'success';
          lastError = null; // Clear last error on success
          break; // Exit retry loop on success
        }

        // --- Handle HTTP errors ---
        const errorData = await response.json().catch(() => ({ error: { message: `HTTP error ${response.status}` } }));
        lastError = errorData.error;
        lastError.statusCode = response.status;

        // Non-retriable errors
        if ([400, 401, 402].includes(response.status)) {
          break; // Break loop to show error immediately
        }

        // Retriable errors
        if ([429, 500, 503].includes(response.status) && attempt < maxRetries) {
          const delay = Math.pow(2, attempt) * 1000; // Exponential backoff: 2s, 4s, 8s
          statusMessage.textContent = `Model is busy. Retrying in ${delay / 1000}s... (Attempt ${attempt}/${maxRetries})`;
          await new Promise(resolve => setTimeout(resolve, delay));
          continue; // Try again
        }

        // Any other error, break to show it
        break;

      } catch (error) { // Catches network errors or JSON parsing errors
        lastError = { message: error.message, statusCode: null };
        if (attempt < maxRetries) {
          const delay = Math.pow(2, attempt) * 1000;
          statusMessage.textContent = `Network error. Retrying in ${delay / 1000}s...`;
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }
        break; // Last attempt failed, break to show error
      }
    }

    // After the loop, if lastError is still set, it means we failed.
    if (lastError) {
      let userMessage = `Error: ${lastError.message}`;
      switch (lastError.statusCode) {
        case 401: userMessage = 'Error: Invalid OpenRouter API Key. Please check your key.'; break;
        case 402: userMessage = 'Error: Insufficient credits on your OpenRouter account.'; break;
        case 429: userMessage = 'Error: Rate limit exceeded. Please wait a moment and try again.'; break;
        case 503: userMessage = 'Error: The selected model is currently overloaded or unavailable. Please try again later or select a different model.'; break;
      }
      console.error('AI Suggestion Error:', lastError);
      statusMessage.textContent = userMessage;
      statusMessage.className = 'error';
    }

    // --- Cleanup ---
    aiSuggestRuleButton.textContent = originalButtonText;
    aiSuggestRuleButton.disabled = false;
    if (logPollInterval) {
      clearInterval(logPollInterval);
      logPollInterval = null;
    }
        setTimeout(() => {
      aiLiveLogContainer.style.display = 'block'; // Show log after delay
    }, 8000); // Keep log visible for 8 seconds to see final output
  });
  saveButton.addEventListener('click', saveSettings); // This now calls the version with validation
  discardButton.addEventListener('click', loadSettings); // Reload settings to discard changes

  clearLogButton.addEventListener('click', () => {
    if (!confirm('Are you sure you want to permanently clear the native host log file?')) {
      return;
    }
    logViewerContent.textContent = 'Clearing log file...';

    chrome.runtime.sendMessage({ command: COMMANDS.CLEAR_LOGS }, (response) => {
      if (chrome.runtime.lastError) {
        logViewerContent.textContent = `Error communicating with background script: ${chrome.runtime.lastError.message}`;
      } else if (response && response.success) {
        logViewerContent.textContent = 'Log file has been cleared. Waiting for new entries.';
      } else {
        logViewerContent.textContent = `Failed to clear log: ${response.message || 'Unknown error.'}`;
      }
    });
  });



  // Add listeners to global inputs
  pingHostInput.addEventListener('input', () => setDirty(true));
  webCheckUrlInput.addEventListener('input', () => setDirty(true));
  autoReconnectCheckbox.addEventListener('change', () => setDirty(true));
  openrouterApiKeyInput.addEventListener('input', () => setDirty(true));
  openrouterModelInput.addEventListener('input', () => setDirty(true));
  openrouterSystemMessageInput.addEventListener('input', () => setDirty(true));
  globalGeoIpBypassCheckbox.addEventListener('change', () => { updatePacScriptPreview(); setDirty(true); });
  globalGeoSiteBypassCheckbox.addEventListener('change', () => { updatePacScriptPreview(); setDirty(true); });
  updateDbButton.addEventListener('click', () => {
    updateDbButton.textContent = 'Updating...';
    updateDbButton.disabled = true;
    statusMessage.textContent = 'Forcing database update from online sources...';
    statusMessage.className = 'info';

    chrome.runtime.sendMessage({ command: COMMANDS.MANUAL_DB_UPDATE }, (response) => {
      if (chrome.runtime.lastError) {
        statusMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
        statusMessage.className = 'error';
      } else if (response.success) {
        statusMessage.textContent = 'Database update complete!';
        statusMessage.className = 'success';
        // Reload the status displays by re-running the load function
        loadSettings();
      } else {
        statusMessage.textContent = `Update failed: ${response.message}`;
        statusMessage.className = 'error';
      }
      updateDbButton.textContent = 'Update Databases Now';
      updateDbButton.disabled = false;
      setTimeout(() => {
        statusMessage.textContent = '';
        statusMessage.className = '';
      }, 5000);
    });
  });

  testButton.addEventListener('click', () => {
    statusMessage.textContent = '';
    statusMessage.className = '';

    (async () => {
      const {
        [STORAGE_KEYS.CORE_CONFIGURATIONS]: configs,
      } = await chrome.storage.sync.get([
        STORAGE_KEYS.CORE_CONFIGURATIONS,
      ]);

      const enabledConfigs = configs ? configs.filter(c => c.enabled) : [];
      const configToTest = enabledConfigs.length > 0 ? enabledConfigs[0] : null;

      if (!configToTest) {
        statusMessage.textContent = 'No enabled configuration to test.';
        statusMessage.className = 'error';
        return;
      }

      const pingHost = pingHostInput.value;
      const webCheckUrl = webCheckUrlInput.value;
      statusMessage.textContent = `Testing first enabled configuration: "${configToTest.name || 'Untitled'}"...`;
      statusMessage.className = 'info';

      const request = {
        command: COMMANDS.TEST_CONNECTION,
        config: configToTest,
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
    })();
  });

    const refreshChartData = () => {
        requestStatusUpdate();
    };

    if (refreshWebLatencyChartButton) {
        refreshWebLatencyChartButton.addEventListener('click', refreshChartData);
    }

    if (refreshTcpPingChartButton) {
        refreshTcpPingChartButton.addEventListener('click', refreshChartData);
    }



  // --- Connection Control Event Listeners ---
  reconnectNowButton.addEventListener('click', () => {
    connectionStatusText.textContent = 'Connecting...';
    chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL }, (response) => {
      if (response && !response.success) {
        const message = response.message.split('\n')[0];
        connectionStatusText.textContent = `Error: ${message}`;
      }
      // The final status will be updated via the broadcast message.
    });
  });

  disconnectTunnelButton.addEventListener('click', () => {
    connectionStatusText.textContent = 'Disconnecting...';
    chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL });
  });

  applyProxyButton.addEventListener('click', () => {
    if (currentStatus && currentStatus.socks_port) {
      connectionStatusText.textContent = 'Applying Proxy...';
      chrome.runtime.sendMessage({ command: COMMANDS.SET_BROWSER_PROXY, socksPort: currentStatus.socks_port });
    }
  });

  revertProxyButton.addEventListener('click', () => {
    connectionStatusText.textContent = 'Reverting Proxy...';
    chrome.runtime.sendMessage({ command: COMMANDS.CLEAR_BROWSER_PROXY });
  });

  // Listen for real-time status updates from the background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.command === COMMANDS.STATUS_UPDATED) {
      updateConnectionUI(request.status);
      updateCharts(request.status);
    }
  });

  // --- Initial Load ---
  loadSettings();
  requestStatusUpdate();
  // Add visibility change listener for live log
  document.addEventListener('visibilitychange', handleVisibilityChange);
  // Start polling for the main log viewer
  handleVisibilityChange();
});