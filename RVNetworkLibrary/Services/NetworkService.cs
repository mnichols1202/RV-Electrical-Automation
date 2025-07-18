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
            using StreamReader reader = new(stream);
            using StreamWriter writer = new(stream) { AutoFlush = true };

            string buffer = string.Empty;
            try
            {
                while (client.Connected && !_cts.Token.IsCancellationRequested)
                {
                    string line = await reader.ReadLineAsync();
                    if (line == null) break;
                    buffer += line;

                    while (buffer.Contains("\n"))
                    {
                        int nlIndex = buffer.IndexOf('\n');
                        string json = buffer.Substring(0, nlIndex);
                        buffer = buffer.Substring(nlIndex + 1);

                        var message = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                        if (message.TryGetValue("type", out object typeObj) && typeObj is string type)
                        {
                            Console.WriteLine($"Received {type} from {remoteIp}");
                            MessageReceived?.Invoke(type, message);

                            switch (type)
                            {
                                case "device_info":
                                    if (message.TryGetValue("target_id", out object idObj) && idObj is string targetId)
                                    {
                                        _devices[targetId] = new DeviceState { Relays = message["relays"] };
                                    }
                                    break;
                                case "heartbeat":
                                    break;
                                case "status_update":
                                    break;
                            }
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
                Console.WriteLine($"TCP client disconnected from {remoteIp}");
            }
        }

        public async Task SendCommandAsync(string targetId, string label, string state)
        {
            Console.WriteLine($"Sending command: {label} to {state} for {targetId}");
            // Placeholder for TCP client sending
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