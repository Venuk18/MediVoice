import re

with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Define is_slot_inquiry function near is_flexible_slot_request
slot_inquiry_def = """def is_slot_inquiry(text: str) -> bool:
    \"\"\"
    Detects when a patient is inquiring about available appointment slots or timings.
    \"\"\"
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    patterns = [
        r"\\b(?:check|show|list|find|see|what|any|get)\\s+(?:available\\s+)?slots?\\b",
        r"\\b(?:available|open|free)\\s+slots?\\b",
        r"\\b(?:what\\s+times?|what\\s+slots?|when\\s+is\\s+(?:he|she|dr|the\\s+doctor))\\s*(?:available|open|free)?\\b",
        r"\\b(?:timings?|time\\s+slots?|appointment\\s+times?|openings?)\\b",
        r"(?:స్లాట్లు|సమయాలు|நேரங்கள்|ಸ್ಲಾಟ್‌ಗಳು|समय|स्लॉट)",
    ]
    return any(re.search(p, low, re.IGNORECASE) for p in patterns)

"""

if "def is_slot_inquiry" not in content:
    content = content.replace("def is_flexible_slot_request", slot_inquiry_def + "def is_flexible_slot_request", 1)

# 2. Add last_turn_timings and _record_timings to GeminiReasoningAdapter
timings_init = """        self.last_error: Optional[str] = None
        self.last_model_used: Optional[str] = None
        self.last_turn_timings: Dict[str, Any] = {}"""

if "        self.last_turn_timings: Dict[str, Any] = {}" not in content:
    content = content.replace(
        "        self.last_error: Optional[str] = None\n        self.last_model_used: Optional[str] = None",
        timings_init,
        1
    )
    content = content.replace(
        "        self.last_error: Optional[str] = None\r\n        self.last_model_used: Optional[str] = None",
        timings_init.replace("\n", "\r\n"),
        1
    )

record_timings_helper = """    def _record_timings(
        self,
        initial_gemini_ms: float,
        tool_router_ms: float,
        followup_gemini_ms: float,
        gemini_calls_count: int,
        t_start: float,
    ) -> None:
        total_time = (time.perf_counter() - t_start) * 1000
        orch_ms = max(0.0, total_time - (initial_gemini_ms + tool_router_ms + followup_gemini_ms))
        self.last_turn_timings = {
            "initial_gemini_request_ms": round(initial_gemini_ms, 2),
            "tool_router_ms": round(tool_router_ms, 2),
            "followup_gemini_request_ms": round(followup_gemini_ms, 2),
            "gemini_calls_count": gemini_calls_count,
            "orchestration_ms": round(orch_ms, 2),
        }

    def _build_tool_declarations(self, available_tools: List[str]) -> List[Dict[str, Any]]:"""

if "def _record_timings" not in content:
    content = content.replace(
        "    def _build_tool_declarations(self, available_tools: List[str]) -> List[Dict[str, Any]]:",
        record_timings_helper,
        1
    )

# 3. Add timing initialization in plan_and_respond
old_plan_start = """    def plan_and_respond(
        self,
        session_state: AgentSessionState,
        user_message: str,
        available_tools: List[str],
        tool_executor: Optional[Callable[[ToolCallIntent], ToolExecutionResult]] = None,
    ) -> AgentAction:
        self.last_error = None
        msg = user_message.strip()"""

new_plan_start = """    def plan_and_respond(
        self,
        session_state: AgentSessionState,
        user_message: str,
        available_tools: List[str],
        tool_executor: Optional[Callable[[ToolCallIntent], ToolExecutionResult]] = None,
    ) -> AgentAction:
        t_start = time.perf_counter()
        initial_gemini_request_ms = 0.0
        tool_router_ms = 0.0
        followup_gemini_request_ms = 0.0
        gemini_calls_count = 0
        self.last_error = None
        self.last_turn_timings = {}
        msg = user_message.strip()"""

if old_plan_start.replace("\n", "\r\n") in content:
    content = content.replace(old_plan_start.replace("\n", "\r\n"), new_plan_start.replace("\n", "\r\n"), 1)
elif old_plan_start in content:
    content = content.replace(old_plan_start, new_plan_start, 1)

# Ensure time is imported in adapters.py
if "import time" not in content:
    content = "import time\n" + content

with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Part 1: adapters.py updated with slot inquiry and timing helpers.")

