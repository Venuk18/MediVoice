import sys
sys.path.insert(0, "backend")
from app.services.speech.tts_service import GnaniTimbreTTS
from app.services.speech.stt_service import GnaniPrismaSTT

tts = GnaniTimbreTTS()
stt = GnaniPrismaSTT()

print("Testing TTS synthesis for 'Search for a cardiologist'...")
wav_bytes = tts.synthesize("Search for a cardiologist", language="en")
print(f"TTS generated {len(wav_bytes)} bytes of audio.")

print("Testing STT transcription...")
res = stt.transcribe(wav_bytes, language="en", content_type="audio/wav")
print("STT Result transcript:", res.get("transcript"))
print("STT confidence:", res.get("confidence"))
