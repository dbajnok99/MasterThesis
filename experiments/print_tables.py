"""
Read a completed experiment results JSON and print LaTeX-ready tables for Chapter 7.

Generates:
  - One ASR table per model (tab:asr-results-<model-slug>)
  - One canary detection table averaged across models
  - One FPR table averaged across models
  - One latency overhead table averaged across models

Usage:
  python -m experiments.print_tables logs/results_paid_api.json
  python -m experiments.print_tables logs/results_paid_api.json --model gpt-4o
  python -m experiments.print_tables logs/results_free_local.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ATTACK_LABELS = {
    "memory_poison":            "1. Memory Poisoning",
    "indirect_injection":       "2. Indirect File Injection",
    "cross_agent_propagation":  "3. Cross-Agent Propagation",
    "planner_hijack":           "4. Planner Hijacking",
    "system_prompt_extraction": "5. System Prompt Extraction",
    "memory_membership_probe":  "6. Memory Membership Probe",
    "tool_result_poisoning":    "7. Tool Result Poisoning",
}

COND_LABELS = {
    "none":      "None",
    "canary":    "Canary",
    "intent":    "Intent anchor",
    "plan_diff": "Plan diff",
    "spotlight": "Spotlight",
    "trust":     "Trust",
    "all":       "All",
}

DEFENSE_ORDER = ["none", "canary", "intent", "plan_diff", "spotlight", "trust", "all"]
CANARY_ATTACKS = [
    "memory_poison", "indirect_injection", "cross_agent_propagation",
    "planner_hijack", "system_prompt_extraction",
    "memory_membership_probe", "tool_result_poisoning",
]

MODEL_LABEL_SLUGS = {
    "gpt-4o":                    "gpt4o",
    "gpt-4o-mini":               "gpt4omini",
    "claude-sonnet-4-6":         "sonnet",
    "claude-haiku-4-5-20251001": "haiku",
    "claude-haiku-4-5":          "haiku",
    "deepseek-chat":             "deepseekchat",
    "deepseek-reasoner":         "deepseekr1",
}

MODEL_DISPLAY = {
    "gpt-4o":                    r"\texttt{gpt-4o}",
    "gpt-4o-mini":               r"\texttt{gpt-4o-mini}",
    "claude-sonnet-4-6":         r"\texttt{claude-sonnet-4-6}",
    "claude-haiku-4-5-20251001": r"\texttt{claude-haiku-4-5}",
    "claude-haiku-4-5":          r"\texttt{claude-haiku-4-5}",
    "deepseek-chat":             r"\texttt{deepseek-chat}",
    "deepseek-reasoner":         r"\texttt{deepseek-reasoner}",
}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (better than normal-approx at small n)."""
    if n == 0:
        return 0.0, 0.0
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5)
    lo = max(0.0, (center - margin) / denom)
    hi = min(1.0, (center + margin) / denom)
    return lo, hi


def asr_cell(cell: dict | None) -> str:
    if not cell or cell.get("asr") is None:
        return r"\emph{N/A}"
    asr = cell["asr"]
    n   = cell["n"]
    successes = cell.get("successes", round(asr * n))
    lo, hi = wilson_ci(successes, n)
    val = f"{asr:.2f} ({n}) [{lo:.2f},{hi:.2f}]"
    if asr == 0.0:
        return r"\textbf{" + val + "}"
    return val


def mean_or_none(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def fmt(v: float | None, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}" if v is not None else "N/A"


def print_asr_table(model: str, summary: dict) -> None:
    attacks  = list(ATTACK_LABELS)
    conds    = DEFENSE_ORDER
    slug     = MODEL_LABEL_SLUGS.get(model, model.replace("-", "").replace(".", ""))
    display  = MODEL_DISPLAY.get(model, f"\\texttt{{{model}}}")
    n_trials = None

    # infer trial count from first available cell
    for atk in attacks:
        for c in conds:
            cell = (summary.get("attacks") or {}).get(atk, {}).get(c)
            if cell:
                n_trials = cell.get("n")
                break
        if n_trials:
            break

    n_label = f"$N = {n_trials}$" if n_trials else "$N = ?$"

    col_fmt = "l" + "r" * len(conds)
    header  = " & ".join(
        [r"\textbf{Attack}"] + [f"\\textbf{{{COND_LABELS[c]}}}" for c in conds]
    )

    print(f"% ── ASR table: {model} " + "─" * 40)
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(f"  \\caption{{Attack success rates per attack and defence condition, {display}")
    print(f"           ({n_label} trials per cell, shown as ASR (n) [95\\% Wilson CI]).")
    print(r"           \textbf{Bold} values indicate the attack was fully neutralised (ASR = 0).}")
    print(f"  \\label{{tab:asr-results-{slug}}}")
    print(r"  \resizebox{\textwidth}{!}{%")
    print(f"  \\begin{{tabular}}{{{col_fmt}}}")
    print(r"    \toprule")
    print(f"    {header} \\\\")
    print(r"    \midrule")

    for atk in attacks:
        cells = [
            asr_cell((summary.get("attacks") or {}).get(atk, {}).get(c))
            for c in conds
        ]
        label = ATTACK_LABELS[atk]
        print(f"    {label} & " + " & ".join(cells) + r" \\")

    # mean row: pool successes/trials across all 7 attacks so the CI reflects
    # the larger combined N, not just one attack's small per-cell N
    means = []
    for c in conds:
        cells = [(summary.get("attacks") or {}).get(a, {}).get(c) for a in attacks]
        cells = [cell for cell in cells if cell and cell.get("asr") is not None]
        if not cells:
            means.append(r"\emph{N/A}")
            continue
        pooled_successes = sum(cell.get("successes", round(cell["asr"] * cell["n"])) for cell in cells)
        pooled_n = sum(cell["n"] for cell in cells)
        m = pooled_successes / pooled_n
        lo, hi = wilson_ci(pooled_successes, pooled_n)
        means.append(f"{m:.2f} [{lo:.2f},{hi:.2f}]")

    print(r"    \midrule")
    print(r"    \textbf{Mean ASR} & " + " & ".join(means) + r" \\")
    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"  }")
    print(r"\end{table}")
    print()


