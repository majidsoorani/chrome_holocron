#!/bin/bash
set -e

# Caching sudo password
echo 'aFcnASUwgC' | sudo -S -v

echo '[*] Downloading sing-box...'
wget -q -O /tmp/sing-box.deb https://github.com/SagerNet/sing-box/releases/download/v1.14.0-alpha.26/sing-box_1.14.0-alpha.26_linux_amd64.deb

echo '[*] Installing sing-box...'
sudo dpkg -i /tmp/sing-box.deb || sudo apt-get install -f -y

echo '[*] Generating VLESS-Reality keys...'
KEYS=$(sing-box generate reality-keypair)
PRIVATE_KEY=$(echo "$KEYS" | grep "PrivateKey" | awk '{print $2}')
PUBLIC_KEY=$(echo "$KEYS" | grep "PublicKey" | awk '{print $2}')
SHORT_ID=$(openssl rand -hex 8)
UUID="c0686cb1-515d-4fe3-8f22-508746811ef3"

echo '[*] Creating config...'
cat << EOF | sudo tee /etc/sing-box/config.json
{
  "log": {
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-reality-in",
      "listen": "0.0.0.0",
      "listen_port": 443,
      "users": [
        {
          "uuid": "$UUID",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "www.microsoft.com",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "www.microsoft.com",
            "server_port": 443
          },
          "private_key": "$PRIVATE_KEY",
          "short_id": "$SHORT_ID"
        }
      }
    }
  ],
  "outbounds": [
    {
      "type": "direct",
      "tag": "direct"
    }
  ]
}
EOF

echo '[*] Restarting sing-box...'
sudo systemctl enable sing-box
sudo systemctl restart sing-box

echo "===RESULTS==="
echo "PUBLIC_KEY=$PUBLIC_KEY"
echo "SHORT_ID=$SHORT_ID"

rm -f /tmp/sing-box.deb
