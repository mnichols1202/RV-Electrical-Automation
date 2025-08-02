using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace RVNetworkLibrary.Services
{
    public class NetworkService : IDisposable
    {
        private readonly int _listenPort;
        private UdpClient _udpClient;
        private readonly int _tcpPort;
        private TcpListener _tcpListener;
        private readonly ConcurrentDictionary<string, TcpClient> _connectedPicos = new();

        public NetworkService(int udpPort = 5000, int tcpPort = 5001)
        {
            _listenPort = udpPort;
            _tcpPort = tcpPort;
            CreateClient();
            Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] UDP server starting on port {_listenPort}");
            Task.Run(() => MonitorLoopAsync());
            Task.Run(() => StartTcpServerAsync());
        }

        private void CreateClient()
        {
            _udpClient = new UdpClient(_listenPort)
            {
                EnableBroadcast = true
            };
        }

        private async Task MonitorLoopAsync()
        {
            while (true)
            {
                try
                {
                    Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Listening for announces...");
                    await ReceiveLoopAsync();
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Error: {ex.Message}. Restarting in 1s");
                }

                _udpClient.Close();
                CreateClient();
                await Task.Delay(1000);
            }
        }

        private async Task ReceiveLoopAsync()
        {
            while (true)
            {
                var result = await _udpClient.ReceiveAsync();
                var remote = result.RemoteEndPoint;
                var json = Encoding.UTF8.GetString(result.Buffer);

                Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Received from {remote}: {json}");

                Announce announce;
                try
                {
                    announce = JsonSerializer.Deserialize<Announce>(json);
                }
                catch (JsonException jex)
                {
                    Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Invalid JSON: {jex.Message}");
                    continue;
                }

                if (announce.Action != "announce")
                {
                    Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Ignored action: {announce.Action}");
                    continue;
                }

                var ack = new Ack
                {
                    Action = "ack",
                    Id = announce.Id,
                    Timestamp = DateTime.UtcNow.ToString("o"),
                    ServerIp = GetLocalIPAddress(),
                    ServerPort = _listenPort
                };

                var ackJson = JsonSerializer.Serialize(ack);
                var ackBytes = Encoding.UTF8.GetBytes(ackJson);
                await _udpClient.SendAsync(ackBytes, ackBytes.Length, remote);

                Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] Sent to {remote}: {ackJson}");
            }
        }

        private async Task StartTcpServerAsync()
        {
            int retryCount = 0;
            int backoff = 1000; // Start with 1 second
            int maxBackoff = 30000; // Cap at 30 seconds

            while (true)
            {
                try
                {
                    _tcpListener = new TcpListener(IPAddress.Any, _tcpPort);
                    _tcpListener.Start();
                    Console.WriteLine($"[TCP] Server listening on port {_tcpPort}");

                    while (true)
                    {
                        TcpClient client = await _tcpListener.AcceptTcpClientAsync();
                        Console.WriteLine($"[TCP] Client connected: {client.Client.RemoteEndPoint}");
                        _ = HandleTcpClientAsync(client); // Handle each client in background
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[{DateTime.UtcNow:o}] [TCP] Error: {ex.Message}. Restarting in {backoff}...");
                    _tcpListener?.Stop();
                    await Task.Delay(backoff);
                    retryCount++;
                    backoff = Math.Min(backoff * 2, maxBackoff); // Exponential backoff
                }
            }
        }

        private async Task HandleTcpClientAsync(TcpClient client)
        {
            using (client)
            using (var stream = client.GetStream())
            {
                var buffer = new byte[1024];
                string picoId = null;
                try
                {
                    // Read initial config/status message to get Pico ID
                    int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length);
                    if (bytesRead > 0)
                    {
                        string received = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                        var doc = JsonDocument.Parse(received);
                        if (doc.RootElement.TryGetProperty("id", out var idProp))
                        {
                            picoId = idProp.GetString();
                            _connectedPicos[picoId] = client;
                            Console.WriteLine($"[TCP] Registered Pico: {picoId}");
                        }
                    }

                    // Main receive loop
                    while (true)
                    {
                        int loopBytesRead = await stream.ReadAsync(buffer, 0, buffer.Length);
                        if (loopBytesRead == 0) break; // Client disconnected

                        string received = Encoding.UTF8.GetString(buffer, 0, loopBytesRead);
                        Console.WriteLine($"[TCP] Received from {picoId}: {received}");

                        // TODO: Parse message, update status, send commands, etc.
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[TCP] Error with Pico {picoId}: {ex.Message}");
                }
                finally
                {
                    if (picoId != null)
                    {
                        _connectedPicos.TryRemove(picoId, out _);
                        Console.WriteLine($"[TCP] Pico {picoId} disconnected");
                    }
                }
            }
        }

        private string GetLocalIPAddress()
        {
            var host = Dns.GetHostEntry(Dns.GetHostName());
            foreach (var ip in host.AddressList)
            {
                if (ip.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(ip))
                {
                    return ip.ToString();
                }
            }
            return "127.0.0.1";
        }

        public void Dispose()
        {
            _udpClient.Close();
            Console.WriteLine($"{DateTime.UtcNow:o} [NetworkService] UDP server disposed");
        }
    }

    internal class Announce
    {
        [JsonPropertyName("action")] public string Action { get; set; }
        [JsonPropertyName("id")] public string Id { get; set; }
        [JsonPropertyName("ip")] public string Ip { get; set; }
        [JsonPropertyName("mac")] public string Mac { get; set; }
        [JsonPropertyName("timestamp")] public string Timestamp { get; set; }
    }

    internal class Ack
    {
        [JsonPropertyName("action")] public string Action { get; set; }
        [JsonPropertyName("id")] public string Id { get; set; }
        [JsonPropertyName("Serverip")] public string ServerIp { get; set; }
        [JsonPropertyName("Serverport")] public int ServerPort { get; set; }
        [JsonPropertyName("timestamp")] public string Timestamp { get; set; }
    }
}
