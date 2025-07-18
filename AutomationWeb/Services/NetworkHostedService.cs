using Microsoft.Extensions.Hosting;
using System.Threading;
using System.Threading.Tasks;
using 

namespace AutomationWeb
{
    public class NetworkHostedService : IHostedService
    {
        private readonly NetworkService _networkService;

        public NetworkHostedService(NetworkService networkService)
        {
            _networkService = networkService;
        }

        public Task StartAsync(CancellationToken cancellationToken)
        {
            _ = _networkService.RunAsync();
            return Task.CompletedTask;
        }

        public Task StopAsync(CancellationToken cancellationToken)
        {
            // Optionally implement graceful shutdown logic
            return Task.CompletedTask;
        }
    }
}