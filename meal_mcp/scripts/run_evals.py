"""Check which tools Claude chooses for fixed prompts. No API key needed: Claude Desktop is the client.

The script shows one prompt at a time. You run it in Claude Desktop and press Enter when the answer
is complete. The script then reads the new TOOL_CALL lines from the MCP log and scores the case.

Usage: python scripts/run_evals.py --log "<path to the Meal MCP log>"
       python scripts/run_evals.py --log "<path>" --only compare-variant,scale
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CASES_FILE = BASE_DIR / "evals" / "cases.json"
RESULTS_DIR = BASE_DIR / "evals" / "results"
TOOL_CALL = re.compile(r"TOOL_CALL (\w+) (ok|error)\s*$")


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_calls(text: str) -> list[dict]:
    calls = []
    for line in text.splitlines():
        match = TOOL_CALL.search(line)
        if match:
            calls.append({"tool": match.group(1), "status": match.group(2)})
    return calls


def score_case(case: dict, calls: list[dict]) -> dict:
    """Required tools must appear in this order (a list means one of them), forbidden tools not at all."""
    names = [call["tool"] for call in calls]
    missing = []
    index = 0
    for step in case["required"]:
        options = [step] if isinstance(step, str) else step
        found = next((i for i in range(index, len(names)) if names[i] in options), None)
        if found is None:
            missing.append(step)
        else:
            index = found + 1
    forbidden = sorted(set(names) & set(case.get("forbidden", [])))
    failed = sorted({call["tool"] for call in calls if call["status"] == "error"})
    return {
        "id": case["id"],
        "passed": not missing and not forbidden and not failed,
        "calls": names,
        "missing": missing,
        "forbidden_used": forbidden,
        "failed_calls": failed,
    }


def print_result(result: dict) -> None:
    print(f"  {'BESTANDEN' if result['passed'] else 'NICHT BESTANDEN'}: {' -> '.join(result['calls']) or 'keine Tools'}")
    for key, label in (("missing", "Fehlt"), ("forbidden_used", "Verboten genutzt"), ("failed_calls", "Fehlgeschlagen")):
        if result[key]:
            print(f"  {label}: {result[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path, help="MCP log of the extension")
    parser.add_argument("--only", default="", help="comma-separated case IDs")
    args = parser.parse_args()
    if not args.log.exists():
        print(f"Log not found: {args.log}", file=sys.stderr)
        return 1

    only = {value for value in args.only.split(",") if value}
    cases = [case for case in load_cases() if not only or case["id"] in only]
    results = []
    for number, case in enumerate(cases, start=1):
        offset = args.log.stat().st_size
        print(f"\n[{number}/{len(cases)}] {case['id']}: {case['checks']}\n\n  {case['prompt']}\n")
        input("Prompt in einem neuen Chat ausführen, dann Enter drücken ...")
        with args.log.open("rb") as log:
            log.seek(offset)
            result = score_case(case, parse_calls(log.read().decode("utf-8", errors="replace")))
        print_result(result)
        results.append(result)

    passed = sum(result["passed"] for result in results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{passed} von {len(results)} bestanden. Ergebnis: {target}")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
