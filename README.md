# RV Electrical Automation

**RV Electrical Automation** is a modular, real-time electrical control system for RVs using Wi-Fi-enabled Raspberry Pi Pico W devices and a Blazor Server web interface built in .NET 9. This project enables automation, relay control, and live device monitoring over a TCP/UDP network.

---

## 📁 Project Structure

```
RV-Electrical-Automation/
├── AutomationWeb/          # .NET 9 Blazor Server Web App
│   ├── Components/         # Razor components
│   ├── Services/           # TCP/UDP networking
│   ├── wwwroot/            # Static assets (CSS, JS)
│   └── Properties/         # Project config files
├── AutomationConsole/      # .NET Console app (test harness / CLI)
├── PicoAutomation/         # MicroPython firmware for Pico W
├── RVNetworkLibrary/       # Shared networking service library
│   └── Services/           # Core UDP/TCP abstractions
├── RV-Electrical-Automation.sln  # Visual Studio Solution File
```

---

## 🚀 Features

- Wi-Fi device auto-discovery using UDP broadcast
- Reliable command/control over TCP
- JSON-configurable Pico firmware
- Button-triggered relay control
- Real-time dashboard in Blazor Server
- Modular support for multiple devices via `target_id`
- Dynamic UI generation from Pico config

---

## 🧠 How It Works

1. Each **Raspberry Pi Pico W** is flashed with MicroPython and a `config.json` file defining relays and GPIO mappings.
2. On boot, the Pico sends a UDP broadcast announcing itself.
3. The **Blazor Server Web App** listens for these broadcasts and establishes a TCP session.
4. Relays can be toggled remotely via web dashboard or locally with buttons.
5. Communication is message-driven and persistent across sessions.

---

## 🔧 Getting Started

### Prerequisites

- .NET 9 SDK
- Raspberry Pi Pico W (with MicroPython 1.25+)
- Visual Studio 2022 or `dotnet` CLI
- Wi-Fi network that supports broadcast and TCP

### Build and Run

1. Clone the repo:
   ```bash
   git clone https://github.com/your-user/RV-Electrical-Automation.git
   cd RV-Electrical-Automation
   ```

2. Build and run the Blazor Web App:
   ```bash
   dotnet run --project AutomationWeb
   ```

3. Flash MicroPython to each Pico and deploy the config + firmware in `PicoAutomation`.

---

## 📄 Configuration Example (`config.json`)

```json
{
  "wifi_ssid": "YourSSID",
  "wifi_password": "YourPassword",
  "target_id": "Pico1",
  "UdpPort": 5000,
  "TcpPort": 5001,
  "relays": [
    { "id": "relay1", "label": "Water Pump", "relay_pin": 0, "button_pin": 9 },
    { "id": "relay2", "label": "Heater", "relay_pin": 1, "button_pin": 10 }
  ]
}
```

---

## 📦 Deployment

- Use Visual Studio to publish `AutomationWeb` to Raspberry Pi or Windows server.
- Deploy MicroPython code using Thonny or rshell to each Pico device.
- Ensure each Pico is on the same Wi-Fi network as the Blazor server.

---

## 🔐 Security Notes

- Consider adding authentication for dashboard access.
- Validate TCP commands on the server before acting.

---

## 🛠 Future Enhancements

- Web-based configuration tool
- Firmware over-the-air updates (OTA)
- Role-based access and audit logging
- Integration with Home Assistant or MQTT

---

## 📬 Contributions

Open to pull requests and collaboration. Modular design encourages expansion.

---

## 📄 License

MIT License. See `LICENSE` file for details.
