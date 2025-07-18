# main.py (paired with pico_network.py for Wi-Fi + UDP + TCP, with simulated toggles)
import json
import time
import _thread  # For lock and simulation thread
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

message_queue = []  # List-based queue for status_updates (simulated now, real from relay_toggle later)
queue_lock = _thread.allocate_lock()  # Lock for thread-safe access

network_manager = NetworkManager(config, message_queue, queue_lock)

# Simulation loop for mock button toggles (remove when integrating relay_toggle.py)
def simulate_toggles():
    relay_labels = [relay['label'] for relay in config['relays']]  # Use labels from config
    state = "OFF"  # Toggle state
    i = 0
    while True:
        label = relay_labels[i % len(relay_labels)]  # Cycle through relays
        state = "ON" if state == "OFF" else "OFF"
        message = {"type": "status_update", "label": label, "state": state}
        with queue_lock:
            message_queue.append(message)  # Thread-safe enqueue
        print(f"Simulated toggle: {label} to {state}")
        i += 1
        time.sleep(10)  # Simulate every 10s

# Start simulation in a separate thread (non-blocking for network loop)
_thread.start_new_thread(simulate_toggles, ())

# Run the self-contained network loop
network_manager.run_network_loop()
