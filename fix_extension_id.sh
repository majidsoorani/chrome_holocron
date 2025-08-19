#!/bin/bash

# This script fixes the connection between the Holocron extension and its
# native host by updating the allowed extension ID in the manifest file.

set -e

echo "🔧 Holocron Extension ID Fixer"
echo ""
echo "This utility is needed if you see the error 'Access to the specified native messaging host is forbidden'."
echo "This usually happens if you reload the unpacked unpacked extension in Chrome, which assigns it a new ID."
echo ""

# --- Configuration ---
NATIVE_HOST_NAME="com.holocron.native_host"
CHROME_NATIVE_HOSTS_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
FINAL_MANIFEST_PATH="$CHROME_NATIVE_HOSTS_DIR/$NATIVE_HOST_NAME.json"

# --- Check if manifest exists ---
if [ ! -f "$FINAL_MANIFEST_PATH" ]; then
    echo "❌ Error: The native host manifest file was not found at:"
    echo "   $FINAL_MANIFEST_PATH"
    echo "Please run the main './install.sh' script first to set up the native host."
    exit 1
fi

echo "The manifest file was found at: $FINAL_MANIFEST_PATH"
echo ""
echo "🔴 ACTION REQUIRED: Please follow these steps carefully 🔴"
echo "1. Open Chrome and go to 'chrome://extensions'."
echo "2. Ensure 'Developer mode' is enabled in the top right."
echo "3. Find the 'Holocron Status' extension."
echo "4. Copy its current 'ID' (it is a long string of letters)."
echo ""

# -p for prompt, -r to prevent backslash interpretation
read -r -p "5. Paste the correct Extension ID here and press [Enter]: " extension_id

if [ -z "$extension_id" ]; then
    echo "❌ No Extension ID provided. Aborting."
    exit 1
fi

echo "✍️  Updating manifest with the new Extension ID..."

# This sed command robustly replaces the old extension ID with the new one.
# It looks for the pattern "chrome-extension://<32-lowercase-letters>/" and replaces the ID part.
sed -i.bak "s#\(chrome-extension://\)[a-z]\{32\}\(/\"\)#\1${extension_id}\2#" "$FINAL_MANIFEST_PATH"
rm "${FINAL_MANIFEST_PATH}.bak"

echo "✅ Manifest updated successfully!"
echo "🚀 FINAL STEP: Please RESTART CHROME completely for the changes to take effect."
echo "   (Cmd+Q on macOS, or right-click the dock icon and choose 'Quit')."