#!/bin/bash
set -e

echo "[*] Downloading sing-box 1.14.0-alpha.26 DEB package for x86_64..."
wget -q -O /tmp/sing-box.deb https://github.com/SagerNet/sing-box/releases/download/v1.14.0-alpha.26/sing-box_1.14.0-alpha.26_linux_amd64.deb

echo "[*] Installing sing-box package..."
sudo dpkg -i /tmp/sing-box.deb || sudo apt-get install -f -y

echo "[*] Generating VLESS-Reality keys..."
KEYS=$(sing-box generate reality-keypair)
PRIVATE_KEY=$(echo "$KEYS" | grep "PrivateKey" | awk '{print $2}')
PUBLIC_KEY=$(echo "$KEYS" | grep "PublicKey" | awk '{print $2}')
SHORT_ID=$(openssl rand -hex 8)
UUID="c0686cb1-515d-4fe3-8f22-508746811ef3"
VPS_IP=$(curl -s https://ipinfo.io/ip)

echo "[*] Creating sing-box configuration..."
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

echo "[*] Enabling and starting sing-box service..."
sudo systemctl enable sing-box
sudo systemctl restart sing-box

echo "=========================================================="
echo "          VLESS-Reality Server Installed!                 "
echo "=========================================================="
echo "VPS IP: $VPS_IP"
echo "UUID: $UUID"
echo "Public Key: $PUBLIC_KEY"
echo "Short ID: $SHORT_ID"
echo "SNI: www.microsoft.com"
echo ""
echo "Client Connection Link:"
echo "vless://$UUID@$VPS_IP:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&pbk=$PUBLIC_KEY&sid=$SHORT_ID#VLESS-Reality-VPS"
echo "=========================================================="

rm -f /tmp/sing-box.deb
