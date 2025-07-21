using System;
using System.Collections.Concurrent;
using System.Linq;
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
        private ConcurrentDictionary<string, TcpClient> _connectedClients = new();

        public event Action<string, object> MessageReceived;
        public event Action<string> DeviceDisconnected;

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

                    if (message.TryGetValue("t", out object typeObj) && typeObj.ToString() == "c")
                    {
                        string targetId = message["i"].ToString();
                        string picoIp = message["ip"].ToString();
                        Console.WriteLine($"Announce from {targetId} at {picoIp}");

                        var ack = new Dictionary<string, object>
                        {
                            { "t", "c" },
                            { "i", targetId },
                            { "server_ip", _localIp },
                            { "tcp_port", _tcpPort }
                        };
                        string ackJson = JsonSerializer.Serialize(ack);
                        byte[] ackBytes = Encoding.UTF8.GetBytes(ackJson);
                        await udpClient.SendAsync(ackBytes, ackBytes.Length, result.RemoteEndPoint);
                        Console.WriteLine($"Sent ACK to {result.RemoteEndPoint}");
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
                    EnableTcpKeepAlives(client);
                    _ = HandleTcpClientAsync(client);
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
            string targetId = null;

            try
            {
                while (client.Connected && !_cts.Token.IsCancellationRequested)
                {
                    int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length, _cts.Token);
                    if (bytesRead == 0)
                    {
                        Console.WriteLine($"TCP client from {remoteIp} disconnected (end of stream)");
                        break;
                    }

                    string receivedData = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    messageBuilder.Append(receivedData);

                    string messages = messageBuilder.ToString();
                    int nlIndex;
                    while ((nlIndex = messages.IndexOf('\n')) != -1)
                    {
                        string line = messages.Substring(0, nlIndex);
                        messages = messages.Substring(nlIndex + 1);
                        messageBuilder = new StringBuilder(messages);

                        Console.WriteLine($"{DateTime.Now} - Processing from {remoteIp}: {line}");

                        try
                        {
                            if (line.StartsWith("{")) // JSON config
                            {
                                var message = JsonSerializer.Deserialize<Dictionary<string, object>>(line);
                                if (message["t"].ToString() == "c" && message.TryGetValue("d", out object devicesObj) && devicesObj is JsonElement devicesElem)
                                {
                                    targetId = message["i"].ToString();
                                    _connectedClients[targetId] = client;
                                    var devicesList = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(devicesElem.GetRawText());
                                    var idToDeviceMap = new ConcurrentDictionary<string, Dictionary<string, object>>();
                                    foreach (var device in devicesList)
                                    {
                                        string devId = device["id"].ToString();
                                        idToDeviceMap[devId] = device;
                                        if (device.TryGetValue("t", out object devType) && devType.ToString() == "r")
                                        {
                                            if (!device.ContainsKey("v"))
                                            {
                                                device["v"] = device.TryGetValue("initial_state", out object initState) ? initState : "off";
                                            }
                                        }
                                    }
                                    _devices[targetId] = new DeviceState { Devices = devicesList, DeviceMap = idToDeviceMap, LastHeartbeat = DateTime.Now };
                                    MessageReceived?.Invoke("config", message);
                                }
                            }
                            else // CSV message
                            {
                                var parts = line.Split(',');
                                if (parts.Length >= 4)
                                {
                                    targetId = parts[1];
                                    string msgType = parts[3];
                                    MessageReceived?.Invoke(msgType, parts);
                                    if (msgType == "heartbeat" && _devices.ContainsKey(targetId))
                                    {
                                        _devices[targetId].LastHeartbeat = DateTime.Now;
                                    }
                                    else if (msgType == "status" && parts.Length == 5 && _devices.ContainsKey(targetId))
                                    {
                                        string deviceId = parts[2];
                                        string state = parts[4];
                                        var deviceMap = _devices[targetId].DeviceMap;
                                        if (deviceMap.TryGetValue(deviceId, out var device))
                                        {
                                            device["v"] = state;
                                        }
                                    }
                                }
                            }
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"Parse error: {ex.Message}");
                        }
                    }
                }
            }
            catch (IOException ex)
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
                    await Task.Delay(10000, _cts.Token);
                    var now = DateTime.Now;
                    foreach (var kvp in _devices.ToArray())
                    {
                        if (now - kvp.Value.LastHeartbeat > TimeSpan.FromSeconds(60))
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

        public async Task SendCommandAsync(string targetId, string deviceType, string label, string state)
        {
            if (_connectedClients.TryGetValue(targetId, out TcpClient client) && client.Connected)
            {
                try
                {
                    using NetworkStream stream = client.GetStream();
                    using StreamWriter writer = new(stream) { AutoFlush = true };
                    string deviceId = null;
                    if (_devices.TryGetValue(targetId, out DeviceState deviceState))
                    {
                        var device = deviceState.Devices.FirstOrDefault(d => d.TryGetValue("l", out var l) && l.ToString() == label);
                        deviceId = device?.TryGetValue("id", out var id) == true ? id.ToString() : null;
                    }
                    if (deviceId == null)
                    {
                        Console.WriteLine($"No device ID found for label {label} in {targetId}");
                        return;
                    }
                    string ts = DateTime.UtcNow.ToString("yyMMddHHmmss");
                    string csv = $"{ts},{targetId},{deviceId},update,{state}";
                    await writer.WriteLineAsync(csv);
                    Console.WriteLine($"Sent command: {deviceType} {label} (id: {deviceId}) to {state} for {targetId}");
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
                client.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.KeepAlive, true);
                byte[] keepAliveValues = new byte[12];
                BitConverter.GetBytes(1).CopyTo(keepAliveValues, 0);
                BitConverter.GetBytes(30000).CopyTo(keepAliveValues, 4);
                BitConverter.GetBytes(10000).CopyTo(keepAliveValues, 8);
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
            return "127.0.0.1";
        }

        public Dictionary<string, List<Dictionary<string, object>>> GetDevices()
        {
            var result = new Dictionary<string, List<Dictionary<string, object>>>();
            foreach (var device in _devices)
            {
                result[device.Key] = device.Value.Devices;
            }
            return result;
        }
    }

    public class DeviceState
    {
        public List<Dictionary<string, object>> Devices { get; set; }
        public ConcurrentDictionary<string, Dictionary<string, object>> DeviceMap { get; set; } = new();
        public DateTime LastHeartbeat { get; set; }
    }
}