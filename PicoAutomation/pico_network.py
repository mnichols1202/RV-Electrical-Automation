import uasyncio as asyncio
import network
import socket
import json
import utime
import time
import rp2
from machine import Pin

class NetworkManager:
    def __init__(self, network_config, message_queue, queue_lock):
        cfg = network_config['config']
        self.ssid            = cfg['wifi_ssid']
        self.password        = cfg['wifi_password']
        self.target_id       = cfg['target_id']
        self.udp_port        = cfg['UdpPort']
        self.tcp_port        = cfg['TcpPort']
        self.ntpserver       = cfg.get('ntpserver', 'pool.ntp.org')
        self.timezone_offset = cfg.get('timezone', 0) * 3600
        self.debug           = cfg.get('debug', False)
        self.ip              = None
        self.macaddress      = None
        self.server_ip       = None
        self.server_tcp_port = None
        self.devices         = network_config.get('devices', [])
        self.message_queue   = message_queue
        self.queue_lock      = queue_lock
        self.time_set        = False  # Track if time has been set

    def debug_print(self, *args):
        if self.debug:
            message = ' '.join(str(arg) for arg in args)
            print(message)
            try:
                with open("bootlog.txt", "a") as f:
                    f.write(message + "\n")
            except Exception as e:
                print("Failed to write to log file:", e)
                
    def flash_led(self, num_flashes, interval=0.5):
        """
        Flashes the onboard LED on Raspberry Pi Pico W a specified number of times.
        
        Parameters:
            num_flashes (int): Number of times to flash the LED.
            interval (float): Time in seconds for each on/off state (default is 0.5 seconds).
        """
        # Initialize the onboard LED for Pico W
        led = Pin("LED", Pin.OUT)
        
        # Flash the LED the specified number of times
        for _ in range(num_flashes):
            led.on()  # Turn LED on
            utime.sleep(interval)  # Wait
            led.off()  # Turn LED off
            utime.sleep(interval)  # Wait
        
    def current_timestamp(self):
        utc = time.time()
        tm  = time.localtime(utc + self.timezone_offset)
        sign = "+" if self.timezone_offset >= 0 else "-"
        hh = abs(int(self.timezone_offset // 3600))
        mm = abs(int((self.timezone_offset % 3600) // 60))
        tz = f"{sign}{hh:02d}:{mm:02d}"
        return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}{}".format(
            tm[0], tm[1], tm[2], tm[3], tm[4], tm[5], tz
        )

    def set_time(self):
        """Attempt to set the time via NTP. Set flag if successful."""
        import ntptime
        self.debug_print("Setting Time:")
        ntptime.host = self.ntpserver
        for attempt in range(1, 6):
            try:
                ntptime.settime()
                self.debug_print(f"NTP time set successfully on attempt {attempt}")
                self.time_set = True
                return True
            except Exception as e:
                self.debug_print(f"NTP settime failed (attempt {attempt}):", e)
                utime.sleep(1)
        self.debug_print("NTP time sync failed after 5 attempts. Continuing with current time.")
        return False

    def connect_wifi(self):
        self.flash_led(5, 0.1)
        rp2.country("US")  # Set country code for Wi-Fi
        network.country("US")   
        wlan = network.WLAN(network.STA_IF)
        wlan.config(pm=0x00000000)
        if wlan.isconnected():
            self.ip = wlan.ifconfig()[0]
            self.debug_print("Already connected. WiFi IP:", self.ip)
            # Only set time if not already set
            if not self.time_set:
                self.set_time()
            return True
        wlan.active(True)
        mac = wlan.config('mac')
        self.macaddress = ':'.join(['{:02x}'.format(b) for b in mac])
        wlan.connect(self.ssid, self.password)
        self.debug_print("WiFi Attempting to Connect")
        while not wlan.isconnected():
            status = wlan.status()
            self.debug_print(f"Status: {status}")
            if status in (-1, -2):
                self.flash_led(abs(status), 0.1)
                wlan.active(False)
                utime.sleep(0.5)
                wlan.active(True)
                utime.sleep(0.5)
                wlan.connect(self.ssid, self.password)
                self.debug_print("WiFi Attempting to Connect Again")
            utime.sleep(0.5)
        self.ip = wlan.ifconfig()[0]
        self.debug_print("WiFi IP:", self.ip)
        # Only set time if not already set
        if not self.time_set:
            self.set_time()
        return True

    def udp_announce(self):
        msg = {
            "action":    "announce",
            "id":        self.target_id,
            "ip":        self.ip,
            "mac":       self.macaddress,
            "timestamp": self.current_timestamp()
        }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast = self.ip.rsplit('.', 1)[0] + '.255'
        for attempt in range(1, 6):
            try:
                self.debug_print(f"UDP announce attempt {attempt} → {broadcast}")
                sock.sendto(json.dumps(msg).encode(), (broadcast, self.udp_port))
                sock.settimeout(5)
                data, _ = sock.recvfrom(1024)
                resp = json.loads(data.decode())
                if resp.get("action") == "ack" and resp.get("id") == self.target_id:
                    self.server_ip = resp.get("Serverip")
                    self.server_tcp_port = resp.get("Serverport")
                    self.debug_print("Got ACK:", json.dumps(resp))
                    sock.close()
                    return True
            except OSError as e:
                self.debug_print(f"UDP announce failed (attempt {attempt}):", e)
                utime.sleep(1)
        sock.close()
        return False

    async def tcp_receive_loop(self, reader):
        while True:
            try:
                line = await reader.readline()
                if not line:
                    self.debug_print("TCP disconnected by server.")
                    break

                # Parse the JSON message
                msg = json.loads(line.decode())

                # Validate required fields
                if "type" not in msg or "data" not in msg:
                    self.debug_print("Invalid message format:", msg)
                    continue

                # Handle message types
                message_type = msg["type"]
                if message_type == "status":
                    self.handle_status_message(msg["data"])
                elif message_type == "command":
                    self.handle_command_message(msg["data"])
                elif message_type == "heartbeat":
                    self.handle_heartbeat_message(msg["data"])
                else:
                    self.debug_print(f"Unknown message type: {message_type}")
            except Exception as e:
                self.debug_print("TCP receive error:", e)
                break

    async def tcp_send_loop(self, writer):
        while True:
            # Wait for a message to send (simulate with a queue)
            if self.message_queue:
                self.queue_lock.acquire()
                try:
                    msg = self.message_queue.pop(0)
                finally:
                    self.queue_lock.release()
                writer.write((json.dumps(msg) + "\n").encode())
                await writer.drain()
                self.debug_print("Sent to server:", msg)
            await asyncio.sleep(0.1)  # Prevent busy loop

    async def tcp_run_async(self):
        for attempt in range(1, 6):
            try:
                self.debug_print(f"TCP connect attempt {attempt} → {self.server_ip}:{self.tcp_port}")
                reader, writer = await asyncio.open_connection(self.server_ip, self.tcp_port)
                self.debug_print("TCP connection established (async).")
                # Run send and receive loops concurrently
                await asyncio.gather(
                    self.tcp_receive_loop(reader),
                    self.tcp_send_loop(writer)
                )
                writer.close()
                await writer.wait_closed()
                return True
            except Exception as e:
                self.debug_print(f"TCP async error (attempt {attempt}):", e)
                await asyncio.sleep(2)
        return False

    async def run_network_loop_async(self):
        while True:
            # Wi-Fi connect (sync)
            if not self.connect_wifi():
                self.debug_print("WiFi not connected. Retrying in 2 seconds...")
                await asyncio.sleep(2)
                continue

            # UDP announce (sync)
            if not self.udp_announce():
                self.debug_print("UDP announce failed. Restarting network loop.")
                await asyncio.sleep(2)
                continue

            # TCP run loop (async)
            if not await self.tcp_run_async():
                self.debug_print("TCP connection failed. Restarting network loop.")
                await asyncio.sleep(2)
                continue

    def connect_wifi_with_backoff(self):
        backoff = 1  # Start with 1 second
        max_backoff = 30  # Cap at 30 seconds
        while True:
            if self.connect_wifi():
                return True
            self.debug_print(f"Wi-Fi connection failed. Retrying in {backoff} seconds...")
            utime.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)  # Exponential backoff

    def udp_announce_with_backoff(self):
        backoff = 1  # Start with 1 second
        max_backoff = 30  # Cap at 30 seconds
        failed_attempts = 0
        while True:
            if self.udp_announce():
                return True
            failed_attempts += 1
            if failed_attempts >= 10:
                self.debug_print("Pausing UDP announcements for 1 minute...")
                utime.sleep(60)  # Pause for 1 minute
                failed_attempts = 0
            else:
                self.debug_print(f"UDP announcement failed. Retrying in {backoff} seconds...")
                utime.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)  # Exponential backoff

    def handle_status_message(self, data):
        """Handle status messages from the server."""
        self.debug_print("Status message received:", data)
        # Process status updates here (e.g., log or update local state)

    def handle_command_message(self, data):
        """Handle command messages from the server."""
        self.debug_print("Command message received:", data)
        devices = data.get("devices", [])
        for device in devices:
            if device.get("device_type") == "relay":
                label = device.get("label")
                state = device.get("state")
                if label and state:
                    self.relay_toggle.toggle_relay(label, state)
                else:
                    self.debug_print("Invalid relay command:", device)

    def handle_heartbeat_message(self, data):
        """Handle heartbeat messages from the server."""
        self.debug_print("Heartbeat message received:", data)
        # Optionally, send a response or log the heartbeat

    async def tcp_run_with_recovery(self):
        while True:
            if await self.tcp_run_async():
                return True
            self.debug_print("TCP connection failed. Retrying...")
            await asyncio.sleep(5)  # Retry after 5 seconds

