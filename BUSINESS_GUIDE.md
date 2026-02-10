# BUSINESS_GUIDE.md

## Release Notes

### Version: 1.6.0
**Date:** 2025-11-10

**Change:** Introduction of OpenWrt Passwall2 Management Mode

**Author:** Gemini, Principal Banking Data Engineer

---

### 1. Description of Change

A new connection type has been added to Holocron to allow for the direct management of the `passwall2` service on a configured OpenWrt router. This new "OpenWrt Passwall2" mode enables users to start, stop, and check the status of `passwall2` from the extension's popup, providing a seamless and integrated control plane for this popular OpenWrt package.

This change aligns with Holocron's strategy of providing robust and secure management for various tunneling and proxy services.

### 2. Technical Implementation

- **New Script:** A new shell script, `backends/sh/passwall2_control.sh`, has been created. This script securely connects to the OpenWrt router via SSH and uses the standard `uci` (Unified Configuration Interface) commands to manage the `passwall2` service.
- **Native Host Integration:** The Python native host, `holocron_native_host.py`, has been updated to include a new `passwall2` command that executes the `passwall2_control.sh` script.
- **UI Enhancements:**
    - **Options Page:** A new "OpenWrt Passwall2" connection type has been added to the configuration options, with fields for the OpenWrt host and SSH key path.
    - **Popup:** The popup UI now dynamically displays a dedicated control section for Passwall2 when a configuration of this type is active, allowing for real-time status checks and start/stop actions.

### 3. Impact Analysis

- **Business Process Impact:** This new mode provides a significant improvement for engineers who rely on `passwall2` for their daily tasks. It eliminates the need for manual SSH sessions to manage the service, reducing context switching and improving efficiency.
- **Data Pipeline Impact:** No direct impact on data pipelines.
- **Security Assessment:** The implementation follows Holocron's strict security standards. All communication with the OpenWrt router is performed over SSH, and sensitive information such as the SSH key path is handled securely through environment variables.

### 4. Updated Usage

1.  **Create a New Configuration:** In the Holocron options page, click "+ Add Custom Configuration".
2.  **Select Connection Type:** Choose "OpenWrt Passwall2" from the "Connection Type" dropdown.
3.  **Enter Details:** Fill in the "OpenWrt Host" (e.g., `192.168.1.1`) and "SSH Key Path" for your OpenWrt router.
4.  **Save and Activate:** Save the configuration and ensure it is the active one.
5.  **Control from Popup:** The extension popup will now show the Passwall2 status and provide buttons to start or stop the service.

### 5. Rollback Procedure

To revert this change, the following steps can be taken:
1.  Delete the `backends/sh/passwall2_control.sh` script.
2.  Revert the changes to `backends/python/holocron_native_host.py`, `options.html`, `options.js`, `popup.html`, `popup.js`, and `constants.js`.
3.  Delete any "OpenWrt Passwall2" configurations from the options page.