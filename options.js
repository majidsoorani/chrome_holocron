import { COMMANDS, STORAGE_KEYS } from './constants.js';

document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');
  const coreConfigListContainer = document.getElementById('core-configurations-list');
  const addConfigButton = document.getElementById('add-config-button');
  const addPredefinedConfigButton = document.getElementById('add-predefined-config-button');
  const coreConfigTemplate = document.getElementById('core-configuration-template');
  const proxyBypassRuleTemplate = document.getElementById('proxy-bypass-rule-template');
  const addProxyRuleButton = document.getElementById('add-proxy-rule-button');
  const autoReconnectCheckbox = document.getElementById('auto-reconnect-enabled');
  const autoSelectBestProxyCheckbox = document.getElementById('auto-select-best-proxy');
  const wifiListContainer = document.getElementById('wifi-networks-list');
  const addWifiButton = document.getElementById('add-wifi-button');
  const ruleTemplate = document.getElementById('port-forward-rule-template');
  const wifiTemplate = document.getElementById('wifi-network-template');
  const statusMessage = document.getElementById('status-message');
  const geoipStatusDiv = document.getElementById('geoip-status');
  const geositeStatusDiv = document.getElementById('geosite-status');
  const updateDbButton = document.getElementById('update-db-button');
  const connectionStatusDot = document.getElementById('connection-status-dot');
  const connectionStatusText = document.getElementById('connection-status-text');
  const connectionActionButton = document.getElementById('connection-action-button');
  const reconnectNowContainer = document.getElementById('manual-reconnect-container');
  const reconnectNowButton = document.getElementById('reconnect-now-button');
  const applyProxyButton = document.getElementById('apply-proxy-button');
  const revertProxyButton = document.getElementById('revert-proxy-button');
  const disablePacButton = document.getElementById('disable-pac-button');
  const webLatencyChartCanvas = document.getElementById('web-latency-chart');
  const tcpPingChartCanvas = document.getElementById('tcp-ping-chart');
    const refreshWebLatencyChartButton = document.getElementById('refresh-web-latency-chart');
    const refreshTcpPingChartButton = document.getElementById('refresh-tcp-ping-chart');
  const globalGeoIpBypassCheckbox = document.getElementById('global-geoip-bypass');
  const globalGeoSiteBypassCheckbox = document.getElementById('global-geosite-bypass');
  const incognitoProxySelect = document.getElementById('incognito-proxy-select');
  const incognitoPermissionWarning = document.getElementById('incognito-permission-warning');
  const proxyBypassRulesList = document.getElementById('proxy-bypass-rules-list');
  const pacScriptPreviewContainer = document.getElementById('pac-script-preview-container');
  const copyPacButton = document.getElementById('copy-pac-button');
  const searchProxyRulesInput = document.getElementById('search-proxy-rules');
  const logViewerContent = document.getElementById('log-viewer-content');
  const clearLogButton = document.getElementById('clear-log-button');
  const toggleLogPollingButton = document.getElementById('toggle-log-polling-button');
  const copyLogButton = document.getElementById('copy-log-button');
  const aiSuggestRuleButton = document.getElementById('ai-suggest-rule-button');
  const aiApiKeyInput = document.getElementById('ai-api-key');
  const aiModelInput = document.getElementById('ai-model');
  const aiSystemMessageInput = document.getElementById('ai-system-message');
  const aiLiveLogContainer = document.getElementById('ai-live-log-container');
  const aiLiveLogContent = document.getElementById('ai-live-log-content');
  const applySystemProxyCheckbox = document.getElementById('apply-system-proxy');
  const autoApplyProxyCheckbox = document.getElementById('auto-apply-proxy');
  const dockerAuthCheckEnabledCheckbox = document.getElementById('docker-auth-check-enabled');
  const webRtcPolicyToggle = document.getElementById('webrtc-policy-toggle');
  const httpProxyEnabledCheckbox = document.getElementById('http-proxy-enabled');
  const httpProxyPortGroup = document.getElementById('http-proxy-port-group');
  const httpProxyPortInput = document.getElementById('http-proxy-port');
  const predefinedModal = document.getElementById('predefined-modal');
  const modalCloseButton = document.getElementById('modal-close-button');
  const predefinedChoices = document.querySelector('.predefined-choices');
  const exportSettingsButton = document.getElementById('export-settings-button');
  const importSettingsButton = document.getElementById('import-settings-button');
  const importFileInput = document.getElementById('import-file-input');
  
  // --- Router Settings Elements ---
  const routerIpInput = document.getElementById('router-ip');
  const routerSshUserInput = document.getElementById('router-ssh-user');
  const routerSshPortInput = document.getElementById('router-ssh-port');
  const routerSshPasswordInput = document.getElementById('router-ssh-password');
  const routerSshKeyPathInput = document.getElementById('router-ssh-key-path');
  const testRouterConnectionBtn = document.getElementById('test-router-connection-btn');
  const routerTestStatus = document.getElementById('router-test-status');
  const proxyModePasswall2Label = document.getElementById('proxy-mode-passwall2-label');


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

  function updateAutoApplyCheckboxState() {
    const parentGroup = autoApplyProxyCheckbox.parentElement;
    if (applySystemProxyCheckbox.checked) {
        // If the main setting is enabled, the auto-apply option is usable.
        autoApplyProxyCheckbox.disabled = false;
        parentGroup.classList.remove('disabled');
    } else {
        // When the main "Apply to OS" is unchecked, disable the auto-apply option
        // but preserve its checked state for when the user re-enables it.
        autoApplyProxyCheckbox.disabled = true;
        parentGroup.classList.add('disabled');
    }
  }

  // --- State ---
  let currentStatus = {}; // Cache the latest status object
  let webLatencyChart = null;
  let tcpPingChart = null;
  let coreConfigsForSelect = []; // Cache configs for dropdowns
  const MAX_CHART_POINTS = 60; // Show last 60 data points
  let configLogPollIntervals = {}; // To hold setInterval IDs for config-specific log polling.
  let logPollInterval = null; // To hold the setInterval ID for log polling
  let mainLogPollInterval = null; // For the main log viewer
  let isLogPollingPaused = false;

  // --- Debouncer for auto-saving ---
  function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        statusMessage.textContent = 'Saving...';
        statusMessage.className = 'info';
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), 750);
    };
  }

  function formatTcpError(error) {
    if (!error) return 'Fail';
    // Provide more user-friendly error messages
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

  // --- Core Configuration Management ---
  async function createConfigElement(config = {}, activeConfigId, startInEditMode = false) {
    const content = coreConfigTemplate.content.cloneNode(true);
    const configCard = content.querySelector('.config-card');
    const details = configCard.querySelector('.config-details');
    const nameDisplay = configCard.querySelector('.config-name');
    const statusBadge = configCard.querySelector('.status-badge');

    // Main controls
    const editButton = configCard.querySelector('.edit-config-button');
    const connectButton = configCard.querySelector('.connect-config-button');
    const disconnectButton = configCard.querySelector('.disconnect-config-button');

    // Details form inputs
    const nameInput = details.querySelector('.config-input-name');
    const typeSelect = details.querySelector('.config-type-select');
    const checkbox = details.querySelector('.config-enabled-checkbox');
    const duplicateButton = details.querySelector('.duplicate-config-button');
    const deleteButton = details.querySelector('.delete-config-button');


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
    const ovpnKeyPassphraseContainer = openvpnSettings.querySelector('.ovpn-key-passphrase-container');
    const ovpnKeyPassphrase = openvpnSettings.querySelector('.ovpn-key-passphrase');

    // V2Ray settings
    const v2raySettings = details.querySelector('.v2ray-settings');
    const v2rayUrlInput = v2raySettings.querySelector('.config-input-v2ray-url');
    const v2rayDetectedParams = v2raySettings.querySelector('.v2ray-detected-params');
    const v2rayParamsList = v2raySettings.querySelector('.v2ray-params-list');

    // External Proxy settings
    const externalSettings = details.querySelector('.external-settings');
    const externalProtocolSelect = externalSettings.querySelector('.config-input-external-protocol');
    const externalHostInput = externalSettings.querySelector('.config-input-external-host');
    const externalPortInput = externalSettings.querySelector('.config-input-external-port');

    // Passwall2 (OpenWrt Router) settings
    const passwall2Settings = details.querySelector('.passwall2-settings');
    const passwall2HostInput = passwall2Settings?.querySelector('.config-input-passwall2-host');
    const passwall2UserInput = passwall2Settings?.querySelector('.config-input-passwall2-user');
    const passwall2PasswordInput = passwall2Settings?.querySelector('.config-input-passwall2-password');
    const passwall2KeyPathInput = passwall2Settings?.querySelector('.config-input-passwall2-key-path');
    const passwall2SocksPortInput = passwall2Settings?.querySelector('.config-input-passwall2-socks-port');
    const passwall2HttpPortInput = passwall2Settings?.querySelector('.config-input-passwall2-http-port');
    
    // Passwall2 management elements
    const passwall2RefreshBtn = passwall2Settings?.querySelector('.passwall2-refresh-btn');
    const passwall2AddProxyBtn = passwall2Settings?.querySelector('.passwall2-add-proxy-btn');
    const passwall2StatusDisplay = passwall2Settings?.querySelector('.passwall2-status-display');
    const passwall2StatusText = passwall2Settings?.querySelector('.passwall2-status-text');
    const passwall2StartServiceBtn = passwall2Settings?.querySelector('.passwall2-start-service-btn');
    const passwall2StopServiceBtn = passwall2Settings?.querySelector('.passwall2-stop-service-btn');
    const passwall2RestartServiceBtn = passwall2Settings?.querySelector('.passwall2-restart-service-btn');
    const passwall2ProxiesList = passwall2Settings?.querySelector('.passwall2-proxies-list');
    const passwall2ProxyCount = passwall2Settings?.querySelector('.passwall2-proxy-count');
    const passwall2AddModal = passwall2Settings?.querySelector('.passwall2-add-modal');
    const passwall2SaveProxyBtn = passwall2Settings?.querySelector('.passwall2-save-proxy-btn');
    const passwall2CancelAddBtn = passwall2Settings?.querySelector('.passwall2-cancel-add-btn');

    // ProtonVPN settings
    const protonvpnSettings = details.querySelector('.protonvpn-settings');
    let protonvpnUsernameInput, protonvpnPasswordInput, protonvpnProtocolSelect, protonvpnStrategySelect;
    let protonvpnServerInput, protonvpnFreeOnlyCheckbox, protonvpnUpdateIntervalSelect;
    let protonvpnDiscoverButton, protonvpnViewServersButton, protonvpnStatusDiv, protonvpnStatusText, protonvpnServersList;
    let protonvpnSpecificServerGroup;
    
    if (protonvpnSettings) {
        protonvpnUsernameInput = protonvpnSettings.querySelector('.config-input-protonvpn-username');
        protonvpnPasswordInput = protonvpnSettings.querySelector('.config-input-protonvpn-password');
        protonvpnProtocolSelect = protonvpnSettings.querySelector('.config-input-protonvpn-protocol');
        protonvpnStrategySelect = protonvpnSettings.querySelector('.config-input-protonvpn-strategy');
        protonvpnServerInput = protonvpnSettings.querySelector('.config-input-protonvpn-server');
        protonvpnFreeOnlyCheckbox = protonvpnSettings.querySelector('.config-input-protonvpn-free-only');
        protonvpnUpdateIntervalSelect = protonvpnSettings.querySelector('.config-input-protonvpn-update-interval');
        protonvpnDiscoverButton = protonvpnSettings.querySelector('.protonvpn-discover-now');
        protonvpnViewServersButton = protonvpnSettings.querySelector('.protonvpn-view-servers');
        protonvpnStatusDiv = protonvpnSettings.querySelector('.protonvpn-status');
        protonvpnStatusText = protonvpnSettings.querySelector('.protonvpn-status-text');
        protonvpnServersList = protonvpnSettings.querySelector('.protonvpn-servers-list');
        protonvpnSpecificServerGroup = protonvpnSettings.querySelector('.protonvpn-specific-server');
    }

    // Live Log viewer
    const liveLogContainer = details.querySelector('.config-live-log-container');
    const liveLogContent = details.querySelector('.config-live-log-content');

    // Health Check elements
    const testConfigButton = configCard.querySelector('.test-config-button');
    const webLatencyValue = configCard.querySelector('.web-latency-value');
    const tcpPingValue = configCard.querySelector('.tcp-ping-value');
    const testStatusValue = configCard.querySelector('.test-status-value');
    const dockerMetricItem = configCard.querySelector('.docker-metric-item');
    const dockerAuthValue = configCard.querySelector('.docker-auth-value');
    const testStatusMessage = configCard.querySelector('.test-status-message');

    const configId = config.id || crypto.randomUUID();
    configCard.dataset.id = configId;

    // --- Helper to check if OVPN profile needs auth ---
    const checkOvpnForAuth = (content) => {
        const needsAuth = /^\s*auth-user-pass\s*$/m.test(content || '');
        const hasEncryptedKey = /BEGIN ENCRYPTED PRIVATE KEY|BEGIN RSA PRIVATE KEY/.test(content || '');
        
        ovpnAuthContainer.style.display = needsAuth ? 'flex' : 'none';
        ovpnKeyPassphraseContainer.style.display = hasEncryptedKey ? 'block' : 'none';
        
        return needsAuth || hasEncryptedKey;
    };

    // --- Type Switching ---
    const toggleSettingsVisibility = () => {
        const type = typeSelect.value;
        sshSettings.style.display = 'none';
        openvpnSettings.style.display = 'none';
        v2raySettings.style.display = 'none';
        externalSettings.style.display = 'none';
        const passwall2Settings = details.querySelector('.passwall2-settings');
        if (passwall2Settings) passwall2Settings.style.display = 'none';
        const protonvpnSettings = details.querySelector('.protonvpn-settings');
        if (protonvpnSettings) protonvpnSettings.style.display = 'none';

        if (type === 'ssh') sshSettings.style.display = 'block';
        else if (type === 'openvpn') openvpnSettings.style.display = 'block';
        else if (type === 'v2ray') v2raySettings.style.display = 'block';
        else if (type === 'external') externalSettings.style.display = 'block';
        else if (type === 'passwall2' && passwall2Settings) passwall2Settings.style.display = 'block';
        else if (type === 'protonvpn' && protonvpnSettings) protonvpnSettings.style.display = 'block';
    };

    typeSelect.addEventListener('change', () => {
        toggleSettingsVisibility();
        debouncedSave();
        
        // Re-apply proxy mode filter when type changes
        const proxyModePasswall2Radio = document.getElementById('proxy-mode-passwall2');
        const currentMode = proxyModePasswall2Radio && proxyModePasswall2Radio.checked ? 'passwall2' : 'local';
        
        // Small delay to ensure the type change is saved first
        setTimeout(() => {
          if (window.filterConfigsByProxyMode) {
            window.filterConfigsByProxyMode(currentMode);
          }
        }, 100);
    });

    // Populate fields
    nameInput.value = config.name || '';
    typeSelect.value = config.type || 'ssh';

    // SSH fields
    if (sshUserInput) sshUserInput.value = config.sshUser || '';
    if (sshHostInput) sshHostInput.value = config.sshHost || '';
    if (sshRemoteCommandInput) sshRemoteCommandInput.value = config.sshRemoteCommand || '';

    // OpenVPN fields
    if (ovpnProfileNameInput) ovpnProfileNameInput.value = config.ovpnProfileName || '';
    
    // Handle ovpn content that might be stored in local storage (for large files)
    let ovpnContent = config.ovpnFileContent || '';
    if (!ovpnContent && config.ovpnFileContentRef) {
        // Load from local storage if stored separately
        const result = await chrome.storage.local.get(config.ovpnFileContentRef);
        ovpnContent = result[config.ovpnFileContentRef] || '';
    }
    
    if (ovpnFileContent) ovpnFileContent.value = ovpnContent;
    if (ovpnAuthUser) ovpnAuthUser.value = config.ovpnUser || '';
    if (ovpnAuthPass) ovpnAuthPass.value = config.ovpnPass || '';
    if (ovpnKeyPassphrase) ovpnKeyPassphrase.value = config.ovpnKeyPassphrase || '';
    if (ovpnContent && ovpnFileStatus) {
        ovpnFileStatus.textContent = `✓ Configuration loaded. Upload a new file to replace it or click Download to save it.`;
        ovpnFileStatus.style.color = 'var(--success-color, #28a745)';
    }
    checkOvpnForAuth(ovpnContent); // Check on initial load

    // V2Ray fields
    // This check prevents a crash if the element doesn't exist in the template.
    if (v2rayUrlInput) v2rayUrlInput.value = config.v2rayUrl || '';

    // External Proxy fields
    if (externalProtocolSelect) externalProtocolSelect.value = config.proxyProtocol || 'SOCKS5';
    if (externalHostInput) externalHostInput.value = config.proxyHost || '127.0.0.1';
    if (externalPortInput) externalPortInput.value = config.proxyPort || '';

    // Passwall2 fields
    if (passwall2HostInput) passwall2HostInput.value = config.passwall2Host || '';
    if (passwall2UserInput) passwall2UserInput.value = config.passwall2User || 'root';
    if (passwall2PasswordInput) passwall2PasswordInput.value = config.passwall2Password || '';
    if (passwall2KeyPathInput) passwall2KeyPathInput.value = config.passwall2KeyPath || '';
    if (passwall2SocksPortInput) passwall2SocksPortInput.value = config.passwall2SocksPort || '1080';
    if (passwall2HttpPortInput) passwall2HttpPortInput.value = config.passwall2HttpPort || '';
    
    // Passwall2 Management Functions
    const getPasswall2Config = () => ({
        id: configId,
        passwall2Host: passwall2HostInput?.value || '',
        passwall2User: passwall2UserInput?.value || 'root',
        passwall2Password: passwall2PasswordInput?.value || '',
        passwall2KeyPath: passwall2KeyPathInput?.value || '',
        passwall2SocksPort: passwall2SocksPortInput?.value || '1080',
        passwall2HttpPort: passwall2HttpPortInput?.value || ''
    });
    
    // Refresh Passwall2 proxies list
    if (passwall2RefreshBtn) {
        passwall2RefreshBtn.addEventListener('click', async () => {
            passwall2RefreshBtn.disabled = true;
            passwall2RefreshBtn.textContent = '🔄 Loading...';
            passwall2ProxiesList.innerHTML = '<div style="text-align: center; padding: 20px;">Connecting to router...</div>';
            
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.PASSWALL2,
                    action: 'list_proxies',
                    config: getPasswall2Config()
                });
                
                if (response.success) {
                    passwall2StatusText.textContent = response.service_status || 'Running';
                    passwall2StatusText.style.color = response.service_status === 'running' ? '#4CAF50' : '#f44336';
                    
                    if (response.proxies && response.proxies.length > 0) {
                        if (passwall2ProxyCount) {
                            passwall2ProxyCount.textContent = `${response.proxies.length} ${response.proxies.length === 1 ? 'proxy' : 'proxies'}`;
                        }
                        
                        passwall2ProxiesList.innerHTML = response.proxies.map(proxy => `
                            <div class="passwall2-proxy-item" data-id="${proxy.id}" style="padding: 14px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; transition: background 0.2s;" onmouseover="this.style.background='#f9f9f9'" onmouseout="this.style.background='white'">
                                <div style="flex: 1;">
                                    <div style="font-weight: bold; margin-bottom: 6px; font-size: 1.05em;">
                                        ${proxy.enabled ? '<span style="color: #4CAF50;">✅</span>' : '<span style="color: #999;">⭕</span>'} 
                                        ${proxy.remarks || proxy.name || 'Unnamed Proxy'}
                                        ${proxy.enabled ? '<span style="background: #4CAF50; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.75em; margin-left: 8px;">ACTIVE</span>' : ''}
                                    </div>
                                    <div style="font-size: 0.9em; color: #666; display: flex; gap: 15px;">
                                        <span><strong>Type:</strong> ${proxy.type}</span>
                                        <span><strong>Server:</strong> ${proxy.address}:${proxy.port}</span>
                                    </div>
                                </div>
                            </div>
                        `).join('');
                        
                        // Add event listeners to toggle/delete buttons
                        passwall2ProxiesList.querySelectorAll('.passwall2-toggle-proxy').forEach(btn => {
                            btn.addEventListener('click', () => togglePasswall2Proxy(btn.dataset.id, btn.dataset.enabled === 'true'));
                        });
                        
                        passwall2ProxiesList.querySelectorAll('.passwall2-delete-proxy').forEach(btn => {
                            btn.addEventListener('click', () => deletePasswall2Proxy(btn.dataset.id));
                        });
                    } else {
                        if (passwall2ProxyCount) passwall2ProxyCount.textContent = '0 proxies';
                        passwall2ProxiesList.innerHTML = `
                            <div style="text-align: center; padding: 40px; color: #999;">
                                <div style="font-size: 56px; margin-bottom: 15px;">📭</div>
                                <div style="font-size: 1.1em; margin-bottom: 8px;">No proxies configured on router</div>
                                <div style="font-size: 0.9em;">Click "Add New Proxy" to add your first proxy to Passwall2</div>
                            </div>`;
                    }
                } else {
                    passwall2ProxiesList.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: #f44336;">
                            <div style="font-size: 56px; margin-bottom: 15px;">❌</div>
                            <div style="font-weight: bold; margin-bottom: 8px;">Connection Failed</div>
                            <div style="font-size: 0.9em;">${response.message || 'Could not connect to OpenWrt router'}</div>
                        </div>`;
                    passwall2StatusText.textContent = 'Error';
                    passwall2StatusText.style.color = '#f44336';
                }
            } catch (error) {
                passwall2ProxiesList.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: #f44336;">
                        <div style="font-size: 56px; margin-bottom: 15px;">⚠️</div>
                        <div style="font-weight: bold; margin-bottom: 8px;">Error</div>
                        <div style="font-size: 0.9em;">${error.message}</div>
                    </div>`;
            } finally {
                passwall2RefreshBtn.disabled = false;
                passwall2RefreshBtn.textContent = '🔄 Refresh List';
            }
        });
    }
    
    // Toggle proxy enable/disable
    const togglePasswall2Proxy = async (proxyId, currentlyEnabled) => {
        try {
            const response = await chrome.runtime.sendMessage({
                command: COMMANDS.PASSWALL2,
                action: currentlyEnabled ? 'disable_proxy' : 'enable_proxy',
                config: getPasswall2Config(),
                proxyId: proxyId
            });
            
            if (response.success) {
                // Refresh the list
                passwall2RefreshBtn.click();
            } else {
                alert(`Failed to ${currentlyEnabled ? 'disable' : 'enable'} proxy: ${response.message}`);
            }
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    };
    
    // Delete proxy
    const deletePasswall2Proxy = async (proxyId) => {
        if (!confirm('Are you sure you want to delete this proxy from Passwall2?\n\nThis will permanently remove it from your router.')) return;
        
        try {
            const response = await chrome.runtime.sendMessage({
                command: COMMANDS.PASSWALL2,
                action: 'delete_proxy',
                config: getPasswall2Config(),
                proxyId: proxyId
            });
            
            if (response.success) {
                // Refresh the list
                passwall2RefreshBtn.click();
            } else {
                alert(`Failed to delete proxy: ${response.message}`);
            }
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    };
    
    // Start/Stop/Restart Passwall2 service
    if (passwall2StartServiceBtn) {
        passwall2StartServiceBtn.addEventListener('click', async () => {
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.PASSWALL2,
                    action: 'start_service',
                    config: getPasswall2Config()
                });
                
                if (response.success) {
                    passwall2StatusText.textContent = 'Running';
                    passwall2StatusText.style.color = '#4CAF50';
                    alert('✅ Passwall2 service started successfully');
                } else {
                    alert(`❌ Failed to start service: ${response.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        });
    }
    
    if (passwall2StopServiceBtn) {
        passwall2StopServiceBtn.addEventListener('click', async () => {
            if (!confirm('Stop Passwall2 service?\n\nThis will disconnect all active proxies on the router.')) return;
            
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.PASSWALL2,
                    action: 'stop_service',
                    config: getPasswall2Config()
                });
                
                if (response.success) {
                    passwall2StatusText.textContent = 'Stopped';
                    passwall2StatusText.style.color = '#f44336';
                    alert('✅ Passwall2 service stopped');
                } else {
                    alert(`❌ Failed to stop service: ${response.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        });
    }
    
    if (passwall2RestartServiceBtn) {
        passwall2RestartServiceBtn.addEventListener('click', async () => {
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.PASSWALL2,
                    action: 'restart_service',
                    config: getPasswall2Config()
                });
                
                if (response.success) {
                    passwall2StatusText.textContent = 'Restarting...';
                    passwall2StatusText.style.color = '#FF9800';
                    alert('✅ Passwall2 service restarted');
                    setTimeout(() => passwall2RefreshBtn.click(), 2000);
                } else {
                    alert(`❌ Failed to restart service: ${response.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        });
    }
    
    // Add new proxy modal
    if (passwall2AddProxyBtn) {
        passwall2AddProxyBtn.addEventListener('click', () => {
            passwall2AddModal.style.display = 'flex';
        });
    }
    
    if (passwall2CancelAddBtn) {
        passwall2CancelAddBtn.addEventListener('click', () => {
            passwall2AddModal.style.display = 'none';
        });
    }
    
    // Save new proxy
    if (passwall2SaveProxyBtn) {
        passwall2SaveProxyBtn.addEventListener('click', async () => {
            const proxyData = {
                type: passwall2AddModal.querySelector('.passwall2-proxy-type').value,
                remarks: passwall2AddModal.querySelector('.passwall2-proxy-remarks').value,
                address: passwall2AddModal.querySelector('.passwall2-proxy-address').value,
                port: passwall2AddModal.querySelector('.passwall2-proxy-port').value,
                method: passwall2AddModal.querySelector('.passwall2-proxy-method').value,
                password: passwall2AddModal.querySelector('.passwall2-proxy-password').value,
                url: passwall2AddModal.querySelector('.passwall2-proxy-url').value
            };
            
            if (!proxyData.remarks && !proxyData.url) {
                alert('⚠️ Please provide at least a name for the proxy');
                return;
            }
            
            if (!proxyData.url && (!proxyData.address || !proxyData.port)) {
                alert('⚠️ Please either:\n• Paste a configuration URL, OR\n• Fill in Server Address and Port manually');
                return;
            }
            
            passwall2SaveProxyBtn.disabled = true;
            passwall2SaveProxyBtn.textContent = '💾 Saving to router...';
            
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.PASSWALL2,
                    action: 'add_proxy',
                    config: getPasswall2Config(),
                    proxyData: proxyData
                });
                
                if (response.success) {
                    passwall2AddModal.style.display = 'none';
                    // Clear form
                    passwall2AddModal.querySelectorAll('input').forEach(input => input.value = '');
                    // Refresh list
                    passwall2RefreshBtn.click();
                    alert('✅ Proxy added successfully to Passwall2!');
                } else {
                    alert(`❌ Failed to add proxy: ${response.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            } finally {
                passwall2SaveProxyBtn.disabled = false;
                passwall2SaveProxyBtn.textContent = '💾 Save to Router';
            }
        });
    }

    // ProtonVPN fields
    if (protonvpnUsernameInput) protonvpnUsernameInput.value = config.protonvpnUsername || '';
    if (protonvpnPasswordInput) protonvpnPasswordInput.value = config.protonvpnPassword || '';
    if (protonvpnProtocolSelect) protonvpnProtocolSelect.value = config.protonvpnProtocol || 'openvpn-tcp';
    if (protonvpnStrategySelect) {
        protonvpnStrategySelect.value = config.protonvpnStrategy || 'fastest';
        // Toggle specific server input based on strategy
        protonvpnStrategySelect.addEventListener('change', () => {
            if (protonvpnSpecificServerGroup) {
                protonvpnSpecificServerGroup.style.display = 
                    protonvpnStrategySelect.value === 'specific' ? 'block' : 'none';
            }
            debouncedSave();
        });
        if (protonvpnSpecificServerGroup) {
            protonvpnSpecificServerGroup.style.display = 
                config.protonvpnStrategy === 'specific' ? 'block' : 'none';
        }
    }
    if (protonvpnServerInput) protonvpnServerInput.value = config.protonvpnServer || '';
    if (protonvpnFreeOnlyCheckbox) protonvpnFreeOnlyCheckbox.checked = config.protonvpnFreeOnly === true;
    if (protonvpnUpdateIntervalSelect) protonvpnUpdateIntervalSelect.value = config.protonvpnUpdateInterval || 'daily';

    // ProtonVPN discover button handler
    if (protonvpnDiscoverButton) {
        protonvpnDiscoverButton.addEventListener('click', async () => {
            protonvpnDiscoverButton.disabled = true;
            protonvpnDiscoverButton.textContent = '🔄 Discovering...';
            protonvpnStatusDiv.style.display = 'block';
            protonvpnStatusText.textContent = 'Scanning ProtonVPN servers for accessibility...';
            protonvpnServersList.innerHTML = '';
            
            try {
                // Send discovery request to background script
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.DISCOVER_PROTONVPN_SERVERS,
                    configId: configId,
                    freeOnly: protonvpnFreeOnlyCheckbox?.checked || false
                });
                
                // Handle undefined or null response
                if (!response) {
                    throw new Error('No response from background script. Make sure the extension is properly loaded.');
                }
                
                if (response.success && response.servers) {
                    protonvpnStatusText.textContent = `Found ${response.servers.length} accessible servers - Click "Create Config" to add as OpenVPN proxy:`;
                    protonvpnServersList.innerHTML = response.servers.map((s, index) => 
                        `<div style="padding: 10px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                ${s.flag} ${s.country} ${s.name}${s.isFree ? ' [FREE]' : ''} - ${s.latency}ms (Ports: ${s.ports.join(', ')})
                            </div>
                            <button class="protonvpn-create-config-btn" data-server-index="${index}" 
                                    style="padding: 5px 10px; background: #4CAF50; color: white; border: none; border-radius: 3px; cursor: pointer;">
                                ➕ Create Config
                            </button>
                        </div>`
                    ).join('');
                    
                    // Store servers temporarily for creating configs
                    window.discoveredProtonVPNServers = response.servers;
                    
                    // Add click handlers for create config buttons
                    document.querySelectorAll('.protonvpn-create-config-btn').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            const serverIndex = parseInt(e.target.getAttribute('data-server-index'));
                            const server = window.discoveredProtonVPNServers[serverIndex];
                            await createProtonVPNConfig(server);
                        });
                    });
                    
                    debouncedSave();
                } else {
                    protonvpnStatusText.textContent = 'No accessible servers found. ' + (response.error || response.message || 'Unknown error');
                }
            } catch (error) {
                console.error('ProtonVPN discovery error:', error);
                protonvpnStatusText.textContent = 'Discovery failed: ' + error.message;
            } finally {
                protonvpnDiscoverButton.disabled = false;
                protonvpnDiscoverButton.textContent = '🔍 Discover Servers Now';
            }
        });
    }

    // ProtonVPN view servers button handler
    if (protonvpnViewServersButton) {
        protonvpnViewServersButton.addEventListener('click', async () => {
            try {
                const response = await chrome.runtime.sendMessage({
                    command: COMMANDS.GET_PROTONVPN_SERVERS,
                    configId: configId
                });
                
                // Handle undefined or null response
                if (!response) {
                    throw new Error('No response from background script. Make sure the extension is properly loaded.');
                }
                
                if (response.success && response.servers && response.servers.length > 0) {
                    protonvpnStatusDiv.style.display = 'block';
                    protonvpnStatusText.textContent = `${response.servers.length} cached servers (last updated: ${new Date(response.lastUpdate).toLocaleString()}):`;
                    protonvpnServersList.innerHTML = response.servers.map(s => 
                        `<div style="padding: 5px; border-bottom: 1px solid #ddd;">
                            ${s.flag} ${s.country} ${s.name}${s.isFree ? ' [FREE]' : ''} - ${s.latency}ms
                        </div>`
                    ).join('');
                } else {
                    alert('No cached servers found. Click "Discover Servers Now" to scan for accessible servers.');
                }
            } catch (error) {
                console.error('ProtonVPN view servers error:', error);
                alert('Failed to load servers: ' + error.message);
            }
        });
    }

    /**
     * Create a new OpenVPN configuration from a discovered ProtonVPN server
     */
    async function createProtonVPNConfig(server) {
        try {
            // Get ProtonVPN credentials from the current config card
            const username = protonvpnUsernameInput?.value?.trim();
            const password = protonvpnPasswordInput?.value?.trim();
            
            if (!username || !password) {
                alert('Please enter your ProtonVPN username and password first.');
                return;
            }
            
            // Generate OpenVPN config content
            const ovpnConfig = generateProtonVPNOpenVPNConfig(server);
            
            // Create a new configuration
            const newConfig = {
                id: generateUUID(),
                name: `ProtonVPN ${server.country} ${server.name}${server.isFree ? ' [FREE]' : ''}`,
                type: 'openvpn',
                enabled: false,
                ovpnUser: username,
                ovpnPass: password,
                metadata: {
                    createdFrom: 'protonvpn-discovery',
                    server: server,
                    createdAt: new Date().toISOString()
                }
            };
            
            // Store the large ovpn file content separately in local storage to avoid quota issues
            // chrome.storage.sync has 8KB/item limit, chrome.storage.local has 10MB total limit
            const ovpnContentKey = `ovpn_content_${newConfig.id}`;
            await chrome.storage.local.set({ [ovpnContentKey]: ovpnConfig });
            
            // Add reference to the stored content
            newConfig.ovpnFileContentRef = ovpnContentKey;
            
            // Get current configurations
            const result = await chrome.storage.sync.get(STORAGE_KEYS.CORE_CONFIGURATIONS);
            const coreConfigs = result[STORAGE_KEYS.CORE_CONFIGURATIONS] || [];
            
            // Add new configuration
            coreConfigs.push(newConfig);
            
            // Save to storage
            await chrome.storage.sync.set({ [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs });
            
            // Show success message
            alert(`✅ Created new OpenVPN configuration: "${newConfig.name}"\n\nYou can now find it in your configurations list and enable it to connect.`);
            
            // Reload the page to show the new config
            window.location.reload();
            
        } catch (error) {
            console.error('Error creating ProtonVPN config:', error);
            alert('Failed to create configuration: ' + error.message);
        }
    }
    
    /**
     * Generate OpenVPN configuration content for ProtonVPN server
     */
    function generateProtonVPNOpenVPNConfig(server) {
        const port = 443; // Use port 443 for censorship bypass
        const proto = 'tcp';
        
        // Minimal config with embedded CA certificate
        // Note: ProtonVPN requires auth-user-pass for OpenVPN/IKEv2 credentials
        return `client
dev tun
proto ${proto}
remote ${server.ip} ${port}
resolv-retry infinite
nobind
persist-key
persist-tun
cipher AES-256-GCM
auth SHA512
tls-version-min 1.2
verb 3
pull-filter ignore "ifconfig-ipv6"
pull-filter ignore "route-ipv6"
remote-cert-tls server
auth-user-pass
script-security 2
dhcp-option DNS 10.2.0.1
<ca>
-----BEGIN CERTIFICATE-----
MIIFszCCA5ugAwIBAgIBATANBgkqhkiG9w0BAQ0FADBnMQswCQYDVQQGEwJDSDEP
MA0GA1UECAwGR2VuZXZhMRAwDgYDVQQHDAdWZXJuaWVyMRYwFAYDVQQKDA1Qcm90
b25WUE4gQUcxHTAbBgNVBAMMFFByb3RvblZQTiBSb290IENBIDIwHhcNMjExMDE4
MTIxNzM2WhcNMzExMDE4MTIxNzM2WjBnMQswCQYDVQQGEwJDSDEPMA0GA1UECAwG
R2VuZXZhMRAwDgYDVQQHDAdWZXJuaWVyMRYwFAYDVQQKDA1Qcm90b25WUE4gQUcx
HTAbBgNVBAMMFFByb3RvblZQTiBSb290IENBIDIwggIiMA0GCSqGSIb3DQEBAQUA
A4ICDwAwggIKAoICAQDDNwG6FLN1bKLXDVXp4fzKmAF2KLdhGh7CWIIbTaD3eXzH
WLKo6FKYVXlLiXu2wVxuHCVwcaWiWiRV48pI6YbXzWqA6k1jnZoUGMywmIPJ5OsP
KMvBEm82BaY9y3y4cEJhH8OQYkGJFUGVzWvI+JGtH1LdNElPCvhBr8KeI4RqCcBy
oFqBNZkBIgzhVcJFgNcTpDrXCYlO7cRKLxqFo0YvBLLaVBxrLHgMqJGvON9xNvgO
MLNL+PQKPGp3SBNrXvGMd7MF9GKTfM3IfQVz3Vc9rLiRWqpJVJTCrCa4FHwU9z0u
fqLJxGz3aA2pqMN3tIVvMJWQ5p9qMYmvYdGr0k8rqCwlXQsUOiEkVKPwYmPgVjmD
sJ8L8r0GQxNrIhP6ecLHHOZNQ9Mm2jJGNvBCPD/qfq8TfPXDLNHWhRPWYpNPV8xR
sQA8HcFR7Lx+OPBNiZKPJPp7e1B7HKPqQ8VbSHT9Fc5iBT8ZNMM7JKkV8lSF/Hy2
t0w3QNXXm8DXRDmBDqJSwULkTHLjqLnqF2nVGhDtJQWW7hDQF+Qhx5Q8TJl8Ujkd
LbJdqGy3SkDiJ8c2pqDLTpqCqaLZpTaVE6NBSjDgALQPkCPMvR3s9eAQJLdH6BWN
UqWV1kjRCqKHWK0pPBEPBNPhZJ7gvXWP0C1qXNKnXqaivYFNZ1rD1fhkCxqQHwID
AQABo2MwYTAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBBjAdBgNVHQ4E
FgQU7B/fKfvQNHMpB8wGQ4GwA1Uc33owHwYDVR0jBBgwFoAU7B/fKfvQNHMpB8wG
Q4GwA1Uc33owDQYJKoZIhvcNAQENBQADggIBABqG6jP5cJNFkLaFNJPy1s5JqSEG
1kzPhYRKROCvRLYVFPTNhcW3sUbMQOjTRRSjQG9LCKSFCmEeZcxVEtMIspVrjmMk
GDhJoL2kMPcGZlGPJCUa3rBjGYv4gPYPu6y1rxJIaJhh7hxUL/H4eUMBJYR0BpJd
7Hq8xpNHqLLw8xfDMEgdnlRDQBJGgN1NvKKyxTr3S5qHG+GJMJ/RKlCLPklHDZ/i
7WpDdCLJPi9mPGvXrQn8pqDWcW/pVqJp1WmXFHIQBXPVzCbHvE9dJyQcFHDlmBJb
S5Yh0mJRfVqJmNTKH7hElOlF6jXlDHJW8MzKTKzXALbhJlF9VEkqz0Nh1mfEuKvC
0VnqkPXKBSL7pxQpPpGNp5x7K0MrLdCkqHfRYmKmHmTmWPYqFqmJ1dI0xYB8Ywhs
pYnLYH9Kpci+pYGPGpOFdJaFcTPZ8EeZmEF8gccU+HMWM3M6nF3g8UpJV2nKAQ2P
LjgWLjUlNvHXD6CUJ2j6z5R8xQVJN7vGGJqPjJmqYBNNLMw5L8SfJ7n0QnK9dRxr
dHWc3GPUIJ2xKjQN2aLaLdIEPGPVQvO3A6DuOL3MQfUTGZM2LTTdBMJTWNXFQvJP
9O6RBpQCPPFPvJdLZcLFQvJLJQcJRZLFGJVGSUXfShm7nW3FNqFYQvqTwNO2lhqX
YFqzPcAaAH9qkYB3
-----END CERTIFICATE-----
</ca>
`;
    }
    
    /**
     * Generate a UUID for new configurations
     */
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }


    // Listen for changes to the enabled state to update the PAC script preview
    checkbox.addEventListener('change', () => {
      updateAllProxyRuleDropdownsAndPreview();
      debouncedSave();
    });

    checkbox.checked = config.enabled === true; // Default to false if undefined

    nameDisplay.textContent = config.name || 'New Configuration';

    // Initial population
    toggleSettingsVisibility(); // Set initial visibility based on loaded config

    // Event Listeners
    editButton.addEventListener('click', () => {
      const isEditing = details.style.display === 'block';
      details.style.display = isEditing ? 'none' : 'block';
      editButton.textContent = isEditing ? 'Edit' : 'Done';
      if (!isEditing) nameInput.focus();
    });

    deleteButton.addEventListener('click', () => {
      if (confirm(`Are you sure you want to delete the "${nameDisplay.textContent}" configuration?`)) {
        configCard.remove();
        updateAllProxyRuleDropdownsAndPreview();
        debouncedSave();
      }
    });

    duplicateButton.addEventListener('click', async () => {
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
        portForwards: (config.portForwards || []).map(p => ({...p})), // Deep copy
      };
      const newElement = await createConfigElement(newConfig, null, true);
      configCard.after(newElement);
      updateAllProxyRuleDropdownsAndPreview();
      debouncedSave();
    });

    // OVPN File handling - Upload/Replace
    ovpnFileUpload.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            ovpnFileContent.value = e.target.result;
            ovpnFileStatus.textContent = `File replaced: ${file.name}`;
            checkOvpnForAuth(e.target.result);
            debouncedSave();
        };
        reader.readAsText(file);
    });

    // OVPN File Download button
    const ovpnDownloadButton = openvpnSettings.querySelector('.ovpn-download-button');
    if (ovpnDownloadButton) {
        ovpnDownloadButton.addEventListener('click', () => {
            const content = ovpnFileContent.value;
            if (!content || !content.trim()) {
                alert('No OpenVPN configuration to download. Please upload a .ovpn file first.');
                return;
            }
            
            // Create filename from config name or use default
            const configName = nameInput.value.trim() || 'config';
            const filename = `${configName.replace(/[^a-z0-9_-]/gi, '_')}.ovpn`;
            
            // Create blob and download
            const blob = new Blob([content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            // Show feedback
            const originalText = ovpnDownloadButton.textContent;
            ovpnDownloadButton.textContent = '✓ Downloaded';
            setTimeout(() => {
                ovpnDownloadButton.textContent = originalText;
            }, 2000);
        });
    }


    nameInput.addEventListener('input', () => {
      nameDisplay.textContent = nameInput.value || 'New Configuration';
      updateAllProxyRuleDropdownsAndPreview();
      debouncedSave();
    });
    // Add debounced save to all other inputs
    // Using .filter(Boolean) safely removes any null elements from the list before adding listeners.
    [
        sshUserInput, sshHostInput, sshRemoteCommandInput, 
        ovpnProfileNameInput, ovpnAuthUser, ovpnAuthPass, ovpnKeyPassphrase, 
        v2rayUrlInput, 
        externalProtocolSelect, externalHostInput, externalPortInput,
        passwall2HostInput, passwall2UserInput, passwall2PasswordInput, passwall2KeyPathInput, passwall2SocksPortInput, passwall2HttpPortInput,
        protonvpnUsernameInput, protonvpnPasswordInput, protonvpnProtocolSelect, protonvpnStrategySelect, protonvpnServerInput, protonvpnFreeOnlyCheckbox, protonvpnUpdateIntervalSelect
    ].filter(Boolean).forEach(input => {
        input.addEventListener('input', debouncedSave);
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
    // This check prevents a crash if the element doesn't exist in the template
    if (v2rayUrlInput) {
      v2rayUrlInput.addEventListener('input', () => parseAndDisplayV2RayUrl(v2rayUrlInput.value));
    }

    connectButton.addEventListener('click', () => {
        const type = typeSelect.value;
        if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);

        // For Passwall2, auto-connect to router and load proxies
        if (type === 'passwall2') {
            const configPayload = getConfigPayloadFromElement(configCard);
            statusMessage.textContent = `Connecting to Passwall2 router "${configPayload.name}"...`;
            statusMessage.className = 'info';
            connectButton.disabled = true;
            
            // Expand the details panel to show Passwall2 management
            details.style.display = 'block';
            
            chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: configPayload }, async (response) => {
                if (response && response.success) {
                    statusMessage.textContent = `Connected to Passwall2 router. Loading proxies...`;
                    statusMessage.className = 'success';
                    
                    // Automatically trigger the refresh button to load proxies from router
                    if (passwall2RefreshBtn) {
                        setTimeout(() => {
                            passwall2RefreshBtn.click();
                        }, 500); // Small delay to ensure connection is fully established
                    }
                } else if (response && !response.success) {
                    statusMessage.textContent = `Failed to connect: ${response.message}`;
                    statusMessage.className = 'error';
                    connectButton.disabled = false;
                }
                // On success, the background script will trigger a full status update
            });
            return;
        }

        // For external proxies, there's no log to poll. Just send the command.
        if (type === 'external') {
            const configPayload = getConfigPayloadFromElement(configCard);
            statusMessage.textContent = `Activating external proxy "${configPayload.name}"...`;
            statusMessage.className = 'info';
            connectButton.disabled = true;

            chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: configPayload }, (response) => {
                if (response && !response.success) {
                    statusMessage.textContent = `Failed to activate: ${response.message}`;
                    statusMessage.className = 'error';
                    connectButton.disabled = false; // Re-enable on failure
                }
                // On success, the background script will trigger a full status update,
                // which will correctly update the button states.
            });
            return;
        }

        details.style.display = 'block'; // Show details to reveal log
        liveLogContainer.style.display = 'block';
        liveLogContent.textContent = 'Initiating connection...';

        const pollConfigLogs = () => {
            if (!document.body.contains(configCard) || liveLogContainer.style.display === 'none') {
                if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);
                delete configLogPollIntervals[configId];
                return;
            }
            chrome.runtime.sendMessage(
                { command: COMMANDS.GET_LOGS, identifier: configId, conn_type: type },
                (response) => {
                    if (!configLogPollIntervals[configId]) return;
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
        const configPayload = getConfigPayloadFromElement(configCard);

        statusMessage.textContent = `Connecting with "${configPayload.name}"...`;
        statusMessage.className = 'info';
        connectButton.disabled = true;
        pollConfigLogs(); // Initial call
        configLogPollIntervals[configId] = setInterval(pollConfigLogs, 1500);

        chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL, config: configPayload }, (response) => {
            if (response && !response.success) {
                if (configLogPollIntervals[configId]) {
                    clearInterval(configLogPollIntervals[configId]);
                    delete configLogPollIntervals[configId];
                }
                statusMessage.textContent = `Failed to connect: ${response.message}`;
                statusMessage.className = 'error';
                if (type === 'openvpn' && response.message.includes("Authentication failed")) {
                    ovpnAuthPass.value = '';
                    ovpnAuthPass.focus();
                }
            }
        });
    });

    disconnectButton.addEventListener('click', () => {
        liveLogContainer.style.display = 'none';
        if (configLogPollIntervals[configId]) clearInterval(configLogPollIntervals[configId]);
        delete configLogPollIntervals[configId];
        statusMessage.textContent = `Disconnecting...`;
        statusMessage.className = 'info';
        const configPayload = getConfigPayloadFromElement(configCard);
        chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL, config: configPayload });
    });

    testConfigButton.addEventListener('click', () => {
        webLatencyValue.textContent = '--';
        tcpPingValue.textContent = '--';
        testStatusValue.textContent = 'Testing...';
        dockerAuthValue.textContent = '--';
        testStatusMessage.textContent = 'Sending test request...';
        testStatusMessage.className = 'test-status-message info';

        const dockerCheckEnabled = dockerAuthCheckEnabledCheckbox.checked;
        const configToTest = getConfigPayloadFromElement(configCard);
        const pingHost = pingHostInput.value;
        const webCheckUrl = webCheckUrlInput.value;

        if (dockerCheckEnabled) {
            dockerMetricItem.style.display = 'flex';
            dockerAuthValue.textContent = 'Testing...';
        } else {
            dockerMetricItem.style.display = 'none';
        }

        const request = { command: COMMANDS.TEST_CONNECTION, config: configToTest, pingHost, webCheckUrl, dockerCheckEnabled };

        // For external proxies, there's no log to poll. Just send the command.
        if (configToTest.type === 'external') {
            // For external proxies, the native host needs the full config to know the protocol, host, and port.
            // The 'request' object already contains this under the 'config' key.
            chrome.runtime.sendMessage(request, (response) => {
                if (chrome.runtime.lastError) {
                    testStatusMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
                    testStatusValue.textContent = 'Error';
                } else handleTestResponse(response);
            });
            return;
        }

        chrome.runtime.sendMessage(request, (response) => {
            if (chrome.runtime.lastError) {
                testStatusMessage.textContent = `Error: ${chrome.runtime.lastError.message}`;
                testStatusValue.textContent = 'Error';
                return;
            }
            handleTestResponse(response);
        });

        function handleTestResponse(response) {
            testStatusMessage.textContent = response.message;
            testStatusMessage.className = `test-status-message ${response.success ? 'success' : 'error'}`;

            if (response.web_check_latency_ms !== undefined && response.web_check_latency_ms > -1) {
                webLatencyValue.textContent = `${response.web_check_latency_ms}ms`;
            } else {
                webLatencyValue.textContent = 'Fail';
            }

            if (response.tcp_ping_ms !== undefined && response.tcp_ping_ms > -1) {
                tcpPingValue.textContent = `${response.tcp_ping_ms}ms`;
            } else {
                tcpPingValue.textContent = formatTcpError(response.tcp_ping_error);
            }

            if (response.docker_check_status_msg !== undefined && response.docker_check_status_msg !== null) {
                dockerMetricItem.style.display = 'flex';
                dockerAuthValue.textContent = response.docker_check_status_msg;
                dockerAuthValue.classList.remove('good', 'bad'); // Reset classes
                if (response.docker_check_status_code === 200 && response.docker_check_status_msg === "OK (Token)") {
                    dockerAuthValue.classList.add('good');
                } else {
                    dockerAuthValue.classList.add('bad');
                }
            } else {
                dockerMetricItem.style.display = 'none';
            }

            if (response.success) {
                testStatusValue.textContent = 'OK';
            } else {
                testStatusValue.textContent = 'Fail';
            }
        }
    });

    // --- Port Forwarding Management ---
    (config.portForwards || []).forEach(rule => {
      portForwardingList.appendChild(createRuleElement(rule));
    });

    addPortForwardRuleButton.addEventListener('click', (e) => {
      e.preventDefault();
      const newRuleEl = createRuleElement();
      portForwardingList.appendChild(newRuleEl);
      debouncedSave();
    });

    if (startInEditMode) {
      details.style.display = 'block';
      editButton.textContent = 'Done';
    }

    return configCard;
  }

  function getConfigPayloadFromElement(item) {
      const id = item.dataset.id;
      const details = item.querySelector('.config-details');
      const type = details.querySelector('.config-type-select').value;
      const config = {
          id: id,
          enabled: details.querySelector('.config-enabled-checkbox').checked,
          name: details.querySelector('.config-input-name').value.trim(),
          type: type,
      };

      if (type === 'ssh') {
          Object.assign(config, {
              sshUser: details.querySelector('.config-input-ssh-user')?.value.trim() || '',
              sshHost: details.querySelector('.config-input-ssh-host')?.value.trim() || '',
              sshRemoteCommand: details.querySelector('.config-input-ssh-remote-command')?.value.trim() || '',
              portForwards: Array.from(
                  details.querySelectorAll('.port-forwarding-rules-list .rule-item')
              ).map(el => {
                  const type = el.querySelector('.rule-type')?.value;
                  const localPort = el.querySelector('.rule-local-port')?.value;
                  const remoteHost = el.querySelector('.rule-remote-host')?.value;
                  const remotePort = el.querySelector('.rule-remote-port')?.value;
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
          Object.assign(config, {
              ovpnProfileName: details.querySelector('.ovpn-profile-name')?.value.trim() || '',
              ovpnFileContent: details.querySelector('.ovpn-file-content')?.value || '',
              ovpnUser: details.querySelector('.ovpn-auth-user')?.value || '',
              ovpnPass: details.querySelector('.ovpn-auth-pass')?.value || '',
              ovpnKeyPassphrase: details.querySelector('.ovpn-key-passphrase')?.value || '',
          });
      } else if (type === 'v2ray') {
          Object.assign(config, {
              v2rayUrl: details.querySelector('.config-input-v2ray-url')?.value.trim() || '',
          });
      } else if (type === 'openwrt_passwall2') {
          Object.assign(config, {
              openwrtMode: details.querySelector('.config-input-openwrt-mode')?.value || 'backend',
              openwrtHost: details.querySelector('.config-input-openwrt-host')?.value.trim() || '',
              openwrtUser: details.querySelector('.config-input-openwrt-user')?.value.trim() || 'root',
              sshKeyPath: details.querySelector('.config-input-ssh-key-path')?.value.trim() || '',
              openwrtSocksPort: details.querySelector('.config-input-openwrt-socks-port')?.value || '1080',
          });
      } else if (type === 'passwall2') {
          Object.assign(config, {
              passwall2Host: details.querySelector('.config-input-passwall2-host')?.value.trim() || '',
              passwall2User: details.querySelector('.config-input-passwall2-user')?.value.trim() || 'root',
              passwall2Password: details.querySelector('.config-input-passwall2-password')?.value || '',
              passwall2KeyPath: details.querySelector('.config-input-passwall2-key-path')?.value.trim() || '',
              passwall2SocksPort: details.querySelector('.config-input-passwall2-socks-port')?.value || '1080',
              passwall2HttpPort: details.querySelector('.config-input-passwall2-http-port')?.value.trim() || '',
          });
      } else if (type === 'external') {
           Object.assign(config, {
              proxyProtocol: details.querySelector('.config-input-external-protocol')?.value || 'SOCKS5',
              proxyHost: details.querySelector('.config-input-external-host')?.value.trim() || '',
              proxyPort: details.querySelector('.config-input-external-port')?.value.trim() || '',
          });
      } else if (type === 'protonvpn') {
          Object.assign(config, {
              protonvpnUsername: details.querySelector('.config-input-protonvpn-username')?.value.trim() || '',
              protonvpnPassword: details.querySelector('.config-input-protonvpn-password')?.value || '',
              protonvpnProtocol: details.querySelector('.config-input-protonvpn-protocol')?.value || 'openvpn-tcp',
              protonvpnStrategy: details.querySelector('.config-input-protonvpn-strategy')?.value || 'fastest',
              protonvpnServer: details.querySelector('.config-input-protonvpn-server')?.value.trim() || '',
              protonvpnFreeOnly: details.querySelector('.config-input-protonvpn-free-only')?.checked || false,
              protonvpnUpdateInterval: details.querySelector('.config-input-protonvpn-update-interval')?.value || 'daily',
          });
      }
      config.httpProxyEnabled = httpProxyEnabledCheckbox.checked;
      config.httpProxyPort = parseInt(httpProxyPortInput.value, 10);
      return config;
  }

  function createProxyBypassRuleElement(rule = {}) {
    const content = proxyBypassRuleTemplate.content.cloneNode(true);
    const ruleElement = content.querySelector('.rule-item');
    const enabledCheckbox = ruleElement.querySelector('.rule-enabled-checkbox');
    const domainInput = ruleElement.querySelector('.bypass-domain-input');
    const targetSelect = ruleElement.querySelector('.bypass-target-select');
    const removeButton = ruleElement.querySelector('.remove-rule-button');

    // For backward compatibility, rules are enabled by default if the property is missing.
    enabledCheckbox.checked = rule.enabled !== false;
    domainInput.value = rule.domain || '';

    // The 'DIRECT' and 'Default Active Proxy' options are in the template.
    // We only need to add the configuration-specific proxy options.
    while (targetSelect.options.length > 2) {
        targetSelect.remove(2);
    }

    // Populate the select dropdown from the cached list of configs
    coreConfigsForSelect.forEach(config => {
        const option = document.createElement('option');
        option.value = config.id;
        option.textContent = `Proxy via: ${config.name}`;
        targetSelect.appendChild(option);
    });

    targetSelect.value = rule.target || 'DIRECT';

    const commonCallback = () => {
        updatePacScriptPreview();
        debouncedSave();
    };

    enabledCheckbox.addEventListener('change', commonCallback);
    domainInput.addEventListener('input', commonCallback);
    targetSelect.addEventListener('change', commonCallback);

    removeButton.addEventListener('click', () => {
      ruleElement.remove();
      commonCallback();
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

    typeSelect.addEventListener('change', () => { toggleInputs(); debouncedSave(); });
    removeButton.addEventListener('click', () => { ruleElement.remove(); debouncedSave(); });

    // Add listeners to inputs
    localPortInput.addEventListener('input', () => debouncedSave());
    remoteHostInput.addEventListener('input', () => debouncedSave());
    remotePortInput.addEventListener('input', () => debouncedSave());

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
    ssidInput.addEventListener('input', () => debouncedSave());
    removeButton.addEventListener('click', () => { ruleElement.remove(); debouncedSave(); });
    wifiListContainer.appendChild(ruleElement);
  }

  // --- Connection & Proxy UI Management ---

  async function updateConnectionUI(status) {
    currentStatus = status; // Cache the status

    // --- Main Compact Status Indicator ---
    if (status.connecting) {
        connectionStatusDot.dataset.status = 'in-progress';
        connectionStatusText.textContent = 'Connecting...';
        connectionActionButton.innerHTML = '⏳';
        connectionActionButton.title = 'In Progress...';
        connectionActionButton.disabled = true;
    } else if (status.connected) {
        connectionStatusDot.dataset.status = 'connected';
        const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
        connectionStatusText.textContent = isProxyManaged ? 'Tunnel Connected (Proxy Applied)' : 'Tunnel Connected';
        connectionActionButton.innerHTML = '⏻';
        connectionActionButton.title = 'Disconnect';
        connectionActionButton.disabled = false;
    } else { // Disconnected
        connectionStatusDot.dataset.status = 'disconnected';
        connectionStatusText.textContent = 'Disconnected';
        connectionActionButton.innerHTML = '⏻';
        connectionActionButton.title = 'Connect';
        connectionActionButton.disabled = false;
    }


    if (!status || !status.connected) {
      applyProxyButton.style.display = 'none';
      revertProxyButton.style.display = 'none';
      reconnectNowContainer.style.display = 'block';

      if (Object.keys(configLogPollIntervals).length > 0) {
        Object.values(configLogPollIntervals).forEach(clearInterval);
        configLogPollIntervals = {};
        document.querySelectorAll('.config-live-log-container').forEach(el => el.style.display = 'none');
      }
    } else {
      if (status.socks_port) {
        const { [STORAGE_KEYS.IS_PROXY_MANAGED]: isProxyManaged } = await chrome.storage.local.get(STORAGE_KEYS.IS_PROXY_MANAGED);
        if (isProxyManaged) {
          applyProxyButton.style.display = 'none';
          revertProxyButton.style.display = 'inline-block';
        } else {
          applyProxyButton.style.display = 'inline-block';
          revertProxyButton.style.display = 'none';
        }
      } else {
        applyProxyButton.style.display = 'none';
        revertProxyButton.style.display = 'none';
      }
      reconnectNowContainer.style.display = 'none';
    }
    // --- Per-Configuration Button State ---
    const activeConfigId = status ? status.activeConfigId : null;
    document.querySelectorAll('#core-configurations-list .config-card').forEach(card => {
        const connectBtn = card.querySelector('.connect-config-button');
        const disconnectBtn = card.querySelector('.disconnect-config-button');
        const statusBadge = card.querySelector('.status-badge');
        const configId = card.dataset.id;

        if (status && (status.connected || status.connecting)) {
            if (configId === activeConfigId) {
                connectBtn.style.display = 'none';
                disconnectBtn.style.display = 'inline-block';
                disconnectBtn.disabled = false;
                statusBadge.textContent = status.connecting ? '[● CONNECTING...]' : '[● CONNECTED]';
                statusBadge.dataset.status = status.connecting ? 'testing' : 'connected';
            } else {
                connectBtn.style.display = 'inline-block';
                connectBtn.disabled = true;
                disconnectBtn.style.display = 'none';
                statusBadge.textContent = '[● INACTIVE]';
                statusBadge.dataset.status = 'disconnected';
            }
        } else {
            connectBtn.style.display = 'inline-block';
            connectBtn.disabled = false;
            disconnectBtn.style.display = 'none';
            statusBadge.textContent = '[● DISCONNECTED]';
            statusBadge.dataset.status = 'disconnected';
        }
    });
  }

  async function checkAndSetIncognitoControls() {
    // This function is only available in Manifest V3 extensions.
    // It might not exist in some testing environments or older browser versions.
    if (typeof chrome.extension?.isAllowedIncognitoAccess !== 'function') {
        console.warn("Could not check for incognito access permission. Feature will be assumed to be available.");
        return;
    }

    try {
        const isAllowed = await chrome.extension.isAllowedIncognitoAccess();
        incognitoProxySelect.disabled = !isAllowed;
        incognitoPermissionWarning.style.display = isAllowed ? 'none' : 'block';
    } catch (e) {
        // Gracefully handle any unexpected errors from the API call.
        console.error("Error checking incognito access:", e);
        incognitoProxySelect.disabled = false; // Default to enabled on error
        incognitoPermissionWarning.style.display = 'none';
    }
  }

  function updatePacScriptPreview() {
    const geoIpBypassEnabled = globalGeoIpBypassCheckbox.checked;
    const geoSiteBypassEnabled = globalGeoSiteBypassCheckbox.checked;

    const customRules = Array.from(
      document.querySelectorAll('#proxy-bypass-rules-list .rule-item')
    ).map(el => {
      const domain = el.querySelector('.bypass-domain-input').value.trim();
      const target = el.querySelector('.bypass-target-select').value;
      const enabled = el.querySelector('.rule-enabled-checkbox').checked;
      if (!domain || !enabled) return null; // Ignore empty or disabled rules
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
    document.querySelectorAll('#core-configurations-list .config-card').forEach(item => {
      const configId = item.dataset.id;
      const configType = item.querySelector('.config-type-select').value;
      const configName = item.querySelector('.config-input-name').value.trim() || 'Untitled';
      const proxyVar = `PROXY_${configId.replace(/-/g, '_')}`;

      if (configType === 'external') {
        const protocol = item.querySelector('.config-input-external-protocol').value;
        const host = item.querySelector('.config-input-external-host').value.trim();
        const port = item.querySelector('.config-input-external-port').value.trim();

        if (host && port) {
            let pacProtocol = 'SOCKS5'; // Default
            if (protocol === 'SOCKS4') pacProtocol = 'SOCKS';
            else if (protocol === 'HTTP') pacProtocol = 'PROXY';
            else if (protocol === 'HTTPS') pacProtocol = 'HTTPS';

            pacScript += `    const ${proxyVar} = "${pacProtocol} ${host}:${port}"; // For "${configName}"\n`;
            proxyDefinitions.push({ id: configId, variable: proxyVar });
        }
      } else if (configType === 'v2ray') {
        // V2Ray uses a hardcoded SOCKS5 port 10808
        pacScript += `    const ${proxyVar} = "SOCKS5 127.0.0.1:10808"; // For "${configName}"\n`;
        proxyDefinitions.push({ id: configId, variable: proxyVar });
      } else {
        // This handles ssh, openvpn which rely on port forwarding rules
        const portForwardingList = item.querySelector('.port-forwarding-rules-list');
        if (portForwardingList) {
          portForwardingList.querySelectorAll('.rule-item').forEach(ruleEl => {
              const type = ruleEl.querySelector('.rule-type').value;
              if (type === 'D') {
                  const port = ruleEl.querySelector('.rule-local-port').value;
                  if (port) {
                      pacScript += `    const ${proxyVar} = "SOCKS5 127.0.0.1:${port}"; // For "${configName}"\n`;
                      proxyDefinitions.push({ id: configId, variable: proxyVar });
                  }
              }
          });
        }
      }
    });

    pacScript += `
    const DIRECT = "DIRECT";

    // Determine the default proxy to use. This will be the proxy of the
    // first *enabled* configuration found with a SOCKS proxy.
`;

    const firstEnabledConfig = Array.from(document.querySelectorAll('#core-configurations-list .config-card'))
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
      shExpMatch(host, "*.local")) {
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
    // These are checked first to ensure they take precedence.
`;
      const rulesByTarget = {};
      customRules.forEach(rule => {
          if (!rulesByTarget[rule.target]) {
              rulesByTarget[rule.target] = [];
          }
          rulesByTarget[rule.target].push(rule.domain);
      });

      const genConditions = domains => domains.map(d => `shExpMatch(host, "${d}")`).join(' ||\n        ');

      if (rulesByTarget.DIRECT) {
          pacScript += `    if (${genConditions(rulesByTarget.DIRECT)}) {\n        return DIRECT;\n    }\n`;
      }
      if (rulesByTarget.PROXY) {
          pacScript += `    if (${genConditions(rulesByTarget.PROXY)}) {\n        return PROXY;\n    }\n`;
      }

      proxyDefinitions.forEach(def => {
          if (rulesByTarget[def.id]) {
              pacScript += `    if (${genConditions(rulesByTarget[def.id])}) {\n        return ${def.variable};\n    }\n`;
          }
      });

    }

    if (geoSiteBypassEnabled) {
      pacScript += `
    // --- GeoSite Bypass for Iran (domain list) ---
    // (Preview uses a placeholder list; actual list is loaded from database)
    // This check is more reliable than GeoIP and is performed first.
    const geoSiteSubdomains = ["ir", "co.ir", "..."];
    for (let i = 0; i < geoSiteSubdomains.length; i++) {
        if (dnsDomainIs(host, geoSiteSubdomains[i])) {
            return DIRECT;
        }
    }
    const geoSiteFullDomains = ["shop.ir", "..."];
    for (let i = g = 0; i < geoSiteFullDomains.length; i++) {
        if (host === geoSiteFullDomains[i]) {
            return DIRECT;
        }
    }
`;
    }

    if (geoIpBypassEnabled) {
      pacScript += `
    // --- GeoIP Bypass for Iran (IP ranges) ---
    // This check is last because dnsResolve() can be unreliable for CDNs.
    // For services like YouTube, add a custom rule to force them through a proxy.
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
    document.querySelectorAll('#core-configurations-list .config-card').forEach(item => {
        const id = item.dataset.id;
        const name = item.querySelector('.config-input-name').value.trim();
        if (id && name) {
            coreConfigsForSelect.push({ id, name });
        }
    });

    // 2. Update all existing dropdowns in the proxy rules
    document.querySelectorAll('#proxy-bypass-rules-list .bypass-target-select').forEach(select => {
        const currentValue = select.value;
        // Clear all but the first two options ('DIRECT' and 'Default Active Proxy')
        while (select.options.length > 2) {
            select.remove(2);
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
    // Don't poll if the page is hidden or if polling is paused
    if (document.hidden || isLogPollingPaused) {
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

  // --- Router Settings Validation ---
  function checkRouterSettingsAndUpdateUI() {
    const hasRouterIp = routerIpInput && routerIpInput.value.trim() !== '';
    const hasRouterUser = routerSshUserInput && routerSshUserInput.value.trim() !== '';
    
    // Show Passwall2 radio option if IP and username are filled
    // Authentication (password or key) is optional - user can add it later or test will prompt
    const isRouterConfigured = hasRouterIp && hasRouterUser;
    
    if (proxyModePasswall2Label) {
      if (isRouterConfigured) {
        proxyModePasswall2Label.style.display = 'inline-block';
      } else {
        proxyModePasswall2Label.style.display = 'none';
        // If Passwall2 mode was selected but router is not configured anymore, switch back to local
        const proxyModeLocalRadio = document.getElementById('proxy-mode-local');
        const proxyModePasswall2Radio = document.getElementById('proxy-mode-passwall2');
        if (proxyModePasswall2Radio && proxyModePasswall2Radio.checked) {
          if (proxyModeLocalRadio) {
            proxyModeLocalRadio.checked = true;
            // Trigger the change event to update the UI
            proxyModeLocalRadio.dispatchEvent(new Event('change'));
          }
        }
      }
    }
    
    return isRouterConfigured;
  }

  // --- Settings Load/Save ---

  async function loadSettings() {
    // Define the keys we expect to find in sync storage. This is more robust
    // than using Object.values(STORAGE_KEYS), which might contain local keys or
    const syncKeysToGet = [
      // New keys
      STORAGE_KEYS.CORE_CONFIGURATIONS,
      STORAGE_KEYS.PROXY_BYPASS_RULES,
      STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED,
      STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED,
      STORAGE_KEYS.INCOGNITO_PROXY_CONFIG_ID,
      STORAGE_KEYS.WEBRTC_IP_HANDLING_POLICY,
      STORAGE_KEYS.OPENROUTER_API_KEY,
      STORAGE_KEYS.OPENROUTER_MODEL,
      STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE,
      STORAGE_KEYS.APPLY_PROXY_TO_SYSTEM,
      STORAGE_KEYS.AUTO_APPLY_PROXY_ON_CONNECT,
      STORAGE_KEYS.DOCKER_AUTH_CHECK_ENABLED,
      // New keys for HTTP proxy
      STORAGE_KEYS.HTTP_PROXY_ENABLED,
      STORAGE_KEYS.HTTP_PROXY_PORT,
      // Router settings
      STORAGE_KEYS.ROUTER_IP,
      STORAGE_KEYS.ROUTER_SSH_USER,
      STORAGE_KEYS.ROUTER_SSH_PORT,
      STORAGE_KEYS.ROUTER_SSH_PASSWORD,
      STORAGE_KEYS.ROUTER_SSH_KEY_PATH,
      // Legacy keys for migration
      STORAGE_KEYS.PING_HOST,
      STORAGE_KEYS.WEB_CHECK_URL,
      STORAGE_KEYS.AUTO_RECONNECT_ENABLED,
      STORAGE_KEYS.LEGACY_PORT_FORWARDS,
      STORAGE_KEYS.WIFI_SSIDS,
      'proxyMode', // Proxy mode preference (local vs passwall2)
      STORAGE_KEYS.AUTO_SELECT_BEST_PROXY,
    ];

    chrome.storage.sync.get(syncKeysToGet, (result) => {
      if (chrome.runtime.lastError) {
        console.error(`Error loading settings from chrome.storage.sync: ${chrome.runtime.lastError.message}`);
        statusMessage.textContent = 'Error loading settings. Check the extension console for details.';
        statusMessage.className = 'error';
        return;
      }

      // Load proxy mode preference (default: local)
      const savedProxyMode = result.proxyMode || 'local';
      const proxyModeLocalRadio = document.getElementById('proxy-mode-local');
      const proxyModePasswall2Radio = document.getElementById('proxy-mode-passwall2');
      
      if (proxyModeLocalRadio && proxyModePasswall2Radio) {
        if (savedProxyMode === 'passwall2') {
          proxyModePasswall2Radio.checked = true;
        } else {
          proxyModeLocalRadio.checked = true;
        }
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
      autoSelectBestProxyCheckbox.checked = result[STORAGE_KEYS.AUTO_SELECT_BEST_PROXY] === true; // Default to false

      wifiListContainer.innerHTML = ''; // Clear existing Wi-Fi networks
      const wifiSsids = result[STORAGE_KEYS.WIFI_SSIDS] || [];
      if (wifiSsids.length === 0) {
      } else {
        wifiSsids.forEach(createWifiElement);
      }

      aiApiKeyInput.value = result[STORAGE_KEYS.OPENROUTER_API_KEY] || '';
      aiModelInput.value = result[STORAGE_KEYS.OPENROUTER_MODEL] || 'openai/gpt-4.1-nano';
      const defaultSystemMessage = `You are a network configuration assistant for a browser extension named Holocron. A user will describe a service, and you must suggest a proxy routing rule for it. The user has a list of available proxy configurations. Your task is to determine if the service should be accessed 'DIRECT' (bypassing the proxy, typically for local or national services) or through one of the available proxy configuration IDs (for international or blocked services). Respond ONLY with a single, valid JSON object in the format: {"domain": "domain.pattern.com", "target": "proxy_id_or_DIRECT"}. Do not include any other text, explanation, or markdown formatting. Example for a user trying to access an Iranian service like "Digikala": {"domain": "*.digikala.com", "target": "DIRECT"}. Example for a user trying to access a service that needs a proxy like "YouTube": {"domain": "*.youtube.com", "target": "some-uuid-for-a-proxy"}.`;
      aiSystemMessageInput.value = result[STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE] || defaultSystemMessage;

      // --- Populate Privacy Controls ---
      // The 'disable_non_proxied_udp' policy is the most restrictive and thus the safest default.
      // The toggle is "on" (checked) if the policy is this, or if it's not set at all (first run).
      webRtcPolicyToggle.checked = result[STORAGE_KEYS.WEBRTC_IP_HANDLING_POLICY] === 'disable_non_proxied_udp' ||
                                  typeof result[STORAGE_KEYS.WEBRTC_IP_HANDLING_POLICY] === 'undefined';

      // --- Populate System Proxy Checkbox ---
      applySystemProxyCheckbox.checked = result[STORAGE_KEYS.APPLY_PROXY_TO_SYSTEM] === true; // Default to false

      // --- Populate Auto-Apply Proxy Checkbox ---
      autoApplyProxyCheckbox.checked = result[STORAGE_KEYS.AUTO_APPLY_PROXY_ON_CONNECT] !== false; // Default to true

      updateAutoApplyCheckboxState(); // Set initial disabled state based on the main checkbox

      // --- Populate Docker Auth Check ---
      dockerAuthCheckEnabledCheckbox.checked = result[STORAGE_KEYS.DOCKER_AUTH_CHECK_ENABLED] !== false; // Default to true

      // --- Populate HTTP Proxy Forwarder Settings ---
      httpProxyEnabledCheckbox.checked = result[STORAGE_KEYS.HTTP_PROXY_ENABLED] === true; // Default false
      httpProxyPortInput.value = result[STORAGE_KEYS.HTTP_PROXY_PORT] || '8888';
      httpProxyPortGroup.style.display = httpProxyEnabledCheckbox.checked ? 'block' : 'none';
      httpProxyEnabledCheckbox.addEventListener('change', () => {
          httpProxyPortGroup.style.display = httpProxyEnabledCheckbox.checked ? 'block' : 'none';
          debouncedSave();
      });

      // --- Populate Router Settings ---
      if (routerIpInput) routerIpInput.value = result[STORAGE_KEYS.ROUTER_IP] || '';
      if (routerSshUserInput) routerSshUserInput.value = result[STORAGE_KEYS.ROUTER_SSH_USER] || 'root';
      if (routerSshPortInput) routerSshPortInput.value = result[STORAGE_KEYS.ROUTER_SSH_PORT] || '22';
      if (routerSshPasswordInput) routerSshPasswordInput.value = result[STORAGE_KEYS.ROUTER_SSH_PASSWORD] || '';
      if (routerSshKeyPathInput) routerSshKeyPathInput.value = result[STORAGE_KEYS.ROUTER_SSH_KEY_PATH] || '';

      // --- Populate Core Configurations UI ---
      coreConfigListContainer.innerHTML = ''; // Clear existing
      coreConfigsForSelect = []; // Reset cache
      
      // Use async IIFE to load configs with async createConfigElement
      (async () => {
        if (coreConfigs && coreConfigs.length > 0) {
          for (const config of coreConfigs) {
            // Cache for dropdowns in other sections
            coreConfigsForSelect.push({ id: config.id, name: config.name });
            const el = await createConfigElement(config, null);
            coreConfigListContainer.appendChild(el);
          }
        } else {
          const el = await createConfigElement({}, null, true);
          coreConfigListContainer.appendChild(el); // Add a blank one for new users, in edit mode
        }
        
        // Apply proxy mode filter after configs are loaded
        window.filterConfigsByProxyMode(savedProxyMode);
        
        // If Passwall2 mode is active, load proxies from router
        if (savedProxyMode === 'passwall2') {
          setTimeout(() => {
            const passwall2RefreshBtn = document.querySelector('.passwall2-refresh-btn');
            if (passwall2RefreshBtn) {
              passwall2RefreshBtn.click();
            }
          }, 500); // Small delay to ensure UI is ready
        }
      })();

      // --- Populate Incognito Proxy Dropdown ---
      incognitoProxySelect.innerHTML = '<option value="">-- Use Regular Proxy Settings --</option>'; // Clear and add default
      coreConfigsForSelect.forEach(config => {
          const option = document.createElement('option');
          option.value = config.id;
          option.textContent = config.name;
          incognitoProxySelect.appendChild(option);
      });
      incognitoProxySelect.value = result[STORAGE_KEYS.INCOGNITO_PROXY_CONFIG_ID] || '';

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

      // Check and update UI based on incognito permissions
      checkAndSetIncognitoControls();
      
      // Check router settings and update Passwall2 radio button visibility
      checkRouterSettingsAndUpdateUI();

      // Request current latency measurements from background script
      chrome.runtime.sendMessage({ command: COMMANDS.GET_LATENCIES }, (response) => {
        if (response && response.latencies) {
          updateLatencyDisplay(response.latencies);
        }
      });
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
        const date = new Date(ipLastUpdate).toLocaleDateString('en-CA'); // YYYY-MM-DD format
        const count = ipRanges ? ipRanges.length : 0;
        geoipStatusDiv.innerHTML = `<strong>GeoIP:</strong> ${count} IP ranges loaded (Last Updated: ${date})`;
      } else {
        geoipStatusDiv.textContent = 'GeoIP: Database has not been updated yet.';
      }

      // GeoSite Status
      const domains = result[STORAGE_KEYS.GEOSITE_DOMAINS];
      const siteLastUpdate = result[STORAGE_KEYS.GEOSITE_LAST_UPDATE];
      if (siteLastUpdate) {
        const date = new Date(siteLastUpdate).toLocaleDateString('en-CA'); // YYYY-MM-DD format
        const count = domains ? domains.length : 0;
        geositeStatusDiv.innerHTML = `<strong>GeoSite:</strong> ${count} domains loaded (Last Updated: ${date})`;
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
    document.querySelectorAll('#core-configurations-list .config-card').forEach((item) => {
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
      } else if (type === 'protonvpn') {
        const protonvpnUsernameInput = item.querySelector('.config-input-protonvpn-username');
        const protonvpnPasswordInput = item.querySelector('.config-input-protonvpn-password');
        if (!protonvpnUsernameInput?.value.trim()) {
            showError(protonvpnUsernameInput, 'ProtonVPN username is required.');
        }
        if (!protonvpnPasswordInput?.value) {
            showError(protonvpnPasswordInput, 'ProtonVPN password is required.');
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
    // The debouncer sets the "Saving..." message.
    // We only need to handle validation failure and success here.

    if (!validateSettings()) {
      statusMessage.textContent = 'Please fix the errors before saving.';
      statusMessage.className = 'error';
      return; // Stop the save if validation fails
    }

    const coreConfigs = [];

    document.querySelectorAll('#core-configurations-list .config-card').forEach(item => {
        coreConfigs.push(getConfigPayloadFromElement(item));
    });

    const proxyBypassRules = Array.from(
        document.querySelectorAll('#proxy-bypass-rules-list .rule-item')
    ).map(el => {
        const domain = el.querySelector('.bypass-domain-input').value.trim();
        const target = el.querySelector('.bypass-target-select').value;
        const enabled = el.querySelector('.rule-enabled-checkbox').checked;
        if (!domain) return null;
        return { domain, target, enabled };
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
            delete config.ovpnPass;
        }
    });

    const settings = {
      [STORAGE_KEYS.CORE_CONFIGURATIONS]: coreConfigs,
      [STORAGE_KEYS.PING_HOST]: pingHostInput.value,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrlInput.value,
      [STORAGE_KEYS.WIFI_SSIDS]: wifiSsids,
      [STORAGE_KEYS.AUTO_RECONNECT_ENABLED]: autoReconnectCheckbox.checked,
      [STORAGE_KEYS.AUTO_SELECT_BEST_PROXY]: autoSelectBestProxyCheckbox.checked,
      [STORAGE_KEYS.PROXY_BYPASS_RULES]: proxyBypassRules,
      [STORAGE_KEYS.INCOGNITO_PROXY_CONFIG_ID]: incognitoProxySelect.value,
      [STORAGE_KEYS.WEBRTC_IP_HANDLING_POLICY]: webRtcPolicyToggle.checked ? 'disable_non_proxied_udp' : 'default',
      [STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED]: globalGeoIpBypassCheckbox.checked,
      [STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED]: globalGeoSiteBypassCheckbox.checked,
      [STORAGE_KEYS.OPENROUTER_API_KEY]: aiApiKeyInput.value.trim(),
      [STORAGE_KEYS.OPENROUTER_MODEL]: aiModelInput.value.trim(),
      [STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE]: aiSystemMessageInput.value.trim(),
      [STORAGE_KEYS.APPLY_PROXY_TO_SYSTEM]: applySystemProxyCheckbox.checked,
      [STORAGE_KEYS.AUTO_APPLY_PROXY_ON_CONNECT]: autoApplyProxyCheckbox.checked,
      [STORAGE_KEYS.DOCKER_AUTH_CHECK_ENABLED]: dockerAuthCheckEnabledCheckbox.checked,
      [STORAGE_KEYS.HTTP_PROXY_ENABLED]: httpProxyEnabledCheckbox.checked,
      [STORAGE_KEYS.HTTP_PROXY_PORT]: parseInt(httpProxyPortInput.value, 10) || 8888,
      // Router settings
      [STORAGE_KEYS.ROUTER_IP]: routerIpInput?.value.trim() || '',
      [STORAGE_KEYS.ROUTER_SSH_USER]: routerSshUserInput?.value.trim() || 'root',
      [STORAGE_KEYS.ROUTER_SSH_PORT]: parseInt(routerSshPortInput?.value, 10) || 22,
      [STORAGE_KEYS.ROUTER_SSH_PASSWORD]: routerSshPasswordInput?.value || '',
      [STORAGE_KEYS.ROUTER_SSH_KEY_PATH]: routerSshKeyPathInput?.value.trim() || '',
    };

    // Replace coreConfigs with the sanitized version for storage.
    settings[STORAGE_KEYS.CORE_CONFIGURATIONS] = settingsToStore;

    chrome.storage.sync.set(settings, () => {
      statusMessage.textContent = 'Settings saved!';
      statusMessage.className = 'success';

      // Notify the background script to apply the new WebRTC policy immediately
      chrome.runtime.sendMessage({ command: COMMANDS.APPLY_WEBRTC_POLICY });

      setTimeout(() => {
        if (statusMessage && statusMessage.textContent === 'Settings saved!') {
          statusMessage.textContent = '';
          statusMessage.className = '';
        }
      }, 3000);
    });
  }


  function requestStatusUpdate() {
    connectionStatusText.textContent = 'Checking...';
    connectionStatusDot.dataset.status = 'in-progress'; // Reset to default
    chrome.runtime.sendMessage({ command: COMMANDS.GET_POPUP_STATUS }, (response) => {
      if (chrome.runtime.lastError) {
        console.error(`Error requesting status: ${chrome.runtime.lastError.message}`);
        updateConnectionUI({ connected: false }); // Assume disconnected on error
      } else {
        updateConnectionUI(response);
      }
    });
  }

  // --- Auto-saving setup ---
  const debouncedSave = debounce(saveSettings, 750);


  // --- Event Listeners ---
  addConfigButton.addEventListener('click', async () => {
    // Get current proxy mode
    const proxyModePasswall2Radio = document.getElementById('proxy-mode-passwall2');
    const isPasswall2Mode = proxyModePasswall2Radio && proxyModePasswall2Radio.checked;
    
    // Create config with appropriate type based on mode
    const newConfig = isPasswall2Mode ? { type: 'passwall2' } : {};
    const newEl = await createConfigElement(newConfig, null, true);
    coreConfigListContainer.appendChild(newEl);
    updateAllProxyRuleDropdownsAndPreview();
    debouncedSave();
  });
  addWifiButton.addEventListener('click', () => { createWifiElement(); debouncedSave(); });
  addProxyRuleButton.addEventListener('click', () => {
      const newRuleEl = createProxyBypassRuleElement();
      proxyBypassRulesList.appendChild(newRuleEl);
      newRuleEl.querySelector('input').focus();
      updatePacScriptPreview();
      debouncedSave();
  });

  copyPacButton.addEventListener('click', () => {
    const pacScript = pacScriptPreviewContainer.querySelector('code').textContent;
    navigator.clipboard.writeText(pacScript).then(() => {
        copyPacButton.textContent = 'Copied!';
        setTimeout(() => {
            copyPacButton.textContent = 'Copy';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy PAC script: ', err);
        copyPacButton.textContent = 'Failed!';
         setTimeout(() => {
            copyPacButton.textContent = 'Copy';
        }, 2000);
    });
  });

  searchProxyRulesInput.addEventListener('input', (e) => {
    const searchTerm = e.target.value.toLowerCase();
    document.querySelectorAll('#proxy-bypass-rules-list .proxy-rule-item').forEach(ruleEl => {
        const domain = ruleEl.querySelector('.bypass-domain-input').value.toLowerCase();
        if (domain.includes(searchTerm)) {
            ruleEl.style.display = 'flex';
        } else {
            ruleEl.style.display = 'none';
        }
    });
  });

  const proxyActionsBar = document.querySelector('.proxy-actions-bar');

  proxyActionsBar.insertAdjacentElement('afterend', aiLiveLogContainer);
  aiLiveLogContainer.style.marginTop = '1em';

  aiSuggestRuleButton.addEventListener('click', async () => {
    const apiKey = aiApiKeyInput.value.trim();
    if (!apiKey) {
        alert('Please enter your GitHub Models API key in the AI Assistant section to use this feature.');
        aiApiKeyInput.focus();
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

        const response = await fetch('https://models.github.ai/inference/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`,
            'X-GitHub-Api-Version': '2022-11-28'
          },
          body: JSON.stringify({
            model: aiModelInput.value.trim() || 'openai/gpt-4.1-nano',
            messages: [
              { role: 'system', content: aiSystemMessageInput.value.trim() },
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
          debouncedSave();
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

  toggleLogPollingButton.addEventListener('click', () => {
    isLogPollingPaused = !isLogPollingPaused;
    toggleLogPollingButton.textContent = isLogPollingPaused ? 'Resume Log' : 'Pause Log';
    // If we are resuming, we need to restart the polling interval.
    if (!isLogPollingPaused) {
        handleVisibilityChange();
    }
  });

  copyLogButton.addEventListener('click', () => {
    const logText = logViewerContent.textContent;
    navigator.clipboard.writeText(logText).then(() => {
        copyLogButton.textContent = 'Copied!';
        setTimeout(() => { copyLogButton.textContent = 'Copy Log'; }, 2000);
    }).catch(err => {
        console.error('Failed to copy log: ', err);
        copyLogButton.textContent = 'Failed!';
        setTimeout(() => { copyLogButton.textContent = 'Copy Log'; }, 2000);
    });
  });



  // Add listeners to global inputs
  pingHostInput.addEventListener('input', () => debouncedSave());
  webCheckUrlInput.addEventListener('input', () => debouncedSave());
  autoReconnectCheckbox.addEventListener('change', () => debouncedSave());
  autoSelectBestProxyCheckbox.addEventListener('change', () => debouncedSave());
  aiApiKeyInput.addEventListener('input', () => debouncedSave());
  aiModelInput.addEventListener('input', () => debouncedSave());
  applySystemProxyCheckbox.addEventListener('change', () => {
    updateAutoApplyCheckboxState();
    debouncedSave();
  });
  autoApplyProxyCheckbox.addEventListener('change', () => debouncedSave());
  aiSystemMessageInput.addEventListener('input', () => debouncedSave());
  globalGeoIpBypassCheckbox.addEventListener('change', () => { updatePacScriptPreview(); debouncedSave(); });
  dockerAuthCheckEnabledCheckbox.addEventListener('change', () => debouncedSave());
  globalGeoSiteBypassCheckbox.addEventListener('change', () => { updatePacScriptPreview(); debouncedSave(); });
  httpProxyEnabledCheckbox.addEventListener('change', () => debouncedSave());
  httpProxyPortInput.addEventListener('input', () => debouncedSave());
  incognitoProxySelect.addEventListener('change', () => debouncedSave());
  webRtcPolicyToggle.addEventListener('change', () => debouncedSave());
  
  // Router settings event listeners - check and update UI when settings change
  if (routerIpInput) routerIpInput.addEventListener('input', () => { 
    checkRouterSettingsAndUpdateUI(); 
    debouncedSave(); 
  });
  if (routerSshUserInput) routerSshUserInput.addEventListener('input', () => { 
    checkRouterSettingsAndUpdateUI(); 
    debouncedSave(); 
  });
  if (routerSshPortInput) routerSshPortInput.addEventListener('input', () => debouncedSave());
  if (routerSshPasswordInput) routerSshPasswordInput.addEventListener('input', () => { 
    checkRouterSettingsAndUpdateUI(); 
    debouncedSave(); 
  });
  if (routerSshKeyPathInput) routerSshKeyPathInput.addEventListener('input', () => { 
    checkRouterSettingsAndUpdateUI(); 
    debouncedSave(); 
  });
  
  // Test router connection button
  if (testRouterConnectionBtn) {
    testRouterConnectionBtn.addEventListener('click', async () => {
      if (!routerIpInput || !routerIpInput.value.trim()) {
        routerTestStatus.textContent = '❌ Please enter router IP address';
        routerTestStatus.style.color = '#f44336';
        return;
      }
      
      if (!routerSshUserInput || !routerSshUserInput.value.trim()) {
        routerTestStatus.textContent = '❌ Please enter SSH username';
        routerTestStatus.style.color = '#f44336';
        return;
      }
      
      // Note: Authentication (password or key) is optional - SSH might work with default keys
      // or the user might have already set up key-based auth
      
      testRouterConnectionBtn.disabled = true;
      testRouterConnectionBtn.textContent = '🔄 Testing...';
      routerTestStatus.textContent = 'Testing connection...';
      routerTestStatus.style.color = '#2196F3';
      
      const routerConfig = {
        ip: routerIpInput.value.trim(),
        user: routerSshUserInput.value.trim(),
        port: parseInt(routerSshPortInput?.value || '22', 10),
        password: routerSshPasswordInput?.value || '',
        keyPath: routerSshKeyPathInput?.value.trim() || '',
      };
      
      chrome.runtime.sendMessage(
        { command: COMMANDS.TEST_ROUTER_CONNECTION, config: routerConfig },
        (response) => {
          testRouterConnectionBtn.disabled = false;
          testRouterConnectionBtn.textContent = '🔌 Test Router Connection';
          
          if (chrome.runtime.lastError) {
            routerTestStatus.textContent = `❌ Error: ${chrome.runtime.lastError.message}`;
            routerTestStatus.style.color = '#f44336';
            return;
          }
          
          if (response && response.success) {
            routerTestStatus.textContent = '✅ Connection successful! Passwall2 mode is ready.';
            routerTestStatus.style.color = '#4CAF50';
            checkRouterSettingsAndUpdateUI(); // Update UI to show Passwall2 option
          } else {
            routerTestStatus.textContent = `❌ ${response?.message || 'Connection failed'}`;
            routerTestStatus.style.color = '#f44336';
          }
        }
      );
    });
  }
  
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
  connectionActionButton.addEventListener('click', () => {
    if (currentStatus.connected) {
        chrome.runtime.sendMessage({ command: COMMANDS.STOP_TUNNEL });
    } else {
        chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL });
    }
  });

  reconnectNowButton.addEventListener('click', () => {
    chrome.runtime.sendMessage({ command: COMMANDS.START_TUNNEL }, (response) => {
      if (response && !response.success) {
        const message = response.message.split('\n')[0];
        statusMessage.textContent = `Error: ${message}`;
        statusMessage.className = 'error';
      }
    });
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

  if (disablePacButton) {
    disablePacButton.addEventListener('click', () => {
        connectionStatusText.textContent = 'Disabling Proxy...';
        statusMessage.textContent = 'Clearing proxy settings...';
        statusMessage.className = 'info';
        chrome.runtime.sendMessage({ command: COMMANDS.CLEAR_BROWSER_PROXY }, (response) => {
            if (chrome.runtime.lastError) {
                statusMessage.textContent = `Error clearing proxy: ${chrome.runtime.lastError.message}`;
                statusMessage.className = 'error';
            } else if (response && response.success) {
                statusMessage.textContent = 'Proxy settings cleared successfully.';
                statusMessage.className = 'success';
            } else {
                statusMessage.textContent = `Failed to clear proxy: ${response ? response.message : 'Unknown error'}`;
                statusMessage.className = 'error';
            }
            requestStatusUpdate();
        });
    });
  }

  // Update latency display for all config cards
  function updateLatencyDisplay(latencies) {
    if (!latencies || typeof latencies !== 'object') return;
    
    // Iterate through all config cards and update their latency displays
    document.querySelectorAll('.config-card').forEach(card => {
      const configId = card.dataset.id;
      if (!configId || !latencies[configId]) return;
      
      const latencyData = latencies[configId];
      const webLatencyValue = card.querySelector('.web-latency-value');
      const tcpPingValue = card.querySelector('.tcp-ping-value');
      
      if (webLatencyValue && latencyData.web_latency !== undefined) {
        webLatencyValue.textContent = latencyData.web_latency > 0 
          ? `${latencyData.web_latency}ms` 
          : '--';
      }
      
      if (tcpPingValue && latencyData.tcp_latency !== undefined) {
        tcpPingValue.textContent = latencyData.tcp_latency > 0 
          ? `${latencyData.tcp_latency}ms` 
          : '--';
      }
    });
  }

  // Listen for real-time status updates from the background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.command === COMMANDS.STATUS_UPDATED) {
      updateConnectionUI(request.status);
      updateCharts(request.status);
    } else if (request.command === COMMANDS.LATENCIES_UPDATED) {
      updateLatencyDisplay(request.latencies);
    }
  });

  // --- Modal Logic ---
  function showModal() {
    predefinedModal.style.display = 'flex';
  }
  function hideModal() {
    predefinedModal.style.display = 'none';
  }

  addPredefinedConfigButton.addEventListener('click', showModal);
  modalCloseButton.addEventListener('click', hideModal);
  predefinedModal.addEventListener('click', (e) => {
    if (e.target === predefinedModal) {
      hideModal();
    }
  });

  async function addPredefinedProfile(profileType) {
    let config = {};
    if (profileType === 'tor') {
      config = {
        name: 'Tor',
        type: 'external',
        proxyProtocol: 'SOCKS5',
        proxyHost: '127.0.0.1',
        proxyPort: '9050',
        enabled: false,
      };
    } else if (profileType === 'privoxy') {
      config = {
        name: 'Privoxy',
        type: 'external',
        proxyProtocol: 'HTTP',
        proxyHost: '127.0.0.1',
        proxyPort: '8118',
        enabled: false,
      };
    } else if (profileType === 'psiphon') {
      config = {
        name: 'Psiphon (SOCKS)',
        type: 'external',
        proxyProtocol: 'SOCKS5',
        proxyHost: '127.0.0.1',
        proxyPort: '1080',
        enabled: false,
      };
    }

    if (config.name) {
      const newEl = await createConfigElement(config, null, true);
      coreConfigListContainer.appendChild(newEl);
      updateAllProxyRuleDropdownsAndPreview();
      debouncedSave();
      hideModal();
    }
  }

  predefinedChoices.addEventListener('click', (e) => {
    const profile = e.target.dataset.profile;
    if (profile) {
      addPredefinedProfile(profile);
    }
  });

  // --- Import/Export Logic ---
  exportSettingsButton.addEventListener('click', async () => {
    try {
        // Define exactly which keys from sync storage should be exported.
        // This avoids exporting local state or sensitive data accidentally.
        const keysToExport = [
            STORAGE_KEYS.CORE_CONFIGURATIONS,
            STORAGE_KEYS.PING_HOST,
            STORAGE_KEYS.WEB_CHECK_URL,
            STORAGE_KEYS.WIFI_SSIDS,
            STORAGE_KEYS.AUTO_RECONNECT_ENABLED,
            STORAGE_KEYS.PROXY_BYPASS_RULES,
            STORAGE_KEYS.GLOBAL_GEOIP_BYPASS_ENABLED,
            STORAGE_KEYS.GLOBAL_GEOSITE_BYPASS_ENABLED,
            STORAGE_KEYS.INCOGNITO_PROXY_CONFIG_ID,
            STORAGE_KEYS.WEBRTC_IP_HANDLING_POLICY,
            STORAGE_KEYS.OPENROUTER_MODEL,
            STORAGE_KEYS.OPENROUTER_SYSTEM_MESSAGE,
            STORAGE_KEYS.APPLY_PROXY_TO_SYSTEM,
            STORAGE_KEYS.AUTO_APPLY_PROXY_ON_CONNECT,
            STORAGE_KEYS.DOCKER_AUTH_CHECK_ENABLED,
            // New keys for HTTP proxy
            STORAGE_KEYS.HTTP_PROXY_ENABLED,
            STORAGE_KEYS.HTTP_PROXY_PORT,
        ];

        const settingsToExport = await chrome.storage.sync.get(keysToExport);

        // Sanitize sensitive data before exporting.
        if (settingsToExport[STORAGE_KEYS.CORE_CONFIGURATIONS]) {
            // Create a deep copy to avoid modifying the in-memory state.
            const sanitizedConfigs = JSON.parse(JSON.stringify(settingsToExport[STORAGE_KEYS.CORE_CONFIGURATIONS]));
            sanitizedConfigs.forEach(config => {
                if (config.type === 'openvpn') {
                    delete config.ovpnPass; // Remove password before exporting
                }
            });
            settingsToExport[STORAGE_KEYS.CORE_CONFIGURATIONS] = sanitizedConfigs;
        }

        const settingsJson = JSON.stringify(settingsToExport, null, 2);
        const blob = new Blob([settingsJson], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const date = new Date().toISOString().split('T')[0];
        a.download = `holocron-settings-${date}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        statusMessage.textContent = 'Settings exported successfully.';
        statusMessage.className = 'success';
    } catch (error) {
        console.error('Failed to export settings:', error);
        statusMessage.textContent = `Error exporting settings: ${error.message}`;
        statusMessage.className = 'error';
    }
  });

  importSettingsButton.addEventListener('click', () => {
    importFileInput.click();
  });

  importFileInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const importedSettings = JSON.parse(e.target.result);

            // Basic validation to ensure it's not a random JSON file.
            if (!importedSettings || typeof importedSettings !== 'object' || !importedSettings[STORAGE_KEYS.CORE_CONFIGURATIONS]) {
                throw new Error('Invalid or corrupted settings file. Missing "coreConfigurations".');
            }

            if (!confirm('This will overwrite ALL your current settings. This action cannot be undone. Are you sure you want to continue?')) {
                importFileInput.value = ''; // Clear the file input
                return;
            }

            // Clear all existing sync data to ensure a clean import.
            chrome.storage.sync.clear(() => {
                if (chrome.runtime.lastError) {
                    throw new Error(`Failed to clear old settings: ${chrome.runtime.lastError.message}`);
                }
                // Set the new settings from the imported file.
                chrome.storage.sync.set(importedSettings, () => {
                    if (chrome.runtime.lastError) {
                        throw new Error(`Failed to import settings: ${chrome.runtime.lastError.message}`);
                    }
                    statusMessage.textContent = 'Settings imported successfully! The page will now reload.';
                    statusMessage.className = 'success';
                    setTimeout(() => location.reload(), 2000);
                });
            });

        } catch (error) {
            console.error('Failed to import settings:', error);
            statusMessage.textContent = `Error importing settings: ${error.message}`;
            statusMessage.className = 'error';
        } finally {
            // Clear the file input so the same file can be selected again if needed.
            importFileInput.value = '';
        }
    };
    reader.readAsText(file);
  });

  // --- Global Passwall2 Management ---
  function getGlobalRouterConfig() {
    return {
      passwall2Host: routerIpInput?.value.trim() || '',
      passwall2User: routerSshUserInput?.value.trim() || 'root',
      passwall2Port: routerSshPortInput?.value.trim() || '22',
      passwall2Password: routerSshPasswordInput?.value.trim() || '',
      passwall2KeyPath: routerSshKeyPathInput?.value.trim() || '',
      passwall2SocksPort: '1080',
      passwall2HttpPort: ''
    };
  }

  function setupGlobalPasswall2Management() {
    const globalRefreshButtons = document.querySelectorAll('.passwall2-refresh-btn');
    const passwall2ProxiesList = document.querySelector('.passwall2-proxies-list');
    const passwall2StatusText = document.querySelector('.passwall2-status-text');
    const passwall2ProxyCount = document.querySelector('.passwall2-proxy-count');
    
    console.log('[Passwall2] Setup: Found', globalRefreshButtons.length, 'refresh buttons');
    console.log('[Passwall2] Setup: ProxiesList element:', passwall2ProxiesList);
    console.log('[Passwall2] Setup: StatusText element:', passwall2StatusText);
    
    globalRefreshButtons.forEach(refreshBtn => {
      if (refreshBtn.dataset.listenerAdded) {
        console.log('[Passwall2] Skipping button - already has listener');
        return;
      }
      refreshBtn.dataset.listenerAdded = 'true';
      console.log('[Passwall2] Adding listener to refresh button');
      
      refreshBtn.addEventListener('click', async () => {
        console.log('[Passwall2] Refresh button clicked!');
        refreshBtn.disabled = true;
        refreshBtn.textContent = '🔄 Loading...';
        if (passwall2ProxiesList) {
          passwall2ProxiesList.innerHTML = '<div style="text-align: center; padding: 20px;">Connecting to router...</div>';
        }
        
        try {
          const routerConfig = getGlobalRouterConfig();
          console.log('[Passwall2] Router config:', routerConfig);
          
          console.log('[Passwall2] Sending message to background...');
          const response = await chrome.runtime.sendMessage({
            command: COMMANDS.PASSWALL2,
            action: 'list_proxies',
            config: routerConfig
          });
          
          console.log('[Passwall2] Response received:', response);
          
          console.log('[Passwall2] Checking response.success:', response.success);
          console.log('[Passwall2] Checking response.proxies:', response.proxies);
          
          if (response.success && response.proxies && response.proxies.length > 0) {
            console.log('[Passwall2] Success! Found', response.proxies.length, 'proxies');
            if (passwall2StatusText) {
              passwall2StatusText.textContent = response.service_status || 'Running';
              passwall2StatusText.style.color = response.service_status === 'running' ? '#4CAF50' : '#f44336';
            }
            if (passwall2ProxyCount) {
              passwall2ProxyCount.textContent = `${response.proxies.length} ${response.proxies.length === 1 ? 'proxy' : 'proxies'}`;
            }
            if (passwall2ProxiesList) {
              console.log('[Passwall2] Rendering proxy list...');
              passwall2ProxiesList.innerHTML = response.proxies.map(proxy => `
                <div style="padding: 14px; border-bottom: 1px solid #eee;">
                  <div style="font-weight: bold; margin-bottom: 6px;">
                    ${proxy.enabled ? '✅' : '⭕'} ${proxy.remarks || proxy.name || 'Unnamed'}
                  </div>
                  <div style="font-size: 0.9em; color: #666;">
                    <strong>Type:</strong> ${proxy.type} | <strong>Server:</strong> ${proxy.address}:${proxy.port}
                  </div>
                </div>
              `).join('');
            }
          } else {
            console.warn('[Passwall2] No proxies or error. Success:', response.success, 'Error:', response.error);
            if (passwall2ProxiesList) {
              const errorMsg = response.error ? `<div>Error: ${response.error}</div>` : '<div>No proxies found on router</div>';
              passwall2ProxiesList.innerHTML = `<div style="text-align: center; padding: 40px; color: #999;">
                <div style="font-size: 56px;">📭</div>
                ${errorMsg}
              </div>`;
            }
          }
        } catch (error) {
          console.error('[Passwall2] Exception caught:', error);
          if (passwall2ProxiesList) {
            passwall2ProxiesList.innerHTML = `<div style="text-align: center; padding: 40px; color: #f44336;">
              <div>Error: ${error.message}</div>
            </div>`;
          }
        } finally {
          console.log('[Passwall2] Finally block - restoring button');
          refreshBtn.disabled = false;
          refreshBtn.textContent = '🔄 Refresh List';
        }
      });
    });
  }

  // --- Proxy Mode Switching ---
  window.filterConfigsByProxyMode = function(mode) {
    const allConfigCards = document.querySelectorAll('.config-card');
    
    allConfigCards.forEach(card => {
      const configId = card.dataset.id;
      if (!configId) return;
      
      // Find the config type from the details
      const typeSelect = card.querySelector('.config-type-select');
      if (!typeSelect) return;
      
      const configType = typeSelect.value;
      
      if (mode === 'passwall2') {
        // In Passwall2 mode, only show Passwall2 type configs
        if (configType === 'passwall2') {
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      } else {
        // In Local mode, show everything EXCEPT Passwall2
        if (configType === 'passwall2') {
          card.style.display = 'none';
        } else {
          card.style.display = 'block';
        }
      }
    });
    
    // Update the "Add Configuration" button text based on mode
    const addConfigButton = document.getElementById('add-config-button');
    if (addConfigButton) {
      if (mode === 'passwall2') {
        addConfigButton.textContent = '+ Add Passwall2 Router Configuration';
      } else {
        addConfigButton.textContent = '+ Add Custom Configuration';
      }
    }
  };
  
  // Add event listeners for proxy mode radio buttons
  const proxyModeLocalRadio = document.getElementById('proxy-mode-local');
  const proxyModePasswall2Radio = document.getElementById('proxy-mode-passwall2');
  
  if (proxyModeLocalRadio && proxyModePasswall2Radio) {
    proxyModeLocalRadio.addEventListener('change', () => {
      if (proxyModeLocalRadio.checked) {
        window.filterConfigsByProxyMode('local');
        chrome.storage.sync.set({ proxyMode: 'local' });
      }
    });
    
    proxyModePasswall2Radio.addEventListener('change', async () => {
      if (proxyModePasswall2Radio.checked) {
        // Switch to Passwall2 mode and load proxies from router
        window.filterConfigsByProxyMode('passwall2');
        chrome.storage.sync.set({ proxyMode: 'passwall2' });
        
        // Automatically load Passwall2 proxies from router
        const passwall2RefreshBtn = document.querySelector('.passwall2-refresh-btn');
        if (passwall2RefreshBtn) {
          // Trigger a click on the refresh button to load proxies
          passwall2RefreshBtn.click();
        }
      }
    });
  }


  // --- Initial Load ---
  loadSettings();
  setupGlobalPasswall2Management();
  requestStatusUpdate();
  // Add visibility change listener for live log
  document.addEventListener('visibilitychange', handleVisibilityChange);
  // Start polling for the main log viewer
  handleVisibilityChange();
});