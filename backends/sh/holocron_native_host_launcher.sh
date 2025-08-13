#!/bin/bash

# This launcher script is referenced by the native messaging host manifest.
# Its purpose is to ensure the Python script is executed with the correct
# interpreter, especially when using virtual environments like Conda or venv.

# IMPORTANT: The paths below are hardcoded. The native messaging manifest
# requires an absolute path to this launcher. An install script is provided
# to configure these paths automatically.

# Path to the Python executable. This will be replaced by the install script.
PYTHON_EXEC="/Users/majidsoorani/chrome_holocron/.venv/bin/python"

# Path to the Python native host script. This will be replaced by the install script.
SCRIPT_PATH="/Users/majidsoorani/chrome_holocron/backends/python/holocron_native_host.py"

# Execute the script with the specified Python interpreter, passing along all arguments.
exec "$PYTHON_EXEC" "$SCRIPT_PATH" "$@"
