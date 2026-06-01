#!/usr/bin/env python3
import json
import sys

sys.path.append("/Users/majidsoorani/chrome_holocron/backends/python")
import holocron_native_host

def main():
    default_config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "0.0.0.0",
                "listen_port": 1080
            },
            {
                "type": "direct",
                "tag": "dns-in",
                "listen": "127.0.0.1",
                "listen_port": 5353
            },
            {
                "type": "tproxy",
                "tag": "tproxy-in",
                "listen": "0.0.0.0",
                "listen_port": 12345
            }
        ],
        "outbounds": [
            {
                "type": "direct",
                "tag": "direct"
            },
            {
                "type": "block",
                "tag": "block"
            },
            {
                "type": "socks",
                "tag": "nooshdaroo",
                "server": "127.0.0.1",
                "server_port": 1085
            },
            {
                "type": "socks",
                "tag": "tunnel-zitel",
                "server": "127.0.0.1",
                "server_port": 1032
            },
            {
                "type": "socks",
                "tag": "tunnel-rightel",
                "server": "127.0.0.1",
                "server_port": 1033
            },
            {
                "type": "socks",
                "tag": "tunnel-mobinnet",
                "server": "127.0.0.1",
                "server_port": 1034
            },
            {
                "type": "vless",
                "tag": "vless-reality-main",
                "server": "130.185.120.216",
                "server_port": 443,
                "uuid": "c0686cb1-515d-4fe3-8f22-508746811ef3",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "utls": { "enabled": True, "fingerprint": "chrome" },
                    "reality": {
                        "enabled": True,
                        "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                        "short_id": "034e50c5756bb22a"
                    }
                },
                "packet_encoding": "xudp",
                "multiplex": { "enabled": True, "protocol": "h2mux", "max_connections": 8 },
                "tcp_fast_open": True,
                "connect_timeout": "5s"
            },
            {
                "type": "vless",
                "tag": "vless-reality-zitel",
                "server": "130.185.120.216",
                "server_port": 443,
                "uuid": "c0686cb1-515d-4fe3-8f22-508746811ef3",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "utls": { "enabled": True, "fingerprint": "chrome" },
                    "reality": {
                        "enabled": True,
                        "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                        "short_id": "034e50c5756bb22a"
                    }
                },
                "packet_encoding": "xudp",
                "multiplex": { "enabled": True, "protocol": "h2mux", "max_connections": 8 },
                "tcp_fast_open": True,
                "connect_timeout": "5s",
                "bind_interface": "wan"
            },
            {
                "type": "vless",
                "tag": "vless-reality-rightel",
                "server": "130.185.120.216",
                "server_port": 443,
                "uuid": "c0686cb1-515d-4fe3-8f22-508746811ef3",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "utls": { "enabled": True, "fingerprint": "chrome" },
                    "reality": {
                        "enabled": True,
                        "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                        "short_id": "034e50c5756bb22a"
                    }
                },
                "packet_encoding": "xudp",
                "multiplex": { "enabled": True, "protocol": "h2mux", "max_connections": 8 },
                "tcp_fast_open": True,
                "connect_timeout": "5s",
                "bind_interface": "lan3"
            },
            {
                "type": "vless",
                "tag": "vless-reality-mobinnet",
                "server": "130.185.120.216",
                "server_port": 443,
                "uuid": "c0686cb1-515d-4fe3-8f22-508746811ef3",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "utls": { "enabled": True, "fingerprint": "chrome" },
                    "reality": {
                        "enabled": True,
                        "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                        "short_id": "034e50c5756bb22a"
                    }
                },
                "packet_encoding": "xudp",
                "multiplex": { "enabled": True, "protocol": "h2mux", "max_connections": 8 },
                "tcp_fast_open": True,
                "connect_timeout": "5s",
                "bind_interface": "lan1"
            },
            {
                "type": "vless",
                "tag": "vless-reality-vps",
                "server": "130.185.120.216",
                "server_port": 443,
                "uuid": "c0686cb1-515d-4fe3-8f22-508746811ef3",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "utls": { "enabled": True, "fingerprint": "chrome" },
                    "reality": {
                        "enabled": True,
                        "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                        "short_id": "034e50c5756bb22a"
                    }
                },
                "packet_encoding": "xudp",
                "multiplex": { "enabled": True, "protocol": "h2mux", "max_connections": 8 },
                "tcp_fast_open": True,
                "connect_timeout": "5s"
            },
            {
                "type": "urltest",
                "tag": "balancer",
                "outbounds": [
                    "vless-reality-main",
                    "vless-reality-zitel",
                    "vless-reality-rightel",
                    "vless-reality-mobinnet",
                    "tunnel-zitel",
                    "tunnel-rightel",
                    "tunnel-mobinnet",
                    "nooshdaroo"
                ],
                "url": "https://www.google.com/generate_204",
                "interval": "30s",
                "tolerance": 50
            }
        ],
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "type": "https",
                    "server": "8.8.8.8",
                    "detour": "balancer"
                },
                {
                    "tag": "dns-direct",
                    "type": "udp",
                    "server": "10.202.10.202"
                }
            ],
            "rules": [
                {
                    "domain_suffix": [
                        "ir",
                        "iranicard.ir",
                        "digikala.com",
                        "aparat.com"
                    ],
                    "server": "dns-direct"
                }
            ],
            "final": "dns-remote"
        },
        "route": {
            "rules": [
                {
                    "inbound": ["mixed-in", "tproxy-in"],
                    "action": "sniff"
                },
                {
                    "port": [53],
                    "action": "hijack-dns"
                },
                {
                    "inbound": ["dns-in"],
                    "action": "hijack-dns"
                },
                {
                    "ip_is_private": True,
                    "action": "route",
                    "outbound": "direct"
                },
                {
                    "ip_cidr": [],
                    "action": "route",
                    "outbound": "direct"
                },
                {
                    "domain_suffix": [],
                    "action": "route",
                    "outbound": "direct"
                }
            ],
            "final": "balancer",
            "auto_detect_interface": True,
            "default_domain_resolver": "dns-direct"
        }
    }

    # Run optimizations to inject domains and IP ranges automatically
    holocron_native_host.optimize_singbox_config(default_config)

    # Write output to scratch
    with open("scratch/default_config.json", "w") as f:
        json.dump(default_config, f, indent=2)
    print("Successfully generated optimized default config to scratch/default_config.json")

if __name__ == "__main__":
    main()
