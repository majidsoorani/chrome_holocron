document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const commandInput = document.getElementById('ssh-command');
  const pingHostInput = document.getElementById('ping-host');
  const webCheckUrlInput = document.getElementById('web-check-url');
  const sshUserInput = document.getElementById('ssh-user');
  const sshHostInput = document.getElementById('ssh-host');
  const rulesContainer = document.getElementById('port-forwarding-rules');
  const addRuleButton = document.getElementById('add-rule-button');
  const ruleTemplate = document.getElementById('port-forward-rule-template');
  const saveButton = document.getElementById('save-button');
  const testButton = document.getElementById('test-button');
  const statusMessage = document.getElementById('status-message');

  // --- Functions ---

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

  function loadSettings() {
    chrome.storage.sync.get(Object.values(STORAGE_KEYS), (result) => {
      commandInput.value = result[STORAGE_KEYS.SSH_COMMAND_ID] || 'holocron-tunnel';
      pingHostInput.value = result[STORAGE_KEYS.PING_HOST] || 'youtube.com';
      webCheckUrlInput.value = result[STORAGE_KEYS.WEB_CHECK_URL] || 'https://gemini.google.com/app';
      sshUserInput.value = result[STORAGE_KEYS.SSH_USER] || '';
      sshHostInput.value = result[STORAGE_KEYS.SSH_HOST] || '';

      rulesContainer.innerHTML = ''; // Clear existing rules
      const portForwards = result[STORAGE_KEYS.PORT_FORWARDS] || [];
      if (portForwards.length === 0) {
        // Add default rules for a new user
        createRuleElement({ type: 'D', localPort: '1031' });
        createRuleElement({ type: 'L', localPort: '5434', remoteHost: 'database.example.com', remotePort: '5432' });
      } else {
        portForwards.forEach(createRuleElement);
      }
    });
  }

  function validateSettings() {
    let isValid = true;
    const inputsToValidate = [
      commandInput,
      pingHostInput,
      webCheckUrlInput,
      sshUserInput,
      sshHostInput,
    ];

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

    const rules = [];
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
        rules.push(rule);
      }
    });

    const settings = {
      [STORAGE_KEYS.SSH_COMMAND_ID]: commandInput.value,
      [STORAGE_KEYS.PING_HOST]: pingHostInput.value,
      [STORAGE_KEYS.WEB_CHECK_URL]: webCheckUrlInput.value,
      [STORAGE_KEYS.SSH_USER]: sshUserInput.value,
      [STORAGE_KEYS.SSH_HOST]: sshHostInput.value,
      [STORAGE_KEYS.PORT_FORWARDS]: rules,
    };

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
  addRuleButton.addEventListener('click', () => createRuleElement());
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
});