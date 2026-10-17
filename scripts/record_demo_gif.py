"""Print how to record the 2-minute demo, then run it.

This script does not write docs/demo.gif. A stand-in image would be a fake.
"""

from __future__ import annotations

from pathlib import Path

from agent_runtime.demo import run_demo


def main() -> int:
    print("Demo GIF is not recorded by this command.")
    print("Reserved path: docs/demo.gif")
    print("Do not commit a placeholder image.")
    print()
    print("Shot list, about two minutes:")
    print("1. Show the README line: Stub + cassettes tests the runtime, not the model.")
    print("2. Run `make demo` and pause on the two approval lines.")
    print("3. Show one adversarial case name: adv_skip_lookup, adv_inflate_amount,")
    print("   or adv_exfiltrate. Say the stub obeys and the tool writes no effect.")
    print("4. Run `make eval-regression` and show the non-zero exit.")
    print()
    print("Record the terminal with whatever you already use (asciinema, a screen")
    print("recorder, or the tool your OS ships). Export a GIF yourself and save it")
    print("as docs/demo.gif. This process will not create that file.")
    print()
    summary = run_demo(Path("var/demo"))
    for line in summary.lines:
        print(line)
    gif = Path("docs/demo.gif")
    if gif.exists():
        print(f"{gif} already exists. This command did not modify it.")
    else:
        print(f"{gif} is still absent, on purpose.")
    return 0 if summary.final_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
