"""Run in .venv-b123d. Generates, executes, grades, and repairs once per cell. Resumable: finished cells are skipped."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grade import ROOT, grade, oracles  # noqa: E402

LIBS = {"build123d": ROOT / ".venv-b123d/bin/python", "cadquery": ROOT / ".venv-cq/bin/python"}
RUN_TIMEOUT_S = 60
CLAUDE_FLAGS = [
    "-p", "--output-format", "json", "--tools", "",
    "--setting-sources", "", "--settings", '{"disableAllHooks":true}',
    "--disable-slash-commands", "--strict-mcp-config", "--no-session-persistence",
]
GRADE_LOCK = threading.Lock()
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


class ApiError(Exception):
    pass


def ask_claude(model, system, user, cache_path):
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    proc = subprocess.run(
        ["claude", *CLAUDE_FLAGS, "--model", model, "--system-prompt", system],
        input=user, capture_output=True, text=True, timeout=600, cwd=cache_path.parent,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ApiError(f"exit {proc.returncode}: {proc.stdout[-300:]} {proc.stderr[-300:]}")
    if out.get("is_error"):
        raise ApiError(str(out.get("result"))[:300])
    cache_path.write_text(json.dumps(out, indent=1))
    return out


def run_and_grade(lib, part_id, cell, n, code):
    script = cell / f"attempt{n}.py"
    script.write_text(code)
    (cell / "out.step").unlink(missing_ok=True)
    try:
        proc = subprocess.run([str(LIBS[lib]), script.name], cwd=cell, capture_output=True,
                              text=True, timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"category": "timeout", "pass": False, "detail": f"exceeded {RUN_TIMEOUT_S}s"}
    if proc.returncode != 0:
        return {"category": "runtime_error", "pass": False, "detail": proc.stderr[-2000:]}
    with GRADE_LOCK:
        result = grade(part_id, cell / "out.step")
    if (cell / "out.step").exists():
        shutil.move(cell / "out.step", cell / f"out{n}.step")
    return result


def usage_summary(resp):
    u = resp.get("usage", {})
    return {
        "duration_ms": resp.get("duration_ms"),
        "cost_usd": resp.get("total_cost_usd"),
        "output_tokens": u.get("output_tokens"),
        "models": list(resp.get("modelUsage", {})),
    }


def repair_message(prompt, code, result):
    what = ("It raised this error:\n" + result["detail"]) if result["category"] in ("runtime_error", "timeout") \
        else f"It ran, but the part is wrong ({result['category']}): {result['detail']}"
    return (f"{prompt}\n\nYour previous script:\n```python\n{code}```\n\n{what}\n\n"
            "Reply with a corrected complete script.")


def run_cell(lib, model, part_id, sample):
    cell = ROOT / "runs" / lib / model / part_id / str(sample)
    if (cell / "log.json").exists():
        return json.loads((cell / "log.json").read_text())
    cell.mkdir(parents=True, exist_ok=True)
    system = (ROOT / "prompts" / f"system_{lib}.md").read_text()
    prompt = oracles()[part_id]["prompt"]
    attempts = []
    user = prompt
    for n in (0, 1):
        resp = ask_claude(model, system, user, cell / f"attempt{n}.json")
        match = CODE_BLOCK.search(resp["result"])
        code = match.group(1) if match else resp["result"]
        result = run_and_grade(lib, part_id, cell, n, code)
        attempts.append({**result, **usage_summary(resp)})
        if result["pass"]:
            break
        user = repair_message(prompt, code, result)
    log = {"lib": lib, "model": model, "part": part_id, "sample": sample,
           "first_try": attempts[0]["pass"], "after_repair": attempts[-1]["pass"], "attempts": attempts}
    (cell / "log.json").write_text(json.dumps(log, indent=1))
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="sonnet,opus")
    ap.add_argument("--libs", default="build123d,cadquery")
    ap.add_argument("--parts", default=",".join(oracles()))
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    cells = [(lib, m, p, s) for s in range(a.samples) for p in a.parts.split(",")
             for m in a.models.split(",") for lib in a.libs.split(",")]
    t0 = time.time()
    done = errors = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        futures = {pool.submit(run_cell, *c): c for c in cells}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                log = fut.result()
                done += 1
                print(f"[{done + errors}/{len(cells)} {time.time() - t0:5.0f}s] {'/'.join(map(str, c))}: "
                      f"first={log['first_try']} repaired={log['after_repair']} "
                      f"({log['attempts'][-1]['category']})", flush=True)
            except Exception as e:  # api errors leave the cell unfinished so a rerun retries it
                errors += 1
                print(f"[{done + errors}/{len(cells)}] {'/'.join(map(str, c))}: ERROR {type(e).__name__}: {e}", flush=True)
    print(f"done={done} errors={errors}")


if __name__ == "__main__":
    main()
