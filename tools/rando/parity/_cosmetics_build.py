"""Builds data/rando/cosmetics_sound.json (music players, fanfares, ocarina, sound effects) from the game files.

usage: python tools/rando/parity/_cosmetics_build.py ROMFS

Everything the cosmetics plugin (tools/rando/parity/cosmetics.py) changes in sound is listed here as
(SLink user, key, sound it plays now), so a seed's plan names exact keys and the apply step can check them.
- bgm.byml players (Sound/Bgm/bgm.Product.111.byml.zs, big-endian BYML) by layer: area music, battle, fanfares.
  A player's "Asset" nodes name keys of its SLinkUserName user, and each key plays a BGM_Static.bars entry streamed
  from Sound/Resource/Stream/<name>.bwav. BGM_Static is in the always-loaded "Boot" list of
  Sound/ResourceListPack/BarslistPack.
- Shufflable area players: every Asset node uses one key and that key plays a looping stream.
- Layered area players (several keys, played one after another, or in parallel after a Fork): every key one plays
  in sequence (a fork's first branch) is listed to play the replacement, and the rest to be silenced.
- Sound effects: the keys that play the sounds OoTR lets you change, found by the sound's name. One row per
  parameter entry, with every user name sharing it. Replacement pools are the sounds (<= 6 s) of the .bars files
  each of those users loads itself (BarslistPack).
- Normal battle music: the enemy packs' BattlePresentationParam files naming BGM_EnemyBattle.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, byml_load, sarc_files  # noqa: E402
import _cosmetics_slink as S  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "cosmetics_sound.json")
BGM = "Sound/Bgm/bgm.Product.111.byml.zs"
BARSLIST = "Sound/ResourceListPack/BarslistPack.Product.111.byml.zs"

# Layers of area music (OoTR background_music) and of jingles (OoTR fanfares). Everything else, like the cutscene
# scores in DemoLayerSet, stays as it is.
AREA_LAYERS = ("MainLayerSet/L_Scene", "MainLayerSet/L_Area", "MainLayerSet/L_PlayableEvent",
               "MainLayerSet/L_NormalBattle", "SubLayerSet/L_Sub")
FANFARES = ["BGM_ItemGet_Small", "BGM_ItemGet_Medium", "BGM_ItemGet_Large", "BGM_HeartGet", "BGM_GameOver",
            "BGM_ReadRiddle", "BGM_ReadRiddle_Small", "BGM_MedalGet", "BGM_SpiritStoneGet", "BGM_FinaleJingle",
            "BGM_ItemGet_FromZelda", "BGM_Dm_MelodyGet_Saria"]
# OoTR sound-effect settings -> the remake sounds they replace (RuntimeAssetName patterns), from SLink2
SFX_TARGETS = {
    "sfx_low_hp": [r"SE_Sys_HeartAlert"],
    "sfx_navi_enemy": [r"SE_Navi_LockOnEnemy"],
    "sfx_menu_cursor": [r"SE_Sys_PlusMenu_ItemSelect00", r"SE_Sys_Cursor00"],
    "sfx_menu_select": [r"SE_Sys_Do00", r"SE_Sys_PlusMenu_ItemEquip00"],
    "sfx_hover_boots": [r"SE_Player_Adult_HoverBoots_WalkOnAir_Loop"],
    "sfx_iron_boots": [r"SE_Player_Adult_FootStep_HeavyBoots_Run0\d"],
    "sfx_boomerang_throw": [r"SE_Item_Boomerang_Flying00"],
    "sfx_hookshot_chain": [r"SE_Weapon_Range_(HookShot|LongShot)_(Launch|Return)ChainLoop\w*"],
    "sfx_arrow_shot": [r"SE_Weapon_Range_Bow_Release00"],
    "sfx_slingshot_shot": [r"SE_Weapon_Range_SlingShot_Release_00"],
    "sfx_magic_arrow_shot": [r"SE_Weapon_(Light|Fire|Ice)Arrow_Shoot00"],
    "sfx_explosion": [r"SE_Item_Bomb_Explosion0\d"],
    "sfx_bombchu_move": [r"SE_Item_BombChu_Move00"],
    "sfx_horse_neigh": [r"SE_Horse(Chd|Cmn)?_(Vo_)?Neigh_00"],
    "sfx_cucco": [r"SE_Animal_Cucco_Cry\w*"],
    "sfx_daybreak": [r"SE_Sys_MorningBreaks00_Srnd"],
    "sfx_nightfall": [r"SE_Sys_NightFalls00_Srnd"],
    "sfx_silver_rupee": [r"SE_Obj_TokenSilver_Get0\d"],
    "sfx_get_small_item": [r"SE_UI_PickUp_Item00"],
}
# kept out of the "ear-safe" pool (OoTR's random-ear-safe avoids grating sounds)
NOT_EAR_SAFE = re.compile(r"Error|Alert|Warning|Buzzer|Damage|Beep|Alarm|Fail|Noise|Crash|Explosion|Scream", re.I)
# looping streams that are not whole pieces (stems, cutscene scores, endings) or repeat another track
EXTRA_SKIP = re.compile(r"_(Intro|Outro|Low|Melody|Pad|Chime|Stem|Vocal|Night|Evening|Morning|Daytime|Base|Noise)|"
                        r"_Dm_|Ending|FirstVisit|_\d\d$|_[A-D]\d?$|^BGM_Shop_(?!KokiriForest$)")
NOTES = ["LowB", "LowC", "LowCsharp", "D", "Dsharp", "E", "F", "Fsharp", "G", "Gsharp", "A", "Asharp", "B", "C",
         "Csharp", "HighD", "HighDsharp", "HighE", "HighF"]


def layer_of(hierarchy):
    out = {}

    def walk(n, path):
        if n["Type"] == "Player":
            out[n["Name"]] = "/".join(path)
        for c in n.get("Underlayer", []):
            walk(c, path + [n["Name"]])
    for h in hierarchy:
        walk(h, [])
    return out


# SLink GroupNames for music, fanfares and the ocarina's notes. Those have their own settings, so
# remake_shuffle_all_sfx leaves out any sound played in one of them.
MUSIC_GROUPS = re.compile(r"^(Bgm|Fanfare|DemoBgm|Ocarina)")
# one-shot length bands in seconds, so a footstep stays a short sound and a cutscene rumble a long one
BANDS = (1.0, 4.0)


def sound_kind(entry, voice):
    """A sound's kind for remake_shuffle_all_sfx: voice or not, loop or one-shot (and its length band), streamed or
    not. Sounds swap only with sounds of the same kind and archive."""
    if entry.get("loop"):
        length = "loop"
    else:
        secs = entry.get("secs") or 0.0
        length = "short" if secs < BANDS[0] else "medium" if secs < BANDS[1] else "long"
    return "|".join(("voice" if voice else "sound", length, "stream" if entry.get("prefetch") else "wave"))


def all_sound_effects(fs, romfs, sl):
    """({archive: {kind: [sounds]}}, {reason: count}) for remake_shuffle_all_sfx. A sound only swaps with another of the
    same archive and kind. Any key that plays one already has that archive loaded (an actor only plays what it loads,
    BarslistPack), so the other one is there too, with no new load and no cost. We leave out sounds in more than one
    archive (we don't know which copy is loaded), sounds of the music, fanfare and ocarina groups, sounds that keys
    play from an offset into them, and the game's silent assets."""
    arch_of, info_of = {}, {}
    for f in sorted(os.listdir(os.path.join(romfs, "Sound", "Resource"))):
        if not f.endswith(".bars.zs") or f == "BGM_Static.bars.zs":
            continue
        for e in S.bars_entries(fs.read("Sound/Resource/" + f)):
            arch_of.setdefault(e["name"], []).append(f)
            info_of.setdefault(e["name"], e)
    groups, offset = {}, set()
    for pos, pp in sl.leaves().items():
        prm = sl.params(pp)
        rt = prm.get("RuntimeAssetName")
        if not rt:
            continue
        groups.setdefault(rt, set()).add(prm.get("GroupName") or "")
        start = prm.get("StartTimePos")
        if start and not start.endswith(":0"):
            offset.add(rt)
    out, left = {}, {}
    for name, gs in sorted(groups.items()):
        why = None
        if name in (S.BLANK, "DummyBlank"):
            why = "silent asset"
        elif name not in arch_of:
            why = "in no sound archive"
        elif len(arch_of[name]) > 1:
            why = "in several archives"
        elif any(MUSIC_GROUPS.match(g) for g in gs):
            why = "music, fanfare or ocarina group"
        elif len({g.endswith("Voice") for g in gs}) > 1:
            why = "played both as a voice and as a sound"
        elif name in offset:
            why = "played from an offset"
        elif sl.name_off(name) is None:
            why = "not in the name table"
        if why:
            left[why] = left.get(why, 0) + 1
            continue
        kind = sound_kind(info_of[name], any(g.endswith("Voice") for g in gs))
        out.setdefault(arch_of[name][0], {}).setdefault(kind, []).append(name)
    pools = {}
    for arch, kinds in sorted(out.items()):
        for kind, names in sorted(kinds.items()):
            if len(names) >= 2:
                pools.setdefault(arch, {})[kind] = sorted(names)
            else:
                left["alone in its archive and kind"] = left.get("alone in its archive and kind", 0) + 1
    return pools, left, info_of


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    bgm = byml_load(fs.read(BGM), allow_big=True)[0]
    sl = S.SLink(fs.read(S.SLINK))
    static = {e["name"]: e for e in S.bars_entries(fs.read("Sound/Resource/BGM_Static.bars.zs"))}
    ui = {e["name"]: e for e in S.bars_entries(fs.read("Sound/Resource/UI_Static.Product.111.bars.zs"))}
    barslist = byml_load(fs.read(BARSLIST), allow_big=True)[0]
    boot = barslist["BarslistTable"].get("Boot", {}).get("Bars", [])
    stream_info = {}

    def stream(name):
        if name not in stream_info:
            p = os.path.join(romfs, "Sound", "Resource", "Stream", name + ".bwav")
            stream_info[name] = S.bwav_info(open(p, "rb").read(0x100)) if os.path.exists(p) else None
        return stream_info[name]

    def where(u, k, rt):
        """File offsets of the RuntimeAssetName values that make user u's key k play rt. Several user names can
        share one table, and several users' assets can share one parameter entry, so rows are told apart by these
        offsets, not by names."""
        return tuple(sorted(sl.runtime_pos(c["params"]) for c in sl.calls(u)
                            if c["key"] == k and c["params"] is not None
                            and sl.params(c["params"]).get("RuntimeAssetName") == rt))

    layers = layer_of(bgm["Hierarchy"])
    players = {}
    for name, p in sorted(bgm["BGM"].items()):
        user = p.get("SLinkUserName")
        keys = sorted({n["Key"] for n in p.get("Node", []) if n.get("Type") == "Asset" and n.get("Key")})
        assets = {k: rt for k, rt, _ in sl.assets(user)} if user else {}
        tracks = {k: assets.get(k) for k in keys}
        players[name] = {"layer": layers.get(name, ""), "user": user, "keys": keys, "tracks": tracks}

    def track_row(player, key):
        p = players[player]
        t = p["tracks"][key]
        info = stream(t) if t in static else None
        return {"player": player, "user": p["user"], "key": key, "track": t,
                "secs": info["secs"] if info else None, "loop": info["loop"] if info else None}

    area, area_silence, seen = [], [], set()
    for name, p in players.items():
        if not p["layer"].startswith(AREA_LAYERS) or not p["user"]:
            continue
        for k in p["keys"]:
            t = p["tracks"].get(k)
            if t in static and where(p["user"], k, t) not in seen:
                seen.add(where(p["user"], k, t))
                area_silence.append({"user": p["user"], "key": k, "was": t})
        if len(p["keys"]) == 1 and not name.startswith("BGM_Dm_"):  # BGM_Dm_* is a cutscene's score
            row = track_row(name, p["keys"][0])
            if row["loop"] and row["track"] in static:
                area.append(row)
    # Each layered player gets one slot. _cosmetics_bgm sets IsDurationAuto so the first replacement node plays the
    # whole track, play_keys picks one path and we mute the other keys. SubLayerSet players (the Lost Woods' lead
    # ocarina, for one) normally play over the area music, so we mute those players entirely or you'd hear two songs
    # at once.
    layered, lseen = [], set()

    def key_loops(user, key):
        t = next((p["tracks"].get(key) for p in players.values() if p["user"] == user and key in p["tracks"]), None)
        info = stream(t) if t in static else None
        return bool(info and info["loop"])

    def play_keys(nodes, user):
        """Keys that play the replacement. Those are the keys reached from the start along each fork's first branch, not
        past a node whose own track loops, and never reached from another branch of any fork.
        What follows a looping node is an outro or an interruption, and a looping replacement would never end there.
        A key reached from another branch would play two copies at once (the Fire Temple's voice branch joins its band
        branch)."""
        by = {nd["Name"]: nd for nd in nodes}

        def walk(starts, first_only, stop_at_loop):
            out, todo, seen = set(), list(starts), set()
            while todo:
                nm = todo.pop()
                if nm in seen or nm not in by:
                    continue
                seen.add(nm)
                nd = by[nm]
                dests = [t["DestinationNode"] for t in nd.get("Transition") or [] if t.get("DestinationNode")]
                if nd.get("Type") == "Asset" and nd.get("Key"):
                    out.add(nd["Key"])
                    if stop_at_loop and key_loops(user, nd["Key"]):
                        continue
                if nd.get("Type") == "Fork" and first_only:
                    dests = dests[:1]
                todo += dests
            return out
        start = [nd["Name"] for nd in nodes if nd.get("Type") == "Start"]
        lead = walk(start, True, True)
        parallel = set()
        for nd in nodes:
            if nd.get("Type") == "Fork":
                others = [t["DestinationNode"] for t in (nd.get("Transition") or [])[1:] if t.get("DestinationNode")]
                parallel |= walk(others, False, False)
        return lead - parallel
    layered_players = [name for name, p_ in sorted(players.items())
                       if p_["layer"].startswith(AREA_LAYERS) and p_["user"] and len(p_["keys"]) >= 2
                       and not name.startswith("BGM_Dm_")]
    # Players can share keys (Kakariko and the Fishing Pond, the Deku Tree, its Fairy Fountain and the Enemy Museum),
    # so a key plays the replacement only if it does in every player that has it.
    silenced_somewhere = set()
    plays = {}
    for name in layered_players:
        p_ = players[name]
        overlay = p_["layer"].startswith("SubLayerSet")
        plays[name] = set() if overlay else play_keys(bgm["BGM"][name].get("Node", []), p_["user"])
        for k in p_["keys"]:
            t = p_["tracks"].get(k)
            if t in static and k not in plays[name]:
                silenced_somewhere.add(where(p_["user"], k, t))
    overlays = []
    for name in layered_players:
        p_ = players[name]
        fork = any(nd.get("Type") == "Fork" for nd in bgm["BGM"][name].get("Node", []))
        play, silence = [], []
        for k in p_["keys"]:
            t = p_["tracks"].get(k)
            w = where(p_["user"], k, t) if t in static else None
            if not w or w in lseen:
                continue
            lseen.add(w)
            (play if k in plays[name] and w not in silenced_somewhere else silence).append(
                {"user": p_["user"], "key": k, "was": t})
        if play:
            layered.append({"player": name, "fork": fork, "play": play, "silence": silence})
        elif silence:
            overlays.append({"player": name, "silence": silence})
    # dedupe players sharing one user and key (e.g. the boss players): one slot each
    slots, used = [], set()
    for row in area:
        w = where(row["user"], row["key"], row["track"])
        if w not in used:
            used.add(w)
            slots.append(row)
    in_slots = {r["track"] for r in slots}
    # full looping tracks the game has that no simple player uses (a whole Kokiri Forest loop, say), as extra sources
    extra = []
    for t in sorted(static):
        info = stream(t)
        if t in in_slots or not info or not info["loop"] or info["secs"] < 40 or sl.name_off(t) is None:
            continue
        if EXTRA_SKIP.search(t):
            continue
        extra.append({"track": t, "secs": info["secs"]})
    fanfares = []
    for name in FANFARES:
        p = players.get(name)
        # the player's own key (fanfare players also hold the shared chest-suspense key BGM_ItemGet_Intro)
        key = name if p and name in p["keys"] else (p["keys"][0] if p and len(p["keys"]) == 1 else None)
        if key is None:
            continue
        row = track_row(name, key)
        if row["track"] in static:
            fanfares.append(row)
    shop = [{"user": "BGM_Shop", "key": k, "was": rt} for k, rt, _ in sl.assets("BGM_Shop") if rt in static]
    battle = [{"user": players["BGM_EnemyBattle"]["user"], "key": k, "was": t}
              for k, t in players["BGM_EnemyBattle"]["tracks"].items()]
    # Event music. OoTR's background music list also takes the event themes (Kaepora Gaebora, Shop, Chamber of the
    # Sages...), so these are the cutscene and playable-event players whose one key plays a whole looping track. They're
    # grouped by that track, since OoTR replaces a sequence everywhere it plays. The owl's ten scenes share one
    # replacement, and a cutscene that plays an area's track follows that area. The ten shop speakers (user BGM_Shop,
    # one 60 s loop each, no player) are OoTR's one "Shop". Cutscene scores with several keys (stems, outros synced to
    # the scene) stay as they are.
    taken = {where(r["user"], r["key"], r["track"]) for r in slots}
    taken |= {where(r["user"], r["key"], r["was"]) for lp in layered for r in lp["play"] + lp["silence"]}
    taken |= {where(r["user"], r["key"], r["was"]) for ov in overlays for r in ov["silence"]}
    events = {}
    for name, p in sorted(players.items()):
        if not p["layer"].startswith(("DemoLayerSet", "MainLayerSet/L_PlayableEvent")) or not p["user"] \
                or len(p["keys"]) != 1:
            continue
        k = p["keys"][0]
        t = p["tracks"][k]
        info = stream(t) if t in static else None
        if not info or not info["loop"] or sl.name_off(t) is None:
            continue
        w = where(p["user"], k, t)
        if not w or w in taken:
            continue
        taken.add(w)
        events.setdefault(t, {"group": t, "secs": info["secs"], "rows": []})["rows"].append(
            {"player": name, "user": p["user"], "key": k, "was": t})
    shop_rows = [r for r in shop if stream(r["was"]) and stream(r["was"])["loop"]]
    if shop_rows:
        events["BGM_Shop"] = {"group": "BGM_Shop", "secs": stream(shop_rows[0]["was"])["secs"], "rows": shop_rows}
    event_groups = [events[t] for t in sorted(events)]
    # Jingles. OoTR's fanfare list also takes the cutscene fanfares (Door of Time, Master Sword, Zelda turns around...),
    # so each cutscene player whose one key plays a whole track that ends gets one fanfare slot. So does the chest
    # suspense (BGM_ItemGet_Intro, OoTR's "Treasure Chest", held by every item-get fanfare user).
    fan_taken = {where(r["user"], r["key"], r["track"]) for r in fanfares}
    jingles = []
    for name, p in sorted(players.items()):
        if not p["layer"].startswith("DemoLayerSet") or not p["user"] or len(p["keys"]) != 1:
            continue
        k = p["keys"][0]
        t = p["tracks"][k]
        info = stream(t) if t in static else None
        if not info or info["loop"] or sl.name_off(t) is None:
            continue
        w = where(p["user"], k, t)
        if not w or w in fan_taken or w in taken:
            continue
        fan_taken.add(w)
        jingles.append(track_row(name, k))
    intro = [{"player": n, "user": players[n]["user"], "key": "BGM_ItemGet_Intro", "was": "BGM_ItemGet_Intro"}
             for n in FANFARES if players.get(n) and players[n]["tracks"].get("BGM_ItemGet_Intro") == "BGM_ItemGet_Intro"]
    seen_i, chest = set(), []
    for r in intro:
        w = where(r["user"], r["key"], r["was"])
        if w and w not in seen_i:
            seen_i.add(w)
            chest.append(r)
    if chest:
        info = stream("BGM_ItemGet_Intro")
        jingles.append({"player": "BGM_ItemGet_Intro", "user": chest[0]["user"], "key": "BGM_ItemGet_Intro",
                        "track": "BGM_ItemGet_Intro", "secs": info["secs"], "loop": info["loop"], "also": chest[1:]})

    ocarina = {k: rt for k, rt, _ in sl.assets("Ocarina")}
    oc_bars = {e["name"]: e for e in S.bars_entries(fs.read("Sound/Resource/Ocarina.bars.zs"))}
    songs = [{"user": "Ocarina", "key": k, "track": rt, "secs": oc_bars.get(rt, {}).get("secs")}
             for k, rt in sorted(ocarina.items()) if k.startswith("Melody_") and rt in oc_bars]
    notes = []
    for k, rt in sorted(ocarina.items()):
        m = re.match(r"(System_)?Ocarina_(\w+)$", k)
        if m and m.group(2) in NOTES and rt == f"Ocarina_{m.group(2)}" and sl.name_off(f"Piccolo_{m.group(2)}"):
            notes.append({"user": "Ocarina", "key": k, "was": rt, "flute": f"Piccolo_{m.group(2)}"})

    # every (user, key) of the whole table that plays a given sound
    plays = {}
    users = {}
    for f in sorted(barslist["BarslistTable"]):
        users[f] = barslist["BarslistTable"][f]
    all_users = sorted(set(users) | {p["user"] for p in players.values() if p["user"]} | {"Player", "Player_Adult",
                       "Player_Child", "Npc_Navi", "Ocarina", "ExpressionSound", "UI_PlusMenu_00", "UI_PickUp_00"})
    for u in all_users:
        for k, rt, _ in sl.assets(u):
            if rt:
                plays.setdefault(rt, []).append((u, k))
    sfx = {}
    for setting, pats in SFX_TARGETS.items():
        rx = re.compile("^(" + "|".join(pats) + ")$")
        # Npc_Navi and Dm_Npc_Navi can share a table, so we keep one row per table and list every user. That way the
        # replacement comes from sound files they all load.
        rows = {}
        for rt in sorted(plays):
            if rx.match(rt):
                for u, k in plays[rt]:
                    row = rows.setdefault(where(u, k, rt), {"user": u, "key": k, "was": rt, "aliases": []})
                    if u not in row["aliases"]:
                        row["aliases"].append(u)
        sfx[setting] = list(rows.values())
    voice = {}
    for age in ("Adult", "Child"):
        voice[age.lower()] = [{"user": f"Player_{age}", "key": k, "was": rt}
                              for k, rt, prm in sl.assets(f"Player_{age}")
                              if prm.get("GroupName") == "PlayerVoice" and rt and rt != S.BLANK]
    # Replacement pools are the short one-shot sounds of the .bars files each target user loads itself (BarslistPack).
    # UI users have no entry and play the always-loaded UI_Static. We don't know if a user can play a sound from a .bars
    # another user loaded (no vanilla user does), so pools stay within the user's own files.
    sfx_users, sfx_bars = {}, {}
    aliases = sorted({u for rows in sfx.values() for r in rows for u in r["aliases"]})
    for u in aliases:
        sfx_users[u] = [b + ".zs" for b in users.get(u, {}).get("Bars", [])] or ["UI_Static.Product.111.bars.zs"]
        for b in sfx_users[u]:
            if b in sfx_bars:
                continue
            entries = S.bars_entries(fs.read("Sound/Resource/" + b))
            sfx_bars[b] = [{"sound": e["name"], "secs": e["secs"], "loop": e["loop"],
                            "ear_safe": not NOT_EAR_SAFE.search(e["name"]) and e["secs"] <= 2.5}
                           for e in entries
                           if e["name"].startswith("SE_") and 0.05 <= (e.get("secs") or 0) <= 6
                           and sl.name_off(e["name"]) is not None]
    sfx_all, sfx_all_left, sound_info = all_sound_effects(fs, romfs, sl)
    for rows in sfx.values():  # each target's loop flag, since a replacement has to be the same kind
        for r in rows:
            r["loop"] = bool(sound_info.get(r["was"], {}).get("loop"))
    # Normal battle music. Enemies name it in their BattlePresentationParam (Pack/Actor/Enemy_*.pack.zs). The same
    # packs carry EnemyNoBattleBgm, the parent without a BgmName that some enemies use as is.
    battle_params = []
    for f in sorted(os.listdir(os.path.join(romfs, "Pack", "Actor"))):
        if not f.startswith("Enemy_") or not f.endswith(".pack.zs"):
            continue
        files = sarc_files(fs.read(f"Pack/Actor/{f}"))
        for inner, raw in sorted(files.items()):
            if inner.startswith("Component/BattlePresentationParam/"):
                root = byml_load(raw)[0]
                if root.get("BgmName") == "BGM_EnemyBattle":
                    battle_params.append({"pack": f"Pack/Actor/{f}", "file": inner})
    # non-UI users that play UI_Static sounds, which shows always-loaded sounds play for any user
    cross = sorted({u for rt, uk in plays.items() if rt in ui for u, _ in uk if not u.startswith("UI_")
                    and "UI_Static.Product.111.bars" not in users.get(u, {}).get("Bars", [])})
    out = {
        "_about": "Built by tools/rando/parity/_cosmetics_build.py from the game files (SLink2 sound link table, "
                  "bgm.byml, BGM_Static / UI_Static / Ocarina .bars, BarslistPack). Rows are (SLink user, key, "
                  "sound it plays now).",
        "boot_bars": boot,
        "bgm_area_slots": slots, "bgm_extra_tracks": extra, "bgm_area_silence": area_silence + shop,
        "bgm_area_layered": layered, "bgm_overlays": overlays, "bgm_event_groups": event_groups,
        "bgm_battle": battle, "battle_presentation": battle_params, "fanfares": fanfares, "jingles": jingles,
        "ocarina_songs": songs, "ocarina_notes": notes,
        "sfx": sfx, "link_voice": voice, "sfx_users": sfx_users, "sfx_bars": sfx_bars,
        "sfx_all": sfx_all, "sfx_all_left_out": sfx_all_left,
        "non_ui_users_playing_always_loaded_ui_sounds": cross[:40],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{OUT}: {len(battle_params)} enemy battle-music params, {len(slots)} area slots, {len(layered)} layered "
          f"players, {len(extra)} extra tracks, {len(area_silence) + len(shop)} music keys "
          f"to silence, {len(overlays)} overlays, {len(event_groups)} event groups "
          f"({sum(len(g['rows']) for g in event_groups)} keys), {len(fanfares)} fanfares, {len(jingles)} jingles, "
          f"{len(songs)} songs, {len(notes)} ocarina notes, "
          f"all-sfx {sum(len(v) for k in sfx_all.values() for v in k.values())} sounds in "
          f"{sum(len(k) for k in sfx_all.values())} pools (left out: {sfx_all_left}), "
          f"{sum(len(v) for v in sfx.values())} sound-effect keys, voice {len(voice['adult'])}/{len(voice['child'])}, "
          f"pools {', '.join(f'{b}: {len(v)}' for b, v in sfx_bars.items())}; {len(cross)} non-UI users play "
          f"always-loaded UI sounds")
    for k, v in sfx.items():
        if not v:
            print("  no keys found for", k)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
