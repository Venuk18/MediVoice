import json

with open("backend/scripts/benchmark_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for k, v in data.items():
    trials = v.get("trials", [])
    if not trials:
        continue
    t_acc = sum(1 for t in trials if t.get("tool_selection_correct"))
    a_acc = sum(1 for t in trials if t.get("args_correct"))
    c_acc = sum(1 for t in trials if t.get("context_retained"))
    f_lat = [t["first_response_latency_ms"] for t in trials]
    tot_lat = [t["total_latency_ms"] for t in trials]
    rounds = [t.get("model_call_rounds", 1) for t in trials]
    n = len(trials)
    f_lat_sorted = sorted(f_lat)
    tot_lat_sorted = sorted(tot_lat)
    med_f = f_lat_sorted[n // 2]
    med_tot = tot_lat_sorted[n // 2]
    
    print(f"=== {k} : {v.get('model')} (fallback={v.get('fallback')}) ===")
    print(f"Trials: {n}")
    print(f"Tool Selection Accuracy: {t_acc}/{n} ({t_acc/n*100:.1f}%)")
    print(f"Arguments Accuracy: {a_acc}/{n} ({a_acc/n*100:.1f}%)")
    print(f"Context Retention: {c_acc}/{n} ({c_acc/n*100:.1f}%)")
    print(f"Mean First Latency: {sum(f_lat)/n:.1f} ms | Median First Latency: {med_f:.1f} ms")
    print(f"Mean Total Latency: {sum(tot_lat)/n:.1f} ms | Median Total Latency: {med_tot:.1f} ms")
    print(f"Mean Call Rounds: {sum(rounds)/n:.2f}")
    print()

