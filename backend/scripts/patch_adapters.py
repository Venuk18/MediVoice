import re

with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

target = "KNOWN_INSURERS: List[Dict[str, Any]] = ["
func_code = '''def is_slot_inquiry(text: Optional[str]) -> bool:
    """
    Detects whether the user is inquiring about available appointment slots, timings, or dates.
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    if re.search(
        r"\\b(slot|slots|time|times|timing|timings|schedule|available\\s+slots|open\\s+slots|free\\s+slots|next\\s+available|show\\s+slots|check\\s+slots|when\\s+available|what\\s+time|when\\s+is|when\\s+can)\\b",
        low,
    ):
        return True
    indic_slot_terms = (
        "\\u0c38\\u0c4d\\u0c32\\u0c3e\\u0c1f\\u0c4d", "\\u0c38\\u0c4d\\u0c32\\u0c3e\\u0c1f\\u0c4d\\u0c32\\u0c41", "\\u0c38\\u0c2e\\u0c2f\\u0c02", "\\u0c1f\\u0c48\\u0c2e\\u0c3f\\u0c02\\u0c17\\u0c4d\\u0c38\\u0c4d",
        "\\u0938\\u094d\\u0932\\u0949\\u091f", "\\u0938\\u092e\\u092f", "\\u0909\\u092a\\u0932\\u092c\\u094d\\u0927",
        "\\u0bb8\\u0bcd\\u0bb2\\u0bbe\\u0b9f\\u0bcd", "\\u0ba8\\u0bc7\\u0bb0\\u0bae\\u0bcd", "\\u0ba8\\u0bc7\\u0bb0\\u0b99\\u0bcd\\u0b95\\u0bb3\\u0bcd",
        "\\u0cb8\\u0ccd\\u0cb2\\u0cbe\\u0c9f\\u0ccd", "\\u0cb8\\u0cae\\u0caf", "\\u0cb2\\u0cad\\u0ccd\\u0caf",
    )
    return any(term in text for term in indic_slot_terms)


'''

if "def is_slot_inquiry" not in content:
    assert target in content, "Target not found"
    new_content = content.replace(target, func_code + target, 1)
    with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Inserted is_slot_inquiry successfully")
else:
    print("is_slot_inquiry already present")

