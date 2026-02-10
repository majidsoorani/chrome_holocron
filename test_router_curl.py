#!/usr/bin/env python3
"""
Test script to execute curl command on OpenWrt router.
This demonstrates how to use the execute_router_command functionality.
"""

import json
import subprocess
import sys

def send_native_message(message):
    """Send a message to the native host."""
    # Convert to JSON
    message_json = json.dumps(message)
    message_bytes = message_json.encode('utf-8')
    
    # Write message length (4 bytes, little-endian)
    sys.stdout.buffer.write(len(message_bytes).to_bytes(4, byteorder='little'))
    
    # Write message
    sys.stdout.buffer.write(message_bytes)
    sys.stdout.buffer.flush()

def read_native_message():
    """Read a message from the native host."""
    # Read message length (4 bytes)
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        return None
    
    message_length = int.from_bytes(raw_length, byteorder='little')
    
    # Read message
    message_bytes = sys.stdin.buffer.read(message_length)
    message_json = message_bytes.decode('utf-8')
    
    return json.loads(message_json)

def test_curl_on_router():
    """
    Execute curl command on OpenWrt router.
    Make sure to configure your router details below.
    """
    
    # Configuration - UPDATE THESE VALUES
    router_config = {
        "ip": "192.168.1.1",  # Your OpenWrt router IP
        "user": "root",        # SSH user (usually root)
        "port": 22,            # SSH port
        # Choose ONE authentication method:
        # Option 1: SSH key (recommended)
        "keyPath": "~/.ssh/id_rsa",  # Path to your SSH private key
        # Option 2: Password
        # "password": "your_router_password",
    }
    
    # The command to execute
    curl_command = "curl https://bit.ly/apply-cressoft"
    
    print(f"Executing on router {router_config['ip']}: {curl_command}")
    print("-" * 60)
    
    # Build the message
    message = {
        "command": "executeRouterCommand",
        "routerCommand": curl_command,
        "config": router_config
    }
    
    # Start the native host
    try:
        native_host = subprocess.Popen(
            ["python3", "/Users/majidsoorani/chrome_holocron/backends/python/holocron_native_host.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Send the message
        message_json = json.dumps(message)
        message_bytes = message_json.encode('utf-8')
        
        # Write message with length prefix
        native_host.stdin.write(len(message_bytes).to_bytes(4, byteorder='little'))
        native_host.stdin.write(message_bytes)
        native_host.stdin.flush()
        
        # Read response
        raw_length = native_host.stdout.read(4)
        if len(raw_length) == 4:
            response_length = int.from_bytes(raw_length, byteorder='little')
            response_bytes = native_host.stdout.read(response_length)
            response = json.loads(response_bytes.decode('utf-8'))
            
            # Display results
            if response.get("success"):
                print("✅ Command executed successfully!")
                print("\nOutput:")
                print(response.get("output", "(no output)"))
            else:
                print("❌ Command failed!")
                print(f"Error: {response.get('message', 'Unknown error')}")
                if response.get("error"):
                    print(f"Details: {response.get('error')}")
        
        # Clean up
        native_host.terminate()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_curl_on_router()
