#!/bin/bash

# This script ensures that the native host is executed with the correct Python interpreter
# from the Anaconda environment, which has the required 'psutil' package installed.

# Path to the Anaconda Python executable.
# This was determined from the 'pip' output showing psutil's location.
PYTHON_EXEC="/opt/homebrew/anaconda3/bin/python"

# Path to the actual Python native host script.
SCRIPT_PATH="/Users/majidsoorani/chrome_holocron/backends/python/holocron_native_host.py"

# Execute the script with the specified Python interpreter, passing along all arguments.
exec "$PYTHON_EXEC" "$SCRIPT_PATH" "$@"
