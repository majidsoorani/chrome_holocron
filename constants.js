// This file centralizes constants used across the extension
// to prevent typos and make maintenance easier.

const STORAGE_KEYS = {
  // --- General Settings ---
  CONNECTION_TYPE: 'connectionType', // 'ssh' or 'openvpn'

  // --- SSH Settings ---
  SSH_COMMAND_ID: 'sshCommandIdentifier',
  SSH_USER: 'sshUser',
  SSH_HOST: 'sshHost',
  PORT_FORWARDS: 'portForwards',
  WIFI_SSIDS: 'wifiSsidList',

  // --- OpenVPN Settings ---
  OVPN_CONFIGS: 'ovpnConfigs', // Stores { name, content, requires_auth }
  ACTIVE_OVPN_CONFIG_NAME: 'activeOvpnConfigName',
  OVPN_USER: 'ovpnUser',
  OVPN_PASS: 'ovpnPass',

  // --- Shared Settings ---
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  GEOIP_BYPASS_ENABLED: 'geoIpBypassEnabled',
  AUTO_RECONNECT_ENABLED: 'autoReconnectEnabled',


  // --- State ---
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
};

const COMMANDS = {
  // --- General Commands ---
  GET_STATUS: 'getStatus',
  STATUS_UPDATED: 'statusUpdated',
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  TEST_CONNECTION: 'testConnection',

  // --- Tunnel Commands ---
  START_TUNNEL: 'startTunnel', // This will become a generic 'start'
  STOP_TUNNEL: 'stopTunnel',   // This will become a generic 'stop'
};