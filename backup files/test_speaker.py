import asyncio, os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aioesphomeapi import APIClient

# --- CONFIGURATION ---
AIPI_IP = "aipi.local"
HOST_IP = "10.0.100.62"
PORT = 8080
VOICE_FILE = "test_voice.wav"

VOICE_WAV_BYTES = b""

# Tiny HTTP server to host the WAV file for the ESP32
class VoiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "audio/wav")
        self.send_header("Content-Length", str(len(VOICE_WAV_BYTES)))
        self.end_headers()
        self.wfile.write(VOICE_WAV_BYTES)

    def log_message(self, format, *args):
        pass # Keeps your terminal clean

def load_voice_file(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"ERROR: Could not find '{filepath}'. Please put a 16kHz Mono WAV file in this folder.")
    print(f"Loading '{filepath}' into memory...")
    with open(filepath, 'rb') as f:
        return f.read()

async def main():
    global VOICE_WAV_BYTES
    
    try:
        VOICE_WAV_BYTES = load_voice_file(VOICE_FILE)
    except Exception as e:
        print(e)
        return

    # Start the background HTTP server
    server = HTTPServer(('0.0.0.0', PORT), VoiceHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Local HTTP server hosting WAV at http://{HOST_IP}:{PORT}/voice.wav")

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
        url = f"http://{HOST_IP}:{PORT}/voice.wav"

        res = cli.media_player_command(media_player.key, media_url=url)
        if asyncio.iscoroutine(res):
            await res

        print("3. Waiting for playback to complete...")
        # NOTE: I bumped this to 5 seconds so your voice sentence doesn't get cut off. 
        # Increase this if your test file is longer.
        await asyncio.sleep(5.0) 

        print("4. Restoring Microphone...")
        await cli.execute_service(service=restore_mic, data={})

    except Exception as e:
        print(f"Test Failed: {e}")
    finally:
        print("Disconnecting...")
        await cli.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
