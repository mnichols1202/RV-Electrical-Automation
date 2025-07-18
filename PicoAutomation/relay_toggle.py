# relay_toggle.py
from machine import Pin
import time
import uasyncio

class RelayToggle:
    def __init__(self, comm, relay_configs, message_queue, queue_lock):
        """Initialize buttons and relays based on configurations."""
        self.comm = comm  # Network communication object (optional, can be set later)
        self.relays = []
        self.message_queue = message_queue  # Shared with network
        self.queue_lock = queue_lock  # Shared lock for thread-safety
        self.debounce_ms = 200

        print("Initializing RelayToggle")
        for config in relay_configs:
            try:
                button_pin = config['button_pin']
                relay_pin = config['relay_pin']
                label = config['label']
                if not (0 <= button_pin <= 28 and 0 <= relay_pin <= 28):
                    raise ValueError(f"Invalid GPIO pin: button={button_pin}, relay={relay_pin}")

                button = Pin(button_pin, Pin.IN, Pin.PULL_DOWN)
                relay = Pin(relay_pin, Pin.OUT)
                relay.value(0)

                self.relays.append({
                    'button': button,
                    'relay': relay,
                    'label': label,
                    'state': False,
                    'last_press': 0
                })

                print(f"Initialized: {label} | Button GP{button_pin} | Relay GP{relay_pin}")
            except Exception as e:
                print(f"Error initializing {config.get('label', 'unknown')}: {e}")

    def get_relay_state(self, relay_info):
        """Return a formatted string of the relay's state."""
        return f"{relay_info['label']} {'ON' if relay_info['state'] else 'OFF'}"

    async def send_queued_messages(self):
        """Send messages from the queue asynchronously if comm is available."""
        print('Starting send_queued_messages loop')
        while True:
            with self.queue_lock:
                if self.message_queue:
                    message = self.message_queue.pop(0)
                    print(f"Sending message: {message}")
                    # Use comm's publish if available (for network)
                    if self.comm and self.comm.is_connected():
                        await self.comm.publish(message)  # Use comm's publish method
            await uasyncio.sleep(0.1)

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
                        # Enqueue JSON dict instead of string
                        message = {"type": "status_update", "label": relay_info['label'], "state": "ON" if relay_info['state'] else "OFF"}
                        print(f"Toggled: {relay_info['label']} to {message['state']}")
                        with self.queue_lock:
                            self.message_queue.append(message)
                break

    def setup(self):
        """Set up IRQ handlers and initial messages."""
        print("Setting up IRQs for relays")
        for relay_info in self.relays:
            try:
                relay_info['button'].irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
                # Enqueue initial JSON status
                message = {"type": "status_update", "label": relay_info['label'], "state": "ON" if relay_info['state'] else "OFF"}
                print(f"Initial state: {relay_info['label']} {message['state']}")
                with self.queue_lock:
                    self.message_queue.append(message)
            except Exception as e:
                print(f"IRQ setup failed for {relay_info['label']}: {e}")