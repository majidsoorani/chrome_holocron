#!/usr/bin/env python3
import json
import os

def main():
    log_path = "/Users/majidsoorani/.gemini/antigravity/brain/d4f60955-87bf-4584-984e-ad7a2f9a6fb5/.system_generated/logs/transcript.jsonl"
    if not os.path.exists(log_path):
        print(f"Log path does not exist: {log_path}")
        return

    core_tags = [
        "ss-zitel", "ss-rightel", "ss-mobinnet", 
        "tunnel-zitel", "tunnel-rightel", "tunnel-mobinnet", 
        "vless-reality-vps", "vless-reality-zitel", "vless-reality-rightel", "vless-reality-mobinnet",
        "direct", "block", "balancer", "nooshdaroo"
    ]

    print("Searching log transcripts...")
    with open(log_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if "cat /etc/sing-box/config.json" in line or "config.json" in line:
                try:
                    data = json.loads(line)
                    content = data.get("content", "")
                    if "Output:\n" in content:
                        parts = content.split("Output:\n")
                        json_str = parts[-1].strip()
                        # If there is a trailing system marker or log block, clean it up
                        if json_str.endswith("`"):
                            json_str = json_str.rstrip("`")
                        # Try parsing
                        try:
                            cfg = json.loads(json_str)
                            print(f"Success on line {line_num}!")
                            # Filter out non-core outbounds
                            cfg["outbounds"] = [o for o in cfg.get("outbounds", []) if o.get("tag") in core_tags]
                            # Write clean file
                            with open("scratch/recovered_config.json", "w") as out_f:
                                json.dump(cfg, out_f, indent=2)
                            print("Recovered config successfully to scratch/recovered_config.json")
                            return
                        except Exception:
                            # It might be truncated, let's keep searching
                            pass
                except Exception:
                    pass
    
    print("Could not find a fully un-truncated config JSON. We will construct a clean default config.")

if __name__ == "__main__":
    main()
