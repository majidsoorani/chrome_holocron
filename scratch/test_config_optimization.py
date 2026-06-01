#!/usr/bin/env python3
import json
import sys
import unittest

sys.path.append("/Users/majidsoorani/chrome_holocron/backends/python")
import holocron_native_host

class TestConfigOptimization(unittest.TestCase):
    def setUp(self):
        # Sample configuration with a balancer pool, reality outbound, and some route rules
        self.config_data = {
            "route": {
                "final": "vless-reality-zitel",
                "rules": [
                    {
                        "outbound": "direct",
                        "domain_suffix": ["example.ir"]
                    }
                ]
            },
            "dns": {
                "servers": [
                    {
                        "tag": "dns-remote",
                        "address": "https://1.1.1.1/dns-query"
                    }
                ],
                "rules": [
                    {
                        "server": "dns-direct",
                        "domain_suffix": ["example.ir"]
                    }
                ]
            },
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "vless-reality-zitel",
                    "server": "1.1.1.1",
                    "server_port": 443,
                    "uuid": "test-uuid",
                    "flow": "",
                    "tls": {
                        "enabled": True,
                        "server_name": "www.microsoft.com",
                        "reality": {
                            "enabled": True,
                            "public_key": "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4",
                            "short_id": "034e50c5756bb22a"
                        }
                    }
                },
                {
                    "type": "urltest",
                    "tag": "balancer",
                    "outbounds": ["vless-reality-zitel"]
                }
            ]
        }

    def test_optimize_singbox_config(self):
        # Run optimization
        holocron_native_host.optimize_singbox_config(self.config_data)

        # 1. Verify routing rules
        route = self.config_data.get("route", {})
        self.assertTrue(route.get("auto_detect_interface"))
        
        rules = route.get("rules", [])
        self.assertTrue(len(rules) >= 2)
        
        # Verify IP rule
        ip_rule = next((r for r in rules if "ip_cidr" in r and r.get("outbound") == "direct"), None)
        self.assertIsNotNone(ip_rule)
        self.assertIn("2.176.0.0/13", ip_rule["ip_cidr"])
        
        # Verify Domain rule
        dom_rule = next((r for r in rules if "domain_suffix" in r and r.get("outbound") == "direct"), None)
        self.assertIsNotNone(dom_rule)
        self.assertIn("ir", dom_rule["domain_suffix"])
        self.assertIn("iranicard.ir", dom_rule["domain_suffix"])
        self.assertIn("example.ir", dom_rule["domain_suffix"])

        # 2. Verify dns direct rules
        dns_rules = self.config_data.get("dns", {}).get("rules", [])
        dns_direct_rule = next((r for r in dns_rules if r.get("server") == "dns-direct"), None)
        self.assertIsNotNone(dns_direct_rule)
        self.assertIn("ir", dns_direct_rule["domain_suffix"])

        # 3. Verify balancer interval
        outbounds = self.config_data.get("outbounds", [])
        balancer = next((o for o in outbounds if o.get("tag") == "balancer"), None)
        self.assertIsNotNone(balancer)
        self.assertEqual(balancer.get("interval"), "30s")
        self.assertEqual(balancer.get("tolerance"), 50)

        # 4. Verify VLESS Reality optimization
        reality_node = next((o for o in outbounds if o.get("tag") == "vless-reality-zitel"), None)
        self.assertIsNotNone(reality_node)
        self.assertEqual(reality_node.get("packet_encoding"), "xudp")
        self.assertEqual(reality_node.get("flow"), "xtls-rprx-vision")
        self.assertTrue(reality_node.get("tcp_fast_open"))
        self.assertEqual(reality_node.get("connect_timeout"), "5s")
        
        # Verify multiplex
        mux = reality_node.get("multiplex", {})
        self.assertTrue(mux.get("enabled"))
        self.assertEqual(mux.get("protocol"), "h2mux")
        self.assertEqual(mux.get("max_connections"), 8)
        
        # Verify reality short_ids list
        tls = reality_node.get("tls", {})
        reality = tls.get("reality", {})
        self.assertEqual(reality.get("short_id"), ["034e50c5756bb22a", "a1b2c3d4e5f67890"])
        self.assertEqual(tls.get("utls", {}).get("fingerprint"), "chrome")

    def test_parse_uri_reality(self):
        # Test parsing VLESS reality URI with single or multiple short_ids
        uri = "vless://c0686cb1-515d-4fe3-8f22-508746811ef3@130.185.120.216:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&pbk=VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4&sid=034e50c5756bb22a,a1b2c3d4e5f67890#vless-reality-main"
        
        parsed = holocron_native_host.parse_uri_to_singbox_outbound(uri, "vless-reality-main")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("type"), "vless")
        self.assertEqual(parsed.get("tag"), "vless-reality-main")
        self.assertEqual(parsed.get("server"), "130.185.120.216")
        self.assertEqual(parsed.get("server_port"), 443)
        self.assertEqual(parsed.get("packet_encoding"), "xudp")
        self.assertTrue(parsed.get("tcp_fast_open"))
        self.assertEqual(parsed.get("connect_timeout"), "5s")
        
        # Verify reality params
        tls = parsed.get("tls", {})
        reality = tls.get("reality", {})
        self.assertTrue(reality.get("enabled"))
        self.assertEqual(reality.get("public_key"), "VHI65v3ql03Yz-4yVtwCA9-58WkiYGOt2tvoFXrQnC4")
        self.assertEqual(reality.get("short_id"), ["034e50c5756bb22a", "a1b2c3d4e5f67890"])

if __name__ == '__main__':
    unittest.main()
