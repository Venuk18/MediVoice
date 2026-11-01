file_path = "backend/app/api/v1/voice.py"
with open(file_path, "r", encoding="utf-8") as f:
    c = f.read().replace("\r\n", "\n")

c = c.replace(
    "    SpeechServiceError,\n    voice_orchestrator,\n)",
    "    SpeechServiceError,\n    voice_orchestrator,\n    is_fixed_greeting,\n)"
)

old_resp = """        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'inline; filename="assistant_response.wav"',
                "Cache-Control": "no-cache",
            },
        )"""

new_resp = """        is_fixed = is_fixed_greeting(payload.text)
        cache_ctrl = "public, max-age=86400" if is_fixed else "no-cache"
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'inline; filename="assistant_response.wav"',
                "Cache-Control": cache_ctrl,
                "X-MediVoice-Cache": "HIT" if is_fixed else "DYNAMIC",
            },
        )"""

assert old_resp in c, "old_resp not found in voice.py"
c = c.replace(old_resp, new_resp, 1)

with open(file_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(c)
print("Updated voice.py")

