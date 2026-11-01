import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")
api_key = os.getenv("GEMINI_API_KEY")
model = "gemini-3.5-flash-lite"
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
headers = {
    "x-goog-api-key": api_key,
    "Content-Type": "application/json",
    "User-Agent": "aistudio-build",
}

tool_spec = {
    "name": "search_doctors",
    "description": "Search doctors by specialty",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "specialty_or_department": {
                "type": "STRING",
                "description": "Specialty name"
            }
        },
        "required": ["specialty_or_department"]
    }
}

configs = [
    ("Default (No thinkingConfig)", None),
    ("thinkingLevel: 'low'", {"thinkingConfig": {"thinkingLevel": "low"}}),
    ("thinkingBudget: 1024", {"thinkingConfig": {"thinkingBudget": 1024}}),
    ("thinkingBudget: 512", {"thinkingConfig": {"thinkingBudget": 512}}),
]

for name, cfg in configs:
    p = {
        "contents": [{"parts": [{"text": "I need to see a cardiologist for my heart"}]}],
        "tools": [{"functionDeclarations": [tool_spec]}]
    }
    if cfg:
        p["generationConfig"] = cfg
    
    t0 = time.perf_counter()
    with httpx.Client(timeout=20.0) as client:
        r = client.post(url, headers=headers, json=p)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        parts = r.json()["candidates"][0]["content"]["parts"]
        has_fc = any("functionCall" in part for part in parts)
        print(f"Config '{name}': {lat:.1f}ms | Status 200 | Has FunctionCall: {has_fc}")
    else:
        print(f"Config '{name}': {lat:.1f}ms | Status {r.status_code} | {r.text[:100]}")

