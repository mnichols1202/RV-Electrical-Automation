# main.py (integrated with relay_toggle and network)
import json
import time
import uasyncio
import _thread  # For lock and threading network loop
from relay_toggle import RelayToggle
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

message_queue = []  # Shared list for status_updates
queue_lock = _thread.allocate_lock()  # Lock for thread-safety

# Setup network (with shared queue/lock)
network_manager = NetworkManager(config, message_queue, queue_lock)

# Setup relay_toggle (with shared queue/lock, and comm = network_manager for publish)
relay_toggle = RelayToggle(network_manager, config['relays'], message_queue, queue_lock)
relay_toggle.setup()  # Sets up IRQs

# Run network loop in a thread (non-blocking for relay async)
_thread.start_new_thread(network_manager.run_network_loop, ())

# Run relay async loop
async def main_loop():
    await relay_toggle.send_queued_messages()

uasyncio.run(main_loop())