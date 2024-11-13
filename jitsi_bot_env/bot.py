import asyncio
import json
import websockets
from jitsi_bot.config import JITSI_URL, ROOM_NAME, BOT_NAME

class JitsiBot:
    def __init__(self):
        self.ws_url = f"wss://{JITSI_URL}/xmpp-websocket"
        self.room = ROOM_NAME
        self.name = BOT_NAME

    async def connect(self):
        async with websockets.connect(self.ws_url) as websocket:
            print(f"Connected to {self.ws_url}")
            # Basic connection message
            await websocket.send(json.dumps({
                "type": "connection",
                "room": self.room,
                "name": self.name
            }))

            while True:
                try:
                    message = await websocket.recv()
                    print(f"Received message: {message}")
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break

async def main():
    bot = JitsiBot()
    await bot.connect()

if __name__ == "__main__":
    asyncio.run(main()) 