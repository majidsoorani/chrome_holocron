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
if [ -z "$PYTHON_EXEC" ]; then
    echo "❌ Error: python3 not found in your PATH. Please install Python 3."
    exit 1
fi
echo "✅ Found Python 3 at: $PYTHON_EXEC"

echo "🔎 Checking for required Python packages..."
if [ -f "$REQUIREMENTS_PATH" ]; then
    if ! "$PYTHON_EXEC" -m pip show -r "$REQUIREMENTS_PATH" &> /dev/null; then
        echo "⚠️ Some Python packages are missing."
        echo "   Attempting to install them using pip..."
        if ! "$PYTHON_EXEC" -m pip install -r "$REQUIREMENTS_PATH"; then
            echo "❌ Error: Failed to install Python packages. Please install them manually from requirements.txt"
            exit 1
        fi
    fi
    echo "✅ All required Python packages are installed."
else
    echo "⚠️ Warning: requirements.txt not found. Skipping package check."
fi

# --- Step 1: Make scripts executable ---
echo "🔧 Setting script permissions..."
chmod +x "$LAUNCHER_SCRIPT_PATH"
chmod +x "$PROJECT_ROOT/backends/sh/work_connect.sh"
echo "✅ Scripts are now executable."

# --- Step 2: Update paths in the launcher script ---
echo "✍️  Updating paths in launcher script..."
sed -i.bak "s|__PYTHON_EXEC_PATH__|$PYTHON_EXEC|" "$LAUNCHER_SCRIPT_PATH"
sed -i.bak "s|__PYTHON_SCRIPT_PATH__|$PYTHON_SCRIPT_PATH|" "$LAUNCHER_SCRIPT_PATH"
rm "${LAUNCHER_SCRIPT_PATH}.bak"
echo "✅ Launcher script configured."

# --- Step 3: Create and install the native host manifest ---
echo "✍️  Creating native host manifest..."
sed "s|__LAUNCHER_PATH__|$LAUNCHER_SCRIPT_PATH|" "$MANIFEST_TEMPLATE_PATH" > "/tmp/$NATIVE_HOST_NAME.json"
echo "✅ Manifest created."

echo "📦 Installing manifest to Chrome's directory..."
mkdir -p "$CHROME_NATIVE_HOSTS_DIR"
mv "/tmp/$NATIVE_HOST_NAME.json" "$FINAL_MANIFEST_PATH"
echo "✅ Manifest installed at: $FINAL_MANIFEST_PATH"

# --- Final Step: Remind user to load the extension ---
echo ""
echo "🎉 Installation Complete!"
echo ""
echo "🔴 IMPORTANT FINAL STEPS 🔴"
echo "1. Open Chrome and go to 'chrome://extensions'."
echo "2. Enable 'Developer mode' in the top right."
echo "3. Click 'Load unpacked' and select the '$PROJECT_ROOT' directory."
echo "4. Once loaded, find the Holocron extension and copy its 'ID' (a long string of letters)."
echo "5. Open the manifest file: $FINAL_MANIFEST_PATH"
echo "6. Replace 'YOUR_EXTENSION_ID_HERE' with the ID you just copied."
echo "7. Save the file and RESTART CHROME for the change to take effect."
echo ""
echo "After that, you can configure the extension:"
echo " - Edit 'backends/sh/work_connect.sh' to add your work Wi-Fi SSIDs."
echo " - Right-click the Holocron icon and select 'Options' to set up your SSH connection."