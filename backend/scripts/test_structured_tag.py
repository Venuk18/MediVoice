import os, json, httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")
key = os.getenv("GEMINI_API_KEY")
url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
p = {
    "systemInstruction": {"parts": [{"text": 'At the end of your response append <draft>{"specialty": "Cardiology"}</draft>'}]},
    "contents": [{"parts": [{"text": "I need a heart checkup"}]}],
    "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}
}
with httpx.Client(timeout=20.0) as client:
    r = client.post(url, headers=headers, json=p)
    parts = r.json()["candidates"][0]["content"]["parts"]
    for part in parts:
        if "text" in part:
            print("Response text:\n", part["text"])

