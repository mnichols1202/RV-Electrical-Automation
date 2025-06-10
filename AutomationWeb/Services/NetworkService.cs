using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using System.Net.NetworkInformation;
using System.IO;

namespace AutomationWeb
{
    public class NetworkService
    {
        private readonly int _broadcastPort;
        private readonly int _tcpPort;
        private readonly string _ackMessagePrefix;

        public event Action<string>? MessageReceived;

        public NetworkService(int broadcastPort = 5000, int tcpPort = 5001, string ackMessagePrefix = "ACK")
        {
            _broadcastPort = broadcastPort;
            _tcpPort = tcpPort;
            _ackMessagePrefix = ackMessagePrefix;
        }

        public async Task RunAsync()
        {
            LogLocalIpAddresses();
            await Task.WhenAll(ListenForBroadcastAsync(), StartTcpServerAsync());
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
                            // Respond with ACK: <console_ip> <TcpPort>
                            string consoleIp = GetLocalIpAddress();
                            string ackResponse = $"{_ackMessagePrefix}: {consoleIp} {_tcpPort}";
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

        private async Task StartTcpServerAsync()
        {
            TcpListener? listener = null;
            try
            {
                listener = new TcpListener(IPAddress.Any, _tcpPort);
                listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                listener.Start();
                Console.WriteLine($"TCP server started on port {_tcpPort} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");

                while (true)
                {
                    try
                    {
                        TcpClient client = await listener.AcceptTcpClientAsync();
                        Console.WriteLine($"Accepted TCP connection from {client.Client.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                        _ = HandleTcpClientAsync(client); // Handle in background
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"TCP accept error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                    }
                }
            }
            catch (SocketException se)
            {
                Console.WriteLine($"Failed to bind TCP port {_tcpPort}: {se.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                Console.WriteLine("Try: (1) Check port usage with 'netstat -a -n -o' (Windows) or 'sudo netstat -tuln' (Linux). (2) Run as administrator.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"TCP server error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
            finally
            {
                listener?.Stop();
                Console.WriteLine($"TCP server stopped at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
        }

        private async Task HandleTcpClientAsync(TcpClient client)
        {
            try
            {
                using NetworkStream stream = client.GetStream();
                byte[] buffer = new byte[64];
                while (client.Connected)
                {
                    try
                    {
                        int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length);
                        if (bytesRead == 0) // Connection closed
                            break;
                        string message = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                        MessageReceived?.Invoke($"TCP: '{message}' from {client.Client.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                        Console.WriteLine($"Received from TCP client: '{message}' from {client.Client.RemoteEndPoint} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");

                        byte[] response = Encoding.UTF8.GetBytes($"Server received: {message}");
                        await stream.WriteAsync(response, 0, response.Length);
                        Console.WriteLine($"Sent response to TCP client: 'Server received: {message}' at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                    }
                    catch (IOException)
                    {
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"TCP client error: {ex.Message} at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
            finally
            {
                client.Close();
                Console.WriteLine($"TCP client connection closed at {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            }
        }
    }
}