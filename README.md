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

- **macOS**: Required for the `wdutil` command used to detect the current Wi-Fi network SSID.
- **Google Chrome** (or other Chromium-based browsers, with path adjustments).
- **Python 3.x**.
- **SSH client** and configured SSH keys for your target host.

## Installation

An installation script is provided to automate the setup process.

1.  **Clone the Repository**
    ```bash
    git clone <your-repo-url>
    cd chrome_holocron
    ```

2.  **Run the Installer**
    This script will install Python dependencies, set script permissions, and configure the native messaging host for Chrome.
    ```bash
    chmod +x install.sh
    ./install.sh
    ```

3.  **Load the Extension in Chrome**
    The installer will guide you through this, but the steps are:
    - Open Chrome and navigate to `chrome://extensions`.
    - Enable **Developer mode** in the top-right corner.
    - Click **Load unpacked**.
    - Select the `chrome_holocron` directory (the one containing `manifest.json`).

4.  **Link the Native Host to the Extension**
    - After loading the extension, find its card on the `chrome://extensions` page and copy the **ID** (it's a long string of letters).
    - Open the native host manifest file. The path was printed by the install script, but it's typically: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.holocron.native_host.json`.
    - In that file, replace `YOUR_EXTENSION_ID_HERE` with the ID you copied.
    - Save the file and **restart Chrome**.

## Configuration

1.  **Set Work Wi-Fi Networks**
    - Edit the script: `backends/sh/work_connect.sh`.
    - Add your work Wi-Fi network names (SSIDs) to the `WORK_SSIDS` array.
    ```sh
    WORK_SSIDS=("MyWorkWifi" "Another-Work-Network")
    ```

2.  **Configure Extension Options**
    - Right-click the Holocron icon in your Chrome toolbar and select **Options**.
    - Fill in all the required fields:
        - **SSH Details**: Your username and the server's hostname.
        - **Health Checks**: The host to ping and the URL for the web check.
        - **Port Forwarding**: Define your local, remote, or dynamic (`-D`) port forwards. A default SOCKS proxy on port 1031 is included.
    - Click **Save Settings**.

3.  **Enable Passwordless Sudo (Recommended)**
    The script needs `sudo` to check your Wi-Fi network. To avoid being prompted for a password, you can add a `sudoers` rule. The application will guide you if this is needed, but you can do it proactively.
    - Run `sudo visudo` in your terminal.
    - Add the following line at the end of the file, replacing `your_username` with your actual macOS username:
    ```
    your_username ALL=(ALL) NOPASSWD: /usr/bin/wdutil
    ```
    - Save the file (in `vi`, press `Esc` then type `:wq!` and `Enter`).

## Troubleshooting

- **"Native host has exited" or "Failed to connect to native host"**: This usually means the Python script failed. Check the log file for errors at `backends/log/holocron_native_host.log`.
- **Extension icon is always red**:
    - Ensure the SSH Command Identifier in the options matches what's used in your scripts.
    - Use the "Test Connection" button in the options page to get a detailed status.
    - Verify you can manually `ssh` to the host from your terminal.
- **Connect button shows "Sudo password required"**: You need to set up passwordless sudo as described in the configuration steps.