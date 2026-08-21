# 🌐 Comprehensive Multi-OS & Deployment Installation Guide

This document provides in-depth installation, configuration, containerization, and troubleshooting instructions for **AgentSocket-Browser** across all platforms and operating environments.

---

## Table of Contents
1. [Native Desktop Installation](#1-native-desktop-installation)
   - [Windows (PowerShell / CMD)](#windows-powershell--cmd)
   - [macOS (Apple Silicon & Intel)](#macos-apple-silicon--intel)
   - [Linux (Ubuntu / Debian / Fedora)](#linux-ubuntu--debian--fedora)
2. [Alternative Chromium Browsers](#2-alternative-chromium-browsers)
   - [Brave Browser Setup](#brave-browser-setup)
   - [Microsoft Edge Setup](#microsoft-edge-setup)
   - [Ungoogled Chromium](#ungoogled-chromium)
3. [Docker & Containerized Headless Setup](#3-docker--containerized-headless-setup)
   - [Using Docker Compose](#using-docker-compose)
   - [Manual Docker Run with Xvfb](#manual-docker-run-with-xvfb)
4. [Enterprise Firewall & Network Configuration](#4-enterprise-firewall--network-configuration)
5. [Model Context Protocol (MCP) Setup Matrix](#5-model-context-protocol-mcp-setup-matrix)
6. [Comprehensive Troubleshooting Guide](#6-comprehensive-troubleshooting-guide)

---

## 1. Native Desktop Installation

### Windows (PowerShell / CMD)

#### Prerequisites
* Python 3.10+ (ensure "Add python.exe to PATH" is checked during installation).
* Google Chrome installed in `%ProgramFiles%\Google\Chrome\Application\chrome.exe` or `%LocalAppData%\Google\Chrome\Application\chrome.exe`.

#### Installation Commands
```powershell
# Clone repository
git clone https://github.com/Seif-Eltaweel/agentsocket-browser.git
cd agentsocket-browser

# Create virtual environment
python -m venv .venv

# PowerShell execution policy (if script execution is restricted)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

### macOS (Apple Silicon & Intel)

#### Prerequisites
* Homebrew (recommended) for Python and Git management.
* Google Chrome installed in `/Applications/Google Chrome.app`.

#### Installation Commands
```bash
# Clone repository
git clone https://github.com/Seif-Eltaweel/agentsocket-browser.git
cd agentsocket-browser

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### Linux (Ubuntu / Debian / Fedora)

#### Prerequisites
```bash
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git google-chrome-stable

# Fedora
sudo dnf install -y python3 python3-pip git google-chrome-stable
```

#### Installation Commands
```bash
git clone https://github.com/Seif-Eltaweel/agentsocket-browser.git
cd agentsocket-browser

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 2. Alternative Chromium Browsers

AgentSocket works with any modern browser supporting Chrome Manifest V3 extensions, Chrome DevTools Protocol (`chrome.debugger`), and the `tabGroups` API.

### Brave Browser Setup
1. Navigate to `brave://extensions`.
2. Enable **Developer mode** and click **Load unpacked** -> select `extension/`.
3. **Brave Shield Configuration**: In `brave://settings/shields`, ensure local loopback connections (`ws://127.0.0.1:8000`) are permitted.

### Microsoft Edge Setup
1. Navigate to `edge://extensions`.
2. Turn on the **Developer mode** toggle in the left sidebar.
3. Click **Load unpacked** in the top toolbar -> select `extension/`.

### Ungoogled Chromium
1. Open `chrome://flags/#extension-mime-request-handling` and set to **Always prompt for install**.
2. Navigate to `chrome://extensions`, enable **Developer mode**, and load unpacked.

---

## 3. Docker & Containerized Headless Setup

For cloud virtual machines (AWS EC2, GCP Compute Engine, DigitalOcean Droplets) or CI/CD test runners without a physical monitor, use the provided Docker setup with **Xvfb (Virtual Framebuffer)**.

### Using Docker Compose (Recommended)

```bash
# Build and start the container
docker compose up -d

# Check container logs
docker compose logs -f
```

The gateway server will be live at `http://localhost:8000`.

### Manual Docker Build & Run

```bash
# 1. Build Docker image
docker build -t agentsocket-browser:latest .

# 2. Run container mapping port 8000 and mounting logs
docker run -d \
  --name agentsocket \
  -p 8000:8000 \
  -v $(pwd)/server/logs:/app/server/logs \
  agentsocket-browser:latest
```

---

## 4. Enterprise Firewall & Network Configuration

AgentSocket is designed with a **Loopback Security Policy** (`127.0.0.1`).

* **Port:** `8000` (HTTP and WebSocket `/ws/extension`).
* **Environment Overrides:**
  ```bash
  # Change default port
  export AGENTSOCKET_PORT=8080
  
  # Change bind host (e.g. For private subnet or container bridge)
  export AGENTSOCKET_HOST="0.0.0.0"
  ```
* If running on corporate VPNs (e.g., Zscaler, Cisco AnyConnect), verify that `localhost` / `127.0.0.1` traffic is excluded from VPN proxy tunnels.

---

## 5. Model Context Protocol (MCP) Setup Matrix

| Agent Tool | Config File Location | Config Format |
|:---|:---|:---|
| **Claude Desktop (Windows)** | `%APPDATA%\Claude\claude_desktop_config.json` | JSON `mcpServers.agentsocket` |
| **Claude Desktop (macOS)** | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON `mcpServers.agentsocket` |
| **Claude Code CLI** | CLI Terminal | `claude mcp add agentsocket python <path>/socket_mcp.py` |
| **Google Antigravity** | `<project_root>/mcp_config.json` | JSON `mcpServers.agentsocket` |
| **Cursor / Windsurf** | Settings -> MCP | Type: `command`, Command: `python <path>/socket_mcp.py` |

---

## 6. Comprehensive Troubleshooting Guide

### Issue: `Extension is offline or disconnected`
1. Check if the gateway is running:
   ```bash
   python server/socket_launcher.py status
   ```
2. Verify Chrome has the extension loaded at `chrome://extensions`.
3. If Chrome was closed, run `python server/socket_launcher.py plug` to launch Chrome and reconnect the socket bridge.

### Issue: `Shadow DOM HUD not rendering on specific websites`
* Some sites with extreme Content Security Policies (CSP) or full-screen canvas elements may hide standard DOM elements. AgentSocket injects `<agentsocket-hud-host>` into `document.documentElement` with `z-index: 2147483647` (maximum 32-bit integer) to guarantee visibility.
