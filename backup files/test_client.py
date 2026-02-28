import asyncio
import websockets

async def test():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        print("Connected! Sending test trigger...")
        # Send 1 second of 'silence' (raw PCM bytes) to trigger the STT
        # Whisper might say 'no speech', but it proves the pipe works.
        await websocket.send(b'\x00' * 32000) 
        
        try:
            # Wait for the AI to send back the voice file
            response = await asyncio.wait_for(websocket.recv(), timeout=30)
            print(f"Received {len(response)} bytes of audio back from the AI!")
            with open("test_response.wav", "wb") as f:
                f.write(response)
            print("Saved response to test_response.wav")
        except Exception as e:
            print(f"No audio returned (expected if silence was sent): {e}")

asyncio.run(test())