def print_canary_table(summaries: dict[str, dict]) -> None:
    print("% ── Canary detection table " + "─" * 44)
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(r"  \caption{Canary detection rate for attacks that exfiltrate memory contents,")
    print(r"           averaged across all evaluated models.")
    print(r"           ASR is the mean over all models for the canary-only condition.}")
    print(r"  \label{tab:canary-detection}")
    print(r"  \begin{tabular}{lcc}")
    print(r"    \toprule")
    print(r"    \textbf{Attack} & \textbf{Mean ASR (canary active)} & \textbf{Mean canary detection rate} \\")
    print(r"    \midrule")

    for atk in CANARY_ATTACKS:
        asrs, dets = [], []
        for s in summaries.values():
            cell = (s.get("attacks") or {}).get(atk, {}).get("canary")
            if cell:
                asrs.append(cell.get("asr"))
                dets.append(cell.get("canary_rate"))
        asr_str = fmt(mean_or_none(asrs))
        det_str = fmt(mean_or_none(dets))
        label = ATTACK_LABELS.get(atk, atk)
        print(f"    {label} & {asr_str} & {det_str} \\\\")

    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"\end{table}")
    print()


def print_fpr_table(summaries: dict[str, dict]) -> None:
    print("% ── FPR table " + "─" * 57)
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(r"  \caption{False positive rates (FPR) per defence on the benign task suite,")
    print(r"           averaged across all evaluated models.}")
    print(r"  \label{tab:fpr-results}")
    print(r"  \begin{tabular}{lcc}")
    print(r"    \toprule")
    print(r"    \textbf{Defence} & \textbf{Mean FPR} & \textbf{Mean incorrectly blocked tasks} \\")
    print(r"    \midrule")

    for cond in ["canary", "intent", "plan_diff", "spotlight", "trust", "all"]:
        fprs, blocked = [], []
        for s in summaries.values():
            cell = (s.get("benign") or {}).get(cond)
            if cell and cell.get("fpr") is not None:
                fprs.append(cell["fpr"])
                blocked.append(round(cell["fpr"] * cell["n"]))
        fpr_str     = fmt(mean_or_none(fprs))
        blocked_str = fmt(mean_or_none([float(b) for b in blocked]), decimals=1)
        label = COND_LABELS[cond]
        print(f"    {label} & {fpr_str} & {blocked_str} \\\\")

    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"\end{table}")
    print()


def print_latency_table(summaries: dict[str, dict]) -> None:
    print("% ── Latency table " + "─" * 53)
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(r"  \caption{Mean latency overhead relative to the per-model undefended baseline")
    print(r"           (benign tasks, averaged across all evaluated models).}")
    print(r"  \label{tab:overhead-results}")
    print(r"  \begin{tabular}{lcc}")
    print(r"    \toprule")
    print(r"    \textbf{Defence} & \textbf{Mean overhead (s)} & \textbf{Relative overhead (\%)} \\")
    print(r"    \midrule")

    baselines: dict[str, float | None] = {}
    for model, s in summaries.items():
        baselines[model] = ((s.get("benign") or {}).get("none") or {}).get("mean_s")

    for cond in ["none", "canary", "intent", "plan_diff", "spotlight", "trust", "all"]:
        abs_times, rel_pcts = [], []
        for model, s in summaries.items():
            cell = (s.get("benign") or {}).get(cond)
            if cell and cell.get("mean_s") is not None:
                t = cell["mean_s"]
                abs_times.append(t)
                b = baselines.get(model)
                if b and cond != "none":
                    rel_pcts.append((t / b - 1) * 100)

        label   = COND_LABELS[cond]
        t_str   = fmt(mean_or_none(abs_times), decimals=1)
        if cond == "none":
            pct_str = "baseline"
        else:
            m = mean_or_none(rel_pcts)
            if m is None:
                pct_str = "N/A"
            elif abs(m) < 3:
                pct_str = r"$\approx 0$\%"
            elif m >= 0:
                pct_str = f"+{m:.0f}\\%"
            else:
                pct_str = f"{m:.0f}\\%"
        print(f"    {label} & {t_str} & {pct_str} \\\\")

    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"\end{table}")
    print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Print LaTeX tables from experiment results")
    p.add_argument("results", help="Path to results JSON file")
    p.add_argument("--model", default=None,
                   help="Print ASR table for one model only (default: all)")
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    data    = load(args.results)
    summary = data.get("summary")

    if not summary:
        print("No summary found. Run experiments.runner first.")
        sys.exit(1)

    # support both old flat format and new per-model format
    if "attacks" in summary:
        # old flat format — wrap it
        models_summary = {"default": summary}
    else:
        models_summary = summary

    models = ([args.model] if args.model else list(models_summary.keys()))

    for model in models:
        if model not in models_summary:
            print(f"% model {model!r} not found in results, skipping")
            continue
        print_asr_table(model, models_summary[model])

    selected = {m: models_summary[m] for m in models if m in models_summary}
    print_canary_table(selected)
    print_fpr_table(selected)
    print_latency_table(selected)


if __name__ == "__main__":
    main()
