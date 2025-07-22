import network
import socket
import time
import json
import rp2
import ntptime

class NetworkManager:
    def __init__(self, network_config, message_queue, queue_lock):
        setup_config = network_config['config']
        self.ssid = setup_config['wifi_ssid']
        self.password = setup_config['wifi_password']
        self.country_code = setup_config.get('country_code', 'US')
        self.target_id = setup_config['target_id']
        self.udp_port = setup_config['UdpPort']
        self.tcp_port = setup_config['TcpPort']
        self.ntpserver = setup_config.get('ntpserver', 'pool.ntp.org')
        self.timezone_offset = setup_config.get('timezone', 0) * 3600
        self.server_ip = None
        self.server_tcp_port = None
        self.message_queue = message_queue
        self.queue_lock = queue_lock
        self.tcp_sock = None
        self.connected = False
        self.relay_toggle = None
        self.start_time = time.time()
        self.settle_delay = 2
        self.debug = setup_config.get('debug', False)
        self.debug_print("Initialized NetworkManager")

    def debug_print(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs)

    def connect_wifi(self):
        wlan = network.WLAN(network.STA_IF)
        self.debug_print(f"Connected: {wlan.isconnected()}")
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            self.debug_print(f"Already connected to WiFi. IP: {ip}")
            self.connected = True
            return True
        
        while not wlan.isconnected():
            self.debug_print("WiFi is Not Connected")
            
            # Deactivate instead of deinit, as deinit may not be available
            wlan.active(False)
            self.debug_print("Deactivated WLAN, sleeping...")
            time.sleep(3)
            
            rp2.country(self.country_code)
            wlan.config(pm=0xa11140)  # Disable power saving
            wlan.active(True)
            self.debug_print("Activated WLAN, sleeping...")
            time.sleep(3)
            
            networks = wlan.scan()
            self.debug_print("Available networks:")
            found = False
            for net in networks:
                ssid_str = net[0].decode()
                rssi = net[3]
                self.debug_print(f"SSID: {ssid_str}, RSSI: {rssi} dBm")
                if ssid_str == self.ssid:
                    found = True
            if not found:
                self.debug_print(f"Warning: SSID {self.ssid} not found in scan!")
                self.connected = False
                return False
            
            wlan.connect(self.ssid, self.password)
            while not wlan.isconnected():
                status = wlan.status()
                if status == 3:  # STAT_GOT_IP
                    break
                elif status < 0:
                    self.debug_print(f"Connection error: status {status}")
                    self.connected = False
                    return False
                if status >= 1:
                    rssi = wlan.status('rssi')
                    if rssi != 0:
                        self.debug_print(f"RSSI: {rssi} dBm")
                
                self.debug_print(f"WiFi status: {status}")
                time.sleep(1)
            
            if wlan.status() == 3:
                ip = wlan.ifconfig()[0]
                self.debug_print(f"Connected to WiFi. IP: {ip}. Settling for {self.settle_delay}s...")
                time.sleep(self.settle_delay + 1)
                # Sync time with NTP after successful connect
                try:
                    self.debug_print(f"Syncing time with NTP server: {self.ntpserver}")
                    ntptime.host = self.ntpserver  # Use configured NTP server
                    ntptime.settime()  # Sync RTC to UTC
                    self.debug_print(f"NTP time sync successful from {self.ntpserver}")
                    # Display current date and time with timezone adjustment
                    local_time = time.localtime(time.time() + self.timezone_offset)
                    year, month, day, hour, minute, second, _, _ = local_time
                    self.debug_print(f"Current date and time: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
                except OSError as e:
                    self.debug_print(f"NTP sync failed: {e}. Using local time.")
                self.connected = True
                return True
            else:
                self.debug_print(f"Connection failed with status {wlan.status()}")
                time.sleep(5)
        
        self.connected = False
        return False
    
    

    def run_network_loop(self):
        backoff = 1
        max_backoff = 60
        while True:
            if not self.connected:
                success = self.connect_wifi()
                if success:
                    self.debug_print("WiFi connection established")
                    backoff = 1  # Reset backoff on successful connection
                else:
                    self.debug_print(f"WiFi connection failed, retrying after {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)  # Exponential backoff
            else:
                # Periodically check if still connected
                wlan = network.WLAN(network.STA_IF)
                if not wlan.isconnected():
                    self.debug_print("WiFi connection lost")
                    self.connected = False
                else:
                    self.debug_print("WiFi still connected")
                    time.sleep(10)  # Check connection every 10 seconds when connected