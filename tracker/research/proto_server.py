"""Tracker prototype server. It only needs the Python standard library at run time (romtools uses the 3.14 stdlib zstd).

Serves tracker/research/web/index.html, the exported map art in cache/maps and cache/icons (run build_maps.py
once), the projected checks in checks_proto.json (run build_checks.py once) and /api/state. /api/state reads the
newest save and Longshot's log on every poll, which is cheap (one 120 KB file and the log's tail).

Run:  python tracker/research/proto_server.py [--port 8765] [--save path/to/progress.sav]
Then open http://127.0.0.1:8765/ . Nothing gets written anywhere, manual marks and the spoiler taint live in the
browser's localStorage.
"""
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import autotrack_proto  # noqa: E402
import mapinfo  # noqa: E402
import savefile  # noqa: E402

STATIC = {"/": ("web/index.html", "text/html; charset=utf-8")}
TYPES = {".webp": "image/webp", ".png": "image/png", ".json": "application/json", ".js": "text/javascript",
         ".css": "text/css", ".html": "text/html; charset=utf-8"}
ARGS = sys.argv[1:]
PORT = int(ARGS[ARGS.index("--port") + 1]) if "--port" in ARGS else 8765
SAVE = ARGS[ARGS.index("--save") + 1] if "--save" in ARGS else None

_AREAS = mapinfo.areas()
_MP = mapinfo.map_param()
_CAP = {}
for _name, _a in _AREAS.items():
    for _b in _a["menu"]["BancName"]:
        _CAP.setdefault(_b, (_name, _a))
POUCH = ["Item_Token_Gold", "Obj_Heart_Piece", "Item_DekuStick", "Item_DekuNut", "Item_Bomb", "Item_Bombchu",
         "Item_DekuSeed", "Item_Arrow_Normal", "Item_MagicBean"] + autotrack_proto.ITEMS


def where(banc, pos):
    """(texture, px, py) of a level + world position on the map art, or (None, None, None)."""
    if not banc or not pos:
        return None, None, None
    base = banc.replace("_Alternative", "")
    if base not in _CAP:
        return None, None, None
    name, a = _CAP[base]
    px, py = mapinfo.project(a["capture"], pos[0], pos[2])
    mp = _MP.get(base) or {}
    if mp.get("Floor"):
        return f"{base}_{mapinfo.floor_name(mp, mapinfo.floor_of(mp, pos[1]))}", px, py
    tex = base + "_00"
    return tex, px, py


def state():
    paths = [SAVE] if SAVE else [p for p, _ in savefile.slots()[:1]]
    out = {"log": {k: v for k, v in autotrack_proto.log_state().items() if k != "probe"}}
    if paths:
        p = paths[0]
        s = savefile.load(p)
        banc = s.string64("Sequence_CurrentBanc")
        pos = s.vector3("Player_Pos_For_Map")
        tex, px, py = where(banc, pos)
        out.update(save=p, mtime=os.path.getmtime(p), banc=banc, pos=pos, player={"texture": tex, "px": px, "py": py},
                   done=sorted(str(k) for k in s.bool64),
                   pouch={a: s.pouch(a) for a in POUCH if s.pouch(a)},
                   isget=sorted(a for a in autotrack_proto.ITEMS if s.bool("IsGet." + a)),
                   life=s.int("PlayerStatus.Life"), rupees=s.int("PlayerStatus.CurrentRupee"))
    out["seed"] = installed_seed()
    return out


def installed_seed():
    """Name of the installed seed's folder (out/<seed>/patch in installed.json), used as a spoiler-free run id."""
    try:
        rec = json.load(open(os.path.join(mapinfo.ROOT, "installed.json"), encoding="utf-8"))
        return os.path.basename(os.path.dirname(os.path.normpath(rec.get("patch", ""))))
    except (OSError, ValueError):
        return None


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if ctype.startswith("image/") else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path in STATIC:
                rel, ctype = STATIC[path]
                return self._send(open(os.path.join(HERE, rel), "rb").read(), ctype)
            if path == "/api/state":
                return self._send(json.dumps(state()).encode(), "application/json")
            if path == "/api/maps":
                names = sorted(f[:-5] for f in os.listdir(os.path.join(HERE, "cache", "maps")) if f.endswith(".webp"))
                return self._send(json.dumps(names).encode(), "application/json")
            if path == "/checks.json":
                return self._send(open(os.path.join(HERE, "checks_proto.json"), "rb").read(), "application/json")
            for prefix, folder in (("/maps/", "cache/maps"), ("/icons/", "cache/icons")):
                if path.startswith(prefix):
                    name = os.path.basename(urllib.parse.unquote(path[len(prefix):]))
                    full = os.path.join(HERE, folder, name)
                    if os.path.isfile(full):
                        return self._send(open(full, "rb").read(), TYPES.get(os.path.splitext(name)[1], "application/octet-stream"))
            self._send(b"not found", "text/plain", 404)
        except Exception as e:  # keep the prototype serving
            self._send(f"error: {e}".encode(), "text/plain", 500)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), Handler) as srv:
        print(f"tracker prototype on http://127.0.0.1:{PORT}/", flush=True)
        srv.serve_forever()
