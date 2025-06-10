import uasyncio
import network
import usocket
import ujson
import machine
import time
import gc

class PicoNetwork:
    def __init__(self, debug=False):
        self.wlan = network.WLAN(network.STA_IF)
        self.console_ip = None
        self.console_port = None
        self.ack_received = False
        self.tcp_sock = None
        self.relay_configs = []
        self.led = machine.Pin("LED", machine.Pin.OUT)
        self.led.off()
        self.debug = debug
        if self.debug:
            print("[DEBUG] PicoNetwork initialized")

    def load_config(self):
        if self.debug:
            print("[DEBUG] Loading configuration from config.json")
        try:
            with open('config.json', 'r') as f:
                config = ujson.load(f)
            self.wifi_ssid = config['wifi_ssid']
            self.wifi_password = config['wifi_password']
            self.target_id = config['target_id']
            self.udp_port = config['UdpPort']
            self.tcp_port = config['TcpPort']
            self.relay_configs = config['relays']
            if self.debug:
                print(f"[DEBUG] Config loaded successfully: SSID={self.wifi_ssid}, TargetID={self.target_id}, UDPPort={self.udp_port}, TCPPort={self.tcp_port}, Relays={len(self.relay_configs)}")
            return True
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] Config load error: {e}")
            return False

    def get_mac(self):
        mac = self.wlan.config('mac')
        mac_str = ':'.join('{:02X}'.format(b) for b in mac)
        if self.debug:
            print(f"[DEBUG] MAC address retrieved: {mac_str}")
        return mac_str

    async def send_device_info(self):
        mac = self.get_mac()
        ip = self.wlan.ifconfig()[0]
        payload = {
            "type": "device_info",
            "mac": mac,
            "target_id": self.target_id,
            "ip": ip,
            "firmware": "v1.0",
            "relays": [
                {"id": r["id"], "label": r["label"]} for r in self.relay_configs
            ]
        }
        payload_str = ujson.dumps(payload)
        if self.debug:
            print(f"[DEBUG] Sending device info: IP={ip}, MAC={mac}, Payload={payload_str}")
        await self.send_message(payload_str)

    async def send_heartbeat(self):
        mac = self.get_mac()
        ip = self.wlan.ifconfig()[0]
        payload = {
            "type": "heartbeat",
            "target_id": self.target_id,
            "mac": mac,
            "uptime": time.ticks_ms() / 1000  # Uptime in seconds
        }
        payload_str = ujson.dumps(payload)
        if self.debug:
            print(f"[DEBUG] Sending heartbeat: IP={ip}, MAC={mac}, Uptime={payload['uptime']:.1f}s, Payload={payload_str}")
        await self.send_message(payload_str)

    async def handle_incoming(self, relay_toggle):
        if self.debug:
            print("[DEBUG] Starting incoming message handler")
        while True:
            if self.tcp_sock:
                try:
                    data = self.tcp_sock.recv(1024)
                    if data:
                        if self.debug:
                            print(f"[DEBUG] Raw data received: {data}")
                        message = ujson.loads(data.decode())
                        if self.debug:
                            print(f"[DEBUG] Decoded message: {message}")
                        if message['type'] == 'command':
                            for r in relay_toggle.relays:
                                if r['label'] == message['label']:
                                    r['state'] = message['state']
                                    r['relay'].value(message['state'])
                                    if self.debug:
                                        print(f"[DEBUG] Relay command executed: Label={message['label']}, State={message['state']}")
                                    break
                    else:
                        if self.debug:
                            print("[DEBUG] TCP connection closed by remote")
                        self.tcp_sock.close()
                        self.tcp_sock = None
                except Exception as e:
                    if self.debug:
                        print(f"[DEBUG] Receive error: {e}")
                        self.tcp_sock.close()
                    self.tcp_sock = None
                    if self.debug:
                        print("[DEBUG] TCP socket closed due to error")
                        await uasyncio.sleep(0.1)
                        
    async def blink_led_while_connecting(self, stop_event):
        print("Blinking LED while connecting...")
        while not stop_event.is_set():
            self.led.toggle()
            await uasyncio.sleep(0.3)
        self.led.off()
  
    async def connect_wifi(self):
        print('Starting connect_wifi')
        print(f'Free memory: {gc.mem_free()} bytes')
        if not self.load_config():
            self.led.off()
            return False

        if self.wlan.isconnected():
            print(f'Already connected: {self.wlan.ifconfig()}')
            self.led.on()
            return True

        print('Scanning for Wi-Fi networks...')
        try:
            self.wlan.active(True)
            await uasyncio.sleep(2)
            nets = self.wlan.scan()
            ssids = [net[0].decode() for net in nets]
            if self.wifi_ssid not in ssids:
                print(f'SSID {self.wifi_ssid} not found')
                self.led.off()
                return False
            print("Available SSIDs:")
            for net in nets:
                print(f"- {net[0].decode()} (RSSI: {net[3]} dBm)")
        except Exception as e:
            print(f'Scan error: {e}')
            self.led.off()
            return False

        for attempt in range(3):
            print(f'Wi-Fi attempt {attempt + 1}')

            try:
                print("Resetting Wi-Fi interface completely...")
                self.wlan.disconnect()
                await uasyncio.sleep(1)
                self.wlan.active(False)
                await uasyncio.sleep(5)
                self.wlan = network.WLAN(network.STA_IF)
                self.wlan.active(True)
                await uasyncio.sleep(2)

                # Optional: Disable low power mode
                try:
                    import rp2
                    rp2.country('US')
                    self.wlan.config(pm=0xa11140)
                except Exception as e:
                    print(f'Power save disable failed: {e}')

                self.wlan.connect(self.wifi_ssid, self.wifi_password)
            except Exception as e:
                print(f'Connect exception: {e}')
                continue

            stop_blink_event = uasyncio.Event()
            uasyncio.create_task(self.blink_led_while_connecting(stop_blink_event))

            for i in range(20):  # 10 seconds
                if self.wlan.isconnected():
                    print(f'Connected: {self.wlan.ifconfig()}')
                    stop_blink_event.set()
                    self.led.on()
                    print(f'Free memory after connection: {gc.mem_free()} bytes')
                    return True
                print(f'Waiting... ({i * 0.5}s), status={self.wlan.status()}')
                await uasyncio.sleep(0.5)

            stop_blink_event.set()
            await uasyncio.sleep(1)
            print('Timeout, retrying...')

        print('Wi-Fi failed')
        self.led.off()
        return False
    async def broadcast_announcement(self):
        if self.debug:
            print("[DEBUG] Starting UDP broadcast announcement")
        sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_BROADCAST, 1)
        pico_ip = self.wlan.ifconfig()[0]
        msg = f'{self.target_id}: {pico_ip}'
        broadcast_ip = pico_ip.rsplit('.', 1)[0] + '.255'
        if self.debug:
            print(f"[DEBUG] Broadcasting announcement: TargetID={self.target_id}, IP={pico_ip}, BroadcastIP={broadcast_ip}, UDPPort={self.udp_port}, Message={msg}")
        for attempt in range(3):
            sock.sendto(msg.encode(), (broadcast_ip, self.udp_port))
            if self.debug:
                print(f"[DEBUG] Broadcast attempt {attempt + 1}/3 sent: {msg}")
            try:
                sock.settimeout(2.0)
                data, addr = sock.recvfrom(64)
                if self.debug:
                    print(f"[DEBUG] Raw UDP data received from {addr}: {data}")
                if data.decode().startswith("ACK:"):
                    parts = data.decode().split(" ")
                    self.console_ip = parts[1]
                    self.console_port = int(parts[2])
                    self.ack_received = True
                    if self.debug:
                        print(f"[DEBUG] ACK received from {self.console_ip}:{self.console_port}, Decoded: {data.decode()}")
                    sock.close()
                    return True
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] Broadcast attempt {attempt + 1}/3 failed: {e}")
            await uasyncio.sleep(1)
        sock.close()
        if self.debug:
            print("[DEBUG] Broadcast announcement failed after 3 attempts")
        return False

    async def establish_tcp(self):
        if self.debug:
            print(f"[DEBUG] Establishing TCP connection to {self.console_ip}:{self.console_port}")
        self.tcp_sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        try:
            self.tcp_sock.connect((self.console_ip, self.console_port))
            if self.debug:
                print(f"[DEBUG] TCP connection established to {self.console_ip}:{self.console_port}")
            return True
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] TCP connection error: {e}")
            self.tcp_sock.close()
            self.tcp_sock = None
            if self.debug:
                print("[DEBUG] TCP socket closed due to connection failure")
            return False

    async def send_message(self, message):
        if self.tcp_sock:
            try:
                encoded_message = (message + '\n').encode()
                self.tcp_sock.send(encoded_message)
                if self.debug:
                    print(f"[DEBUG] TCP message sent: {message} (Raw: {encoded_message})")
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] Send failed: {e}")
                self.tcp_sock.close()
                self.tcp_sock = None
                if self.debug:
                    print("[DEBUG] TCP socket closed due to send failure")

    def is_connected(self):
        connected = self.wlan.isconnected() and self.tcp_sock is not None and self.ack_received
        if self.debug:
            print(f"[DEBUG] Connection status: WiFi={'Connected' if self.wlan.isconnected() else 'Disconnected'}, "
                  f"TCP={'Active' if self.tcp_sock is not None else 'Inactive'}, "
                  f"ACK={'Received' if self.ack_received else 'Not received'}, "
                  f"Overall={'Connected' if connected else 'Disconnected'}")
        return connected

    async def start(self):
        if self.debug:
            print("[DEBUG] Starting PicoNetwork")
        self.ack_received = False
        if not self.load_config():
            if self.debug:
                print("[DEBUG] Startup failed: Configuration load failed")
            return
        if not await self.connect_wifi():
            if self.debug:
                print("[DEBUG] Startup failed: WiFi connection failed")
            return
        if not await self.broadcast_announcement():
            if self.debug:
                print("[DEBUG] Startup failed: Broadcast announcement failed")
            return
        if not await self.establish_tcp():
            if self.debug:
                print("[DEBUG] Startup failed: TCP connection failed")
            return
        if self.debug:
            print("[DEBUG] PicoNetwork startup completed successfully")
