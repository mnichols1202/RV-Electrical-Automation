# pico_network.py (version: Wi-Fi + UDP discovery, self-contained with run_network_loop)
import network
import socket
import time
import json
import rp2  # For country code
from machine import Pin

class NetworkManager:
    def __init__(self, network_config):
        """Initialize with config, mirroring RelayToggle style."""
        self.ssid = network_config['wifi_ssid']
        self.password = network_config['wifi_password']
        self.country_code = network_config.get('country_code', 'US')
        self.target_id = network_config['target_id']
        self.udp_port = network_config['UdpPort']
        self.tcp_port = network_config['TcpPort']
        self.relays = network_config['relays']  # For future use
        self.led = Pin("LED", Pin.OUT)
        self.server_ip = None  # Stored from ACK
        self.server_tcp_port = None  # Stored from ACK
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
        networks = wlan.scan()
        print("Available networks:")
        for net in networks:
            ssid_str = net[0].decode()
            rssi = net[3]
            print(f"SSID: {ssid_str}, RSSI: {rssi} dBm")
        return networks

    def connect_wifi(self, max_retries=30, settle_delay=2, max_attempts=5):
        """Connect to WiFi with retries on DHCP failure (status 2)."""
        for attempt in range(1, max_attempts + 1):
            print(f"WiFi connect attempt {attempt}/{max_attempts}")
            wlan = network.WLAN(network.STA_IF)
            
            # Reset Wi-Fi chipset state
            wlan.deinit()
            time.sleep(0.1)
            
            # Set country code
            rp2.country(self.country_code)
            
            # Activate interface
            wlan.active(True)
            time.sleep(0.5)  # Added delay for stability
            
            # Disable power-saving
            wlan.config(pm=0xa11140)
            
            # Connect
            wlan.connect(self.ssid, self.password)
            
            # Wait with timeout, check RSSI if connected
            start_time = time.time()
            while time.time() - start_time < max_retries:
                status = wlan.status()
                if status == 3:  # Success
                    break
                elif status < 0:  # Error, break to retry full connect
                    print(f"Connection error: status {status}")
                    break
                
                if status >= 1:  # Joined, check RSSI
                    rssi = wlan.status('rssi')
                    print(f"RSSI: {rssi} dBm")
                
                # Blink during attempts
                self.led.value(1)
                time.sleep(0.1)
                self.led.value(0)
                time.sleep(0.1)
                
                print(f"WiFi status: {status}")
                time.sleep(1)
            
            if wlan.status() == 3:
                ip = wlan.ifconfig()[0]
                print(f"Connected to WiFi. IP: {ip}. Settling for {settle_delay}s...")
                time.sleep(settle_delay)
                self.led.value(1)  # Solid on success
                return ip
            else:
                print(f"Attempt {attempt} failed with status {wlan.status()}")
                self.failure_blink(duration=5)  # Shorter blink between attempts
                time.sleep(5)  # Wait before retry
        
        print("All attempts failed to connect to WiFi.")
        self.failure_blink()
        return None

    def udp_announce(self, ip, max_attempts=5, timeout=5):
        """Broadcast announcement via UDP and wait for ACK."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', self.udp_port))
        
        message = json.dumps({
            "type": "announce",
            "target_id": self.target_id,
            "ip": ip
        }).encode()
        
        for attempt in range(1, max_attempts + 1):
            # Blink during attempt
            self.led.value(1)
            time.sleep(0.1)
            self.led.value(0)
            time.sleep(0.1)
            
            print(f"UDP announce attempt {attempt}/{max_attempts}")
            sock.sendto(message, ('<broadcast>', self.udp_port))
            
            sock.settimeout(timeout)
            try:
                data, addr = sock.recvfrom(1024)
                response = json.loads(data.decode())
                if response.get("type") == "ack":
                    self.server_ip = response["server_ip"]
                    self.server_tcp_port = response["tcp_port"]
                    print(f"Received ACK: Server IP {self.server_ip}:{self.server_tcp_port}")
                    sock.close()
                    return True
            except OSError as e:
                print(f"UDP timeout or error: {e}")
        
        sock.close()
        print("No ACK received after attempts.")
        self.failure_blink(duration=5)
        return False

    def run_network_loop(self):
        """Self-contained loop for Wi-Fi and UDP, mirroring relay's internal handling."""
        backoff = 1  # Initial backoff seconds
        max_backoff = 60

        while True:
            ip = self.connect_wifi()
            if ip:
                print(f"WiFi stable! IP: {ip}")
                if self.udp_announce(ip):
                    print(f"UDP discovery complete! Server at {self.server_ip}:{self.server_tcp_port}")
                    # Hold for testing; later add TCP here
                    while True:
                        time.sleep(10)
                        if not network.WLAN(network.STA_IF).isconnected():
                            print("WiFi disconnected. Reconnecting...")
                            backoff = 1  # Reset backoff
                            break
                else:
                    # UDP failed; backoff and retry full sequence
                    print(f"UDP failed. Backoff sleep: {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            else:
                # WiFi failed; backoff and retry
                print(f"WiFi failed. Backoff sleep: {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)