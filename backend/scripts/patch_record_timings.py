with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

target = "        self.last_error: Optional[str] = None\r\n        self.last_model_used: Optional[str] = None\r\n"
if target not in content:
    target = "        self.last_error: Optional[str] = None\n        self.last_model_used: Optional[str] = None\n"

insertion = """        self.last_turn_timings: Dict[str, Any] = {}

    def _record_timings(
        self,
        initial_gemini_request_ms: float,
        tool_router_ms: float,
        followup_gemini_request_ms: float,
        gemini_calls_count: int,
        t_start: float,
    ) -> None:
        total_agent_ms = round((time.perf_counter() - t_start) * 1000, 2)
        self.last_turn_timings = {
            "initial_gemini_request_ms": round(initial_gemini_request_ms, 2),
            "tool_router_ms": round(tool_router_ms, 2),
            "followup_gemini_request_ms": round(followup_gemini_request_ms, 2),
            "gemini_calls_count": gemini_calls_count,
            "agent_ms": total_agent_ms,
        }
"""

if "def _record_timings" not in content:
    assert target in content, "Target not found in content"
    if "\r\n" in target:
        insertion = insertion.replace("\n", "\r\n")
    new_content = content.replace(target, target + insertion, 1)
    with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Added _record_timings successfully")
else:
    print("Already present")

