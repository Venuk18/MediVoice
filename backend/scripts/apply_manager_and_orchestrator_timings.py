# 1. Update conversation_manager.py
with open("backend/app/agent/conversation_manager.py", "r", encoding="utf-8") as f:
    cm_code = f.read()

# Add t_start in process_message
old_cm_start = """        session = self.get_or_create_session(session_id, patient_reference)
        session.last_active_at = datetime.now(timezone.utc).isoformat()"""

new_cm_start = """        t_start = time.perf_counter()
        session = self.get_or_create_session(session_id, patient_reference)
        session.last_active_at = datetime.now(timezone.utc).isoformat()"""

if old_cm_start.replace("\n", "\r\n") in cm_code:
    cm_code = cm_code.replace(old_cm_start.replace("\n", "\r\n"), new_cm_start.replace("\n", "\r\n"), 1)
elif old_cm_start in cm_code:
    cm_code = cm_code.replace(old_cm_start, new_cm_start, 1)

# Add timings return at end of process_message
old_cm_return = """        # Record assistant reply in history
        session.history.append(ChatMessage(role="assistant", content=final_reply))
        return self._build_response(session, final_reply, turn_tool_calls=turn_tool_calls)"""

new_cm_return = """        # Record assistant reply in history
        session.history.append(ChatMessage(role="assistant", content=final_reply))
        turn_timings = dict(getattr(self.adapter, "last_turn_timings", {}) or {})
        turn_timings["agent_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        if "gemini_calls_count" not in turn_timings:
            turn_timings["gemini_calls_count"] = 0
        return self._build_response(session, final_reply, turn_tool_calls=turn_tool_calls, timings=turn_timings)"""

if old_cm_return.replace("\n", "\r\n") in cm_code:
    cm_code = cm_code.replace(old_cm_return.replace("\n", "\r\n"), new_cm_return.replace("\n", "\r\n"), 1)
elif old_cm_return in cm_code:
    cm_code = cm_code.replace(old_cm_return, new_cm_return, 1)

with open("backend/app/agent/conversation_manager.py", "w", encoding="utf-8") as f:
    f.write(cm_code)
print("Updated conversation_manager.py successfully.")

# 2. Update voice_orchestrator.py
with open("backend/app/services/speech/voice_orchestrator.py", "r", encoding="utf-8") as f:
    vo_code = f.read()

old_vo_timings = """        total_ms = (time.perf_counter() - t_voice_start) * 1000
        timings = {
            "transcode_ms": round(transcode_ms, 2),
            "stt_ms": round(stt_ms, 2),
            "agent_ms": round(agent_ms, 2),
            "tool_ms": round(tool_ms, 2),
            "tts_ms": round(tts_ms, 2),
            "total_turn_ms": round(total_ms, 2),
        }"""

new_vo_timings = """        total_ms = (time.perf_counter() - t_voice_start) * 1000
        timings = {
            "transcode_ms": round(transcode_ms, 2),
            "stt_ms": round(stt_ms, 2),
            "agent_ms": round(agent_ms, 2),
            "tool_ms": round(tool_ms, 2),
            "tts_ms": round(tts_ms, 2),
            "total_turn_ms": round(total_ms, 2),
            "first_audible_response_ms": round(total_ms, 2),
        }
        if chat_response.timings:
            timings.update(chat_response.timings)"""

if old_vo_timings.replace("\n", "\r\n") in vo_code:
    vo_code = vo_code.replace(old_vo_timings.replace("\n", "\r\n"), new_vo_timings.replace("\n", "\r\n"), 1)
elif old_vo_timings in vo_code:
    vo_code = vo_code.replace(old_vo_timings, new_vo_timings, 1)

with open("backend/app/services/speech/voice_orchestrator.py", "w", encoding="utf-8") as f:
    f.write(vo_code)
print("Updated voice_orchestrator.py successfully.")

