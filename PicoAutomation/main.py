# main.py (integrated with relay_toggle, network, and hardware watchdog)
import json
import time
import uasyncio
import _thread  # For lock and threading network loop
from machine import WDT  # Import hardware watchdog
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
            'timezone': 0, # Default UTC
            'debug': False
        },
        'devices': []
    }
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        print("Loaded config")
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
        print("File not found. Using defaults.")
        return defaults
    except ValueError as e:  # MicroPython json raises ValueError for decode errors
        print(f"Config error: {e}. Using defaults.")
        return defaults

config = load_config()

message_queue = []  # Shared list for status_updates
queue_lock = _thread.allocate_lock()  # Lock for thread-safety

# Setup hardware watchdog (8 seconds timeout)
# wdt = WDT(timeout=8000)

# Setup network (with shared queue/lock); pass full config
network_manager = NetworkManager(config, message_queue, queue_lock)

# Setup relay_toggle (with shared queue/lock, and comm = network_manager for publish if needed)
relay_toggle = RelayToggle(network_manager, config['devices'], message_queue, queue_lock)
relay_toggle.setup()  # Sets up IRQs

# Link relay_toggle instance to network_manager
network_manager.relay_toggle = relay_toggle

print("Run Network Loop (uasyncio)")
uasyncio.run(network_manager.run_network_loop_async())

# Keep main thread alive and feed the watchdog
while True:
#    wdt.feed()  # Feed the watchdog to prevent reset
    time.sleep(1)
