// This file centralizes constants used across the extension
// to prevent typos and make maintenance easier.

export const STORAGE_KEYS = {
  // --- Settings (stored in chrome.storage.sync) ---
  CORE_CONFIGURATIONS: 'coreConfigurations',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  WIFI_SSIDS: 'wifiSsidList',
  AUTO_RECONNECT_ENABLED: 'autoReconnectEnabled',
  // New Global Proxy Settings
  PROXY_BYPASS_RULES: 'proxyBypassRules',
  GLOBAL_GEOIP_BYPASS_ENABLED: 'globalGeoIpBypassEnabled',
  GLOBAL_GEOSITE_BYPASS_ENABLED: 'globalGeoSiteBypassEnabled',
  INCOGNITO_PROXY_CONFIG_ID: 'incognitoProxyConfigId',
  WEBRTC_IP_HANDLING_POLICY: 'webRtcIpHandlingPolicy',
  OPENROUTER_API_KEY: 'openrouter_api_key',
  OPENROUTER_MODEL: 'openrouter_model',
  OPENROUTER_SYSTEM_MESSAGE: 'openrouter_system_message',

  // --- Legacy Keys (for migration) ---
  LEGACY_SSH_COMMAND_ID: 'sshCommandIdentifier',
  LEGACY_SSH_USER: 'sshUser',
  LEGACY_SSH_HOST: 'sshHost',
  LEGACY_SSH_REMOTE_COMMAND: 'sshRemoteCommand',
  LEGACY_PORT_FORWARDS: 'portForwards',
  LEGACY_ACTIVE_CONFIGURATION_ID: 'activeConfigurationId',

  // --- State (stored in chrome.storage.local) ---
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
  CURRENTLY_ACTIVE_CONFIG_ID: 'currentlyActiveConfigId',
  GEOIP_RANGES: 'geoIpRanges',
  GEOIP_LAST_UPDATE: 'geoIpLastUpdate',
  GEOSITE_DOMAINS: 'geoSiteDomains',
  GEOSITE_LAST_UPDATE: 'geoSiteLastUpdate',
  LATENCY_HISTORY: 'latencyHistory',
};

export const COMMANDS = {
  GET_STATUS: 'getStatus',
  STATUS_UPDATED: 'statusUpdated',
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  TEST_CONNECTION: 'testConnection',
  START_TUNNEL: 'startTunnel',
  STOP_TUNNEL: 'stopTunnel',
  MANUAL_DB_UPDATE: 'manualDbUpdate',
  GET_LOGS: 'getLogs',
  CLEAR_LOGS: 'clearLogs',
  APPLY_WEBRTC_POLICY: 'applyWebRtcPolicy',
};