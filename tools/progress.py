"""How far a tool is, for the randomizer app's progress bar (release/app/Randomizer.cs).

With REMAKE_PROGRESS=1 in the environment (the app sets it for the steps it runs), report(f) prints a line
"@progress F" on stdout (F is the share of this tool's work done, 0..1) and flushes it, so the app hears it at
once. The app keeps these lines out of its log. Without it nothing gets printed, so a tool's output from the
command line and everything it writes stay exactly as they are. The app weighs each step by how long it took
last time and moves the bar with the clock between reports, so a tool only reports where its time really goes.
REMAKE_PROGRESS_TRACE=1 adds the seconds since the tool started ("@progress F T"), for setting a tool's shares.
"""
import os
import sys
import time

ON = os.environ.get("REMAKE_PROGRESS") == "1"
TRACE = os.environ.get("REMAKE_PROGRESS_TRACE") == "1"
_START = time.monotonic()
_last = [-1.0, 0.0]  # the last fraction printed, and when


def report(fraction):
    """Reports this tool's share done (0..1). It prints a line at most every 0.2 s unless the share moved 0.5% or
    more."""
    if not ON:
        return
    f = min(1.0, max(0.0, float(fraction)))
    now = time.monotonic()
    if f < 1.0 and abs(f - _last[0]) < 0.005 and now - _last[1] < 0.2:
        return
    _last[0], _last[1] = f, now
    sys.stdout.write(f"@progress {f:.4f}" + (f" {now - _START:.2f}" if TRACE else "") + "\n")
    sys.stdout.flush()


def span(items, start, end):
    """The items, in order, with the share moving from start to end along them."""
    items = list(items)
    for i, x in enumerate(items):
        report(start + (end - start) * i / max(1, len(items)))
        yield x
    report(end)
