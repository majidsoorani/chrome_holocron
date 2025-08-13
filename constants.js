// This file centralizes constants used across the extension
// to prevent typos and make maintenance easier.

const STORAGE_KEYS = {
  // --- Settings ---
  SSH_COMMAND_ID: 'sshCommandIdentifier',
  SSH_USER: 'sshUser',
  SSH_HOST: 'sshHost',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  PORT_FORWARDS: 'portForwards',
  WIFI_SSIDS: 'wifiSsidList', // New key for Wi-Fi networks
  GEOIP_BYPASS_ENABLED: 'geoIpBypassEnabled',

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