import paramiko
import sys
import os

VPS_HOST = "130.185.120.44"
KEYS = [
    ("/Users/majidsoorani/.ssh/id_ed25519", "id_ed25519"),
    ("/Users/majidsoorani/.ssh/arvan_deploy_key", "arvan_deploy_key")
]
PASSWORDS = ["maJId!@#$5", "root"]

users = ["ubuntu", "root"]

for user in users:
    print(f"\n--- Testing User: {user} ---")
    
    # Test keys
    for key_path, key_name in KEYS:
        if not os.path.exists(key_path):
            continue
        print(f"Testing key: {key_name} ({key_path})...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=VPS_HOST,
                username=user,
                key_filename=key_path,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            print(f"✅ SUCCESS: Connected as {user} using key {key_name}!")
            client.close()
        except Exception as e:
            print(f"❌ FAILED: {e}")

    # Test passwords
    for password in PASSWORDS:
        print(f"Testing password: {password}...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=VPS_HOST,
                username=user,
                password=password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            print(f"✅ SUCCESS: Connected as {user} using password!")
            client.close()
        except Exception as e:
            print(f"❌ FAILED: {e}")
