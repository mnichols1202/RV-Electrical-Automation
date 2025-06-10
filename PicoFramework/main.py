import uasyncio
from pico_network import PicoNetwork
from relay_toggle import RelayToggle

# Global debug flag: True enables debug messages, False disables them
DEBUG = True

if DEBUG:
    print("Debug mode is ON")

async def main():
    if DEBUG:
        print("Starting PicoNetwork")
    pico_net = PicoNetwork(debug=DEBUG)
    await pico_net.start()

    if pico_net.is_connected():
        if DEBUG:
            print("PicoNetwork connected, setting up RelayToggle")
        relay_toggle = RelayToggle(pico_net, pico_net.relay_configs, debug=DEBUG)
        relay_toggle.setup()
        await pico_net.send_device_info()
        uasyncio.create_task(relay_toggle.send_queued_messages())
        uasyncio.create_task(send_heartbeats(pico_net))
        uasyncio.create_task(pico_net.handle_incoming(relay_toggle))

        while True:
            if not pico_net.is_connected():
                if DEBUG:
                    print("Connection lost, attempting to reconnect")
                await pico_net.start()
            await uasyncio.sleep(10)

async def send_heartbeats(pico_net):
    while True:
        if pico_net.is_connected():
            if DEBUG:
                print("Sending heartbeat")
            await pico_net.send_heartbeat()
        else:
            if DEBUG:
                print("Not connected, skipping heartbeat")
        await uasyncio.sleep(30)  # Send heartbeat every 30 seconds

if __name__ == '__main__':
    try:
        uasyncio.run(main())
    except Exception as e:
        print(f'Main error: {e}')