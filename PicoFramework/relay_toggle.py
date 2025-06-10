from machine import Pin
import time
import uasyncio
import ujson

class RelayToggle:
    def __init__(self, wifi, relay_configs, debug=False):
        self.wifi = wifi
        self.relays = []
        self.message_queue = []
        self.debounce_ms = 200
        self.debug = debug

        for config in relay_configs:
            button = Pin(config['button_pin'], Pin.IN)
            relay = Pin(config['relay_pin'], Pin.OUT)
            relay.value(0)
            self.relays.append({
                'id': config['id'],
                'label': config['label'],
                'button': button,
                'relay': relay,
                'state': False,
                'last_press': 0
            })

    def setup(self):
        if self.debug:
            print("Setting up relays")
        for r in self.relays:
            r['button'].irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
            self.message_queue.append(ujson.dumps({
                "type": "relay_status",
                "target_id": self.wifi.target_id,
                "mac": self.wifi.get_mac(),
                "id": r['id'],
                "label": r['label'],
                "state": r['state']
            }))

    def button_handler(self, pin):
        now = time.ticks_ms()
        for r in self.relays:
            if r['button'] == pin:
                if time.ticks_diff(now, r['last_press']) < self.debounce_ms:
                    if self.debug:
                        print(f"Debounced button press for {r['label']}")
                    return
                if pin.value() == 0:
                    if self.debug:
                        print(f"Ignoring button release for {r['label']}")
                    return
                r['state'] = not r['state']
                r['relay'].value(r['state'])
                r['last_press'] = now
                self.message_queue.append(ujson.dumps({
                    "type": "toggle",
                    "target_id": self.wifi.target_id,
                    "mac": self.wifi.get_mac(),
                    "id": r['id'],
                    "label": r['label'],
                    "state": r['state']
                }))

    async def send_queued_messages(self):
        while True:
            if self.message_queue and self.wifi.is_connected():
                msg = self.message_queue.pop(0)
                if self.debug:
                    print(f"Sending queued message: {msg}")
                await self.wifi.send_message(msg)
            await uasyncio.sleep(0.1)