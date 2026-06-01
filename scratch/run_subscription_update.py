#!/usr/bin/env python3
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backends" / "python"
sys.path.append(str(backend_dir))

from holocron_native_host import execute_singbox_emulation_command

def main():
    print("Starting subscription update on router...")
    ssh_cmd_base = ["ssh", "-o", "StrictHostKeyChecking=no", "root@192.168.1.1"]
    
    result = execute_singbox_emulation_command(
        action="update_subscription",
        ssh_cmd_base=ssh_cmd_base
    )
    
    print("========================================")
    print("Result of subscription update:")
    print(f"Success: {result.get('success')}")
    print(f"Message: {result.get('message')}")
    print("========================================")

if __name__ == "__main__":
    main()
