"""Dungeon rooms that lock Link in without the item they expect (every seed, merged by generate.py after _ammo).

Each is a vanilla room whose way out depends on an item the vanilla game always gives first, so a randomized seed
can send Link in without it. The remake has no save warp and some of these rooms autosave, so the player stays
trapped. Each fix is a new-file default of the saved Bool that the room's own logic module sets when its puzzle is
solved (all three are saved, default false, ResetTypeValue 8, SaveFileIndex 0, checked in GameDataList). Other
remake randomizers saw each fix work in game:
  - InsideTheDekuTree_RoomC_Cleared: the Deku Tree slingshot room's only exit is the ladder its eye switch drops
    (InsideTheDekuTree_Level_Room_C_Prefab_efa7: Obj_EyeSwitch_A_02 -> RoomC_Cleared -> the falling ladder and the
    stopper). With the Slingshot chest holding another item and no Boomerang, Link was trapped and the room's
    autosave kept him there (GyroMK/barajador-de-hyrule, a user report). The way in (the 2F scrub's shutter)
    is unchanged.
  - Gimmick_DefeatEnemy_Open_ForestTemple_03: the Forest Temple bow room, entered from the west without a bow. The
    west door waits for an arrow in its eye, the east door needs key 4, and warps are refused (Kaepora 3288862,
    seen). The fix was seen working, no bars and you walk out west (also GyroMK's user).
  - SpiritTemple_Room07_Unlocked: the door from the statue room to the child climb room stays shut for the adult
    until the cracked wall inside is broken from the child side, which can strand keys counted there (Kaepora
    c6555cf, seen). The fix was seen working: the door opens both ways, and the wall stays and still breaks.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

DEFAULTS = {"InsideTheDekuTree_RoomC_Cleared": True,
            "Gimmick_DefeatEnemy_Open_ForestTemple_03": True,
            "SpiritTemple_Room07_Unlocked": True}
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"


def _rows(fs):
    from romtools import byml_load, murmur3_32
    root = byml_load(fs.read(GAMEDATA), allow_big=True)[0]
    rows = {int(r["Hash"]): r for r in root["Data"]["Bool"]}
    return {name: rows.get(murmur3_32(name)) for name in DEFAULTS}


def ops(romfs=None):
    """Plan sections for the new-file defaults. Each one is checked to be a saved Bool, default false in the vanilla
    files."""
    from romtools import Romfs
    fs = Romfs(romfs or os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(),
               os.path.join(HERE, "original"))
    for name, r in _rows(fs).items():
        if r is None or r.get("DefaultValue") is not False or int(r.get("SaveFileIndex", -1)) != 0:
            raise ValueError(f"{GAMEDATA}: {name} is no longer a saved Bool defaulting to false")
    return {"gamedata": [{"defaults": dict(DEFAULTS)}], "_verify_plugins": ["_room_exits"],
            "_notes_room_exits": [f"new file: {n} = {v} (a room that locks Link in without its item)"
                                  for n, v in DEFAULTS.items()]}


def verify(patch, plan, romfs):
    """Reads the defaults back from the built patch's GameDataList (in_game_check, plan "_verify_plugins")."""
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    return [f"room exits: {name} is not a saved Bool defaulting to {DEFAULTS[name]}"
            for name, r in _rows(fs).items()
            if r is None or r.get("DefaultValue") is not DEFAULTS[name] or int(r.get("SaveFileIndex", -1)) != 0]
