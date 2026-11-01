with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update is_predictable_specialty_or_doctor
old_pred = """        is_predictable_specialty_or_doctor = (
            (doc_search_term is not None or spec_query is not None)
            and not emergency_kind
            and not is_insurance_inquiry(msg)
            and not is_lab_report_inquiry(msg)
            and not session_state.draft.is_complete()
            and (
                bool(re.search(r"\\b(find|search|see|meet|consult|need|want|book|schedule|show|check|looking\\s+for|thinking\\s+to\\s+meet|appointment\\s+with|doctor|specialist|physician)\\b", msg.lower()))
                or len(msg.split()) <= 5
            )
        )"""

new_pred = """        has_slot_pattern = bool(re.search(r"\\bslot-[a-z0-9\\-]+", msg.lower()))
        is_predictable_specialty_or_doctor = (
            self.http_client is None
            and not has_slot_pattern
            and not valid_slot_id
            and (doc_search_term is not None or spec_query is not None)
            and not emergency_kind
            and not is_insurance_inquiry(msg)
            and not is_lab_report_inquiry(msg)
            and not session_state.draft.is_complete()
            and (
                bool(re.search(r"\\b(find|search|see|meet|consult|need|want|book|schedule|show|check|looking\\s+for|thinking\\s+to\\s+meet|appointment\\s+with|doctor|specialist|physician)\\b", msg.lower()))
                or len(msg.split()) <= 5
            )
        )"""

old_pred_crlf = old_pred.replace("\n", "\r\n")
new_pred_crlf = new_pred.replace("\n", "\r\n")

if old_pred_crlf in content:
    content = content.replace(old_pred_crlf, new_pred_crlf, 1)
elif old_pred in content:
    content = content.replace(old_pred, new_pred, 1)
else:
    print("Warning: old_pred not found directly")

# 2. Update is_slot_inquiry deterministic route
old_slot = 'if is_slot_inquiry(msg) and session_state.draft.doctor_id and "get_available_slots" in available_tools and tool_executor is not None:'
new_slot = 'if self.http_client is None and is_slot_inquiry(msg) and session_state.draft.doctor_id and "get_available_slots" in available_tools and tool_executor is not None:'
content = content.replace(old_slot, new_slot, 1)

# 3. Update simple tool short-circuiting
old_short = """                if tool_result.success and tool_intent.tool_name in (
                    "search_doctors", "get_available_slots", "search_hospital_insurance", "check_lab_report_status"
                ):"""
new_short = """                if self.http_client is None and tool_result.success and tool_intent.tool_name in (
                    "search_doctors", "get_available_slots", "search_hospital_insurance", "check_lab_report_status"
                ):"""
old_short_crlf = old_short.replace("\n", "\r\n")
new_short_crlf = new_short.replace("\n", "\r\n")

if old_short_crlf in content:
    content = content.replace(old_short_crlf, new_short_crlf, 1)
elif old_short in content:
    content = content.replace(old_short, new_short, 1)
else:
    print("Warning: old_short not found directly")

with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated adapters.py successfully")

