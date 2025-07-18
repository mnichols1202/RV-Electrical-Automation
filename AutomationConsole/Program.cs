using RVNetworkLibrary.Services;
using System.Threading.Tasks;

namespace AutomationConsole
{
    class Program
    {
        static async Task Main(string[] args)
        {
            var service = new NetworkService();
            await service.StartAsync();
        }
    }
}