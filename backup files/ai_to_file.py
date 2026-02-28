import requests
import io
import re
from gtts import gTTS
from pydub import AudioSegment, effects

# --- CONFIG ---
GPU_SERVER_URL = "http://10.0.100.52:8080/v1/chat/completions"
# We add a strict instruction to provide the story immediately
PROMPT = "Write a 2-sentence funny story about a robot. Start the story immediately. No introductions."

print(f"1. Requesting from DeepSeek-R1 (.52)...")
payload = {
    "model": "DeepSeek-R1-1.5B-Q8_0",
    "messages": [
        {"role": "system", "content": "You are a direct storyteller. Do not provide a thinking phase. Output only the story."},
        {"role": "user", "content": PROMPT}
    ],
    "max_tokens": 300,
    "temperature": 0.2 # Lower temperature makes it more direct
}

try:
    response = requests.post(GPU_SERVER_URL, json=payload, timeout=60)
    if response.status_code == 200:
        data = response.json()
        message = data['choices'][0]['message']
        
        # FIX: Check both content AND reasoning_content
        content = message.get('content', '')
        reasoning = message.get('reasoning_content', '')
        
        # If content is empty, the story might be in the reasoning block
        full_response = content if content else reasoning
        
        # Strip any <think> tags if they exist
        clean_text = re.sub(r'(?i)<think>.*?</think>', '', full_response, flags=re.DOTALL).strip()
        
        if not clean_text:
            print("ERROR: AI returned no text in content or reasoning.")
            exit()

        print(f"   AI Response: {clean_text}")

        print(f"2. Generating speech on Brain (.62)...")
        tts = gTTS(text=clean_text, lang='en')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)

        print(f"3. Formatting audio...")
        audio = AudioSegment.from_file(mp3_fp, format="mp3")
        audio = effects.normalize(audio)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        print(f"4. Saving to 'ai_story_test.wav'...")
        audio.export("ai_story_test.wav", format="wav")
        print("\nSUCCESS! You can now listen to 'ai_story_test.wav'.")

    else:
        print(f"ERROR: Server status {response.status_code}")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
