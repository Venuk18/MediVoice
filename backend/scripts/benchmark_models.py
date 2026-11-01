"""
MediVoice AI — Gemini Model Benchmark and Latency Evaluation Script.
Compares Gemini 2.5 Flash, Gemini 3.5 Flash, and Gemini 3.5 Flash-Lite
across identical clinical and conversational appointment scenarios.
"""

import os
import sys
import time
import json
import statistics
from typing import Dict, Any, List, Optional

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.agent.schemas import AgentSessionState, BookingDraft, ToolCallIntent, ToolExecutionResult
from app.agent.adapters import GeminiReasoningAdapter, ReasoningAdapterError
from app.agent.tool_router import RestrictedToolRouter
from app.agent.conversation_manager import ConversationManager


def run_single_turn_benchmark(
    adapter: GeminiReasoningAdapter,
    db,
    user_message: str,
    draft_setup: Optional[Dict[str, Any]] = None,
    previous_assistant_question: Optional[str] = None,
    expected_tool: Optional[str] = None,
    expected_arg_key: Optional[str] = None,
    expected_arg_val: Optional[str] = None,
    expected_reply_phrase: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs a single live conversational turn and measures latency and accuracy metrics."""
    router = RestrictedToolRouter()
    manager = ConversationManager(tool_router=router, adapter=adapter)
    session_id = f"bench-{int(time.time() * 1000)}"
    session = manager.get_or_create_session(session_id)

    if draft_setup:
        for k, v in draft_setup.items():
            setattr(session.draft, k, v)
    if previous_assistant_question:
        session.previous_assistant_question = previous_assistant_question

    first_response_latency_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    model_call_rounds = 0
    error: Optional[str] = None
    tool_calls_executed: List[str] = []
    reply_text = ""
    tool_selection_correct = False
    args_correct = False
    context_retained = True

    t_start = time.perf_counter()
    try:
        res = manager.process_message(db, message=user_message, session_id=session_id)
        total_latency_ms = (time.perf_counter() - t_start) * 1000.0
        # In multi-round REST calls, first call latency is approximated by turn latency or round tracker
        first_response_latency_ms = total_latency_ms / max(len(res.tool_calls) + 1, 1)
        reply_text = res.reply
        tool_calls_executed = [tc.tool_name for tc in res.tool_calls]
        model_call_rounds = len(res.tool_calls) + 1

        if expected_tool is None:
            tool_selection_correct = len(res.tool_calls) == 0
            args_correct = True
        else:
            matching_tc = [tc for tc in res.tool_calls if tc.tool_name == expected_tool]
            if matching_tc:
                tool_selection_correct = True
                if expected_arg_key and expected_arg_val:
                    # Check argument correctness
                    args = matching_tc[0].arguments if hasattr(matching_tc[0], "arguments") else {}
                    val = str(args.get(expected_arg_key, "")).lower()
                    args_correct = expected_arg_val.lower() in val
                else:
                    args_correct = True
            else:
                tool_selection_correct = False

        if expected_reply_phrase:
            context_retained = expected_reply_phrase.lower() in reply_text.lower()

    except Exception as exc:
        total_latency_ms = (time.perf_counter() - t_start) * 1000.0
        first_response_latency_ms = total_latency_ms
        error = str(exc)

    return {
        "user_message": user_message,
        "first_response_latency_ms": first_response_latency_ms,
        "total_latency_ms": total_latency_ms,
        "model_call_rounds": model_call_rounds,
        "tools_executed": tool_calls_executed,
        "tool_selection_correct": tool_selection_correct,
        "args_correct": args_correct,
        "context_retained": context_retained,
        "reply_preview": reply_text[:120] if reply_text else "",
        "error": error,
    }


def run_benchmark_suite(model_name: str, enable_fallback: bool = False, trials_per_scenario: int = 2) -> Dict[str, Any]:
    """Executes the full suite of required test scenarios across multiple trials."""
    db = SessionLocal()
    api_key = settings.GEMINI_API_KEY.strip()
    adapter = GeminiReasoningAdapter(
        api_key=api_key,
        model=model_name,
        enable_model_fallback=enable_fallback,
        timeout_seconds=25.0,
    )

    scenarios = [
        {
            "id": "cardiology_search",
            "name": "Cardiology Doctor Search",
            "message": "I need to consult a cardiologist for chest pain",
            "expected_tool": "search_doctors",
            "expected_arg_key": "specialty_or_department",
            "expected_arg_val": "Cardiology",
        },
        {
            "id": "flexible_slot",
            "name": "'Anyone is okay' Slot Selection",
            "message": "Anyone is okay, earliest slot please",
            "draft_setup": {"specialty": "Cardiology"},
            "expected_tool": "search_doctors",
            "expected_arg_key": "specialty_or_department",
            "expected_arg_val": "Cardiology",
        },
        {
            "id": "contextual_no",
            "name": "Contextual 'No' for New Patient",
            "message": "No, I'm new here",
            "previous_question": "Before preparing your appointment, may I know whether you've visited Aarogya One Hospital before?",
            "expected_tool": None,
            "expected_reply_phrase": "name",
        },
        {
            "id": "insurance_lookup",
            "name": "Insurance Provider Lookup",
            "message": "Do you accept Star Health Insurance?",
            "expected_tool": "search_hospital_insurance",
            "expected_arg_key": "query",
            "expected_arg_val": "Star Health",
        },
        {
            "id": "lab_verification",
            "name": "Lab Report Verification",
            "message": "Check my lab report with verification code 847291",
            "expected_tool": "check_lab_report_status",
            "expected_arg_key": "verification_code",
            "expected_arg_val": "847291",
        },
        {
            "id": "multilingual_telugu",
            "name": "Telugu Specialty Inquiry",
            "message": "నాకు గుండె నొప్పిగా ఉంది, కార్డియాలజిస్ట్ కావాలి",
            "expected_tool": "search_doctors",
            "expected_arg_key": "specialty_or_department",
            "expected_arg_val": "Cardiology",
        },
        {
            "id": "multilingual_hindi",
            "name": "Hindi Consultation Inquiry",
            "message": "मुझे बुखार है, क्या जनरल फिजिशियन मिल सकते हैं?",
            "expected_tool": "search_doctors",
            "expected_arg_key": "specialty_or_department",
            "expected_arg_val": "General Medicine",
        },
    ]

    results = []
    print(f"\n=======================================================")
    print(f"BENCHMARKING MODEL: {model_name} (Fallback={enable_fallback})")
    print(f"=======================================================")

    for sc in scenarios:
        scenario_trials = []
        for trial in range(trials_per_scenario):
            trial_res = run_single_turn_benchmark(
                adapter=adapter,
                db=db,
                user_message=sc["message"],
                draft_setup=sc.get("draft_setup"),
                previous_assistant_question=sc.get("previous_question"),
                expected_tool=sc.get("expected_tool"),
                expected_arg_key=sc.get("expected_arg_key"),
                expected_arg_val=sc.get("expected_arg_val"),
                expected_reply_phrase=sc.get("expected_reply_phrase"),
            )
            trial_res["scenario_id"] = sc["id"]
            trial_res["scenario_name"] = sc["name"]
            trial_res["trial_num"] = trial + 1
            scenario_trials.append(trial_res)
            print(
                f"[{sc['id']}] Trial {trial+1}: "
                f"Latency={trial_res['total_latency_ms']:.1f}ms | "
                f"Tools={trial_res['tools_executed']} | "
                f"ToolOK={trial_res['tool_selection_correct']} | "
                f"Err={trial_res['error']}"
            )
        results.extend(scenario_trials)

    db.close()
    return {"model": model_name, "fallback": enable_fallback, "trials": results}


if __name__ == "__main__":
    trials_count = 2

    # 1. Test gemini-2.5-flash (without fallback)
    res_25_direct = run_benchmark_suite("gemini-2.5-flash", enable_fallback=False, trials_per_scenario=trials_count)

    # 2. Test gemini-2.5-flash (with fallback enabled)
    res_25_fallback = run_benchmark_suite("gemini-2.5-flash", enable_fallback=True, trials_per_scenario=trials_count)

    # 3. Test gemini-3.5-flash-lite (target model)
    res_35_lite = run_benchmark_suite("gemini-3.5-flash-lite", enable_fallback=False, trials_per_scenario=trials_count)

    # 4. Test gemini-3.5-flash (standard Flash comparison)
    res_35_flash = run_benchmark_suite("gemini-3.5-flash", enable_fallback=False, trials_per_scenario=trials_count)

    summary = {
        "gemini_2_5_flash_direct": res_25_direct,
        "gemini_2_5_flash_fallback": res_25_fallback,
        "gemini_3_5_flash_lite": res_35_lite,
        "gemini_3_5_flash": res_35_flash,
    }

    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nBenchmark results saved to: {out_path}")

