import json, sys

with open("backend/scripts/benchmark_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for k, v in data.items():
    trials = v.get("trials", [])
    if not trials:
        continue
    print(f"==================== {k} ====================")
    for t in trials:
        scen = t.get("scenario_id")
        trial_num = t.get("trial_num")
        tools = t.get("tools_executed")
        tool_ok = t.get("tool_selection_correct")
        args_ok = t.get("args_correct")
        first_l = t.get("first_response_latency_ms")
        tot_l = t.get("total_latency_ms")
        reply = t.get("reply_preview", "")[:50].encode('ascii', errors='backslashreplace').decode('ascii')
        print(f"[{scen} T{trial_num}] tools={tools} tool_ok={tool_ok} args_ok={args_ok} lat={first_l:.0f}/{tot_l:.0f}ms reply={reply}")
