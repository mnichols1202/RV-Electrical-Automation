# main.py (integrated with relay_toggle and network)
import json
import time
import uasyncio
import _thread  # For lock and threading network loop
from relay_toggle import RelayToggle
from pico_network import NetworkManager

def load_config(filename='config.json'):
    defaults = {
        'config': {
            'wifi_ssid': '',
            'wifi_password': '',
            'target_id': 'default_pico',
            'UdpPort': 5000,
            'TcpPort': 5001,
            'ntpserver': 'pool.ntp.org',
            'timezone': 0  // Default UTC
        },
        'devices': []
    }
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        print(f"Loaded config")
        required_keys = ['config', 'devices']  # Top-level keys
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing key: {key}")
        # Validate nested 'config' keys
        nested_required = ['wifi_ssid', 'wifi_password', 'target_id', 'UdpPort', 'TcpPort', 'ntpserver', 'timezone']
        for key in nested_required:
            if key not in config['config']:
                raise ValueError(f"Missing nested key in 'config': {key}")
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

# Setup network (with shared queue/lock); pass full config
network_manager = NetworkManager(config, message_queue, queue_lock)

# Setup relay_toggle (with shared queue/lock, and comm = network_manager for publish if needed)
relay_toggle = RelayToggle(network_manager, config['devices'], message_queue, queue_lock)
relay_toggle.setup()  # Sets up IRQs

# Link relay_toggle instance to network_manager
network_manager.relay_toggle = relay_toggle

# Run network loop in a thread (non-blocking)
_thread.start_new_thread(network_manager.run_network_loop, ())

# Keep main thread alive (no async loop needed since queuing is handled in network thread)
while True:
    time.sleep(1)