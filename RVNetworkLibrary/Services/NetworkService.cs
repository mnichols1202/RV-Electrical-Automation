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
            Console.WriteLine($"[StartAsync] CancellationToken linked. Launching UDP listener...");
            var udpTask = StartUdpListenerAsync();
            Console.WriteLine($"[StartAsync] Launching TCP server...");
            var tcpTask = StartTcpServerAsync(_cts.Token);
            await Task.WhenAll(udpTask, tcpTask);
        }

        private async Task StartUdpListenerAsync()
        {
            Console.WriteLine($"[UDP] Listener starting on {_localIp}:{_udpPort}");
            using (var udpClient = new UdpClient(_udpPort))
            {
                try
                {
                    while (true)
                    {
                        Console.WriteLine($"[UDP] Awaiting packet...");
                        UdpReceiveResult result = await udpClient.ReceiveAsync();

                        string message = Encoding.UTF8.GetString(result.Buffer);
                        IPEndPoint remoteEP = result.RemoteEndPoint;
                        Console.WriteLine($"[UDP] Received from {remoteEP.Address}:{remoteEP.Port} → {message}");

                        try
                        {
                            Console.WriteLine($"[UDP] Parsing JSON...");
                            using var doc = JsonDocument.Parse(message);
                            var root = doc.RootElement;
                            string action = root.GetProperty("action").GetString();
                            Console.WriteLine($"[UDP] action = {action}");

                            if (action == "announce" &&
                                root.TryGetProperty("id", out JsonElement idProp))
                            {
                                string deviceId = idProp.GetString();
                                Console.WriteLine($"[UDP] Announce from deviceId = {deviceId}");

                                var ack = new
                                {
                                    action = "ack",
                                    id = deviceId,
                                    timestamp = DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz"),
                                    data = new
                                    {
                                        server_ip = _localIp,
                                        tcp_port = _tcpPort
                                    }
                                };

                                byte[] ackBytes = JsonSerializer.SerializeToUtf8Bytes(ack);
                                var senderEp = new IPEndPoint(remoteEP.Address, remoteEP.Port);
                                Console.WriteLine($"[UDP] Sending ACK to {senderEp.Address}:{senderEp.Port}");
                                await udpClient.SendAsync(ackBytes, ackBytes.Length, senderEp);
                                Console.WriteLine($"[UDP] ACK sent successfully");
                            }
                            else
                            {
                                Console.WriteLine($"[UDP] Ignored non‑announce or missing id");
                            }
                        }
                        catch (JsonException je)
                        {
                            Console.WriteLine($"[UDP] JSON parse error: {je.Message}");
                        }
                    }
                }
                catch (SocketException ex)
                {
                    Console.WriteLine($"[UDP] Socket error: {ex.Message}");
                }
                finally
                {
                    Console.WriteLine($"[UDP] Listener exiting and socket closing");
                }
            }
        }

        public async Task StartTcpServerAsync(CancellationToken cancellationToken = default)
        {
            var listener = new TcpListener(IPAddress.Any, _tcpPort);
            listener.Start();
            Console.WriteLine($"[TCP] Server listening on port {_tcpPort}");

            while (!cancellationToken.IsCancellationRequested)
            {
                TcpClient client = await listener.AcceptTcpClientAsync(cancellationToken);
                Console.WriteLine($"[TCP] Client connected: {client.Client.RemoteEndPoint}");
                _ = HandleTcpClientAsync(client, cancellationToken); // Handle each client in background
            }
        }

        private async Task HandleTcpClientAsync(TcpClient client, CancellationToken cancellationToken)
        {
            using (client)
            using (var stream = client.GetStream())
            {
                var buffer = new byte[1024];
                while (!cancellationToken.IsCancellationRequested)
                {
                    int bytesRead = await stream.ReadAsync(buffer, cancellationToken);
                    if (bytesRead == 0) break; // Client disconnected

                    string received = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    Console.WriteLine($"[TCP] Received: {received}");
                }
                Console.WriteLine("[TCP] Client disconnected");
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
    }
}
