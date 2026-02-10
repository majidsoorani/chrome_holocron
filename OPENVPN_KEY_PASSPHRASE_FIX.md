# OpenVPN Private Key Passphrase Support

## Error That Occurred

When attempting to connect to an OpenVPN server with an encrypted private key, the connection failed with:

```
neither stdin nor stderr are a tty device and you have neither a controlling tty nor systemd - 
can't ask for 'Enter Auth Password:'. If you used --daemon, you need to use --askpass to make 
passphrase-protected keys work, and you can not use --auth-nocache.
```

## Root Cause

The OpenVPN configuration file (`.ovpn`) contained an encrypted private key that required a passphrase. When OpenVPN runs without a terminal (TTY), it cannot interactively prompt for the passphrase. The existing implementation only handled username/password authentication via `--auth-user-pass`, but did not handle private key passphrases via `--askpass`.

## Solution Implemented

### 1. Backend Changes (`holocron_native_host.py`)

Modified the OpenVPN connection logic to:
- Detect if the OVPN content contains an encrypted private key (looks for `BEGIN ENCRYPTED PRIVATE KEY` or `BEGIN RSA PRIVATE KEY`)
- Accept a new configuration parameter `ovpnKeyPassphrase`
- Use `--askpass` flag instead of `--auth-user-pass` when dealing with encrypted keys
- Write the passphrase to the auth file for non-interactive use

```python
# Check if the ovpn content contains an encrypted private key
ovpn_key_passphrase = config.get("ovpnKeyPassphrase")
has_encrypted_key = "BEGIN ENCRYPTED PRIVATE KEY" in ovpn_content or "BEGIN RSA PRIVATE KEY" in ovpn_content

# Use --askpass for encrypted keys, --auth-user-pass for username/password auth
if has_encrypted_key and ovpn_key_passphrase:
    cmd_list.extend(["--askpass", str(auth_file)])
elif ovpn_user is not None and ovpn_pass is not None:
    cmd_list.extend(["--auth-user-pass", str(auth_file)])
```

### 2. Frontend Changes

#### `options.html`
Added a new password field for the private key passphrase:

```html
<div class="form-group ovpn-key-passphrase-container" style="display: none;">
    <label>Private Key Passphrase</label>
    <input type="password" class="ovpn-key-passphrase" autocomplete="off" 
           placeholder="Leave empty if key is not encrypted">
    <small>Only needed if your .ovpn file contains an encrypted private key</small>
</div>
```

#### `options.js`
- Added references to the new passphrase field elements
- Modified `checkOvpnForAuth()` to detect encrypted keys and show/hide the passphrase field
- Added `ovpnKeyPassphrase` to config save/load logic
- Added passphrase field to input event listeners for auto-save

```javascript
const checkOvpnForAuth = (content) => {
    const needsAuth = /^\s*auth-user-pass\s*$/m.test(content || '');
    const hasEncryptedKey = /BEGIN ENCRYPTED PRIVATE KEY|BEGIN RSA PRIVATE KEY/.test(content || '');
    
    ovpnAuthContainer.style.display = needsAuth ? 'flex' : 'none';
    ovpnKeyPassphraseContainer.style.display = hasEncryptedKey ? 'block' : 'none';
    
    return needsAuth || hasEncryptedKey;
};
```

## How to Use

1. **Upload your .ovpn file** as usual in the extension settings
2. **If the file contains an encrypted private key**, a "Private Key Passphrase" field will automatically appear
3. **Enter your passphrase** in that field
4. **Save** and test the connection

The passphrase field only appears when needed (when an encrypted key is detected in the OVPN file).

## Technical Details

### OpenVPN Authentication Methods

1. **Username/Password (`--auth-user-pass`)**: Used for server authentication credentials
2. **Private Key Passphrase (`--askpass`)**: Used to decrypt the client's private key file

These are separate authentication mechanisms and can both be required for the same connection.

### Detection Logic

The code checks for the following patterns in the OVPN content:
- `BEGIN ENCRYPTED PRIVATE KEY` - Modern PEM format
- `BEGIN RSA PRIVATE KEY` - Legacy RSA key format (may or may not be encrypted)

### Security

- Passphrases are stored in Chrome's sync storage (encrypted by Chrome)
- Temporary auth files are created with `0o600` permissions (owner read/write only)
- Auth files are cleaned up after connection attempts

## Testing

To test this fix:
1. Reload the extension
2. Open the extension options
3. Create a new OpenVPN configuration
4. Upload an .ovpn file with an encrypted private key
5. Enter the passphrase when prompted
6. Test the connection

## Files Modified

1. `backends/python/holocron_native_host.py` - Backend OpenVPN connection logic
2. `options.html` - Added passphrase input field
3. `options.js` - Added passphrase field handling and detection logic
