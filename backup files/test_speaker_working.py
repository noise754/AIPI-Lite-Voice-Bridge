import asyncio, math, struct, wave, io, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aioesphomeapi import APIClient

# --- CONFIGURATION ---
AIPI_IP = "aipi.local"
HOST_IP = "10.0.100.62" 
PORT = 8080

TONE_WAV_BYTES = b""

# Tiny HTTP server to host the WAV file for the ESP32
class ToneHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "audio/wav")
        self.send_header("Content-Length", str(len(TONE_WAV_BYTES)))
        self.end_headers()
        self.wfile.write(TONE_WAV_BYTES)
        
    def log_message(self, format, *args):
        pass # Keeps your terminal clean

def generate_pure_tone(duration_ms=2000, freq=440):
    print(f"Generating {duration_ms}ms tone at {freq}Hz...")
    sample_rate = 16000
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    amplitude = 16000 
    
    beep_data = bytearray()
    for i in range(num_samples):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate))
        beep_data.extend(struct.pack('<h', sample))
        
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2) 
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(beep_data)
        
    return wav_io.getvalue()

async def main():
    global TONE_WAV_BYTES
    TONE_WAV_BYTES = generate_pure_tone()

    # Start the background HTTP server
    server = HTTPServer(('0.0.0.0', PORT), ToneHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Local HTTP server hosting WAV at http://{HOST_IP}:{PORT}/tone.wav")

    cli = APIClient(AIPI_IP, 6053, password=None)
    
    try:
        print(f"Connecting to AiPi at {AIPI_IP}...")
        await cli.connect(login=True)
        
        _, services = await cli.list_entities_services()
        prepare_speaker = next((s for s in services if s.name == "prepare_speaker"), None)
        restore_mic = next((s for s in services if s.name == "restore_mic"), None)
        
        entities, _ = await cli.list_entities_services()
        media_player = next((e for e in entities if e.name == "AiPi Media Player"), None)

        if not prepare_speaker or not restore_mic or not media_player:
            print("ERROR: Could not find required services or media player.")
            return

        print("1. Toggling GPIO9 Amplifier ON and running I2C overrides...")
        await cli.execute_service(service=prepare_speaker, data={})
        
        await asyncio.sleep(1.0) 
        
        print("2. Telling ESP32 to stream the audio URL...")
        url = f"http://{HOST_IP}:{PORT}/tone.wav"
        
        # Send the play command (Removed the invalid has_media_url argument)
        res = cli.media_player_command(media_player.key, media_url=url)
        if asyncio.iscoroutine(res):
            await res
            
        print("3. Waiting for playback to complete...")
        await asyncio.sleep(3.0) 
        
        print("4. Restoring Microphone...")
        await cli.execute_service(service=restore_mic, data={})
        
    except Exception as e:
        print(f"Test Failed: {e}")
    finally:
        print("Disconnecting...")
        await cli.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
