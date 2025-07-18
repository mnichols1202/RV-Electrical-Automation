using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using System.Net.NetworkInformation;
using System.Text.Json;
using MQTTnet;
using MQTTnet.Server;
using Microsoft.Extensions.Logging;

namespace AutomationWeb
{
    public class NetworkService
    {
        private readonly int _broadcastPort;
        private readonly int _mqttPort;  // New: MQTT broker port (default 1883)
        private readonly string _ackMessagePrefix;
        private IMqttServer? _mqttServer;
        private readonly ILogger<NetworkService>? _logger;  // Optional: Inject if using DI
        public Dictionary<string, Dictionary<string, string>> DeviceStates { get; private set; } = new();  // e.g., { "PicoW1": { "relay1": "ON" } }

        public event Action<string>? MessageReceived;  // Keep for raw logging if needed

        public NetworkService(int broadcastPort = 5000, int mqttPort = 1883, string ackMessagePrefix = "ACK", ILogger<NetworkService>? logger = null)
        {
            _broadcastPort = broadcastPort;
            _mqttPort = mqttPort;
            _ackMessagePrefix = ackMessagePrefix;
            _logger = logger;
        }

        public async Task RunAsync()
        {
            LogLocalIpAddresses();
            await Task.WhenAll(ListenForBroadcastAsync(), StartMqttBrokerAsync());
        }

        private void LogLocalIpAddresses()
        {
            try
            {
                var interfaces = NetworkInterface.GetAllNetworkInterfaces();
                foreach (var ni in interfaces)
                {
                    if (ni.OperationalStatus == OperationalStatus.Up && ni.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                    {
                        var props = ni.GetIPProperties();
                        foreach (var ip in props.UnicastAddresses)
                        {
                            if (ip.Address.AddressFamily == AddressFamily.InterNetwork)
                            {
                                Console.WriteLine($"Local IP: {ip.Address} (Interface: {ni.Name})");
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error getting local IPs: {ex.Message}");
            }
        }

        private string GetLocalIpAddress()
        {
            try
            {
                var interfaces = NetworkInterface.GetAllNetworkInterfaces();
                foreach (var ni in interfaces)
                {
                    if (ni.OperationalStatus == OperationalStatus.Up && ni.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                    {
                        var props = ni.GetIPProperties();
                        foreach (var ip in props.UnicastAddresses)
                        {
                            if (ip.Address.AddressFamily == AddressFamily.InterNetwork)
                            {
                                return ip.Address.ToString();
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error getting local IP: {ex.Message}");
            }
            return "127.0.0.1"; // Fallback
        }

        private async Task ListenForBroadcastAsync()
        {
            UdpClient? udpClient = null;
            try
            {
                udpClient = new UdpClient();
                udpClient.EnableBroadcast = true;
                udpClient.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                udpClient.Client.Bind(new IPEndPoint(IPAddress.Any, _broadcastPort));
                Console.WriteLine($"UDP listener bound to port {_broadcastPort} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");

                while (true)
                {
                    try
                    {
                        UdpReceiveResult result = await udpClient.ReceiveAsync();
                        string message = Encoding.UTF8.GetString(result.Buffer);
                        MessageReceived?.Invoke($"UDP: '{message}' from {result.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                        Console.WriteLine($"Received UDP: '{message}' from {result.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");

                        if (message.Contains(":"))
                        {
                            // Respond with ACK: <console_ip> <mqttPort>
                            string consoleIp = GetLocalIpAddress();
                            string ackResponse = $"{_ackMessagePrefix}: {consoleIp} {_mqttPort}";
                            byte[] ackBytes = Encoding.UTF8.GetBytes(ackResponse);
                            await udpClient.SendAsync(ackBytes, ackBytes.Length, result.RemoteEndPoint);
                            Console.WriteLine($"Sent acknowledgment '{ackResponse}' to {result.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                        }
                        else
                        {
                            Console.WriteLine($"Ignored invalid UDP message: '{message}'");
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"UDP receive error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                    }
                }
            }
            catch (SocketException se)
            {
                Console.WriteLine($"Failed to bind UDP port {_broadcastPort}: {se.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                Console.WriteLine("Try: (1) Check port usage with 'netstat -a -n -o' (Windows) or 'sudo netstat -tuln' (Linux). (2) Run as administrator.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"UDP listener error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
            finally
            {
                udpClient?.Close();
                Console.WriteLine($"UDP listener closed at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
        }

        private async Task StartMqttBrokerAsync()
        {
            try
            {
                var mqttFactory = new MqttFactory();
                _mqttServer = mqttFactory.CreateMqttServer();

                var options = new MqttServerOptionsBuilder()
                    .WithDefaultEndpoint()
                    .WithDefaultEndpointPort(_mqttPort)
                    .Build();

                _mqttServer.ClientConnectedAsync += OnClientConnected;
                _mqttServer.ApplicationMessageNotConsumedAsync += OnMessageReceived;  // Handle incoming messages

                await _mqttServer.StartAsync(options);
                Console.WriteLine($"MQTT broker started on port {_mqttPort} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"MQTT broker error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
        }

        private Task OnClientConnected(MqttServerClientConnectedEventArgs args)
        {
            Console.WriteLine($"MQTT client connected: {args.ClientId} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            return Task.CompletedTask;
        }

        private Task OnMessageReceived(MqttApplicationMessageInterceptorContext context)
        {
            var topic = context.ApplicationMessage.Topic;
            var payload = Encoding.UTF8.GetString(context.ApplicationMessage.PayloadSegment);
            Console.WriteLine($"Received MQTT message on {topic}: {payload} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");

            try
            {
                var message = JsonSerializer.Deserialize<Dictionary<string, object>>(payload);
                if (message != null && message.TryGetValue("type", out var typeObj) && typeObj.ToString() == "status_update")
                {
                    // Update device states (e.g., for UI binding)
                    var deviceId = message["device_id"].ToString();
                    var componentId = message["component_id"].ToString();
                    var state = message["state"].ToString();

                    if (!DeviceStates.ContainsKey(deviceId))
                    {
                        DeviceStates[deviceId] = new Dictionary<string, string>();
                    }
                    DeviceStates[deviceId][componentId] = state;
                }
                // Handle other types like device_info, heartbeat similarly
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Message parse error: {ex.Message}");
            }

            return Task.CompletedTask;
        }

        public async Task SendCommandAsync(string deviceId, string componentId, string state)
        {
            if (_mqttServer == null) return;

            var message = new MqttApplicationMessageBuilder()
                .WithTopic($"rv/{deviceId}/commands")
                .WithPayload(JsonSerializer.Serialize(new { type = "command", device_id = deviceId, component_id = componentId, state }))
                .WithQualityOfServiceLevel(MQTTnet.Protocol.MqttQualityOfServiceLevel.AtLeastOnce)
                .Build();

            await _mqttServer.InjectApplicationMessage(new InjectedMqttApplicationMessage(message));
            Console.WriteLine($"Sent command to {deviceId}/{componentId}: {state}");
        }

        // Add StopAsync if needed to shutdown broker
        public async Task StopAsync()
        {
            if (_mqttServer != null)
            {
                await _mqttServer.StopAsync();
            }
        }
    }
}