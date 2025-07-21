# relay_toggle.py
from machine import Pin
import time
import uasyncio

class RelayToggle:
    def __init__(self, comm, device_configs, message_queue, queue_lock):  # Changed relay_configs to device_configs
        """Initialize buttons and relays based on configurations."""
        self.comm = comm  # Network communication object (optional, can be set later)
        self.relays = []  # Keep as relays for now, but filter by device_type
        self.message_queue = message_queue  # Shared with network
        self.queue_lock = queue_lock  # Shared lock for thread-safety
        self.debounce_ms = 200

        print("Initializing RelayToggle")
        for config in device_configs:
            if config.get('device_type') == 'relay':  # Only process relays for now
                try:
                    button_pin = config['button_pin']
                    relay_pin = config['relay_pin']
                    label = config['label']
                    if not (0 <= button_pin <= 28 and 0 <= relay_pin <= 28):
                        raise ValueError(f"Invalid GPIO pin: button={button_pin}, relay={relay_pin}")

                    button = Pin(button_pin, Pin.IN, Pin.PULL_DOWN)
                    relay = Pin(relay_pin, Pin.OUT)
                    relay.value(0)  # Initial off

                    self.relays.append({
                        'button': button,
                        'relay': relay,
                        'label': label,
                        'state': False,  # Initial state False (off)
                        'last_press': 0
                    })

                    print(f"Initialized relay: {label} | Button GP{button_pin} | Relay GP{relay_pin}")
                except Exception as e:
                    print(f"Error initializing {config.get('label', 'unknown')}: {e}")

    def get_relay_state(self, relay_info):
        """Return a formatted string of the relay's state."""
        return f"{relay_info['label']} {'on' if relay_info['state'] else 'off'}"  # Changed to lowercase

    def button_handler(self, pin):
        """Handle button press via IRQ."""
        current_time = time.ticks_ms()
        for relay_info in self.relays:
            if relay_info['button'] == pin:
                if (current_time - relay_info['last_press']) > self.debounce_ms:
                    # Confirm it's still pressed
                    if pin.value() == 1:
                        relay_info['state'] = not relay_info['state']
                        relay_info['relay'].value(relay_info['state'])
                        relay_info['last_press'] = current_time
                        # Standardized message with "devices" array
                        state_str = "on" if relay_info['state'] else "off"
                        message = {
                            "type": "status",
                            "data": {
                                "devices": [{"device_type": "relay", "label": relay_info['label'], "state": state_str}]
                            }
                        }
                        print(f"Toggled: {relay_info['label']} to {state_str}")
                        with self.queue_lock:
                            self.message_queue.append(message)
                break

    def toggle_relay(self, label, state_str):
        """Toggle relay by label and state (for server commands), enqueue status."""
        for relay_info in self.relays:
            if relay_info['label'] == label:
                state = (state_str.lower() == "on")  # Handle case-insensitivity
                relay_info['state'] = state
                relay_info['relay'].value(state)
                # Standardized message with "devices" array
                state_str_lower = "on" if state else "off"
                message = {
                    "type": "status",
                    "data": {
                        "devices": [{"device_type": "relay", "label": label, "state": state_str_lower}]
                    }
                }
                print(f"Command toggled: {label} to {state_str_lower}")
                with self.queue_lock:
                    self.message_queue.append(message)
                return True
        print(f"Relay not found: {label}")
        return False

    def setup(self):
        """Set up IRQ handlers and initial messages."""
        print("Setting up IRQs for relays")
        for relay_info in self.relays:
            try:
                relay_info['button'].irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
                # Enqueue initial standardized status with "devices" array
                state_str = "on" if relay_info['state'] else "off"
                message = {
                    "type": "status",
                    "data": {
                        "devices": [{"device_type": "relay", "label": relay_info['label'], "state": state_str}]
                    }
                }
                print(f"Initial state: {relay_info['label']} {state_str}")
                with self.queue_lock:
                    self.message_queue.append(message)
            except Exception as e:
                print(f"IRQ setup failed for {relay_info['label']}: {e}")