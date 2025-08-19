#!/bin/bash

# This script automates the installation of the Holocron native messaging host.

set -e # Exit immediately if a command exits with a non-zero status.

echo "🚀 Starting Holocron Native Host Installation..."

# --- Configuration ---
# The name of the native host, must match the manifest.json and background.js
NATIVE_HOST_NAME="com.holocron.native_host"
# The directory where Chrome looks for native messaging host manifests
# This path is for Google Chrome. Modify for other Chromium browsers if needed.
CHROME_NATIVE_HOSTS_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"

# --- Get Absolute Paths ---
# Get the absolute path to the directory containing this script
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT="$SCRIPT_DIR" # Assuming install.sh is in the project root

LAUNCHER_SCRIPT_PATH="$PROJECT_ROOT/backends/sh/holocron_native_host_launcher.sh"
PYTHON_SCRIPT_PATH="$PROJECT_ROOT/backends/python/holocron_native_host.py"
MANIFEST_TEMPLATE_PATH="$PROJECT_ROOT/com.holocron.native_host.json.template"
FINAL_MANIFEST_PATH="$CHROME_NATIVE_HOSTS_DIR/$NATIVE_HOST_NAME.json"
REQUIREMENTS_PATH="$PROJECT_ROOT/requirements.txt"

# --- Pre-flight Checks ---
echo "🔎 Checking for Python interpreter..."
PYTHON_EXEC=$(which python3)
if [ -z "$PYTHON_EXEC" ] || [ ! -x "$PYTHON_EXEC" ]; then
    echo "❌ Error: python3 not found in your PATH. Please install Python 3."
    exit 1
fi
echo "✅ Found system Python 3 at: $PYTHON_EXEC"

echo "🔎 Checking for OpenVPN client (optional)..."
if ! command -v openvpn &> /dev/null; then
    echo "⚠️  Warning: The 'openvpn' command-line tool was not found in your PATH."
    echo "   To use OpenVPN configurations, you must install the official client."
    echo "   On macOS, the recommended way is via Homebrew: brew install openvpn"
else
    echo "✅ Found OpenVPN client."
fi

echo "🔎 Checking for Xray-core (optional)..."
XRAY_EXEC_PATH=""
if command -v xray &> /dev/null; then
    XRAY_EXEC_PATH=$(command -v xray)
else
    # Check common non-PATH locations for GUI apps
    for path in "/opt/homebrew/bin/xray" "/usr/local/bin/xray"; do
        if [ -x "$path" ]; then
            XRAY_EXEC_PATH="$path"
            break
        fi
    done
fi

if [ -z "$XRAY_EXEC_PATH" ]; then
    echo "⚠️  Warning: The 'xray' command-line tool was not found in your PATH or standard Homebrew locations."
    echo "   To use V2Ray configurations, you must install Xray-core."
    echo "   On macOS, the recommended way is via Homebrew: brew install xray"
else
    echo "✅ Found Xray-core at: $XRAY_EXEC_PATH"
fi

echo "🔎 Checking for required passwordless sudo configuration..."

missing_sudo_rules=()
required_paths=()

# Check for wdutil (for Wi-Fi based auto-connect)
if ! sudo -n -l /usr/bin/wdutil &> /dev/null; then
    missing_sudo_rules+=("wdutil (for automatic connection on Wi-Fi change)")
    required_paths+=("/usr/bin/wdutil")
fi

# Check for openvpn
OPENVPN_EXEC=$(which openvpn)
if [ -n "$OPENVPN_EXEC" ]; then
    if ! sudo -n -l "$OPENVPN_EXEC" &> /dev/null; then
        missing_sudo_rules+=("openvpn (for starting VPN connections)")
        required_paths+=("$OPENVPN_EXEC")
    fi
fi

