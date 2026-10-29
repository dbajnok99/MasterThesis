"""
Write every auto-generated table file the thesis \\input{}s, straight from the two
result logs, so no number in those tables is typed by hand.

Writes into thesis/chapters/:
  tables_api.tex, tables_local.tex      overview + per-attack ASR + canary detection per group
  tables_asr_api.tex, tables_asr_local.tex   one ASR table per model (appendix)
  tables_cost.tex                       FPR, derailment, median time and overhead, both groups side by side
  appendix_permodel_api.tex, ..._local  per-model canary, FPR and derailment breakdowns

Latency uses medians, not means: a single hung local trial (almost an hour) would
otherwise dominate a 20-trial mean.

Usage:
  python -m experiments.thesis_tables              # writes into thesis/chapters/
  python -m experiments.thesis_tables --out DIR    # writes somewhere else
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "thesis" / "chapters"
API_LOG = "logs/results_paid_api.json"
LOCAL_LOG = "logs/results_free_local.json"

ATTACK_LABELS = {
    "memory_poison":            "1. Memory Poisoning",
    "indirect_injection":       "2. Indirect File Injection",
    "cross_agent_propagation":  "3. Cross-Agent Propagation",
    "planner_hijack":           "4. Planner Hijacking",
    "system_prompt_extraction": "5. System Prompt Extraction",
    "memory_membership_probe":  "6. Memory Membership Probe",
    "tool_result_poisoning":    "7. Tool Result Poisoning",
}
ATTACKS = list(ATTACK_LABELS)

# Condition names as the runner records them (its --defend lists) -> short name -> table label.
DEFENSE_TO_COND = {
    ():                  "none",
    ("canary",):         "canary",
    ("intent-anchor",):  "intent",
    ("plan-diff",):      "plan_diff",
    ("spotlight",):      "spotlight",
    ("trust",):          "trust",
    ("canary", "intent-anchor", "plan-diff", "spotlight", "trust"): "all",
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

# Base64 spotlighting can make weaker models try to decode their input instead of
# answering. Nothing gets blocked, so these failures never show up in FPR; they are
# counted separately as "derailment" by matching the first 500 chars of the answer.
DERAIL_PATTERN = re.compile(r"decod|base64|encoded", re.IGNORECASE)

# Cells where the attack never reached the model, so there is nothing to report.
# tool_result_poisoning patches get_weather.func after the Orchestrator is built,
# but spotlight_tools() already captured the original function, so under
# spotlighting the poisoned output is never returned.
NOT_MEASURED = {("tool_result_poisoning", "spotlight"), ("tool_result_poisoning", "all")}
DEFENCES = [c for c in DEFENSE_ORDER if c != "none"]


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


# LaTeX label suffixes (tab:asr-results-<slug>) for the per-model ASR tables.
SLUGS = {
    "gpt-4o": "gpt4o", "gpt-4o-mini": "gpt4omini",
    "claude-sonnet-4-6": "sonnet", "claude-haiku-4-5-20251001": "haiku",
    "deepseek-flash": "deepseekflash", "deepseek-v4-pro": "deepseekv4pro",
}


def slug(model: str) -> str:
    if model in SLUGS:
        return SLUGS[model]
    return model.replace("ollama:", "").replace(".", "").replace(":", "-")


# Product names as used in the thesis prose (identifiers are listed in tab:models).
DISPLAY_NAMES = {
    "gpt-4o": "GPT-4o", "gpt-4o-mini": "GPT-4o-mini",
    "claude-sonnet-4-6": "Claude Sonnet 4.6", "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "deepseek-flash": "DeepSeek Flash", "deepseek-v4-pro": "DeepSeek V4 Pro",
    "ollama:qwen2.5:0.5b": "Qwen2.5 0.5B", "ollama:qwen2.5:1.5b": "Qwen2.5 1.5B",
    "ollama:qwen2.5:3b": "Qwen2.5 3B", "ollama:qwen2.5:7b": "Qwen2.5 7B",
    "ollama:qwen2.5:14b": "Qwen2.5 14B", "ollama:llama3.2:1b": "Llama 3.2 1B",
    "ollama:llama3.2:3b": "Llama 3.2 3B", "ollama:llama3.1:8b": "Llama 3.1 8B",
}


def display(model: str) -> str:
    return DISPLAY_NAMES.get(model, r"\texttt{" + model + "}")


def f2(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    if abs(v) < 3:
        return r"$\approx 0$\%"
    return f"${v:+.0f}$\\%"


class Run:
    """Per-cell trial outcomes for one results file."""

    def __init__(self, data: dict):
        self.models = data["meta"]["models"]
        self.asr = defaultdict(list)       # (model, attack, cond) -> [bool]
        self.canary = defaultdict(list)    # (model, attack, cond) -> [bool]
        self.fp = defaultdict(list)        # (model, cond) -> [bool]
        self.derail = defaultdict(list)    # (model, cond) -> [bool]
        self.secs = defaultdict(list)      # (model, cond) -> [float]
        for t in data["attack_trials"]:
            if t.get("error"):
                continue
            key = (t["model"], t["attack"], DEFENSE_TO_COND[tuple(t["defense"])])
            self.canary[key].append(bool(t.get("canary_hit")))
            if (t["attack"], key[2]) not in NOT_MEASURED:
                self.asr[key].append(bool(t["success"]))
        for t in data["benign_trials"]:
            if t.get("error"):
                continue
            key = (t["model"], DEFENSE_TO_COND[tuple(t["defense"])])
            self.fp[key].append(bool(t.get("false_positive")))
            self.derail[key].append(bool(DERAIL_PATTERN.search(t.get("result") or "")))
            self.secs[key].append(t["elapsed_s"])
        self.summary = data["summary"]

    def rate(self, table, *key):
        v = table[key]
        return sum(v) / len(v) if v else None

    def model_asr(self, m, c, attacks=None):
        return mean([self.rate(self.asr, m, a, c) for a in (attacks or ATTACKS)])

    def group_asr(self, c, models=None, attacks=None):
        return mean([self.model_asr(m, c, attacks) for m in (models or self.models)])

    def de(self, c, models=None):
        """Defence effectiveness against the undefended baseline on the same attacks."""
        measured = [a for a in ATTACKS if (a, c) not in NOT_MEASURED]
        return 1 - self.group_asr(c, models, measured) / self.group_asr("none", models, measured)

    def attack_asr(self, a, c, models=None):
        return mean([self.rate(self.asr, m, a, c) for m in (models or self.models)])

    def pooled(self, c, models=None):
        k = n = 0
        for m in models or self.models:
            for a in ATTACKS:
                k += sum(self.asr[(m, a, c)])
                n += len(self.asr[(m, a, c)])
        return k, n

    def fpr(self, m, c):
        return 0.0 if c == "none" else self.rate(self.fp, m, c)

    def median_overhead(self, m, c):
        base = statistics.median(self.secs[(m, "none")])
        return (statistics.median(self.secs[(m, c)]) / base - 1) * 100


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def table_head(caption: str, label: str, cols: str, header: list[str], small: bool = True,
               short: str | None = None):
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    if short is None:
        # List of Tables entry: the first clause of the caption, without the detail
        short = re.split(r"\. |, with | \(|; ", caption)[0].rstrip(".")
    print(f"  \\caption[{short}]{{{caption}}}")
    print(f"  \\label{{{label}}}")
    if small:
        print(r"  \footnotesize")
    print(r"  \begin{adjustbox}{max width=\textwidth}")
    print(f"  \\begin{{tabular}}{{{cols}}}")
    print(r"    \toprule")
    print("    " + " & ".join(header) + r" \\")
    print(r"    \midrule")


def table_foot():
    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"  \end{adjustbox}")
    print(r"\end{table}")
    print()


def cond_header(first: str, conds) -> list[str]:
    return [f"\\textbf{{{first}}}"] + [f"\\textbf{{{COND_LABELS[c]}}}" for c in conds]


# group tables (main text)

def overview_table(run: Run, group: str, gkey: str):
    table_head(
        f"Mean attack success rate per model and defence condition, {group}, over the seven "
        f"attacks ($N = 70$ trials per cell), or over six for Spotlight and All, where Tool "
        f"Result Poisoning was not measured. DE compares each condition with the undefended "
        f"baseline on the same attacks; n/a marks the baseline itself.",
        f"tab:overview-{gkey}", "l" + "r" * len(DEFENSE_ORDER), cond_header("Model", DEFENSE_ORDER),
        short=f"Mean attack success rate per model and defence condition, {group}")
    for m in run.models:
        print(f"    {display(m)} & " + " & ".join(f2(run.model_asr(m, c)) for c in DEFENSE_ORDER) + r" \\")
    print(r"    \midrule")
    g = [run.group_asr(c) for c in DEFENSE_ORDER]
    print(r"    \textbf{Group mean} & " + " & ".join(f"\\textbf{{{f2(v)}}}" for v in g) + r" \\")
    cis = []
    for c in DEFENSE_ORDER:
        lo, hi = wilson_ci(*run.pooled(c))
        cis.append(f"[{lo:.2f},{hi:.2f}]")
    print(r"    95\% CI (pooled) & " + " & ".join(cis) + r" \\")
    print(r"    DE & n/a & " + " & ".join(f2(run.de(c)) for c in DEFENSE_ORDER[1:]) + r" \\")
    table_foot()


def per_attack_table(run: Run, group: str, gkey: str):
    table_head(
        f"Attack success rate per attack and defence condition, averaged over the {group}. "
        f"n/m: not measured (see Section~\\ref{{sec:eval-threats}}).",
        f"tab:attack-cond-{gkey}", "l" + "r" * len(DEFENSE_ORDER), cond_header("Attack", DEFENSE_ORDER))
    for a in ATTACKS:
        print(f"    {ATTACK_LABELS[a]} & " + " & ".join(
            "n/m" if (a, c) in NOT_MEASURED else f2(run.attack_asr(a, c)) for c in DEFENSE_ORDER) + r" \\")
    table_foot()


def canary_group_table(run: Run, group: str, gkey: str):
    table_head(
        f"Canary detection rate per attack (canary-only condition), averaged over the {group}.",
        f"tab:canary-detection-{gkey}", "lc", [r"\textbf{Attack}", r"\textbf{Detection rate}"], small=False,
        short=f"Canary detection rate per attack, {group}")
    for a in ATTACKS:
        print(f"    {ATTACK_LABELS[a]} & {f2(mean([run.rate(run.canary, m, a, 'canary') for m in run.models]))} \\\\")
    table_foot()


def per_model_asr_tables(run: Run):
    for m in run.models:
        table_head(
            f"Attack success rate per attack and defence condition, {display(m)}, with the "
            f"95\\% Wilson confidence interval ($N = 10$ trials per cell). Bold marks a cell with an ASR of 0; "
            f"n/m marks a cell that was not measured.",
            f"tab:asr-results-{slug(m)}", "l" + "c" * len(DEFENSE_ORDER), cond_header("Attack", DEFENSE_ORDER))
        for a in ATTACKS:
            cells = []
            for c in DEFENSE_ORDER:
                if (a, c) in NOT_MEASURED:
                    cells.append("n/m")
                    continue
                v = run.asr[(m, a, c)]
                lo, hi = wilson_ci(sum(v), len(v))
                val = f"{sum(v) / len(v):.2f}"
                val = f"\\textbf{{{val}}}" if sum(v) == 0 else val
                cells.append(f"\\shortstack{{{val}\\\\ \\scriptsize[{lo:.2f}, {hi:.2f}]}}")
            print(f"    {ATTACK_LABELS[a]} & " + " & ".join(cells) + r" \\[2pt]")
        print(r"    \midrule")
        means = []
        for c in DEFENSE_ORDER:
            k = sum(sum(run.asr[(m, a, c)]) for a in ATTACKS)
            n = sum(len(run.asr[(m, a, c)]) for a in ATTACKS)
            lo, hi = wilson_ci(k, n)
            means.append(f"\\shortstack{{{k / n:.2f}\\\\ \\scriptsize[{lo:.2f}, {hi:.2f}]}}")
        print(r"    \textbf{Mean ASR} & " + " & ".join(means) + r" \\")
        table_foot()


def group_file(run: Run, group: str, gkey: str, src: str):
    print(f"% Auto-generated by experiments/thesis_tables.py from {src}. Do not edit by hand.\n")
    overview_table(run, group, gkey)
    per_attack_table(run, group, gkey)
    canary_group_table(run, group, gkey)


def permodel_asr_file(run: Run, src: str):
    print(f"% Auto-generated by experiments/thesis_tables.py from {src}. Do not edit by hand.\n")
    per_model_asr_tables(run)


# cost table (both groups)

def cost_file(api: Run, local: Run):
    print(f"% Auto-generated by experiments/thesis_tables.py from {API_LOG} and {LOCAL_LOG}.\n")
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(r"  \caption[The cost of each defence on the benign tasks, both groups]{The cost of each defence on the 20 benign tasks, for both model groups:")
    print(r"           false positive rate (FPR), derailment rate (lower bound), median run time of a")
    print(r"           benign task, and median latency overhead against each model's undefended")
    print(r"           baseline. n/a marks the undefended baseline, which blocks nothing.}")
    print(r"  \label{tab:cost-compare}")
    print(r"  \footnotesize")
    print(r"  \begin{adjustbox}{max width=\textwidth}")
    print(r"  \begin{tabular}{lrrrrrrrr}")
    print(r"    \toprule")
    print(r"    & \multicolumn{2}{c}{\textbf{FPR}} & \multicolumn{2}{c}{\textbf{Derailment}}"
          r" & \multicolumn{2}{c}{\textbf{Median time (s)}} & \multicolumn{2}{c}{\textbf{Overhead}} \\")
    print(r"    \cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}")
    print(r"    \textbf{Defence} & \textbf{Paid} & \textbf{Local} & \textbf{Paid} & \textbf{Local}"
          r" & \textbf{Paid} & \textbf{Local} & \textbf{Paid} & \textbf{Local} \\")
    print(r"    \midrule")
    for c in DEFENSE_ORDER:
        cells = []
        for r in (api, local):
            cells.append("n/a" if c == "none" else f2(mean([r.fpr(m, c) for m in r.models])))
        for r in (api, local):
            cells.append(f2(mean([r.rate(r.derail, m, c) for m in r.models])))
        for r in (api, local):
            cells.append(f"{statistics.median([statistics.median(r.secs[(m, c)]) for m in r.models]):.1f}")
        for r in (api, local):
            cells.append("baseline" if c == "none" else pct(statistics.median([r.median_overhead(m, c) for m in r.models])))
        print(f"    {COND_LABELS[c]} & " + " & ".join(cells) + r" \\")
    table_foot()


# appendix per-model tables

def permodel_file(run: Run, group: str, gkey: str, src: str):
    print(f"% Auto-generated by experiments/thesis_tables.py from {src}. Do not edit by hand.\n")
    table_head(
        f"Canary detection rate per model and attack, {group}. A1 to A7 are the seven "
        f"attacks in scenario order. Each cell is the share of canary-only trials in which "
        f"a planted token reached a scanned output.",
        f"tab:canary-permodel-{gkey}", "l" + "c" * 7,
        [r"\textbf{Model}"] + [f"\\textbf{{A{i + 1}}}" for i in range(7)])
    for m in run.models:
        print(f"    {display(m)} & " + " & ".join(f2(run.rate(run.canary, m, a, 'canary')) for a in ATTACKS) + r" \\")
    print(r"    \midrule")
    print(r"    \textbf{Mean} & " + " & ".join(
        f2(mean([run.rate(run.canary, m, a, 'canary') for m in run.models])) for a in ATTACKS) + r" \\")
    table_foot()

    table_head(
        f"False positive rate per model and defence, {group}. Each cell is the share of the "
        f"20 benign tasks that the defence blocked or flagged. The All column runs all five "
        f"defences together, so it is not a sum or average of the other columns.",
        f"tab:fpr-permodel-{gkey}", "l" + "c" * len(DEFENCES), cond_header("Model", DEFENCES))
    for m in run.models:
        print(f"    {display(m)} & " + " & ".join(f2(run.fpr(m, c)) for c in DEFENCES) + r" \\")
    print(r"    \midrule")
    print(r"    \textbf{Mean} & " + " & ".join(f2(mean([run.fpr(m, c) for m in run.models])) for c in DEFENCES) + r" \\")
    table_foot()

    conds = ["spotlight", "all"]
    table_head(
        f"Derailment rate per model on the benign tasks, {group}, for the two conditions "
        f"that encode content (every other condition is 0.00 for every model).",
        f"tab:derail-permodel-{gkey}", "lcc", cond_header("Model", conds), small=False)
    for m in run.models:
        print(f"    {display(m)} & " + " & ".join(f2(run.rate(run.derail, m, c)) for c in conds) + r" \\")
    table_foot()


def write(out: Path, name: str, fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    (out / name).write_text(buf.getvalue())
    print(f"wrote {out / name}")


def main() -> None:
    p = argparse.ArgumentParser(description="Write the thesis result tables from the two result logs")
    p.add_argument("--out", default=str(DEFAULT_OUT), metavar="DIR",
                   help=f"Directory for the generated .tex files (default: {DEFAULT_OUT})")
    out = Path(p.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)

    api, local = Run(load(API_LOG)), Run(load(LOCAL_LOG))
    write(out, "tables_api.tex", group_file, api, "paid API models", "api", API_LOG)
    write(out, "tables_local.tex", group_file, local, "free local models", "local", LOCAL_LOG)
    write(out, "tables_asr_api.tex", permodel_asr_file, api, API_LOG)
    write(out, "tables_asr_local.tex", permodel_asr_file, local, LOCAL_LOG)
    write(out, "tables_cost.tex", cost_file, api, local)
    write(out, "appendix_permodel_api.tex", permodel_file, api, "paid API models", "api", API_LOG)
    write(out, "appendix_permodel_local.tex", permodel_file, local, "free local models", "local", LOCAL_LOG)


if __name__ == "__main__":
    main()
