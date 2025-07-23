import network
import socket
import time
import json
import rp2
import ntptime
import _thread

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


    def debug_print(self, *args):
        if self.debug:
            print(*args)

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

    def connect_wifi(self):
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        mac = wlan.config('mac')
        self.macaddress = ':'.join(['{:02x}'.format(b) for b in mac])
        if not wlan.isconnected():
            rp2.country('US')
            wlan.config(pm=0xa11140)
            wlan.connect(self.ssid, self.password)
            while not wlan.isconnected():
                time.sleep(1)
        self.ip = wlan.ifconfig()[0]
        self.debug_print("WiFi IP:", self.ip)
        try:
            ntptime.host = self.ntpserver
            ntptime.settime()
        except:
            pass
        return True

    def udp_announce(self):
        msg = {
            "action":    "announce",
            "id":        self.target_id,
            "timestamp": self.current_timestamp(),
            "data": {
                "ip":        self.ip,
                "tcp_port":  self.tcp_port,
                "mac":       self.macaddress
            }
        }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast = self.ip.rsplit('.', 1)[0] + '.255'
        while True:
            try:
                self.debug_print("UDP announce →", broadcast)
                sock.sendto(json.dumps(msg).encode(), (broadcast, self.udp_port))
                sock.settimeout(5)
                data, _ = sock.recvfrom(1024)
                resp = json.loads(data.decode())
                if resp.get("action") == "ack" and resp.get("id") == self.target_id:
                    d = resp["data"]
                    self.server_ip       = d["server_ip"]
                    self.server_tcp_port = d["tcp_port"]
                    self.debug_print("Got ACK:", d)
                    return
            except OSError as e:
                self.debug_print("UDP announce failed, retrying:", e)
                time.sleep(1)

    def tcp_run_loop(self):
        while True:
            try:
                self.debug_print("TCP connect →", self.server_ip)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.server_ip, self.server_tcp_port))
                # send config
                cfg = {
                    "action":    "config",
                    "id":        self.target_id,
                    "timestamp": self.current_timestamp(),
                    "data":      { "devices": self.devices }
                }
                s.send((json.dumps(cfg) + "\n").encode())

                f = s.makefile("r")
                # read loop
                while True:
                    line = f.readline()
                    if not line:
                        raise OSError("TCP disconnected")
                    msg = json.loads(line)
                    # handle incoming commands here, e.g.:
                    if msg["action"] == "command":
                        self.relay_toggle.handle_remote(msg["data"]["devices"])
                s.close()
            except Exception as e:
                self.debug_print("TCP error, restarting:", e)
                time.sleep(1)
                continue

    def run_network_loop(self):
        while True:
            self.connect_wifi()
            self.udp_announce()
            #self.tcp_run_loop()
