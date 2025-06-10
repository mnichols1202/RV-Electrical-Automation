# RV Electrical Automation

This project is a work-in-progress platform for automating electrical systems in an RV using a network-connected microcontroller (Raspberry Pi Pico W) and a Blazor Server Web UI. The system allows real-time control of relays and communication with devices over TCP/IP and UDP protocols.

---

## 🧩 Project Structure

### 1. **AutomationWeb/**  
A .NET 9 Blazor Server application used to manage and monitor connected devices from a web interface.

- `Program.cs` – Initializes services and configures the app.
- `NetworkService.cs` – Handles incoming UDP broadcasts and TCP device communication.
- `NetworkHostedService.cs` – Manages background listening for device discovery.
- `Components/` – Contains Razor components and layout.
- `wwwroot/app.css` – Basic styling.
- `appsettings.json` – Configuration settings for ports and services.

### 2. **PicoFramework/**  
A MicroPython-based firmware for Raspberry Pi Pico W that connects to Wi-Fi, broadcasts its identity, listens for TCP commands, and toggles relays.

- `main.py` – Entry point for the device; handles boot logic and task scheduling.
- `pico_network.py` – Manages network setup, UDP broadcasting, and TCP socket handling.
- `relay_toggle.py` – Contains logic for relay GPIO activation.
- `config.json` – Stores device ID (e.g., `"Orange"` or `"Blue"`) and Wi-Fi credentials.

---

## 🖥️ Features

- 🔌 Control electrical relays from a browser interface
- 📡 Auto-discovery of Pico devices via UDP broadcast
- 🔗 Reliable communication via TCP/IP
- ⚡ Toggle relays in real-time
- 🧠 Device roles configurable via JSON

---

## 🚧 Planned Features

- Persistent relay state and event logging (SQL Server or LiteDB)
- Device health/status display (e.g., uptime, IP, RSSI)
- Authentication for access control
- UI enhancements with real-time status feedback
- Mobile-responsive layout for dashboard access on the go

---

## 🚀 Getting Started

### Prerequisites
- Raspberry Pi Pico W with MicroPython firmware
- .NET 9 SDK installed
- Visual Studio 2022+
- Wi-Fi network shared between the Pico and server

### Setup Instructions

#### 1. **Raspberry Pi Pico W**
- Flash the Pico with MicroPython
- Upload the contents of `PicoFramework/` via Thonny or rshell
- Edit `config.json`:
  ```json
  {
    "id": "Orange",
    "wifi_ssid": "YourSSID",
    "wifi_password": "YourPassword"
  }
