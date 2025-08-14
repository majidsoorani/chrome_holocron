# Holocron Connection Manager

![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple)

Holocron is a Google Chrome extension designed to seamlessly manage multiple proxy connections, including SSH, V2Ray, and Shadowsocks. It provides real-time connection and latency status, one-click browser proxy configuration, and a simple interface for importing and managing your proxy list.

## Features

- **Multi-Protocol Support**: Natively manages SSH, V2Ray (VLESS), and Shadowsocks connections.
- **Easy Configuration Import**: Quickly import proxy configurations by pasting standard URI links (`vless://`, `ss://`).
- **Manual SSH Configuration**: A dedicated UI for manually adding and editing complex SSH tunnels with multiple port-forwards.
- **Centralized Proxy List**: All your configurations are managed in a simple, clean list on the options page.
- **One-Click Activation**: Activate any proxy from the list with a single click.
- **Real-time Status**: The extension icon and popup provide immediate feedback on the active connection's status.
- **Latency Monitoring**:
    - **Web Check**: Measures latency of a full HTTPS request to a specified URL through the active tunnel.
    - **TCP Ping**: Measures raw TCP socket connection latency to a specified host.
    - **Dynamic Icon**: The extension icon changes color based on latency, giving you an at-a-glance view of connection quality.
- **Browser Proxy Management**:
    - Applies a SOCKS5 proxy with one click to route your browser traffic through the active connection.
    - Includes a smart PAC script to bypass the proxy for local addresses and specific domains (e.g., `*.ir`).
    - Reverts to your original proxy settings with a single click.

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
      +-------------------+-----------------+
      |                   |                 |
      v                   v                 v
  work_connect.sh       v2ray           ss-local
      |
      v
     ssh
```

- **UI (HTML/CSS/JS)**: The popup and options pages that you interact with. The options page allows you to manage a list of proxy configurations.
- **Background Script**: The extension's core logic. It orchestrates status checks, manages the active proxy state, and communicates with the native host.
- **Native Host (Python)**: A flexible Python script that acts as a bridge between the browser and your local system. It can generate configuration files and manage processes for SSH, V2Ray, and Shadowsocks.
- **Control Scripts/Executables**: The native host executes the appropriate command-line tool (`ssh`, `v2ray`, `ss-local`) based on the active proxy's type.

## Prerequisites

- **macOS**: Required for the `wdutil` command used to detect the current Wi-Fi network SSID for the SSH auto-connect feature. Manual controls will work on other Unix-like systems.
- **Google Chrome** (or other Chromium-based browsers, with path adjustments).
- **Python 3.x**.
- **Required Proxy Clients**:
    - **SSH**: A standard SSH client is required (`/usr/bin/ssh`).
    - **V2Ray**: The `v2ray` executable must be in your system's PATH.
    - **Shadowsocks**: The `ss-local` executable must be in your system's PATH (e.g., from `shadowsocks-libev`).

## Installation

An installation script is provided to automate the setup process.

1.  **Clone the Repository**
    ```bash
    git clone <your-repo-url>
    cd holocron-extension
    ```

2.  **Run the Installer**
    This script will check for dependencies, create a Python virtual environment, install packages, set script permissions, and configure the native messaging host for Chrome.
    ```bash
    chmod +x install.sh
    ./install.sh
    ```
    The script will warn you if any optional proxy clients (like `v2ray` or `ss-local`) are missing. It will then pause and ask you to complete the next steps.

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

## Configuration

The extension is managed through the Options page. Right-click the Holocron icon in your Chrome toolbar and select **Options**.

1.  **Importing Proxies**
    - Click the **Import from URL(s)** button.
    - A dialog will appear. Paste one or more proxy URIs (one per line).
    - Supported formats currently include `vless://` and `ss://`.
    - Click "Import". The proxies will be added to your list.

2.  **Adding an SSH Tunnel Manually**
    - Click the **Add SSH Manually** button.
    - A dialog will appear. Fill in the required SSH details, including a unique Process Identifier, user, host, and any port forwarding rules.
    - Click "Save SSH Config".

3.  **Managing Proxies**
    - The main view shows your list of configured proxies.
    - **Activate**: Click the "Activate" button on any proxy to make it the active connection. The extension will automatically try to connect to it.
    - **Edit**: Click "Edit" to modify a proxy's configuration (currently only supported for SSH).
    - **Delete**: Click "Delete" to remove a proxy from the list.

4.  **Global Settings**
    - You can configure global settings like the health check URLs that apply to all connections.

## Security Considerations

**Security is paramount.** This system is designed to interact with sensitive infrastructure. Adhere to the following principles:

- **Never share logs or screenshots without redacting sensitive information.**
- **Use a secrets manager for production credentials.**
- **The import feature will parse credentials from URIs.** Be mindful of where you source these URIs from.

## Troubleshooting

- **"Native host has exited"**: This usually means the Python script failed. Check the log file for errors at `backends/log/holocron_native_host.log`. The last few lines usually contain a detailed Python error message.
- **Connection Fails**: If a specific proxy type fails to connect, ensure the corresponding client (`v2ray`, `ss-local`) is installed correctly and accessible in your system's PATH. Check the Python script log for any errors from the subprocess.
- **SSH Connection Fails**: Verify your SSH keys are set up correctly. For automatic Wi-Fi based connection, ensure you have configured passwordless sudo for `wdutil` if required.