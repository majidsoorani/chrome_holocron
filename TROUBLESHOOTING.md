# Troubleshooting Guide

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
