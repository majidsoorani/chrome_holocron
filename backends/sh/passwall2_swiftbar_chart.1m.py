#!/usr/bin/env python3
# <bitbar.title>Passwall2 Status & Hardware Chart</bitbar.title>
# <bitbar.version>v1.1</bitbar.version>
# <bitbar.author>Antigravity</bitbar.author>
# <bitbar.desc>Shows Passwall2 status, router CPU/Mem usage, and interface latencies in menu bar</bitbar.desc>
# <bitbar.dependencies>python3</bitbar.dependencies>

import os
import re
from datetime import datetime

LOG = os.path.expanduser("/Users/majidsoorani/chrome_holocron/backends/log/passwall2_watchdog.log")
HW_LOG = os.path.expanduser("/Users/majidsoorani/chrome_holocron/backends/log/router_hardware_debug.log")
MAX_POINTS = 30

spark_chars = "▁▂▃▄▅▆▇█"

entries = []
if os.path.exists(LOG):
    with open(LOG) as f:
        for line in f:
            m = re.match(r'\[(.*?)\] (.*)', line)
            if m:
                ts, msg = m.groups()
                entries.append((ts, msg))

# Only keep last MAX_POINTS
entries = entries[-MAX_POINTS:]

# Parse status: 1=ok, 0=down
points = []
for ts, msg in entries:
    if "internet restored" in msg or "INFO" in msg:
        points.append(1)
    elif "internet check failed" in msg or "ERROR" in msg or "WARN" in msg:
        points.append(0)
    else:
        points.append(1)

# Build sparkline
if points:
    spark = ''.join(spark_chars[int(p*(len(spark_chars)-1))] for p in points)
else:
    spark = 'no data'

# Current status
status = "OK" if points and points[-1] else "DOWN"
color = "green" if status == "OK" else "red"

# Parse hardware stats
hw_info = {}
if os.path.exists(HW_LOG):
    try:
        with open(HW_LOG, "r") as f:
            content = f.read()
        blocks = content.split("======================================================================")
        # Find the last non-empty block
        valid_blocks = [b.strip() for b in blocks if "DIAGNOSTIC REPORT" in b]
        if valid_blocks:
            last_block = valid_blocks[-1]
            
            # Parse load
            load_match = re.search(r"Load average:\s*([\d\.\s,]+)", last_block)
            if load_match:
                hw_info["load"] = load_match.group(1).split(',')[0].strip()
                
            # Parse memory
            mem_match = re.search(r"Mem:\s+(\d+)\s+(\d+)", last_block)
            if mem_match:
                total_mem = int(mem_match.group(1))
                used_mem = int(mem_match.group(2))
                pct = int(used_mem / total_mem * 100) if total_mem > 0 else 0
                hw_info["mem"] = f"{used_mem}/{total_mem} MB ({pct}%)"
                hw_info["mem_pct"] = pct
                
            # Parse interface latencies
            latencies = []
            for line in last_block.splitlines():
                if "Connected (Latency:" in line:
                    m = re.search(r"Interface\s+(\w+).*?Latency:\s*([\d\.]+)ms", line)
                    if m:
                        iface, lat = m.groups()
                        latencies.append((iface, f"{float(lat):.0f}ms"))
                elif "Connection FAILED" in line:
                    m = re.search(r"Interface\s+(\w+)", line)
                    if m:
                        latencies.append((m.group(1), "LOSS"))
            if latencies:
                hw_info["latencies"] = latencies
    except Exception as e:
        hw_info["error"] = str(e)

# Menu Bar display text
menu_bar_text = f"🌐"
if "mem_pct" in hw_info:
    menu_bar_text += f" [M:{hw_info['mem_pct']}%]"
if "load" in hw_info:
    menu_bar_text += f" [L:{hw_info['load']}]"

# Find primary active latency to show in menu bar
if "latencies" in hw_info:
    active_lats = [f"{iface}:{lat}" for iface, lat in hw_info["latencies"] if lat != "LOSS"]
    if active_lats:
        menu_bar_text += f" [{active_lats[0]}]"

print(f"{menu_bar_text}|color={color}")
print("---")
print(f"Status: <b><font color='{color}'>{status}</font></b>")
print(f"Watchdog Log: {spark}")

if hw_info:
    print("---")
    print("<b>Router Hardware Resource Usage:</b>")
    if "load" in hw_info:
        print(f"CPU Load (1m): {hw_info['load']}")
    if "mem" in hw_info:
        print(f"Memory: {hw_info['mem']}")
    if "latencies" in hw_info:
        print("---")
        print("<b>Interface Latencies (8.8.8.8):</b>")
        for iface, lat in hw_info["latencies"]:
            icon = "🟢" if lat != "LOSS" else "🔴"
            print(f"{icon} {iface}: {lat}")
else:
    print("---")
    print("No router hardware stats logged yet.")

print("---")
print(f"Log: {LOG}")
print(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
