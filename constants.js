export const COMMANDS = {
  GET_STATUS: 'getStatus',
  START_TUNNEL: 'startTunnel',
  STOP_TUNNEL: 'stopTunnel',
  TEST_CONNECTION: 'testConnection',
  GET_LOGS: 'getLogs',
  CLEAR_LOGS: 'clearLogs',
  GET_POPUP_STATUS: 'getPopupStatus',
  STATUS_UPDATED: 'statusUpdated',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  MANUAL_DB_UPDATE: 'manualDbUpdate',
  APPLY_WEBRTC_POLICY: 'applyWebrtcPolicy',
  SET_SYSTEM_PROXY: 'setSystemProxy',
  PASSWALL2: 'passwall2',
  LATENCIES_UPDATED: 'latenciesUpdated',
  GET_LATENCIES: 'getLatencies',
  TEST_ROUTER_CONNECTION: 'testRouterConnection',
  // ProtonVPN commands
  DISCOVER_PROTONVPN_SERVERS: 'discoverProtonVPNServers',
  GET_PROTONVPN_SERVERS: 'getProtonVPNServers',
};

export const STORAGE_KEYS = {
  // --- Core Configurations (sync) ---
  CORE_CONFIGURATIONS: 'coreConfigurations',
  WIFI_SSIDS: 'wifiSsidList',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  AUTO_RECONNECT_ENABLED: 'autoReconnectEnabled',
  AUTO_SELECT_BEST_PROXY: 'autoSelectBestProxy',
  DOCKER_AUTH_CHECK_ENABLED: 'dockerAuthCheckEnabled',

  // --- Proxy & Routing (sync) ---
  PROXY_BYPASS_RULES: 'proxyBypassRules',
  GLOBAL_GEOIP_BYPASS_ENABLED: 'globalGeoIpBypassEnabled',
  GLOBAL_GEOSITE_BYPASS_ENABLED: 'globalGeoSiteBypassEnabled',
  APPLY_PROXY_TO_SYSTEM: 'applyProxyToSystem',
  AUTO_APPLY_PROXY_ON_CONNECT: 'autoApplyProxyOnConnect',
  INCOGNITO_PROXY_CONFIG_ID: 'incognitoProxyConfigId',
  HTTP_PROXY_ENABLED: 'httpProxyEnabled',
  HTTP_PROXY_PORT: 'httpProxyPort',

  // --- Settings & Privacy (sync) ---
  WEBRTC_IP_HANDLING_POLICY: 'webRtcIpHandlingPolicy',
  OPENROUTER_API_KEY: 'openrouterApiKey',
  OPENROUTER_MODEL: 'openrouterModel',
  OPENROUTER_SYSTEM_MESSAGE: 'openrouterSystemMessage',
  
  // --- Passwall2 Global Router Settings (sync) ---
  ROUTER_IP: 'routerIp',
  ROUTER_SSH_USER: 'routerSshUser',
  ROUTER_SSH_PORT: 'routerSshPort',
  ROUTER_SSH_PASSWORD: 'routerSshPassword',
  ROUTER_SSH_KEY_PATH: 'routerSshKeyPath',

  // --- Runtime State (local) ---
  CURRENTLY_ACTIVE_CONFIG_ID: 'currentlyActiveConfigId',
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
  LATENCY_HISTORY: 'latencyHistory',
  GEOIP_RANGES: 'geoipRanges',
  GEOIP_LAST_UPDATE: 'geoipLastUpdate',
  GEOSITE_DOMAINS: 'geositeDomains',
  GEOSITE_LAST_UPDATE: 'geositeLastUpdate',
  PROTONVPN_DISCOVERED_SERVERS: 'protonvpnDiscoveredServers',
  PROTONVPN_LAST_DISCOVERY: 'protonvpnLastDiscovery',

  // --- Legacy Keys (for migration) ---
  LEGACY_SSH_USER: 'sshUser',
  LEGACY_SSH_HOST: 'sshHost',
  LEGACY_SSH_REMOTE_COMMAND: 'sshRemoteCommand',
  LEGACY_PORT_FORWARDS: 'portForwardingRules',
  LEGACY_ACTIVE_CONFIGURATION_ID: 'activeConfigurationId',
};