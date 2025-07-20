using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Net.NetworkInformation;
using System.Threading;
using System.Threading.Tasks;

namespace RVNetworkLibrary.Services
{
    public class NetworkService
    {
        private readonly int _udpPort;
        private readonly int _tcpPort;
        private readonly string _localIp;
        private CancellationTokenSource _cts = new();
        private TcpListener _tcpListener;
        private ConcurrentDictionary<string, DeviceState> _devices = new();
        private ConcurrentDictionary<string, TcpClient> _connectedClients = new(); // Track clients by target_id

        public event Action<string, object> MessageReceived;
        public event Action<string> DeviceDisconnected; // New event for disconnect notifications

        public NetworkService(int udpPort = 5000, int tcpPort = 5001)
        {
            _udpPort = udpPort;
            _tcpPort = tcpPort;
            _localIp = GetLocalIpAddress();
        }

        public async Task StartAsync(CancellationToken cancellationToken = default)
        {
            _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            await Task.WhenAll(StartUdpListenerAsync(), StartTcpServerAsync(), HeartbeatMonitorAsync());
        }

        public void Stop()
        {
            _cts.Cancel();
            _tcpListener?.Stop();
            foreach (var client in _connectedClients.Values)
            {
                client.Close();
            }
            _connectedClients.Clear();
            _devices.Clear();
        }

