"""Logic worker for the Archipelago world (apworld/rando_of_time).
It holds one player's world of our generator and answers Archipelago's "what can this player reach" questions.
The apworld starts one per player of our game.

  python tools/archipelago/worker.py          (PYTHONHASHSEED=0; it restarts itself with it otherwise)

JSON lines on stdin, one reply line per request on stdout:
  {"cmd": "build", "seed": "123", "options": {our settings}, "plugins": null, "seed_key": "8-16 letters/digits"}
      -> {"ok": true, "world": {...}}   (tools/archipelago/world.py UnfilledWorld.describe)
         "options" are Archipelago's option values, read over config/rando_settings.json like the app's settings files;
         "settings" (already resolved, as settings_used.json) may be given instead.
  {"cmd": "reach", "have": {item: count}}
      -> {"ok": true, "reach": "<hex bitmask of reachable locations, by index>", "goal": bool}
  {"cmd": "quit"}
A failed request gets {"ok": false, "error": "..."}. Everything else (OoTR's and the plugins' prints) goes to stderr.

Why a separate process? OoTR's modules (Main, Fill, Utils, Item, Region...) share names with Archipelago's own, our
generator needs PYTHONHASHSEED=0 to rebuild a seed's world exactly, and its plugins need the randomizer's Python
packages. The apworld only speaks this protocol.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")  # A plugin imports NumPy. One BLAS thread keeps its buffers small.


def main():
    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints never reach the protocol stream
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        out.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.path.insert(0, HERE)
    import world as W

    def send(obj):
        out.write(json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n")
        out.flush()
    uw = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("cmd")
            if cmd == "quit":
                send({"ok": True})
                return 0
            if cmd == "build":
                t0 = time.perf_counter()
                cfg = req.get("settings")
                if cfg is None:
                    cfg = W.resolve_settings(req.get("options") or {})
                uw = W.UnfilledWorld(str(req["seed"]), cfg, req.get("plugins"), seed_key=req.get("seed_key"))
                send({"ok": True, "world": uw.describe(), "ms": round((time.perf_counter() - t0) * 1000)})
            elif cmd == "reach":
                if uw is None:
                    raise RuntimeError("no world built yet")
                bits, goal = uw.reach(req.get("have") or {})
                send({"ok": True, "reach": format(bits, "x"), "goal": goal})
            else:
                raise ValueError(f"unknown command {cmd!r}")
        except Exception as e:  # noqa: BLE001 - the apworld shows the reason
            import traceback
            traceback.print_exc()
            send({"ok": False, "error": f"{type(e).__name__}: {e}"})
    return 0


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        import subprocess
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=dict(os.environ, PYTHONHASHSEED="0")))
    sys.exit(main())
