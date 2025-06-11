# main.py
import uasyncio
from pico_network import PicoNetwork
from relay_toggle import RelayToggle

async def main():
    print('Starting main')
    # Initialize PicoNetwork
    pico_net = PicoNetwork()

    # Wait for network to connect and stabilize
    print('Attempting network connection')
    await pico_net.start()
    if pico_net.is_connected():
        print('Initial network connection established')
    else:
        print('Initial network connection failed, proceeding with relay setup')

    # Initialize RelayToggle after network is settled
    relay_toggle = RelayToggle(pico_net, pico_net.relay_configs)
    relay_toggle.setup()
    print('RelayToggle setup complete')

    # Run the message queue processor
    uasyncio.create_task(relay_toggle.send_queued_messages())

    # Monitor and maintain network connection
    while True:
        if not pico_net.is_connected():
            print('Network disconnected, attempting to reconnect')
            await pico_net.start()
            if pico_net.is_connected():
                print('Network reconnected successfully')
            else:
                print('Network reconnection failed, continuing')
        else:
            print('Network connection active')
        await uasyncio.sleep(10)

if __name__ == '__main__':
    try:
        uasyncio.run(main())
    except Exception as e:
        print(f'Main error: {e}')
        print('Continuing execution to maintain relay functionality')