        private async Task StartUdpListenerAsync()
        {
            using UdpClient udpClient = new(_udpPort);
            Console.WriteLine($"UDP listener started on {_localIp}:{_udpPort}");

            while (!_cts.Token.IsCancellationRequested)
            {
                try
                {
                    UdpReceiveResult result = await udpClient.ReceiveAsync(_cts.Token);
                    string json = Encoding.UTF8.GetString(result.Buffer);
                    var message = JsonSerializer.Deserialize<Dictionary<string, object>>(json);

                    if (message.TryGetValue("type", out object typeObj) && typeObj.ToString() == "config" &&
                        message.TryGetValue("data", out object dataObj) && dataObj is JsonElement dataElem)
                    {
                        var data = JsonSerializer.Deserialize<Dictionary<string, object>>(dataElem.GetRawText());
                        if (data.TryGetValue("action", out object actionObj) && actionObj.ToString() == "announce")
                        {
                            string targetId = message["target_id"].ToString();
                            string picoIp = data["ip"].ToString();
                            Console.WriteLine($"Announce from {targetId} at {picoIp}");

                            var ackData = new Dictionary<string, object>
                            {
                                { "action", "ack" },
                                { "server_ip", _localIp },
                                { "tcp_port", _tcpPort }
                            };
                            var ack = new Dictionary<string, object>
                            {
                                { "type", "config" },
                                { "timestamp", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss") },
                                { "data", ackData },
                                { "version", 1 }
                            };
                            string ackJson = JsonSerializer.Serialize(ack);
                            byte[] ackBytes = Encoding.UTF8.GetBytes(ackJson);
                            await udpClient.SendAsync(ackBytes, ackBytes.Length, result.RemoteEndPoint);
                            Console.WriteLine($"Sent ACK to {result.RemoteEndPoint}");
                        }
                    }
                }
                catch (OperationCanceledException) { }
                catch (Exception ex)
                {
                    Console.WriteLine($"UDP error: {ex.Message}");
                }
            }
        }

        private async Task StartTcpServerAsync()
        {
            _tcpListener = new TcpListener(IPAddress.Any, _tcpPort);
            _tcpListener.Start();
            Console.WriteLine($"TCP server started on {_localIp}:{_tcpPort}");

            while (!_cts.Token.IsCancellationRequested)
            {
                try
                {
                    TcpClient client = await _tcpListener.AcceptTcpClientAsync(_cts.Token);
                    EnableTcpKeepAlives(client); // Enable keepalives for faster disconnect detection
                    _ = HandleTcpClientAsync(client); // Fire and forget
                }
                catch (OperationCanceledException) { }
                catch (Exception ex)
                {
                    Console.WriteLine($"TCP accept error: {ex.Message}");
                }
            }

            _tcpListener.Stop();
        }

        private async Task HandleTcpClientAsync(TcpClient client)
        {
            string remoteIp = ((IPEndPoint)client.Client.RemoteEndPoint).Address.ToString();
            Console.WriteLine($"TCP client connected from {remoteIp}");

            using NetworkStream stream = client.GetStream();

            byte[] buffer = new byte[1024];
            StringBuilder messageBuilder = new StringBuilder();

            string targetId = null; // To be set from device_info

            try
            {
                while (client.Connected && !_cts.Token.IsCancellationRequested)
                {
                    int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length, _cts.Token).ConfigureAwait(false);
                    if (bytesRead == 0)
                    {
                        Console.WriteLine($"TCP client from {remoteIp} disconnected (end of stream)");
                        break;
                    }

                    string receivedData = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    //Console.WriteLine($"Raw data received from {remoteIp}: {receivedData}");

                    messageBuilder.Append(receivedData);

                    string messages = messageBuilder.ToString();
                    int nlIndex;
                    while ((nlIndex = messages.IndexOf('\n')) != -1)
                    {
                        string json = messages.Substring(0, nlIndex);
                        messages = messages.Substring(nlIndex + 1);
                        messageBuilder = new StringBuilder(messages);

                        Console.WriteLine($"{DateTime.Now} - Processing JSON from {remoteIp}: {json}");

                        try
                        {
                            var message = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                            if (message.TryGetValue("type", out object typeObj) && typeObj is string type &&
                                message.TryGetValue("data", out object dataObj) && dataObj is JsonElement dataElem)
                            {
                                var data = JsonSerializer.Deserialize<Dictionary<string, object>>(dataElem.GetRawText());
                                Console.WriteLine($"Received {type} from {remoteIp}: {json}");
                                MessageReceived?.Invoke(type, message);

                                switch (type)
                                {
                                    case "config":
                                        var action = data.TryGetValue("action", out object actionObj) ? actionObj.ToString() : null;
                                        if (action == "device_info" && message.TryGetValue("target_id", out object idObj) && idObj is string id &&
                                            data.TryGetValue("devices", out object devicesObj) && devicesObj is JsonElement devicesElem)  // Changed to "devices"
                                        {
                                            targetId = id;
                                            _connectedClients[id] = client; // Store client for sending commands
                                            var devicesList = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(devicesElem.GetRawText());
                                            // Initialize states if not present; filter/process only relays for now
                                            foreach (var device in devicesList)
                                            {
                                                if (device.TryGetValue("device_type", out object devType) && devType.ToString() == "relay")
                                                {
                                                    if (!device.ContainsKey("state"))
                                                    {
                                                        device["state"] = device.TryGetValue("initial_state", out object initState) ? initState : "off";
                                                    }
                                                }
                                                // Future: handle other types
                                            }
                                            _devices[id] = new DeviceState { Devices = devicesList, LastHeartbeat = DateTime.Now };  // Changed to Devices
                                        }
                                        break;
                                    case "status":
                                        var statusAction = data.TryGetValue("action", out object statusActionObj) ? statusActionObj.ToString() : null;
                                        if (statusAction == "heartbeat" && targetId != null)
                                        {
                                            _devices[targetId].LastHeartbeat = DateTime.Now;
                                        }
                                        else if (targetId != null && data.TryGetValue("devices", out object devicesStatusObj) && devicesStatusObj is JsonElement devicesStatusElem)  // Changed to "devices"
                                        {
                                            var devicesStatus = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(devicesStatusElem.GetRawText());
                                            if (_devices[targetId].Devices is List<Dictionary<string, object>> deviceList)
                                            {
                                                foreach (var devStatus in devicesStatus)
                                                {
                                                    if (devStatus.TryGetValue("device_type", out object devTypeObj) && devTypeObj.ToString() == "relay" &&
                                                        devStatus.TryGetValue("label", out object labelObj) && labelObj is string label &&
                                                        devStatus.TryGetValue("state", out object stateObj))
                                                    {
                                                        var matchingDevice = deviceList.FirstOrDefault(d => d["label"].ToString() == label);
                                                        if (matchingDevice != null)
                                                        {
                                                            matchingDevice["state"] = stateObj;
                                                        }
                                                    }
                                                    // Future: handle other device_types
                                                }
                                            }
                                        }
                                        break;
                                }
                            }
                        }
                        catch (JsonException ex)
                        {
                            Console.WriteLine($"JSON parse error: {ex.Message}");
                        }
                    }
                }
            }
            catch (IOException ex) // Specific for socket errors
            {
                Console.WriteLine($"TCP client from {remoteIp} disconnected due to IO error: {ex.Message}");
            }
            catch (ObjectDisposedException ex)
            {
                Console.WriteLine($"TCP client from {remoteIp} disconnected due to disposal: {ex.Message}");
            }
            catch (OperationCanceledException) { }
            catch (Exception ex)
            {
                Console.WriteLine($"TCP client error: {ex.Message}");
            }
            finally
            {
                client.Close();
                if (targetId != null)
                {
                    _connectedClients.TryRemove(targetId, out _);
                    _devices.TryRemove(targetId, out _);
                    DeviceDisconnected?.Invoke(targetId);
                }
                Console.WriteLine($"TCP client disconnected from {remoteIp}");
            }
        }

