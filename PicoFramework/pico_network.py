# pico_network.py
import uasyncio
import time
import network
import usocket
import ujson
import machine
import gc

class PicoNetwork:
    def __init__(self):
        print("Initializing PicoNetwork")
        self.wlan = network.WLAN(network.STA_IF)
        self.console_ip = None
        self.console_port = None
        self.ack_received = False
        self.event_queue = uasyncio.Event()
        self.tcp_sock = None
        self.relay_configs = []

        self.wifi_ssid = None
        self.wifi_password = None
        self.target_id = None
        self.udp_port = None
        self.tcp_port = None

        self.led = machine.Pin("LED", machine.Pin.OUT)
        self.led.off()

    def load_config(self):
        print('Loading config.json')
        try:
            with open('config.json', 'r') as f:
                config = ujson.load(f)
            self.wifi_ssid = config.get('wifi_ssid')
            self.wifi_password = config.get('wifi_password')
            self.target_id = config.get('target_id', 'PicoW1')
            self.udp_port = config.get('UdpPort', 5000)
            self.tcp_port = config.get('TcpPort', 5001)
            self.relay_configs = config.get('relays', [])
            if not self.wifi_ssid or not self.wifi_password:
                print('Error: Missing Wi-Fi credentials')
                return False
            if not self.relay_configs:
                print('Error: No relay configurations found')
                return False
            print(f'Loaded config: SSID={self.wifi_ssid}, TargetID={self.target_id}, Relays={self.relay_configs}')
            return True
        except Exception as e:
            print(f'Config error: {e}')
            return False

    async def reset_wifi_module(self):
        print('Resetting Wi-Fi module')
        self.wlan.active(False)
        await uasyncio.sleep(5)
        self.wlan.active(True)
        await uasyncio.sleep(3)
        print('Wi-Fi module reset complete')

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
        print(f'Broadcasting on {self.udp_port}')
        sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_BROADCAST, 1)

        try:
            pico_ip = self.wlan.ifconfig()[0]
            sock.bind((pico_ip, self.udp_port))
            msg = f'{self.target_id}: {pico_ip}'
            broadcast_ip = pico_ip.rsplit('.', 1)[0] + '.255'

            for _ in range(3):
                sock.sendto(msg.encode(), (broadcast_ip, self.udp_port))
                print('Sent UDP')
                sock.settimeout(2.0)
                try:
                    data, addr = sock.recvfrom(64)
                    msg_received = data.decode()
                    if msg_received.startswith('ACK:'):
                        parts = msg_received.split(' ')
                        if len(parts) >= 2:
                            self.console_ip = parts[1]
                            self.console_port = int(parts[2]) if len(parts) > 2 else self.tcp_port
                            self.ack_received = True
                            print(f'ACK from {addr}')
                            return True
                except OSError:
                    print('No ACK received')
                await uasyncio.sleep(2)
            return False
        except Exception as e:
            print(f'Broadcast error: {e}')
            return False
        finally:
            sock.close()

    async def establish_tcp(self):
        print(f'TCP to {self.console_ip}:{self.console_port}')
        self.tcp_sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        try:
            self.tcp_sock.settimeout(5.0)
            self.tcp_sock.connect((self.console_ip, self.console_port))
            self.tcp_sock.send('Hello from Pico W!'.encode())
            data = self.tcp_sock.recv(64)
            print(f'TCP response: {data.decode() if data else "None"}')
            self.tcp_sock.settimeout(0)
            return True
        except Exception as e:
            print(f'TCP error: {e}')
            try:
                self.tcp_sock.close()
            except:
                pass
            self.tcp_sock = None
            return False

    async def send_message(self, message):
        print(f'Sending: {message}')
        if not self.tcp_sock:
            print('No TCP socket')
            return None
        try:
            self.tcp_sock.send(message.encode())
            start_time = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start_time) < 5000:
                try:
                    data = self.tcp_sock.recv(64)
                    if data:
                        response = data.decode()
                        print(f'Received: {response}')
                        return response
                except OSError as e:
                    if e.args[0] != 11:
                        print(f'Receive error: {e}')
                        return None
                await uasyncio.sleep(0.1)
            return None
        except Exception as e:
            print(f'Send error: {e}')
            try:
                self.tcp_sock.close()
            except:
                pass
            self.tcp_sock = None
            return None

    def is_connected(self):
        if not self.wlan.isconnected() or not self.ack_received or self.tcp_sock is None:
            return False
        try:
            self.tcp_sock.send(b'')
        except OSError:
            try:
                self.tcp_sock.close()
            except:
                pass
            self.tcp_sock = None
            return False
        return True

    async def start(self):
        print('Starting PicoNetwork')
        try:
            self.console_ip = None
            self.console_port = None
            self.ack_received = False
            if self.tcp_sock:
                try:
                    self.tcp_sock.close()
                except:
                    pass
                self.tcp_sock = None
            await self.reset_wifi_module()
            if not await self.connect_wifi():
                return
            await uasyncio.sleep(1)
            if not await self.broadcast_announcement():
                return
            if not await self.establish_tcp():
                return
            print('Network up')
        except Exception as e:
            print(f'Network error: {e}')
 
