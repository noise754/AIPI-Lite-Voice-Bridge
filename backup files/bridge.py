import asyncio, socket, io, wave, re, requests, math, struct, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aioesphomeapi import APIClient
from faster_whisper import WhisperModel
from gtts import gTTS
from pydub import AudioSegment
from pydub.generators import Sine

# --- CONFIGURATION ---
AIPI_IP = "aipi.local" # Switched to DNS!
HOST_IP = "10.0.100.62" # The Middleman IP
PORT = 8080
GPU_SERVER_URL = "http://10.0.100.52:8080/v1/chat/completions" 
UDP_PORT = 50000

print("DEBUG: Loading Whisper (Tiny.en)...")
stt_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

# --- HTTP SERVER FOR ESP32 AUDIO STREAMING ---
VOICE_WAV_BYTES = b""

class VoiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "audio/wav")
        self.send_header("Content-Length", str(len(VOICE_WAV_BYTES)))
        self.end_headers()
        self.wfile.write(VOICE_WAV_BYTES)

    def log_message(self, format, *args):
        pass # Keeps terminal clean

# --- MASTER AI BRIDGE ---
class MasterBridge:
    def __init__(self, cli):
        self.cli = cli
        self.audio_buffer = bytearray()
        self.is_recording = False
        self.loop = asyncio.get_event_loop()

    async def handle_start(self, conversation_id, sample_rate, audio_settings, wakeword):
        print("\n[EVENT] Voice Start - Capturing Microphone...")
        self.audio_buffer.clear()
        self.is_recording = True
        return UDP_PORT

    async def handle_stop(self, is_cancelled):
        self.is_recording = False
        print(f"[EVENT] Voice Stop - Received {len(self.audio_buffer)} bytes.")
        if len(self.audio_buffer) > 1000:
            self.loop.create_task(self.process_voice())

    async def handle_audio(self, data):
        if self.is_recording:
            self.audio_buffer.extend(data)

    async def process_voice(self):
        try:
            # 1. Transcribe the Audio
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
                f.writeframes(bytes(self.audio_buffer))
            wav_io.seek(0)
            segments, _ = stt_model.transcribe(wav_io, beam_size=1)
            text = " ".join([s.text for s in segments]).strip()
            if not text: return
            print(f"Whisper Heard: {text}")

            # 2. Query Local LLM on the AMD Machine
            r = await asyncio.to_thread(requests.post, GPU_SERVER_URL, json={
                "model": "DeepSeek-R1-1.5B-Q8_0",
                "messages": [{"role": "user", "content": text}],
                "max_tokens": 500,
                "temperature": 0.6
            }, timeout=60)
            
            raw_text = r.json()['choices'][0]['message'].get('content', '')
            clean = re.sub(r'(?i)<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
            if not clean: clean = "I am ready."
            print(f"AI Responded: {clean}")

            # 3. Generate TTS & Build the Audio File
            tts = gTTS(text=clean, lang='en')
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            
            # Convert TTS to 16kHz Mono
            voice_audio = AudioSegment.from_file(mp3_fp, format="mp3").set_frame_rate(16000).set_channels(1).set_sample_width(2)
            
            # Generate the diagnostic beep and stitch it to the front of the voice
            beep = Sine(440).to_audio_segment(duration=500).set_frame_rate(16000).set_channels(1).set_sample_width(2)
            final_audio = beep + voice_audio
            
            # Calculate how long the total audio file is so we know exactly how long to sleep
            playback_duration_sec = len(final_audio) / 1000.0
            
            # Export to WAV and load it into the HTTP server
            out_wav_io = io.BytesIO()
            final_audio.export(out_wav_io, format="wav")
            
            global VOICE_WAV_BYTES
            VOICE_WAV_BYTES = out_wav_io.getvalue()

            # 4. Stream Directly via the Safe HTTP Bypass
            print(f"DEBUG: Waking DAC and Streaming {playback_duration_sec:.2f} seconds of audio...")
            
            _, services = await self.cli.list_entities_services()
            prepare_speaker = next((s for s in services if s.name == "prepare_speaker"), None)
            restore_mic = next((s for s in services if s.name == "restore_mic"), None)
            
            entities, _ = await self.cli.list_entities_services()
            media_player = next((e for e in entities if e.name == "AiPi Media Player"), None)
            
            if prepare_speaker and media_player and restore_mic:
                # Wake up the hardware
                await self.cli.execute_service(service=prepare_speaker, data={})
                await asyncio.sleep(1.0)
                
                # Command the media player to fetch our generated WAV
                url = f"http://{HOST_IP}:{PORT}/voice.wav"
                res = self.cli.media_player_command(media_player.key, media_url=url)
                if asyncio.iscoroutine(res):
                    await res
                    
                # Wait for the entire audio file to finish playing
                await asyncio.sleep(playback_duration_sec + 0.5)
                
                # Turn the amplifier back off and re-engage the mic
                await self.cli.execute_service(service=restore_mic, data={})
                print("Hardware pipeline reset. Ready for next prompt.")
            else:
                print("ERROR: ESP32 services are missing. Check your aipi.yaml.")

        except Exception as e:
            print(f"Processing Error: {e}")

    async def udp_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', UDP_PORT))
        sock.setblocking(False)
        while True:
            try:
                data, _ = await self.loop.sock_recvfrom(sock, 4096)
                if self.is_recording:
                    self.audio_buffer.extend(data)
            except:
                await asyncio.sleep(0.001)

async def main():
    # Start the background HTTP server for the audio payload
    server = HTTPServer(('0.0.0.0', PORT), VoiceHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Internal HTTP Server initialized at http://{HOST_IP}:{PORT}/voice.wav")

    cli = APIClient(AIPI_IP, 6053, password=None)
    bridge = MasterBridge(cli)
    
    while True:
        try:
            print(f"Connecting to AiPi at {AIPI_IP}...")
            await cli.connect(login=True)
            cli.subscribe_voice_assistant(
                handle_start=bridge.handle_start, 
                handle_stop=bridge.handle_stop, 
                handle_audio=bridge.handle_audio
            )
            print("Connected and Subscribed.")
            asyncio.create_task(bridge.udp_listener())
            
            while True:
                await asyncio.sleep(10)
                
        except Exception as e:
            print(f"Connection Error: {e}")
            try: await cli.disconnect()
            except: pass
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