        private async Task HeartbeatMonitorAsync()
        {
            while (!_cts.Token.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(10000, _cts.Token); // Check every 10s
                    var now = DateTime.Now;
                    foreach (var kvp in _devices.ToArray())
                    {
                        if (now - kvp.Value.LastHeartbeat > TimeSpan.FromSeconds(60)) // Timeout after 60s (2x heartbeat interval)
                        {
                            Console.WriteLine($"Device {kvp.Key} disconnected due to heartbeat timeout");
                            if (_connectedClients.TryRemove(kvp.Key, out var client))
                            {
                                client.Close();
                            }
                            _devices.TryRemove(kvp.Key, out _);
                            DeviceDisconnected?.Invoke(kvp.Key);
                        }
                    }
                }
                catch (OperationCanceledException) { }
            }
        }

        public async Task SendCommandAsync(string targetId, string deviceType, string label, string state)  // Added deviceType param
        {
            if (_connectedClients.TryGetValue(targetId, out TcpClient client) && client.Connected)
            {
                try
                {
                    using NetworkStream stream = client.GetStream();
                    using StreamWriter writer = new(stream) { AutoFlush = true };

                    var commandData = new Dictionary<string, string>
                    {
                        { "device_type", deviceType },  // Added
                        { "label", label },
                        { "state", state }
                    };
                    var command = new Dictionary<string, object>
                    {
                        { "type", "command" },
                        { "target_id", targetId },
                        { "timestamp", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss") },
                        { "data", commandData },
                        { "version", 1 }
                    };
                    string json = JsonSerializer.Serialize(command);
                    await writer.WriteLineAsync(json);
                    Console.WriteLine($"Sent command: {deviceType} {label} to {state} for {targetId}");
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Send command error: {ex.Message}");
                }
            }
            else
            {
                Console.WriteLine($"No connected client for {targetId}");
            }
        }

        private void EnableTcpKeepAlives(TcpClient client)
        {
            try
            {
                // Enable keepalive
                client.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.KeepAlive, true);

                // Custom keepalive settings (Windows/Linux compatible via IOControl)
                // Bytes: on (4 bytes), time (4 bytes, ms), interval (4 bytes, ms)
                byte[] keepAliveValues = new byte[12];
                BitConverter.GetBytes(1).CopyTo(keepAliveValues, 0); // Enable
                BitConverter.GetBytes(30000).CopyTo(keepAliveValues, 4); // Idle time before probe (30s)
                BitConverter.GetBytes(10000).CopyTo(keepAliveValues, 8); // Probe interval (10s)
                client.Client.IOControl(IOControlCode.KeepAliveValues, keepAliveValues, null);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Failed to set TCP keepalives: {ex.Message}");
            }
        }

        private string GetLocalIpAddress()
        {
            foreach (NetworkInterface ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus == OperationalStatus.Up &&
                    ni.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                {
                    foreach (UnicastIPAddressInformation ip in ni.GetIPProperties().UnicastAddresses)
                    {
                        if (ip.Address.AddressFamily == AddressFamily.InterNetwork)
                        {
                            return ip.Address.ToString();
                        }
                    }
                }
            }
            return "127.0.0.1"; // Fallback if no valid interface is found
        }
    }

    public class DeviceState
    {
        public List<Dictionary<string, object>> Devices { get; set; }  // Changed from Relays to Devices
        public DateTime LastHeartbeat { get; set; }
    }
}