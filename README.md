# Holocron SSH Tunnel Manager

![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple)

Holocron is a Google Chrome extension designed to seamlessly manage an SSH tunnel connection. It automatically connects when you're on a designated Wi-Fi network, provides real-time connection and latency status, and offers one-click browser proxy configuration.

## Features

- **Automatic Tunneling**: Connects the SSH tunnel automatically when you join a pre-configured work Wi-Fi network.
- **Real-time Status**: The extension icon and popup provide immediate feedback on the tunnel's status (Connected/Disconnected).
- **Latency Monitoring**:
    - **Web Check**: Measures latency of a full HTTPS request to a specified URL through the tunnel.
    - **TCP Ping**: Measures raw TCP socket connection latency to a specified host.
    - **Dynamic Icon**: The extension icon changes color and shape based on latency, giving you an at-a-glance view of connection quality.
- **Manual Controls**: Easily connect or disconnect the tunnel manually from the extension popup.
- **Browser Proxy Management**:
    - Apply a SOCKS5 proxy with one click to route your browser traffic through the tunnel.
    - Includes a smart PAC script to bypass the proxy for local addresses and specific domains (e.g., `*.ir`).
    - Revert to your original proxy settings with a single click.
- **Highly Configurable**: An intuitive options page allows you to set:
    - SSH connection details (user, host).
    - Custom port forwarding rules (local, remote, and dynamic/SOCKS).
    - Hosts and URLs for latency checks.

- **AI-Powered Suggestions**: Utilizes an external AI model (e.g., from GitHub) to suggest proxy bypass rules based on natural language input.
## How It Works (Architecture)

Holocron uses a combination of a Chrome extension and a local native application to interact with your system.

```
  UI (Popup/Options)
        |
        v
Background Script (background.js)
        |
        v (Native Messaging)
Native Host (holocron_native_host.py)
        |
        v (Subprocess)
Control Script (work_connect.sh)
        |
        v
      ssh
```

- **UI (HTML/CSS/JS)**: The popup and options pages that you interact with.
- **Background Script**: The extension's core logic. It orchestrates status checks, manages state, and communicates with the native host.
- **Native Host (Python)**: A small Python script that acts as a bridge between the browser and your local system. It can check processes and execute shell scripts.
- **Control Script (Bash)**: A shell script that handles the logic of checking the Wi-Fi network (`wdutil`) and starting/stopping the `ssh` process.

## Prerequisites

- **macOS**: Required for the `wdutil` command used to detect the current Wi-Fi network SSID. The automatic connection feature is currently macOS-only. Manual controls will work on other Unix-like systems.
- **Google Chrome** (or other Chromium-based browsers, with path adjustments).
- **Python 3.x**.
- **SSH client** and configured SSH keys for your target host.
- **OpenVPN client** (if you plan to use OpenVPN configurations). The command-line tool must be installed and available in your system's PATH. The recommended way to install it on macOS is via [Homebrew](https://brew.sh/): `brew install openvpn`.

## Installation

An installation script is provided to automate the setup process.

1.  **Clone the Repository**
    ```bash
    git clone <your-repo-url>
    cd chrome_holocron
    ```

2.  **Run the Installer**
    This script will create a Python virtual environment, install dependencies, set script permissions, and configure the native messaging host for Chrome.
    ```bash
    chmod +x install.sh
    ./install.sh
    ```
    **The script will pause and ask you to complete the next steps.**

3.  **Load the Extension in Chrome**
    - Open Chrome and navigate to `chrome://extensions`.
    - Enable **Developer mode** in the top-right corner.
    - Click **Load unpacked**.
    - Select the `chrome_holocron` directory (the one containing `manifest.json`).

4.  **Link the Native Host to the Extension**
    - After loading the extension, copy its **ID** (a long string of letters).
    - Paste this ID back into the terminal where the `install.sh` script is waiting.
    - The script will automatically configure the connection.
    - **Restart Chrome completely** for the changes to take effect.

4.  **Enable Passwordless Sudo (Required for macOS)**
    On macOS, the extension needs `sudo` for two operations:
    - To check your Wi-Fi network with `wdutil` (for automatic connection).
    - To create a network interface for OpenVPN connections.

    To avoid being prompted for a password, you must add rules to the `sudoers` file.
    - Run `sudo visudo` in your terminal.
    - Add the following line at the end of the file, replacing `your_username` with your actual macOS username and `/path/to/openvpn` with the output of `which openvpn`:
    ```
    your_username ALL=(ALL) NOPASSWD: /usr/bin/wdutil, /path/to/openvpn
    ```
    - **Example**: For a standard Homebrew installation on Apple Silicon, this would be `/opt/homebrew/sbin/openvpn`.
    - Save the file (in `vi`, press `Esc` then type `:wq!` and `Enter`).

## Configuration

1.  **Configure Extension Options**
    - Right-click the Holocron icon in your Chrome toolbar and select **Options**.
    - Fill in the required fields for your desired connection types (SSH, OpenVPN, etc.).
    - To use the AI rule suggestion feature, navigate to the "Settings & Logs" tab and enter your API key for the desired service (e.g., GitHub Models).
    - Click **Save Settings**.

## Security Considerations

**Security is paramount.** This system is designed to interact with sensitive infrastructure. Adhere to the following principles:

- **Never share logs or screenshots without redacting sensitive information.** Logs can contain real IP addresses and hostnames, which is a security risk. Always replace sensitive data with placeholders like `<redacted>` or `bastion.example.com` before sharing.
- **Use a secrets manager for production credentials.** While this tool uses your local SSH configuration, for any team-based or production environment, SSH keys and other secrets should be managed through a proper secrets management tool.
- **The default configuration uses safe placeholders.** The initial values in the options page use non-real hostnames like `database.example.com`. This is intentional to protect your infrastructure details.

## Troubleshooting

- **"Native host has exited" or "Failed to connect to native host"**: This usually means the Python script failed. The first step is to check the log file for errors at `backends/log/holocron_native_host.log`. The last few lines will usually contain a detailed Python error message (a "traceback") that explains why the script stopped. The log file is automatically rotated when it reaches 1MB in size, so it will not grow indefinitely.
- **"Access to the specified native messaging host is forbidden"**: This is a security error from Chrome. It means the extension's ID has changed and no longer matches the one authorized in the native host manifest. This commonly happens when you reload the unpacked extension.
    - **Solution**: Run the `./fix_extension_id.sh` script. It will prompt you for the new extension ID from `chrome://extensions` and update the configuration file. You must restart Chrome after running it.
- **Extension icon is always red**:
    - Use the "Test Connection" button in the options page to get a detailed status.
    - Verify you can manually `ssh` to the host from your terminal.
- **Popup is stuck on "Connecting..." but the tunnel is already running**: This could happen if the extension's state gets out of sync. The periodic status check (every minute) or clicking the connect button again will force a refresh. The changes implemented in this version make this scenario much less likely by handling the "already running" state more intelligently.
- **Connection fails with "Permission denied (publickey)" or similar SSH errors**: This error, which may appear in the popup after a connection attempt, means the SSH connection itself is failing. Verify that your SSH keys are correctly set up in `~/.ssh/` and that your public key has been added to the `~/.ssh/authorized_keys` file on the remote server (`bastion.example.com`).
- **Connect button shows "Sudo password required"**: You need to set up passwordless sudo as described in the configuration steps.