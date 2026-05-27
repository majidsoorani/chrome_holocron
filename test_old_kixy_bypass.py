#!/usr/bin/env python3
import json
import subprocess
import time
import sys

ROUTER_IP = "192.168.1.1"

XRAY_CONF = {
    "log": {
        "loglevel": "warning"
    },
    "inbounds": [{
        "port": 1089,
        "listen": "0.0.0.0",
        "protocol": "socks",
        "settings": {
            "udp": True,
            "auth": "noauth"
        },
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls"]
        }
    }],
    "outbounds": [{
        "protocol": "vless",
        "settings": {
            "vnext": [{
                "address": "mail.somedayy.com",
                "port": 15673,
                "users": [{
                    "id": "380d2e6d-ea81-445b-e629-63e771d9ef8a",
                    "encryption": "none",
                    "flow": ""
                }]
            }]
        },
        "streamSettings": {
            "network": "tcp",
            "security": "tls",
            "tlsSettings": {
                "serverName": "mail.somedayy.com",
                "allowInsecure": False,
                "fingerprint": "chrome"
            }
        }
    }]
}

def ssh_exec(cmd):
    result = subprocess.run(["ssh", f"root@{ROUTER_IP}", cmd], capture_output=True, text=True)
    return result

def main():
    print("🚀 Setting up temporary Xray instance for 'old-kixy'...")
    conf_str = json.dumps(XRAY_CONF)
    
    # Write config
    ssh_exec(f"echo '{conf_str}' > /tmp/old_kixy_test.json")
    
    # Kill any existing test instance
    ssh_exec("kill $(ps w | grep '/tmp/old_kixy_test.json' | grep -v grep | awk '{print $1}') 2>/dev/null")
    
    print("🔄 Starting Xray process on router (SOCKS port 1089)...")
    # Start it in the background but capture output to a file
    ssh_exec("/tmp/etc/passwall2/bin/xray run -c /tmp/old_kixy_test.json > /tmp/old_kixy_xray.log 2>&1 &")
    
    # Wait for startup
    time.sleep(3)
    
    # Check if it actually started
    check_pid = ssh_exec("ps w | grep '/tmp/old_kixy_test.json' | grep -v grep")
    if not check_pid.stdout.strip():
        print("❌ ERROR: Xray failed to start! Checking logs:")
        logs = ssh_exec("cat /tmp/old_kixy_xray.log")
        print(logs.stdout)
        sys.exit(1)
    
    urls_to_test = [
        ("socks5h", "https://www.google.com/generate_204", None),  # Remote DNS
        ("socks5h", "https://www.youtube.com", None),              # Remote DNS
        ("socks5", "https://www.youtube.com", None),               # Local DNS
        ("socks5h", "https://142.250.72.110", "www.youtube.com")   # Pure IP, bypass DNS
    ]
    
    for proxy_type, url, host_header in urls_to_test:
        print(f"\n▶ Testing: {url} (Proxy: {proxy_type}, Host: {host_header or 'Default'})")
        test_cmd = ["curl", "-4", "-v", "-x", f"{proxy_type}://{ROUTER_IP}:1089", "-I", "-s", "--connect-timeout", "10"]
        if host_header:
            test_cmd.extend(["-H", f"Host: {host_header}"])
        test_cmd.append(url)
        
        curl_result = subprocess.run(test_cmd, capture_output=True, text=True)
        
        if curl_result.returncode == 0:
            print("✅ SUCCESS!")
        else:
            print(f"❌ FAILED (Exit code: {curl_result.returncode})")
            
        # Print a snippet of the stderr log for debugging
        if curl_result.stderr:
            err_lines = curl_result.stderr.strip().split('\n')
            for line in err_lines[-5:]: # Show last 5 lines for context
                print(f"   {line}")
            
    # Cleanup
    print("\n🧹 Cleaning up...")
    ssh_exec("kill $(ps w | grep '/tmp/old_kixy_test.json' | grep -v grep | awk '{print $1}') 2>/dev/null")
    ssh_exec("rm /tmp/old_kixy_test.json")
    print("Done.")

if __name__ == "__main__":
    main()
