// AutomationWeb/Services/NetworkHostedService.cs
using Microsoft.Extensions.Hosting;
using System;
using System.Threading;
using System.Threading.Tasks;
using RVNetworkLibrary.Services;

namespace AutomationWeb.Services
{
    public class NetworkHostedService : IHostedService
    {
        private readonly NetworkService _networkService;

        public NetworkHostedService(NetworkService networkService)
        {
            _networkService = networkService ?? throw new ArgumentNullException(nameof(networkService));
            _networkService.MessageReceived += OnMessageReceived;
        }

        public Task StartAsync(CancellationToken cancellationToken)
        {
            Console.WriteLine("Starting NetworkHostedService");
            return _networkService.StartAsync(cancellationToken);
        }

        public Task StopAsync(CancellationToken cancellationToken)
        {
            Console.WriteLine("Stopping NetworkHostedService");
            _networkService.MessageReceived -= OnMessageReceived;
            _networkService.Stop();
            return Task.CompletedTask;
        }

        private void OnMessageReceived(string type, object message)
        {
            // Handle incoming messages (e.g., update Blazor UI state)
            Console.WriteLine($"Message received in hosted service: Type={type}, Message={message}");
            // Later: Update Blazor state (e.g., SignalR or StateContainer)
        }
    }
}