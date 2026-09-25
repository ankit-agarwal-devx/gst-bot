"""How far along am I?  uv run python progress.py

Runs the visible tests and prints one line per task. A task's visible part is done when every
one of its tests passes. The grader also runs hidden checks for each task (same rules, different
inputs and failure sequences); you see how many of those pass when you submit.
"""
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TASKS = [
    ("test_task1_faq", "Task 1  The bot doesn't recognise my question"),
    ("test_task2_gst", "Task 2  The GST on my invoice is wrong"),
    ("test_task3_upstream", "Task 3  The bot sometimes spins forever, then errors"),
    ("test_task4_resilience", "Task 4  Keep helping users when tax-model is struggling"),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
                        "tests/bot"], capture_output=True)
        if not junit.exists():
            print("pytest did not run: try `uv run pytest` to see why")
            return 2
        results: dict[str, list[bool]] = {module: [] for module, _ in TASKS}
        seen = {}
        for case in ET.parse(junit).getroot().iter("testcase"):
            module = case.get("classname", "").rsplit(".", 1)[-1]
            key = (module, case.get("name"))
            ok = not any(child.tag in ("failure", "error") for child in case)
            seen[key] = seen.get(key, True) and ok
        for (module, _), ok in seen.items():
            results.setdefault(module, []).append(ok)

    all_done = True
    for module, title in TASKS:
        outcomes = results.get(module, [])
        passed, total = sum(outcomes), len(outcomes)
        done = total > 0 and passed == total
        all_done &= done
        print(f"{'✅' if done else '❌'}  {title:58} {passed:3}/{total}")
    print()
    print("All visible tests pass. Submit to see the hidden checks." if all_done
          else "Run `uv run pytest tests/bot/<file> -x` to work on one task at a time.")
    return 0 if all_done else 1


if __name__ == "__main__":
    sys.exit(main())
