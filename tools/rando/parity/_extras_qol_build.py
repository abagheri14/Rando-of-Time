"""Build data/rando/extras_qol_data.json: the game facts the extras_qol plugin (extras_qol.py) relies on, read from the
game files (vanilla view: ./original copies win), so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_extras_qol_build.py ROMFS [VANILLA_DIR]

What it records and checks (the build stops when a file differs from what the plugin was written against):
- talon: the castle story steps that set Goto_HyruleCastle to a step before Step04 (each one's flowchart, next step
  and every step or entry leading to it), and the save-data rows the skip sets
- frogs: the frog song game's note timer step (MiniGame_FrogTenors EventTriggerPrepareScoreForFrog)
- replays: Dm_SY_Ocarina's three calls of the "song played" replay (:PlayAuto), and the per-song waits that follow
  each call before the song takes effect (RequestCreateConditionSensor) or its own scene starts
- packs: the wallet capacity rows (IsItemStockMax), the beehive's slingshot damage rate and the player's damage
  rates
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32, sarc_files  # noqa: E402
from evfl import Evfl  # noqa: E402
from parity._story_build import newest, step_info, describe, flat  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "extras_qol_data.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"

TALON_GUARDS = {"Event14": "Step02", "Event51": "Step02_01", "Event46": "Step03", "Event88": "Step03_02"}
TALON_FLAGS = {"Step_Goto_HyruleCastle": "Enum", "Talon_AfterWakeUp": "Bool",
               "HavePlayedEvent.Dm_HrlCastle_0020": "Bool", "Goto_HyruleCastle_IsAfter_Step03_02_Exp": "BoolExp",
               "PlayerStatus.CurrentRupee": "Int"}
# the pouch wallets and the get-demo items that carry the same capacity row (the starting wallet has no Item_ pack)
WALLET_PACKS = [(f"{kind}_Wallet_{size}", f"GameParameter/ExpansionMaxNumActor/Item_Wallet_{size}"
                 f".game__actor__ExpansionMaxNumActor.bgyml")
                for size in ("Small", "Medium", "Large") for kind in ("Item", "Pouch")
                if (kind, size) != ("Item", "Small")]
BEEHIVE = ("Obj_Kokiri_Beehive_A_01", "Life/DamageParameters/Obj_Beehive.game__life__DamageParameters.bgyml")
PLAYER_PACKS = ("Player_Base", "Player_Child", "Player_Adult")
PLAYER_DAMAGE = "Life/DamageParameters/Player.game__life__DamageParameters.bgyml"


def fail(msg):
    raise SystemExit(f"_extras_qol_build: {msg} (the plugin was written against another version of the game)")


def flow(fs, romfs, base):
    rel, versions = newest(romfs, base)
    if len(versions) != 1:
        fail(f"{base}: {versions}: the plugin edits one version only")
    return Evfl(fs.read(rel)).flowcharts[0]


def nexts(fc, e):
    ev = fc["events"]
    if e["type"] in ("action", "subflow", "join", "type6"):
        return [ev[e["next"]]["name"]] if e.get("next") is not None and e["next"] < len(ev) else []
    if "cases" in e:
        return [ev[c["next"]]["name"] for c in e["cases"]]
    if e["type"] == "fork":
        return [ev[x]["name"] for x in e["forks"]] + [ev[e["join"]]["name"]]
    return []


def talon(fs, romfs):
    fc = flow(fs, romfs, "Goto_HyruleCastle")
    by = {e["name"]: e for e in fc["events"]}
    out = {"flowchart": fc["name"], "steps": {}}
    for name, step in TALON_GUARDS.items():
        e = by.get(name)
        info = step_info(fc, e) if e else None
        if info is None or info["kind"] != "action ChallengeSystemActor.EventExecuteProgressChallengeStep" or \
                info["params"].get("ChallengeName") != "Goto_HyruleCastle" or info["params"].get("StepName") != step:
            fail(f"Goto_HyruleCastle {name}: not the Step {step} progress step")
        if not info["preds"]:
            fail(f"Goto_HyruleCastle {name}: nothing leads to it")
        out["steps"][name] = {"next": info["next"], "preds": info["preds"], "step": step}
    return out


def frogs(fs, romfs):
    """Every frog score step (the final song's note list, one per difficulty level and the tutorial's) with the seconds
    the player has for each note (PlayableSeconds) and for the first one (FirstPlayableSeconds)."""
    fc = flow(fs, romfs, "MiniGame_FrogTenors")
    hits = [e for e in fc["events"] if describe(fc, e) == "action GameSystemActor.EventTriggerPrepareScoreForFrog"]
    if len(hits) != 5:
        fail(f"MiniGame_FrogTenors: {len(hits)} frog score steps (5 expected)")
    steps = {}
    for e in hits:
        p = flat(e.get("params"), {})
        if not isinstance(p.get("PlayableSeconds"), float) or not isinstance(p.get("FirstPlayableSeconds"), float):
            fail(f"MiniGame_FrogTenors {e['name']}: no PlayableSeconds / FirstPlayableSeconds")
        steps[e["name"]] = {"PlayableSeconds": p["PlayableSeconds"], "FirstPlayableSeconds": p["FirstPlayableSeconds"],
                            "Num": p.get("Num"), "IsRandom": p.get("IsRandom")}
    return {"flowchart": fc["name"], "steps": steps}


WAITS = ("action EventSystemActor.EventWait", "action GameSystemActor.EventWaitFrameOrSkip")


def replays(fc):
    """The :PlayAuto calls and the per-song waits right after each (the first step every melody case of the dispatch
    queries reaches)."""
    by = {e["name"]: e for e in fc["events"]}
    calls = [e for e in fc["events"] if e["type"] == "subflow" and e.get("entry_point") == "PlayAuto"
             and not e.get("flowchart")]
    if len(calls) != 3:
        fail(f"Dm_SY_Ocarina: {len(calls)} calls of :PlayAuto (3 expected)")
    out = {"flowchart": fc["name"], "calls": {}, "waits": {}}
    for c in calls:
        start = nexts(fc, c)
        if len(start) != 1:
            fail(f"Dm_SY_Ocarina {c['name']}: the replay call has no single next step")
        waits, seen, stack = set(), set(), list(start)
        while stack:  # follow the melody queries to each song's first action
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            e = by[n]
            if e["type"] == "switch":
                stack.extend(nexts(fc, e))
                continue
            if describe(fc, e) in WAITS:
                frames = flat(e.get("params"), {}).get("Frames")
                after = nexts(fc, e)
                # The song takes effect after the replay wait, sometimes after a fork or camera step.
                if isinstance(frames, int) and frames >= 90 and after:
                    waits.add(n)
                    out["waits"][n] = frames
        if not waits:
            fail(f"Dm_SY_Ocarina {c['name']}: no replay wait after the call")
        out["calls"][c["name"]] = {"next": start[0], "waits": sorted(waits, key=lambda x: int(x[5:]))}
    # every wait must lead on to the replay's end (the song's effect sensor, the light reset, the melody fade, or the
    # song's own scene such as Saria's call)
    for w in out["waits"]:
        seen, stack, found = set(), [w], False
        while stack and not found:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            d = describe(fc, by[n])
            if any(k in d for k in ("RequestCreateConditionSensor", "LightOff", "LightPaletteOff_NoCapture",
                                    "FadeOcarinaMelodyHandle", "call Dm_SY_Ocarina_")):
                found = True
            stack.extend(nexts(fc, by[n]))
        if not found:
            fail(f"Dm_SY_Ocarina {w}: the wait does not lead to the replay's end")
    return out


def packs(fs):
    out = {"wallets": [], "beehive": None, "player": []}
    for pack, rel in WALLET_PACKS:
        files = sarc_files(fs.read(f"Pack/Actor/{pack}.pack.zs"))
        if rel not in files:
            fail(f"{pack}: no {rel}")
        d = byml_load(files[rel])[0]
        if d.get("GameData") != "Rupee" or d.get("IsItemStockMax") is not False:
            fail(f"{pack}: {rel} is not a rupee capacity row with IsItemStockMax false")
        out["wallets"].append({"pack": f"Pack/Actor/{pack}.pack.zs", "file": rel, "MaxNum": d.get("MaxNum")})
    pack, rel = BEEHIVE
    files = sarc_files(fs.read(f"Pack/Actor/{pack}.pack.zs"))
    rates = byml_load(files[rel])[0]["ExternalDamageParameters"]["DamageRates"]
    sling = murmur3_32("SlingshotBullet")
    if rates.get(sling) != 0.0 or rates.get(murmur3_32("Arrow")) != 1.0:
        fail(f"{pack}: the beehive's slingshot/arrow damage rates are not 0 / 1")
    out["beehive"] = {"pack": f"Pack/Actor/{pack}.pack.zs", "file": rel, "key": str(sling)}
    for p in PLAYER_PACKS:
        files = sarc_files(fs.read(f"Pack/Actor/{p}.pack.zs"))
        rates = byml_load(files[PLAYER_DAMAGE])[0]["ExternalDamageParameters"]["DamageRates"]
        out["player"].append({"pack": f"Pack/Actor/{p}.pack.zs", "file": PLAYER_DAMAGE,
                              "rates": {str(k): v for k, v in sorted(rates.items())}})
    return out


def gamedata(fs):
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    index = {e["Hash"]: (t, e) for t, rows in gd["Data"].items() if t != "Bool64bitKey" for e in rows}
    out = {}
    for name, kind in TALON_FLAGS.items():
        hit = index.get(murmur3_32(name))
        if hit is None or hit[0] != kind:
            fail(f"save data: {name} is not a {kind}")
        out[name] = {"type": kind}
        if kind == "Enum":
            if "Step04" not in hit[1]["RawValues"]:
                fail(f"save data: {name} has no Step04")
            out[name]["values"] = hit[1]["RawValues"]
    return out


def main(romfs, vanilla=None):
    fs = Romfs(romfs, vanilla or os.path.join(HERE, "original"))
    out = {"_about": "Built by tools/rando/parity/_extras_qol_build.py from the game files; read by extras_qol.py.",
           "talon": talon(fs, romfs), "frogs": frogs(fs, romfs),
           "replays": replays(flow(fs, romfs, "Dm_SY_Ocarina")), "packs": packs(fs), "gamedata": gamedata(fs)}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {len(out['talon']['steps'])} castle guards, {len(out['replays']['waits'])} song waits, "
          f"{len(out['packs']['wallets'])} wallet rows")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
