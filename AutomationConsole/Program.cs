using RVNetworkLibrary.Services;
using System.Threading.Tasks;

namespace AutomationConsole
{
    class Program
    {
        static async Task Main(string[] args)
        {
            var service = new NetworkService(5000);
            
            // keep the process alive forever
            await Task.Delay(Timeout.Infinite);

        }
    }
}