if [ ${#missing_sudo_rules[@]} -gt 0 ]; then
    echo "
🔴 ACTION REQUIRED: Passwordless Sudo Configuration

The extension needs permission to run certain commands without a password prompt.
This is required for:
"
    for rule_desc in "${missing_sudo_rules[@]}"; do
        echo "  - ${rule_desc}"
    done
    echo "
Please open a new terminal and run 'sudo visudo' to edit the sudoers file.
Add the following line to the VERY END of the file, then save and exit.

    $(whoami) ALL=(ALL) NOPASSWD: $(IFS=,; echo "${required_paths[*]}")

"
    read -r -p "Press [Enter] after you have saved the sudoers file to continue the installation..."
    echo "✅ Continuing installation. Thank you."
else
    echo "✅ Passwordless sudo configuration is correct."
fi

# --- Step 1: Setup Python Virtual Environment ---
echo "🔧 Setting up Python virtual environment..."
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_EXEC" -m venv "$VENV_DIR"
    echo "✅ Virtual environment created at: $VENV_DIR"
else
    echo "✅ Virtual environment already exists."
fi
# From now on, use the Python interpreter from the virtual environment
PYTHON_EXEC="$VENV_DIR/bin/python"

echo "🔎 Checking for required Python packages..."
if [ -f "$REQUIREMENTS_PATH" ]; then
    echo "   Installing/updating packages from requirements.txt..."
    if ! "$PYTHON_EXEC" -m pip install -r "$REQUIREMENTS_PATH"; then
        echo "❌ Error: Failed to install Python packages into the virtual environment."
        exit 1
    fi
    echo "✅ Python packages are up to date in the virtual environment."
else
    echo "⚠️ Warning: requirements.txt not found. Skipping package check."
fi

# --- Step 1: Make scripts executable ---
echo "🔧 Setting script permissions..."
chmod +x "$LAUNCHER_SCRIPT_PATH"
chmod +x "$PROJECT_ROOT/backends/sh/work_connect.sh"
echo "✅ Scripts are now executable."

# --- Step 3: Update paths in the launcher script ---
echo "✍️  Updating paths in launcher script..."
sed -i.bak "s|__PYTHON_EXEC_PATH__|$PYTHON_EXEC|" "$LAUNCHER_SCRIPT_PATH"
sed -i.bak "s|__PYTHON_SCRIPT_PATH__|$PYTHON_SCRIPT_PATH|" "$LAUNCHER_SCRIPT_PATH"
rm "${LAUNCHER_SCRIPT_PATH}.bak"
echo "✅ Launcher script configured."

# --- Step 4: Create and install the native host manifest ---
echo "✍️  Creating native host manifest..."
sed "s|__LAUNCHER_PATH__|$LAUNCHER_SCRIPT_PATH|" "$MANIFEST_TEMPLATE_PATH" > "/tmp/$NATIVE_HOST_NAME.json"
echo "✅ Manifest created."

echo "📦 Installing manifest to Chrome's directory..."
mkdir -p "$CHROME_NATIVE_HOSTS_DIR"
mv "/tmp/$NATIVE_HOST_NAME.json" "$FINAL_MANIFEST_PATH"
echo "✅ Manifest installed at: $FINAL_MANIFEST_PATH"

# --- Final Step: Interactive Extension ID Configuration ---
echo ""
echo "🎉 Installation Complete!"
echo ""
echo "🔴 ACTION REQUIRED: Please follow these steps carefully 🔴"
echo "1. Open Chrome and go to 'chrome://extensions'."
echo "2. Enable 'Developer mode' in the top right."
echo "3. Click 'Load unpacked' and select the '$PROJECT_ROOT' directory."
echo "4. The 'Holocron Status' extension will appear. Find its 'ID' (it is a long string of letters)."
echo ""
echo "IMPORTANT: If you ever 'Reload' the extension from the extensions page, Chrome may"
echo "assign it a NEW ID. If this happens, the native host will stop working. You can"
echo "run the 'fix_extension_id.sh' script to quickly update it without a full reinstall."

# -p for prompt, -r to prevent backslash interpretation
read -r -p "5. Paste the Extension ID here and press [Enter]: " extension_id

if [ -z "$extension_id" ]; then
    echo "❌ No Extension ID provided. Please run the script again."
    exit 1
fi

echo "✍️  Updating manifest with your Extension ID..."

# This makes the script idempotent. It first tries to replace the placeholder.
# If the placeholder isn't found (e.g., on a re-run), it uses a more robust
# regex to replace whatever 32-character extension ID is already there. This
# is the same logic used by the fix_extension_id.sh script.
if grep -q "YOUR_EXTENSION_ID_HERE" "$FINAL_MANIFEST_PATH"; then
    sed -i.bak "s|YOUR_EXTENSION_ID_HERE|$extension_id|" "$FINAL_MANIFEST_PATH"
else
    sed -i.bak "s#\(chrome-extension://\)[a-z]\{32\}\(/\"\)#\1${extension_id}\2#" "$FINAL_MANIFEST_PATH"
fi
rm -f "${FINAL_MANIFEST_PATH}.bak"

echo "✅ Manifest updated successfully!"
echo "🔒 The native host is now locked to your specific extension instance."
echo ""
echo "🚀 FINAL STEP: Please RESTART CHROME completely for the changes to take effect."
echo "   (Cmd+Q on macOS, or right-click the dock icon and choose 'Quit')."