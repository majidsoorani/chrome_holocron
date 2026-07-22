# AGENTS.md

## Cursor Cloud specific instructions

### What this project is
Holocron is a Google Chrome **Manifest V3 extension** (plain HTML/CSS/JS at the repo root: `manifest.json`, `background.js`, `popup.*`, `options.*`) plus a **Python native-messaging host backend** (`backends/python/holocron_native_host.py`) and helper shell scripts (`backends/sh/*.sh`). The extension talks to the Python host over Chrome native messaging; the host starts/stops SSH / OpenVPN / V2Ray tunnels and runs latency/health checks.

There is **no JS build system, bundler, package manager, or automated test/lint suite** — the extension is loaded unpacked as-is. The only dependency install is the Python backend (`requirements.txt`: `psutil`, `requests`, `pysocks`) into a `.venv`. `install.sh` is **macOS-only** (Chrome paths, `wdutil`, `sudoers`); it is not used on Linux/Cloud.

### Running the backend
- The venv lives at `.venv` (created by the update script). Run the host with `.venv/bin/python backends/python/holocron_native_host.py`.
- The host speaks Chrome native messaging (4-byte little-endian length prefix + JSON). You can test it directly by piping a framed JSON message to stdin (e.g. `{"command":"getStatus","config":{"type":"ssh","sshCommandIdentifier":"x"},"pingHost":"youtube.com","webCheckUrl":"https://example.com"}`) and decoding the framed response.
- Logs: `backends/log/holocron_native_host.log`. Default level is INFO, so routine `getStatus` calls (DEBUG) are **not** logged; test/start/stop actions are.

### Loading the extension in Chrome (Linux/Cloud)
- Chrome is at `/usr/bin/google-chrome-stable`. Load unpacked from `/workspace` via `chrome://extensions` (Developer mode → Load unpacked).
- For an unpacked extension the ID is derived from the load path; loading `/workspace` yields ID `mfcnnpgffdelhlegadfaiedfiklhjacl`.
- To let the extension reach the Python host, install a native-messaging manifest at `~/.config/google-chrome/NativeMessagingHosts/com.holocron.native_host.json` whose `path` points to a launcher that execs `.venv/bin/python backends/python/holocron_native_host.py`, and whose `allowed_origins` is `chrome-extension://<extension-id>/`. (This is the Linux equivalent of what `install.sh` does on macOS.)

### Exercising the SSH tunnel end-to-end (no real bastion needed)
- Run a local `sshd`, set up key-based auth for `ubuntu@127.0.0.1`, and add `127.0.0.1` to `~/.ssh/known_hosts` — `work_connect.sh` does **not** disable `StrictHostKeyChecking`, so an unknown host key will make the tunnel fail.
- Configure a profile with SSH user `ubuntu`, host `127.0.0.1`, and a **Dynamic (-D)** port forward (e.g. `1080`), then use the options page "Test Connection" button. It starts the tunnel and runs web/TCP checks through the SOCKS proxy. `work_connect.sh` needs `nc` (netcat) to verify the SOCKS port.

### Non-obvious gotchas
- The popup/`updateStatus` only queries the native host when a config is already marked **connected**; when disconnected it reports `{connected:false}` without pinging, so the popup shows TCP "Fail" / "--" by design — this is **not** a broken native-messaging bridge.
- The extension logs two harmless startup 404s trying to fetch external GeoIP/GeoSite databases; these do not affect core functionality.
