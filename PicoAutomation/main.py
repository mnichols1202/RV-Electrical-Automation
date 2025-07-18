# main.py (paired with pico_network.py for Wi-Fi + UDP testing)
import json
import time
from pico_network import NetworkManager

def load_config(filename='config.json'):
    defaults = {
        'wifi_ssid': '',
        'wifi_password': '',
        'target_id': 'default_pico',
        'UdpPort': 5000,
        'TcpPort': 5001,
        'relays': []
    }
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        print(f"Loaded config")
        required_keys = ['wifi_ssid', 'wifi_password', 'target_id', 'UdpPort', 'TcpPort', 'relays']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing key: {key}")
        return config
    except OSError:
        print("File not found. Defaults.")
        return defaults
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error: {e}. Defaults.")
        return defaults

config = load_config()

network_manager = NetworkManager(config)  # Mirrors RelayToggle init

# Optional: Scan before running loop
# network_manager.scan_wifi()

# Run the self-contained network loop (sync for standalone; thread for integration)
network_manager.run_network_loop()