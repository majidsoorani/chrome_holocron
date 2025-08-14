// This file centralizes constants used across the extension
// to prevent typos and make maintenance easier.

const STORAGE_KEYS = {
  // --- Settings ---
  // --- Settings ---
  // The main list of all configured proxies
  PROXY_LIST: 'proxyList',

  // Common settings that apply globally
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  WIFI_SSIDS: 'wifiSsidList',
  GEOIP_BYPASS_ENABLED: 'geoIpBypassEnabled',
  AUTO_RECONNECT_ENABLED: 'autoReconnectEnabled',

  // --- State ---
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
};

const COMMANDS = {
  GET_STATUS: 'getStatus',
  STATUS_UPDATED: 'statusUpdated',
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  TEST_CONNECTION: 'testConnection',
  START_TUNNEL: 'startTunnel',
  STOP_TUNNEL: 'stopTunnel',
};