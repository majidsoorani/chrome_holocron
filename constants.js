// Holocron Shared Constants

const STORAGE_KEYS = {
  // --- Sync settings (user-configured) ---
  SSH_COMMAND_ID: 'sshCommandIdentifier',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
  SSH_USER: 'sshUser',
  SSH_HOST: 'sshHost',
  PORT_FORWARDS: 'portForwards',

  // Local state (managed by extension)
  IS_PROXY_MANAGED: 'isProxyManagedByHolocron',
  ORIGINAL_PROXY: 'originalProxySettings',
};

const COMMANDS = {
  // To native host
  GET_STATUS: 'getStatus',

  // From UI/other scripts to background script
  GET_POPUP_STATUS: 'getPopupStatus',
  SET_BROWSER_PROXY: 'setBrowserProxy',
  CLEAR_BROWSER_PROXY: 'clearBrowserProxy',
  TEST_CONNECTION: 'testConnection',
  START_TUNNEL: 'startTunnel',
  STOP_TUNNEL: 'stopTunnel',

  // From background script to UI
  STATUS_UPDATED: 'statusUpdated',
};

// Note: This file should be included via <script> tag in options.html and popup.html,
// and imported in the background service worker manifest.