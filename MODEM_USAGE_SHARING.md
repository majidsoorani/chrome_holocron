# Feature Specification: Modem Usage Distribution Circular Meter (4th Circle)

This document describes the design and implementation plan for adding a **4th Realtime Internet Health Circular Meter** representing the relative traffic/usage share of active modems on the OpenWrt router.

---

## 1. Context & Objectives

Currently, the dashboard displays 3 circular meters:
1. **Internet Stability** (Ping loss/RTT success rates)
2. **DNS Health** (Resolution success/speed)
3. **Tunnel Quality** (Proxy latency and active channel tests)

We want to introduce a **4th Meter** next to them:
- **Name**: "Modem Distribution" or "WAN Traffic Share".
- **Objective**: Display the real-time share of traffic going through each active modem (Zitel `wan`, RighTel `lan3`, Irancell `wl1-sta0`, Mobinnet `lan1`/`wl0-sta0`).
- **Constraint**: Must be extremely lightweight. No packet capture, no ntopng, no high-CPU monitoring commands on the OpenWrt router. It should not cause any overhead on the modems or CPU.

---

## 2. Recommended Solution: Kernel-Level Traffic Statistics

Instead of invoking active network tests (which consume bandwidth and CPU), we will leverage the Linux kernel's built-in network device statistics.

### A. Data Retrieval (`/proc/net/dev`)
The Linux kernel maintains cumulative packet/byte counters for all interfaces in `/proc/net/dev`. Reading this file takes `< 1ms` and consumes negligible CPU.

An example of `/proc/net/dev` output:
```text
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  wan: 19572910    24192    0    0    0     0          0         0  4219482     3920    0    0    0     0       0          0
 lan3:  4829102     5201    0    0    0     0          0         0   920482      840    0    0    0     0       0          0
 wl1-sta0: 102048     120    0    0    0     0          0         0    39281       92    0    0    0     0       0          0
```

### B. Calculation Algorithm (Throughput Delta)
To compute real-time throughput without putting load on the modems:
1. Every $T$ seconds (e.g. $T = 5$ seconds), read the cumulative `rx_bytes` (received) and `tx_bytes` (transmitted) for each interface $i$:
   $$\text{TotalBytes}_{i}(t) = \text{rx\_bytes}_{i}(t) + \text{tx\_bytes}_{i}(t)$$
2. Compute the delta bytes since the last check:
   $$\Delta \text{Bytes}_{i} = \text{TotalBytes}_{i}(t) - \text{TotalBytes}_{i}(t - T)$$
3. Calculate the current throughput speed (bytes/sec) for each interface:
   $$\text{Speed}_{i} = \frac{\Delta \text{Bytes}_{i}}{T}$$
4. Calculate the sum of speeds of all interfaces:
   $$\text{Speed}_{\text{total}} = \sum_{j} \text{Speed}_{j}$$
5. Calculate the percentage share for each interface:
   $$\text{Share}_{i} = \left( \frac{\text{Speed}_{i}}{\text{Speed}_{\text{total}}} \right) \times 100\%$$

If $\text{Speed}_{\text{total}} = 0$, then the distribution share is set to $0\%$ (or equally distributed among UP interfaces).

---

## 3. Frontend Circular Meter Design

To represent multiple modems inside a single circular meter:
1. **Circular Segment Display**:
   - The SVG circle's stroke is split into multiple colored sections representing each interface's share (e.g., Zitel = Purple segment, Irancell = Blue, RighTel = Yellow, Mobinnet = Green).
   - Alternatively, the circular meter shows the **Primary interface's share** (the interface carrying the highest percentage, e.g., "75% Zitel") while the other shares are displayed inside or on hover.
2. **Breakdown Info**:
   - Inside the circle: Displays the name and percentage of the dominant modem (e.g., `Zitel\n75%`).
   - Hover Tooltip: Hovering over the circle displays a hovercard showing current absolute speeds and percentages:
     - 🟣 **Zitel (wan)**: $1.2\text{ MB/s}$ ($75\%$)
     - 🔵 **Mobinnet (lan1)**: $320\text{ KB/s}$ ($20\%$)
     - 🟡 **RighTel (lan3)**: $80\text{ KB/s}$ ($5\%$)
3. **Visual Aesthetics**:
   - Match the glassmorphism and neon glows of the other three circles.
   - Use vibrant HSL accents: Zitel (`hsl(270, 100%, 65%)`), Mobinnet (`hsl(145, 80%, 50%)`), RighTel (`hsl(45, 95%, 55%)`), Irancell (`hsl(205, 90%, 55%)`).

---

## 4. Integration with Options Dashboard

- **Backend (Python Host)**:
  We will add an action `get_modem_traffic` inside `holocron_native_host.py`. It reads `/proc/net/dev` on the OpenWrt router over SSH, maintains the states in memory to compute the delta, and returns a JSON payload containing the current speeds and ratios.
- **Frontend (options.js & options.html)**:
  - Add a 4th `<div class="health-meter" id="meter-modems">` in the HTML.
  - In `options.js`, fetch this data periodically and update the SVG segments and text labels.
