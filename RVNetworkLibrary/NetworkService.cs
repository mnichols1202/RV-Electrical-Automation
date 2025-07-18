// NetworkService.cs (in RVNetworkLibrary project)
// Handles UDP discovery (listen for announces, send ACKs) and TCP server (accept connections, parse JSON messages, send commands).
// Conforms to pico_network.py protocol: UDP for zero-config discovery, TCP for bidirectional JSON (device_info, heartbeat, status_update from Pico; commands from server).
// Uses System.Text.Json for serialization. Designed for reuse in console testing and Blazor hosted service.
// Assumes .NET 9; add NuGet: System.Text.Json if needed.

using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

public class NetworkService
{
    private readonly int _udpPort;
    private readonly int _tcpPort;
    private readonly string _localIp;
    private CancellationTokenSource _cts = new();
    private TcpListener _tcpListener;
    private ConcurrentDictionary<string, DeviceState> _devices = new(); // target_id -> state (for UI/monitoring)

    public event Action<string, object> MessageReceived; // Event for handling incoming JSON (e.g., update UI in Blazor)

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
    }

    // UDP: Listen for announces, send ACK
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

                    // Send ACK
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

    // TCP: Start server, accept connections, handle messages
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

                // Process complete JSON (framed by \n)
                while (buffer.Contains("\n"))
                {
                    int nlIndex = buffer.IndexOf('\n');
                    string json = buffer.Substring(0, nlIndex);
                    buffer = buffer.Substring(nlIndex + 1);

                    var message = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                    if (message.TryGetValue("type", out object typeObj) && typeObj is string type)
                    {
                        Console.WriteLine($"Received {type} from {remoteIp}");
                        MessageReceived?.Invoke(type, message); // Raise event for external handling (e.g., update _devices)

                        switch (type)
                        {
                            case "device_info":
                                // Handle device_info (e.g., store relays)
                                if (message.TryGetValue("target_id", out object idObj) && idObj is string targetId)
                                {
                                    _devices[targetId] = new DeviceState { Relays = message["relays"] }; // Update state
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

    // Send command to Pico (call from external, e.g., Blazor UI)
    public async Task SendCommandAsync(string targetId, string label, string state)
    {
        // Assume you have a way to get the TcpClient for targetId (e.g., store connected clients in a dict)
        // For simplicity, this is a placeholder—implement client tracking as needed
        Console.WriteLine($"Sending command: {label} to {state} for {targetId}");
        // var commandJson = JsonSerializer.Serialize(new { type = "command", label, state });
        // Write to client's stream...
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

// Simple state class for devices (expand as needed)
public class DeviceState
{
    public object Relays { get; set; } // List of relays from device_info
    // Add current states, etc.
}