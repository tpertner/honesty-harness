"""Honesty Harness runner.

Loads a YAML test suite, executes each case against a Provider, scores results,
and writes a JSONL results file plus a JSON summary to ./results/.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

import yaml

from .providers import MockProvider, Provider
from .report import summarize
from .scorers import score_case, score_metamorphic_pair


@dataclass
class Case:
    id: str
    category: str
    severity: int
    prompt: Optional[str] = None
    expected: Optional[Dict[str, Any]] = None
    metamorphic: Optional[Dict[str, Any]] = None
    notes: str = ""


def load_suite(path: str) -> List[Case]:
    """Load a YAML suite file into Case objects."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cases: List[Case] = []
    for c in data.get("cases", []):
        cases.append(
            Case(
                id=c["id"],
                category=c["category"],
                severity=int(c["severity"]),
                prompt=c.get("prompt"),
                expected=c.get("expected"),
                metamorphic=c.get("metamorphic"),
                notes=c.get("notes", ""),
            )
        )
    return cases


def _parse_categories(raw: Optional[str]) -> Optional[Set[str]]:
    if not raw:
        return None
    cats = {c.strip() for c in raw.split(",") if c.strip()}
    return cats or None


def run_suite(
    suite_path: str,
    provider: Provider,
    trials: int = 5,
    flaky_low: float = 0.2,
    flaky_high: float = 0.8,
    categories: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Run all cases in a suite and return a payload with summary + results."""
    cases = load_suite(suite_path)

    if categories is not None:
        cases = [c for c in cases if c.category in categories]

    results: List[Dict[str, Any]] = []

    for case in cases:
        trial_outputs: List[Any] = []
        trial_passes: List[bool] = []
        trial_reasons: List[List[str]] = []
        elapsed_list: List[float] = []

        for _ in range(trials):
            start = time.time()

            if case.metamorphic:
                a_prompt = case.metamorphic["a_prompt"]
                b_prompt = case.metamorphic["b_prompt"]

                out_a = provider.generate(a_prompt)
                out_b = provider.generate(b_prompt)

                score = score_metamorphic_pair(out_a, out_b, case.metamorphic.get("expectation", {}))
                output: Any = {"a": out_a, "b": out_b}
            else:
                out = provider.generate(case.prompt or "")
                score = score_case(out, case.expected or {})
                output = out

            elapsed = time.time() - start

            trial_outputs.append(output)
            trial_passes.append(bool(score.passed))
            trial_reasons.append(score.reasons)
            elapsed_list.append(round(elapsed, 4))

        pass_count = sum(1 for p in trial_passes if p)
        pass_rate = (pass_count / trials) if trials else 0.0

        flaky = flaky_low < pass_rate < flaky_high
        stable_failure = pass_rate == 0.0
        stable_pass = pass_rate == 1.0

        failed_trials = [
            {"trial": i, "reasons": trial_reasons[i], "output": trial_outputs[i]}
            for i, passed in enumerate(trial_passes)
            if not passed
        ]

        results.append(
            {
                "id": case.id,
                "category": case.category,
                "severity": case.severity,
                "trials": trials,
                "pass_count": pass_count,
                "pass_rate": round(pass_rate, 3),
                "reproducibility": round(pass_rate, 3),
                "flaky": flaky,
                "stable_pass": stable_pass,
                "stable_failure": stable_failure,
                "elapsed_s": elapsed_list,
                "notes": case.notes,
                "failed_trials": failed_trials[:3],  # keep report light
            }
        )

    summary = summarize(results)
    return {"summary": summary, "results": results}


def save_results(payload: Dict[str, Any], out_dir: str = "results", run_label: str = "run") -> str:
    """Write results to disk and return the JSONL path."""
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")

    jsonl_path = os.path.join(out_dir, f"{run_label}-{ts}.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in payload["results"]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = os.path.join(out_dir, f"summary-{run_label}-{ts}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(payload["summary"], f, indent=2)

    return jsonl_path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Honesty Harness YAML suites and write results.")
    p.add_argument("--suite", default="testsuites/mini_suite.yaml", help="Path to YAML suite file")
    p.add_argument("--trials", type=int, default=5, help="Trials per case")
    p.add_argument("--out-dir", default="results", help="Output directory")
    p.add_argument(
        "--model",
        default="provider://default",
        help="Model label for reporting (e.g., gpt-4o, claude-3, provider://default).",
    )
    p.add_argument(
        "--categories",
        default="",
        help="Comma-separated categories to run (e.g., truthfulness,calibration). Empty = all.",
    )
    return p


def _status_label(r: Dict[str, Any]) -> str:
    if r.get("stable_pass"):
        return "PASS"
    if r.get("flaky"):
        return "FLAKY"
    return "FAIL"


def main() -> int:
    args = build_arg_parser().parse_args()

    # Today: always run through MockProvider for a no-keys smoke test.
    # (You can swap in a real provider later without changing the harness API.)
    provider: Provider = MockProvider()

    categories = _parse_categories(args.categories)

    payload = run_suite(args.suite, provider, trials=args.trials, categories=categories)

    run_label = "run"
    if args.model:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in args.model.strip())
        run_label = f"run-{safe}" if safe else "run"

    out_path = save_results(payload, out_dir=args.out_dir, run_label=run_label)

    # Console output: quick, scannable.
    print(f"Suite: {args.suite}")
    print(f"Model: {args.model}")
    if categories:
        print(f"Categories: {', '.join(sorted(categories))}")
    print("")

    for r in payload["results"]:
        status = _status_label(r)
        print(f"{status:5} {r['id']:7} {r['category']:<18} (severity {r['severity']})  pass_rate={r['pass_rate']}")

    print("")
    print("Saved:", out_path)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
