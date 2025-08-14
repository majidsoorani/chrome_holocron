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

echo "🔎 Checking for V2Ray (optional)..."
if ! command -v v2ray &> /dev/null; then
    echo "⚠️ Warning: 'v2ray' command not found in your PATH."
    echo "   The V2Ray functionality will not work until V2Ray is installed and accessible."
else
    echo "✅ Found V2Ray executable."
fi

echo "🔎 Checking for Shadowsocks (optional)..."
if ! command -v ss-local &> /dev/null; then
    echo "⚠️ Warning: 'ss-local' command not found in your PATH."
    echo "   The Shadowsocks functionality will not work until a client (like shadowsocks-libev) is installed."
else
    echo "✅ Found ss-local executable."
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

# -p for prompt, -r to prevent backslash interpretation
read -r -p "5. Paste the Extension ID here and press [Enter]: " extension_id

if [ -z "$extension_id" ]; then
    echo "❌ No Extension ID provided. Please run the script again."
    exit 1
fi

echo "✍️  Updating manifest with your Extension ID..."
sed -i.bak "s|YOUR_EXTENSION_ID_HERE|$extension_id|" "$FINAL_MANIFEST_PATH"
rm "${FINAL_MANIFEST_PATH}.bak"

echo "✅ Manifest updated successfully!"
echo "🔒 The native host is now locked to your specific extension instance."
echo ""
echo "🚀 FINAL STEP: Please RESTART CHROME completely for the changes to take effect."
echo "   (Cmd+Q on macOS, or right-click the dock icon and choose 'Quit')."