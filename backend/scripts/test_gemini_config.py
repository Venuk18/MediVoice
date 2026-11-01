import os
import json
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

print(f"Testing model endpoint: {url}")

# Test 1: Standard generation
p1 = {
    "contents": [{"parts": [{"text": "Hello, respond with 'OK'."}]}]
}
with httpx.Client(timeout=20.0) as client:
    r1 = client.post(url, headers=headers, json=p1)
    print("Test 1 (Standard):", r1.status_code)
    if r1.status_code == 200:
        print("Test 1 Reply:", r1.json()["candidates"][0]["content"]["parts"])

# Test 2: Function calling with search_doctors tool
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
p2 = {
    "contents": [{"parts": [{"text": "I need to see a cardiologist for my heart"}]}],
    "tools": [{"functionDeclarations": [tool_spec]}]
}
with httpx.Client(timeout=20.0) as client:
    r2 = client.post(url, headers=headers, json=p2)
    print("Test 2 (Function calling):", r2.status_code)
    if r2.status_code == 200:
        print("Test 2 Parts:", r2.json()["candidates"][0]["content"]["parts"])

# Test 3: Thinking config tests
for cfg_name, cfg in [
    ("thinkingBudget: 1024", {"thinkingConfig": {"thinkingBudget": 1024}}),
    ("thinkingLevel: 'low'", {"thinkingConfig": {"thinkingLevel": "low"}}),
    ("thinkingLevel: 'normal'", {"thinkingConfig": {"thinkingLevel": "normal"}}),
]:
    p3 = {
        "contents": [{"parts": [{"text": "What is 2+2?"}]}],
        "generationConfig": cfg
    }
    with httpx.Client(timeout=20.0) as client:
        r3 = client.post(url, headers=headers, json=p3)
        print(f"Test 3 ({cfg_name}): status={r3.status_code}")
        if r3.status_code != 200:
            print("  Error:", r3.text[:150])

