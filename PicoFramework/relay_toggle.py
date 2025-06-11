# relay_toggle.py
from machine import Pin
import time
import uasyncio

class RelayToggle:
    def __init__(self, wifi, relay_configs):
        """Initialize buttons and relays based on configurations."""
        self.wifi = wifi  # PicoNetwork instance for sending messages
        self.relays = []
        self.message_queue = []
        self.debounce_ms = 200

        print("Initializing RelayToggle")
        for config in relay_configs:
            try:
                button_pin = config['button_pin']
                relay_pin = config['relay_pin']
                label = config['label']
                if not (0 <= button_pin <= 28 and 0 <= relay_pin <= 28):
                    raise ValueError(f"Invalid GPIO pin: button={button_pin}, relay={relay_pin}")
                button = Pin(button_pin, Pin.IN)
                print(f"Button GP{button_pin} initial state: {'HIGH' if button.value() else 'LOW'}")
                relay = Pin(relay_pin, Pin.OUT)
                relay.value(0)
                self.relays.append({
                    'button': button,
                    'relay': relay,
                    'label': label,
                    'state': False,
                    'last_press': 0
                })
                print(f"Initialized relay: {label} (Button: GP{button_pin}, Relay: GP{relay_pin})")
            except Exception as e:
                print(f"Error initializing relay {config.get('label', 'unknown')}: {e}")

    def get_relay_state(self, relay_info):
        """Return current relay state as a string."""
        return f"{relay_info['label']} {'ON' if relay_info['state'] else 'OFF'}"

    async def send_queued_messages(self):
        """Process messages in the queue asynchronously."""
        print('Starting send_queued_messages')
        while True:
            if self.message_queue:
                message = self.message_queue.pop(0)
                print(f"Sending queued message: {message}")
                if self.wifi:
                    try:
                        response = await self.wifi.send_message(message)
                        print(f"Received response: {response}")
                    except Exception as e:
                        print(f"Error sending message: {e}")
            await uasyncio.sleep(0.1)

    def button_handler(self, pin):
        """Interrupt handler for button press."""
        print(f"Interrupt triggered on pin {pin}")
        current_time = time.ticks_ms()
        for relay_info in self.relays:
            if relay_info['button'] == pin:
                print(f"Button match for {relay_info['label']}, pin value: {'HIGH' if pin.value() else 'LOW'}")
                if pin.value() == 0:  # Skip if pin is LOW
                    print(f"Ignoring interrupt on LOW for {relay_info['label']}")
                    return
                if (current_time - relay_info['last_press']) > self.debounce_ms:
                    print(f"Valid button press for {relay_info['label']}")
                    relay_info['state'] = not relay_info['state']
                    relay_info['relay'].value(relay_info['state'])
                    message = self.get_relay_state(relay_info)
                    print(f"RelayToggle: {message}")
                    self.message_queue.append(message)
                    relay_info['last_press'] = current_time
                    # Disable interrupt temporarily
                    relay_info['button'].irq(handler=None)
                    # Wait for button release with timeout
                    start_time = time.ticks_ms()
                    while relay_info['button'].value() == 1 and time.ticks_diff(time.ticks_ms(), start_time) < 1000:
                        time.sleep(0.01)
                    time.sleep(0.05)  # Additional delay for stability
                    # Re-enable interrupt
                    relay_info['button'].irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
                else:
                    print(f"Debounced button press for {relay_info['label']}")
                break
            else:
                print(f"No match for pin {pin} with {relay_info['label']} button")

    def setup(self):
        """Configure interrupts for all buttons and queue initial states."""
        print('Setting up RelayToggle')
        for relay_info in self.relays:
            try:
                relay_info['button'].irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
                print(f"Interrupt configured for {relay_info['label']} on GP{relay_info['button']}")
                message = self.get_relay_state(relay_info)
                print(f"RelayToggle initial state: {message}")
                self.message_queue.append(message)
            except Exception as e:
                print(f"Error setting up interrupt for {relay_info['label']}: {e}")
