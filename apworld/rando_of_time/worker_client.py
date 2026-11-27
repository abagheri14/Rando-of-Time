"""The apworld's side of our randomizer's logic worker (tools/archipelago/worker.py). There's one process per player
of this game, started from the randomizer folder named in Archipelago's host.yaml. Nothing here imports
Archipelago, so the test harness (tools/archipelago/harness.py) can drive it too.

The access rule is a cached sweep of our logic for the player's collected progression items. That's the pattern
from OotrR's apworld (github.com/Mozencaz/OotrR, src/oot_rando/archipelago/bridge.py PlayerWorld.reach;
MIT License, Copyright (c) 2026 Mozencaz; see LICENSE-OotrR.txt).
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

WORKER = os.path.join("tools", "archipelago", "worker.py")
_ALL = []


def find_python(folder, configured=""):
    """The Python that runs our randomizer. host.yaml's if it's set, else the randomizer's own python\\python.exe (the
    release bundles one), else the Python launcher or python on PATH. Never Archipelago's executable, it's a frozen
    build."""
    if configured:
        return [configured]
    bundled = os.path.join(folder, "python", "python.exe" if os.name == "nt" else "bin/python3")
    if os.path.isfile(bundled):
        return [bundled]
    if os.name == "nt" and shutil.which("py"):
        return ["py", "-3"]
    for name in ("python3", "python"):
        if shutil.which(name):
            return [shutil.which(name)]
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    raise FileNotFoundError("no Python found to run Rando of Time: set python in host.yaml "
                            "(rando_of_time_options)")


def check_folder(folder):
    if not folder or not os.path.isfile(os.path.join(folder, WORKER)):
        raise FileNotFoundError(f"{folder!r} is not a Rando of Time folder ({WORKER} missing): set "
                                "randomizer_folder in host.yaml (rando_of_time_options)")
    return os.path.abspath(folder)


class WorkerError(RuntimeError):
    pass


class Worker:
    """One logic worker process. Requests are JSON lines; one reply line each."""

    def __init__(self, folder, python=""):
        folder = check_folder(folder)
        fd, self.log_path = tempfile.mkstemp(prefix="rando_of_time_worker_", suffix=".log")
        self._log = os.fdopen(fd, "wb")
        env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        for var in ("PYTHONHOME", "PYTHONPATH"):  # Keep frozen Archipelago paths out of the worker.
            env.pop(var, None)
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen(find_python(folder, python) + ["-u", os.path.join(folder, WORKER)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log, cwd=folder,
                                     env=env, creationflags=flags)
        self.lock = threading.Lock()
        self.pending = False
        _ALL.append(self)

    def send(self, obj):
        line = (json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except OSError as e:
            raise WorkerError(f"the logic worker stopped: {e}\n{self.log_tail()}") from e

    def recv(self):
        line = self.proc.stdout.readline()
        if not line:
            raise WorkerError(f"the logic worker stopped (exit code {self.proc.poll()})\n{self.log_tail()}")
        reply = json.loads(line.decode("utf-8"))
        if not reply.get("ok"):
            raise WorkerError(f"{reply.get('error')}\n{self.log_tail()}")
        return reply

    def request(self, obj):
        with self.lock:
            self.send(obj)
            return self.recv()

    def start(self, obj):
        """Sends a request now and reads its reply later (finish), so several players' workers build at the same
        time."""
        with self.lock:
            self.send(obj)
            self.pending = True

    def finish(self):
        with self.lock:
            self.pending = False
            return self.recv()

    def log_tail(self, n=3000):
        try:
            self._log.flush()
            with open(self.log_path, "rb") as f:
                data = f.read()
            return data[-n:].decode("utf-8", "replace")
        except OSError:
            return ""

    def close(self):
        if self.proc.poll() is None:
            try:
                with self.lock:
                    self.send({"cmd": "quit"})
                self.proc.wait(5)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        try:
            self._log.close()
            os.remove(self.log_path)
        except OSError:
            pass


@atexit.register
def _close_all():
    for w in _ALL:
        try:
            w.close()
        except Exception:  # noqa: BLE001
            pass


def check_slot(folder, python, aprr_path, timeout=900):
    """Runs build_patch.py --check on a written .aprr and returns (ok, message). Our generator's post-fill checks run
    there (the plugins' after_fill, the chests' scene-row budget, every placement still in place), same as when the
    player builds."""
    folder = check_folder(folder)
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    for var in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(var, None)
    flags = 0x08000000 if os.name == "nt" else 0
    cmd = find_python(folder, python) + [os.path.join(folder, "tools", "archipelago", "build_patch.py"), aprr_path,
                                         "--check"]
    try:
        r = subprocess.run(cmd, cwd=folder, env=env, capture_output=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return False, f"build_patch --check took over {timeout} s"
    text = (r.stdout + r.stderr).decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("Hint copies")]
    return r.returncode == 0, chr(10).join(lines[-12:])


class PlayerLogic:
    """One player's world as the worker described it, and the cached access rule."""

    CACHE_SIZE = 4096

    def __init__(self, worker, world):
        self.worker, self.world = worker, world
        self.names = world["locations"]
        self.progression = frozenset(world["progression"])
        self.always = 0
        for i in world.get("always", ()):
            self.always |= 1 << i
        self.cache = {}
        self.queries = 0

    def key(self, counts):
        return frozenset((k, v) for k, v in counts.items() if v > 0 and k in self.progression)

    def reach(self, counts):
        """(bitmask of reachable locations by index, goal reached) for this player's collected items."""
        key = self.key(counts)
        hit = self.cache.get(key)
        if hit is None:
            if len(self.cache) >= self.CACHE_SIZE:
                self.cache.clear()
            reply = self.worker.request({"cmd": "reach", "have": dict(key)})
            hit = (int(reply["reach"], 16) | self.always, bool(reply["goal"]))
            self.cache[key] = hit
            self.queries += 1
        return hit

    def reachable(self, index, counts):
        return bool((self.reach(counts)[0] >> index) & 1)

    def item_rules(self):
        """index -> (own item names allowed, foreign items allowed)."""
        names = self.world["rule_items"]
        every = frozenset(names)
        deny = self.world["deny"]
        foreign_deny = set(self.world["foreign_deny"])
        locked = self.world["locked"]
        out = {}
        for i in range(len(self.names)):
            if str(i) in locked:  # placed by our rules before Archipelago's fill, so only that item
                out[i] = (frozenset([locked[str(i)]]), False)
                continue
            d = deny.get(str(i))
            out[i] = (every - {names[k] for k in d} if d else every, i not in foreign_deny)
        return out
