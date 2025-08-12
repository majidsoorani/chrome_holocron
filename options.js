// --- Constants ---
// NOTE: In a larger project, these would be in a shared file.
const STORAGE_KEYS = {
  SSH_COMMAND_ID: 'sshCommandIdentifier',
  PING_HOST: 'pingHost',
  WEB_CHECK_URL: 'webCheckUrl',
};

const COMMANDS = {
  TEST_CONNECTION: 'testConnection',
};
// --- End Constants ---

document.addEventListener('DOMContentLoaded', () => {
  const commandInput = document.getElementById('ssh-command');
  const saveButton = document.getElementById('save-button');
  const statusMessage = document.getElementById('status-message');
  const testButton = document.getElementById('test-button');
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');

  // Load the saved command identifier when the options page opens
  chrome.storage.sync.get([
      STORAGE_KEYS.SSH_COMMAND_ID,
      STORAGE_KEYS.PING_HOST,
      STORAGE_KEYS.WEB_CHECK_URL
    ], (result) => {
      commandInput.value = result[STORAGE_KEYS.SSH_COMMAND_ID] || '';
      // Set a default value if one isn't stored yet.
      pingHostInput.value = result[STORAGE_KEYS.PING_HOST] || 'youtube.com';
      webCheckUrlInput.value = result[STORAGE_KEYS.WEB_CHECK_URL] || 'https://gemini.google.com/app';
    }
  );

  // Save the command identifier when the save button is clicked
  saveButton.addEventListener('click', () => {
    const sshIdentifier = commandInput.value;
    const pingHost = pingHostInput.value;
    const webCheckUrl = webCheckUrlInput.value;
    chrome.storage.sync.set({
      [STORAGE_KEYS.SSH_COMMAND_ID]: sshIdentifier,
      [STORAGE_KEYS.PING_HOST]: pingHost,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrl
    }, () => {
      statusMessage.textContent = 'Settings saved!';
      statusMessage.className = 'success';
      setTimeout(() => {
        statusMessage.textContent = '';
        statusMessage.className = '';
      }, 1000);
    });
  });

  // Test the connection when the test button is clicked
  testButton.addEventListener('click', () => {
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
});