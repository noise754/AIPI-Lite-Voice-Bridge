# AiPi: Local Voice Assistant Bridge (V1 Stable)

> **A Note to the Community:** This bridge represents what we came up with to solve some brutal memory fragmentation, state machine deadlocks, and EMI interference hurdles with the ESP32-S3 audio pipeline on AIPI-Lite AI Robot (known as Xorigin and XiaoZhi). While this iteration is highly stable, there might be better, cleaner, or more native ways to handle some of these workarounds. We are releasing this publicly so the community can build on it, improve it, and make it even better. Pull requests, forks, and ideas are highly encouraged!

## Architecture Overview
This project bridges a custom ESP32-S3 hardware agent with a local, multi-server AI stack. It bypasses the rigid ESPHome Voice Assistant pipeline to allow dynamic TTS streaming over a local HTTP connection.

* **Ears (Hardware):** ESP32-S3 captures raw I2S audio via an external microphone and streams it over UDP to the Python bridge.
* **Brain (Middleman & Backend):** * A Python Bridge transcribes the audio using `faster-whisper`.
  * The transcribed text is sent to a local LLM (in my case, DeepSeek-R1-1.5B) running on an AMD 395+ (known as Strix Halo) server (but you do you).
  * The bridge includes custom regex logic to safely parse and strip DeepSeek's `<think>` tags, gracefully defaulting to reading the thought process if the model fails to provide a final formatted answer.
* **Mouth (Hardware):** The LLM text is converted to speech via `gTTS`, stitched with a wake beep and a hardware-flushing silence tail, dynamically volume-adjusted, and hosted on a temporary local HTTP server. The ESP32 is commanded to stream this WAV file natively.

## Key Hardware Workarounds
1. **Octal PSRAM:** The ESP32-S3 is explicitly configured to use `mode: octal` PSRAM to prevent the massive `media_player` HTTP buffers from exhausting the SRAM and crashing the microphone allocation.
2. **Decoupled Pipelines:** The `voice_assistant` component in ESPHome is strictly "listen-only". It never attempts to lock the speaker bus, allowing the `media_player` to stream asynchronously.
3. **EMI Isolation:** The `speaker_enable` pin (GPIO9) is strictly toggled to physically cut power to the amplifier during microphone capture. This prevents the WiFi antenna's electromagnetic interference from bleeding into the analog audio circuit as deafening white noise.
4. **I2C Deep Mute:** The `restore_mic` service explicitly commands `media_player.stop` and sends a deep mute command via I2C to the ES8311 DAC. This physically releases the I2S clocks between prompts without killing the shared data lines the microphone relies on.
5. **Dynamic Audio Control:** The Python script uses a `?t=timestamp` URL parameter for cache-busting so the ESP32 never plays stale audio, and includes a built-in `pydub` decibel reduction step to safely limit physical speaker volume.

Acknowledgements & Credits
This build stands on the shoulders of giants. A massive thank you to the developers who laid the groundwork for this hardware:

Robert Lipe: For the phenomenal deep-dive engineering and documentation on the AiPi hardware and I2S/I2C interfacing. Read his work here: https://www.robertlipe.com/449-2/

sticks918: For the foundational ESPHome configurations and the AiPi-Lite repository that made this custom integration possible. Check out the repo here: https://github.com/sticks918/AIPI-Lite-ESPHome

Running the Agent
Flash aipi.yaml (I was using Visual Studio Code) to your ESP32-S3.

Ensure your AI backend server is running its local LLM (in my case it is llama-cpp).

Start the bridge: python3 bridge.py


Dependencies
Ensure your middleman server running the Python bridge has the following installed in its virtual environment:

```bash
pip install aioesphomeapi faster-whisper gtts pydub requests
