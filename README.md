# RV Electrical Automation

**RV Electrical Automation** is a modular automation system for managing electrical components in an RV using Wi-Fi-enabled Raspberry Pi Pico W devices and a .NET 9 Blazor Server web application. Each Pico controls relays and communicates with a central dashboard over the network.

---

## Features

- Real-time control of RV components via web dashboard
- Auto-discovery of Pico devices using UDP broadcast
- Reliable TCP command/control communication
- JSON-configured relay mapping with labeled outputs
- Dynamic UI generation based on device configuration
- Physical button toggle support on the Pico
- Multi-device support using unique `target_id` values

---

## Project Structure

```
RV-Electrical-Automation/
├── AutomationWeb/              # Blazor Server web application
│   ├── Components/             # Razor UI components
│   ├── Services/               # TCP/UDP network logic
│   └── wwwroot/                # Static files (CSS, JS)
├── PicoFramework/              # MicroPython code for Raspberry Pi Pico W
│   ├── config.json             # Device and relay configuration
│   ├── main.py                 # Entry point
│   ├── pico_network.py         # Networking logic
│   └── relay_toggle.py         # GPIO relay control
└── RV-Electrical-Automation.sln
```

---

## Device Configuration (`config.json`)

Each Pico is configured using a `config.json` file:

```json
{
  "wifi_ssid": "YourSSID",
  "wifi_password": "YourPassword",
  "target_id": "PicoW1",
  "UdpPort": 5000,
  "TcpPort": 5001,
  "relays": [
    { "id": "relay1", "label": "Water Heater", "relay_pin": 0, "button_pin": 19 },
    { "id": "relay2", "label": "Water Pump", "relay_pin": 1, "button_pin": 18 },
    { "id": "relay3", "label": "Exterior Lights", "relay_pin": 2, "button_pin": 17 },
    { "id": "relay4", "label": "Interior Lights", "relay_pin": 3, "button_pin": 16 }
  ]
}
```

- `target_id`: Unique name to identify the device on the network
- `relays`: Array of relay/button mappings with GPIO assignments and display labels

---

## Communication Protocol

| Protocol | Port  | Purpose                      |
|----------|-------|------------------------------|
| UDP      | 5000  | Device broadcasts availability on startup |
| TCP      | 5001  | Server sends/receives commands to/from Pico |

---

## Getting Started

### Hardware Requirements

- Raspberry Pi Pico W
- Relay modules (3.3V logic)
- Optional: momentary push-buttons
- Shared Wi-Fi network with the server

### Raspberry Pi Setup

1. Flash MicroPython to the Pico W
2. Upload all files from `PicoFramework/` to the device
3. Update `config.json` with Wi-Fi and relay settings
4. Reboot the device

### Server Setup

1. Open `RV-Electrical-Automation.sln` in Visual Studio 2022+
2. Build and run the `AutomationWeb` project
3. Open a browser to `http://localhost:<port>` to access the UI
4. Connected devices and their relays will appear automatically

---

## Operation Flow

1. Pico connects to Wi-Fi and broadcasts its `target_id` over UDP
2. Server listens and establishes a TCP connection
3. Pico sends its relay configuration to the server
4. UI is generated using relay labels from the config
5. User interacts with the UI to toggle relays
6. Server sends commands via TCP
7. Pico updates GPIO states and optionally responds

---

## Roadmap

- [ ] Add persistent storage (SQL or LiteDB)
- [ ] Implement user authentication
- [ ] Add real-time status and telemetry display
- [ ] Define automation rules or timers
- [ ] Improve mobile UI support

---

## License

This project is licensed under the MIT License.

---

## Contributions

Contributions, suggestions, and testing are welcome. This system is under active development for real-world RV use.

