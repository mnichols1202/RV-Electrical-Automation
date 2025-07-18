// RVNetworkLibrary/Services/NetworkService.cs
using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
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

        public NetworkService(int udpPort = 5000, int tcpPort = 5001)
        {
            _udpPort = udpPort;
            _tcpPort = tcpPort;
            _localIp = GetLocalIpAddress();
        }

        public async Task StartAsync(CancellationToken cancellationToken = default)
        {
            _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            await Task.WhenAll(StartUdpListenerAsync(), StartTcpServerAsync());
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
                    var message = JsonSerializer.Deserialize<Dictionary<string, string>>(json);

                    if (message.TryGetValue("type", out string type) && type == "announce")
                    {
                        string targetId = message["target_id"];
                        string picoIp = message["ip"];
                        Console.WriteLine($"Announce from {targetId} at {picoIp}");

                        var ack = new Dictionary<string, object>
                        {
                            { "type", "ack" },
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
                    int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length, _cts.Token);
                    if (bytesRead == 0) break;

                    string receivedData = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    Console.WriteLine($"Raw data received from {remoteIp}: {receivedData}");

                    messageBuilder.Append(receivedData);

                    string messages = messageBuilder.ToString();
                    int nlIndex;
                    while ((nlIndex = messages.IndexOf('\n')) != -1)
                    {
                        string json = messages.Substring(0, nlIndex);
                        messages = messages.Substring(nlIndex + 1);
                        messageBuilder = new StringBuilder(messages);

                        Console.WriteLine($"Processing JSON from {remoteIp}: {json}");

                        try
                        {
                            var message = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                            if (message.TryGetValue("type", out object typeObj) && typeObj is string type)
                            {
                                Console.WriteLine($"Received {type} from {remoteIp}: {json}");
                                MessageReceived?.Invoke(type, message);

                                switch (type)
                                {
                                    case "device_info":
                                        if (message.TryGetValue("target_id", out object idObj) && idObj is string id)
                                        {
                                            targetId = id;
                                            _connectedClients[id] = client; // Store client for sending commands
                                            _devices[id] = new DeviceState { Relays = message["relays"] };
                                        }
                                        break;
                                    case "heartbeat":
                                        // Log or update liveness
                                        break;
                                    case "status_update":
                                        // Update relay state in _devices
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
                }
                Console.WriteLine($"TCP client disconnected from {remoteIp}");
            }
        }

        public async Task SendCommandAsync(string targetId, string label, string state)
        {
            if (_connectedClients.TryGetValue(targetId, out TcpClient client) && client.Connected)
            {
                try
                {
                    using NetworkStream stream = client.GetStream();
                    using StreamWriter writer = new(stream) { AutoFlush = true };

                    var command = new Dictionary<string, string>
                    {
                        { "type", "command" },
                        { "label", label },
                        { "state", state }
                    };
                    string json = JsonSerializer.Serialize(command);
                    await writer.WriteLineAsync(json);
                    Console.WriteLine($"Sent command: {label} to {state} for {targetId}");
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

        private string GetLocalIpAddress()
        {
            var host = Dns.GetHostEntry(Dns.GetHostName());
            foreach (var ip in host.AddressList)
            {
                if (ip.AddressFamily == AddressFamily.InterNetwork)
                {
                    return ip.ToString();
                }
            }
            return "127.0.0.1";
        }
    }

    public class DeviceState
    {
        public object Relays { get; set; }
    }
}