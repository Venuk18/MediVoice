file_path = "backend/app/services/speech/__init__.py"
with open(file_path, "r", encoding="utf-8") as f:
    c = f.read().replace("\r\n", "\n")

c = c.replace(
    "    normalize_tts_language,\n)",
    "    normalize_tts_language,\n    is_fixed_greeting,\n    clear_greeting_cache,\n)"
)
c = c.replace(
    '    "generate_synthetic_wav",\n]',
    '    "generate_synthetic_wav",\n    "is_fixed_greeting",\n    "clear_greeting_cache",\n]'
)

with open(file_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(c)
print("Updated __init__.py")

