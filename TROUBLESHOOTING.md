# Troubleshooting Guide

## Release Notes: 2026-02-26

### Addition of Auto Refresh Proxy Script

- **New Feature:** Created `auto_refresh_proxy.py` to automate testing and applying the fastest Cloudflare proxy node to the Passwall2 router configuration.
- **Resilience:** Implemented a robust fallback sequence that will fall back to a local SOCKS5 proxy (`127.0.0.1:1032`) if Cloudflare fetching fails, and will issue a router reboot command if that fallback also fails.
- **Optimization:** Added `check_if_node_changed()` and `is_node_active()` safeguards to ensure the script only restarts Passwall2 and interrupts the network when the underlying proxy details have actually changed.

### Impact Analysis

- **Business Process:** No impact on existing manual connections. Provides a 24/7 background worker to manage default proxy routing stability.
- **Data Pipelines:** None.
- **Breaking Changes:** Replaces previous ad-hoc manual scripts but functions completely identically.

## Release Notes: 2026-02-11

### Update to Monitor Modems Script

- **Target Update:** `monitor_modems.sh` now targets `34.244.201.246` instead of `18.161.69.75` for connectivity checks.
- **New Feature:** Added logic to compare latency across all interfaces (`wan`, `wl1-sta0`, `lan3`) and highlight the "Best" connection in real-time.
- **Output Format:** The output table now includes a "Best" column.

### Impact Analysis

- **Business Process:** No impact on main extension functionality. This is a helper script for diagnostics.
- **Data Pipelines:** None.
- **Breaking Changes:** None. The script is standalone.

### Update to Passwall Node List

- **Target Update:** "URL Test" button logic now queries `https://www.google.com/generate_204` via `test.sh`.
- **New Feature:** Added "URL Test" option to the "Automatic detection delay" dropdown in `node_list.lua`.
- **New Feature:** Implemented `urltestAllNodes()` in `node_list.htm` which auto-runs URL tests on all nodes when the new dropdown option is selected and the page loads.
- **Impact:** Automatically checks connectivity to Google (generate_204) for all nodes if configured.

### Common Issues

### "Best" Column Shows "NONE"

- **Cause:** All pings failed or returned "LOSS".
- **Solution:** Check physical connections and interface status on the router.

### Latency Values are "9999"

- **Cause:** Internal representation for "LOSS" or "DOWN".
- **Solution:** Ignore for metric purposes; indicates no connectivity.
