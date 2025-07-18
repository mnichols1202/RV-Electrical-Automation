# pico_network.py (version: Wi-Fi + UDP + TCP connection, with thread-safe list queue)
import network
import socket
import time
import json
import rp2  # For country code
from machine import Pin

class NetworkManager:
    def __init__(self, network_config, message_queue, queue_lock):
        """Initialize with config, mirroring RelayToggle style."""
        self.ssid = network_config['wifi_ssid']
        self.password = network_config['wifi_password']
        self.country_code = network_config.get('country_code', 'US')
        self.target_id = network_config['target_id']
        self.udp_port = network_config['UdpPort']
        self.tcp_port = network_config['TcpPort']
        self.relays = network_config['relays']
        self.led = Pin("LED", Pin.OUT)
        self.server_ip = None
        self.server_tcp_port = None
        self.message_queue = message_queue  # Shared list for status_updates
        self.queue_lock = queue_lock  # Shared lock for thread-safety
        self.tcp_sock = None
        self.connected = False
        print("Initialized NetworkManager")

    def failure_blink(self, duration=10, blink_interval=0.1):
        start_time = time.time()
        while time.time() - start_time < duration:
            self.led.value(1)
            time.sleep(blink_interval)
            self.led.value(0)
            time.sleep(blink_interval)
        self.led.value(0)

    def scan_wifi(self):
        """Scan for available networks to verify SSID visibility and RSSI."""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        time.sleep(0.5)
        networks = wlan.scan()
        print("Available networks:")
        found = False
        for net in networks:
            ssid_str = net[0].decode()
            rssi = net[3]
            print(f"SSID: {ssid_str}, RSSI: {rssi} dBm")
            if ssid_str == self.ssid:
                found = True
        if not found:
            print(f"Warning: SSID {self.ssid} not found in scan!")
        return found

    def connect_wifi(self, max_retries=30, settle_delay=2, max_attempts=5):
        """Connect to WiFi with retries on DHCP failure (status 2) or LINK_FAIL (-1)."""
        for attempt in range(1, max_attempts + 1):
            print(f"WiFi connect attempt {attempt}/{max_attempts}")
            wlan = network.WLAN(network.STA_IF)
            
            wlan.deinit()
            time.sleep(0.2)
            rp2.country(self.country_code)
            wlan.active(True)
            time.sleep(1)
            wlan.config(pm=0xa11140)
            wlan.connect(self.ssid, self.password)
            
            start_time = time.time()
            while time.time() - start_time < max_retries:
                status = wlan.status()
                if status == 3:
                    break
                elif status < 0:
                    print(f"Connection error: status {status}")
                    break
                
                if status >= 1:
                    rssi = wlan.status('rssi')
                    if rssi != 0:
                        print(f"RSSI: {rssi} dBm")
                
                self.led.value(1)
                time.sleep(0.1)
                self.led.value(0)
                time.sleep(0.1)
                print(f"WiFi status: {status}")
                time.sleep(1)
            
            if wlan.status() == 3:
                ip = wlan.ifconfig()[0]
                print(f"Connected to WiFi. IP: {ip}. Settling for {settle_delay}s...")
                time.sleep(settle_delay + 1)
                self.led.value(1)
                return ip
            else:
                print(f"Attempt {attempt} failed with status {wlan.status()}")
                self.failure_blink(duration=5)
                time.sleep(5)
        
        print("All attempts failed to connect to WiFi.")
        self.failure_blink()
        return None

    def udp_announce(self, ip, max_attempts=5, timeout=5):
        """Broadcast announcement via UDP and wait for ACK."""
        if not isinstance(self.udp_port, int) or not (0 <= self.udp_port <= 65535):
            print(f"Invalid UDP port: {self.udp_port}")
            self.failure_blink(duration=5)
            return False

        # Calculate broadcast IP (e.g., 192.168.2.255)
        broadcast_ip = ip.rsplit('.', 1)[0] + '.255'
        print(f"Binding to UDP port: {self.udp_port} with IP: {ip}")

        sock = None
        for bind_attempt in range(1, 6):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind((ip, self.udp_port))
                print(f"Successfully bound to {ip}:{self.udp_port}")
                break
            except OSError as e:
                print(f"Bind attempt {bind_attempt}/5 failed: {e}")
                if sock:
                    sock.close()
                time.sleep(0.5)
                if bind_attempt == 5:
                    print(f"Failed to bind to {ip}:{self.udp_port}")
                    self.failure_blink(duration=5)
                    return False
        
        try:
            message = json.dumps({
                "type": "announce",
                "target_id": self.target_id,
                "ip": ip
            }).encode()
            
            for attempt in range(1, max_attempts + 1):
                self.led.value(1)
                time.sleep(0.1)
                self.led.value(0)
                time.sleep(0.1)
                
                print(f"UDP announce attempt {attempt}/{max_attempts} to {broadcast_ip}:{self.udp_port}")
                sock.sendto(message, (broadcast_ip, self.udp_port))
                
                sock.settimeout(timeout)
                try:
                    data, addr = sock.recvfrom(1024)
                    response = json.loads(data.decode())
                    if response.get("type") == "ack":
                        self.server_ip = response["server_ip"]
                        self.server_tcp_port = response["tcp_port"]
                        print(f"Received ACK: Server IP {self.server_ip}:{self.server_tcp_port}")
                        return True
                except OSError as e:
                    print(f"UDP timeout or error: {e}")
        finally:
            if sock:
                sock.close()
                print("UDP socket closed")
        
        print("No ACK received after attempts.")
        self.failure_blink(duration=5)
        return False

    def tcp_connect(self):
        """Establish TCP connection and send device_info."""
        if not self.server_ip or not self.server_tcp_port:
            return False

        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.tcp_sock.connect((self.server_ip, self.server_tcp_port))
            self.connected = True
            print(f"TCP connected to {self.server_ip}:{self.server_tcp_port}")
            self.led.value(1)  # Solid LED on connected

            # Send device_info
            device_info = {
                "type": "device_info",
                "target_id": self.target_id,
                "relays": self.relays
            }
            self.tcp_sock.sendall(json.dumps(device_info).encode() + b'\n')
            return True
        except OSError as e:
            print(f"TCP connect failed: {e}")
            self.tcp_sock.close()
            self.tcp_sock = None
            self.connected = False
            self.led.value(0)
            return False

    def tcp_send_loop(self):
        """Send queued messages and heartbeats."""
        last_heartbeat = 0
        heartbeat_interval = 30  # seconds
        
        while self.connected:
            # Send heartbeat
            if time.time() - last_heartbeat > heartbeat_interval:
                heartbeat = {"type": "heartbeat", "target_id": self.target_id}
                try:
                    self.tcp_sock.sendall(json.dumps(heartbeat).encode() + b'\n')
                    print("Sent heartbeat")
                    last_heartbeat = time.time()
                except OSError:
                    self.connected = False
                    break
            
            # Send queued status_updates (thread-safe with lock)
            with self.queue_lock:
                if self.message_queue:
                    msg = self.message_queue.pop(0)
                    try:
                        self.tcp_sock.sendall(json.dumps(msg).encode() + b'\n')
                        print(f"Sent status_update: {msg}")
                    except OSError:
                        self.connected = False
                        break
            
            time.sleep(1)  # Sleep 1s to reduce polling

    def tcp_receive_loop(self):
        """Receive and handle incoming commands."""
        buffer = b''
        while self.connected:
            try:
                self.tcp_sock.settimeout(1)  # Non-blocking recv with 1s timeout
                data = self.tcp_sock.recv(1024)
                self.tcp_sock.settimeout(None)  # Reset
                if not data:
                    self.connected = False
                    break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        msg = json.loads(line.decode())
                        print(f"Received message: {msg}")
                        if msg.get("type") == "command":
                            label = msg.get("label")
                            state = msg.get("state")
                            # Execute toggle (assume relay_toggle has this function)
                            from relay_toggle import toggle_relay
                            toggle_relay(label, state)
                            print(f"Executed command: {label} to {state}")
                    except json.JSONDecodeError:
                        print("Invalid JSON received")
            except OSError as e:
                if e.args[0] == 110:  # ETIMEDOUT, continue loop
                    continue
                self.connected = False
            time.sleep(0.1)  # Short yield

    def run_network_loop(self):
        """Self-contained loop for Wi-Fi, UDP, and TCP."""
        backoff = 1
        max_backoff = 60

        while True:
            if not self.scan_wifi():
                print("Skipping connect due to SSID not found")
                self.failure_blink(duration=5)
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue

            ip = self.connect_wifi()
            if ip:
                print(f"WiFi stable! IP: {ip}")
                if self.udp_announce(ip):
                    print(f"UDP discovery complete! Server at {self.server_ip}:{self.server_tcp_port}")
                    if self.tcp_connect():
                        # Run send and receive synchronously with simulation
                        while self.connected:
                            self.tcp_send_loop()
                            self.tcp_receive_loop()
                        # Connection lost, reconnect
                        print("TCP disconnected. Reconnecting...")
                        self.tcp_sock.close()
                        self.tcp_sock = None
                        self.connected = False
                        self.led.value(0)
                        time.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)
                    else:
                        print(f"TCP failed. Backoff sleep: {backoff}s")
                        time.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)
                else:
                    print(f"UDP failed. Backoff sleep: {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            else:
                print(f"WiFi failed. Backoff sleep: {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
