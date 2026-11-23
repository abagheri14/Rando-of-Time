"""The remake has no save warp: a seed must never strand the player.

OoT Randomizer's logic searches from its Root region and never tracks where the player stands, because in OoT the
player can always get back to Root. Save and quit puts Link at his spawn (Link's house as a child, the Temple of
Time as an adult), or at the dungeon entrance inside a dungeon. The remake doesn't do that. Loading a save resumes
exactly where it was made (Sequence/TitleToMainWithLoadSave: PlayerStatus.SavePos in Sequence_CurrentBanc), and a
game over reloads the latest save too (Sequence/Retry). The game autosaves after every level change
(Sequence/AfterChangeBanc: SeqOneShotAutoSaveMgrRequestAutoSave), so dying returns Link to where he entered the
current level. Inside a dungeon that's OoTR's own in-dungeon save warp target (Region.savewarp), elsewhere it's
the area he came in from.

So every seed is checked sphere by sphere, the way the player would progress. With the items reachable so far,
every region either age can reach must lead back home (that age's spawn) by walking (exits whose rules hold now),
by dying inside a dungeon (its save-warp target), or by a warp song the player can already play whose pad itself
leads home by walking. A seed that strands the player somewhere is rejected and the generator tries again.

A warp song only counts when its pad is such a place (other randomizers' players saw it in game). A
child at the Bolero pad can't leave the crater's centre, and neither age walks back from the Requiem pad (OoTR's
reverse wasteland is a trick).

With remake_navi_return "everywhere" Navi takes either age home from anywhere but a boss room (D-pad right,
parity/_extras_navi.py), which is OoTR's own save warp, so every other region leads home. "dungeons" is what dying
already does here.
"""

PSEUDO = ("Root", "Root Exits", "Child Spawn", "Adult Spawn")


def _is_pseudo(region):
    # OoTR treats spawns, warp pads and "skippable" sets as shortcuts from Root. Link never stands in these regions.
    return (region.name in PSEUDO or region.name.endswith(" Warp") or "Skippable Locations" in region.name
            or region.name in ("Deliver Rutos Letter Region", "GF Above Jail Child Locations"))


def _home(world, age):
    spawn = world.get_region("Child Spawn" if age == "child" else "Adult Spawn")
    return {e.connected_region for e in spawn.exits if e.connected_region is not None}


def _safe_warp(world, state, age, ok):
    """True if `age` can play a warp song now whose pad (the " Warp" region's exit target, whatever warp song shuffle
    made it) is in `ok`, the regions that lead home by walking. Then that song is a way home from anywhere."""
    for e in world.get_region("Root Exits").exits:
        warp = e.connected_region
        if warp is None or not warp.name.endswith(" Warp") or not e.access_rule(state, spot=e, age=age):
            continue
        if any(x.connected_region in ok for x in warp.exits if x.connected_region is not None):
            return True
    return False


def _dungeon_of(region):
    d = getattr(region, "dungeon_name", None) or (region.dungeon.name if region.dungeon else None)
    if d is None and region.name.endswith(" Boss Room"):  # boss rooms are part of their dungeon's level here
        parents = {getattr(e.parent_region, "dungeon_name", None) for e in region.entrances} - {None}
        if len(parents) == 1:
            d = parents.pop()
    return d


def _static_edges(world):
    """Edges that don't depend on items. Dying takes Link back to the autosave made where the dungeon or area was
    entered (he can always take damage: enemies, falls, heat). And he can step back out of a dead-end region (OoTR
    models some spots inside a room as regions with no exits of their own)."""
    edges = []
    entry = {}  # entry points into each dungeon or area, where the game autosaves on arrival

    def area(r):
        return ("dungeon", _dungeon_of(r)) if _dungeon_of(r) else ("scene", getattr(r, "scene", None))
    for region in world.regions:
        if region.name in PSEUDO:
            continue
        for e in region.exits:
            t = e.connected_region
            if t is not None and not _is_pseudo(t) and area(t)[1] and area(t) != area(region):
                entry.setdefault(area(t), set()).add(t)
    for region in world.regions:
        if _is_pseudo(region) or not area(region)[1]:
            continue
        for t in entry.get(area(region), ()):
            if t is not region:
                edges.append((region, t))
    parents = {}
    for region in world.regions:
        if region.name in PSEUDO:
            continue
        for e in region.exits:
            if e.connected_region is not None:
                parents.setdefault(e.connected_region, set()).add(region)
    for region in world.regions:
        real_exits = [e for e in region.exits if e.connected_region is not None and e.connected_region.name not in PSEUDO]
        if not real_exits and not _is_pseudo(region):
            for p in parents.get(region, ()):
                edges.append((region, p))
    return edges


def _navi_home(world):
    """remake_navi_return "everywhere": every region outside a boss room leads home (either age)."""
    remake = getattr(getattr(world, "settings", None), "remake", None) or {}
    return remake.get("remake_navi_return", "off") == "everywhere"


def _escapable(world, state, age, static):
    """Regions from which `age` can get home with `state`: a reverse search from home over usable exits."""
    incoming = {}
    for region in world.regions:
        if region.name in PSEUDO:
            continue  # the save warp itself
        for e in region.exits:
            target = e.connected_region
            if target is None or target.name in PSEUDO:
                continue
            incoming.setdefault(target, []).append(e)
    for src, dst in static:
        incoming.setdefault(dst, []).append(_Static(src))
    ok = set(_home(world, age))
    if _navi_home(world):
        ok |= {r for r in world.regions if not _is_pseudo(r) and not r.name.endswith(" Boss Room")}
    todo = list(ok)
    while todo:
        r = todo.pop()
        for e in incoming.get(r, []):
            src = e.parent_region
            if src in ok:
                continue
            if isinstance(e, _Static) or e.access_rule(state, spot=e, age=age):
                ok.add(src)
                todo.append(src)
    return ok


class _Static:
    def __init__(self, region):
        self.parent_region = region


def check(world):
    """[(sphere, age, region name)] where the player could be stranded (empty: the seed is safe)."""
    from Search import Search
    search = Search([world.state.copy()])
    # only items logic can use (junk has no solver id and can't be collected into a search state)
    filled = [loc for loc in world.get_filled_locations() if getattr(loc.item, "solver_id", None) is not None]
    collected, problems, sphere = set(), [], 0
    static = _static_edges(world)
    while True:
        child_regions, adult_regions, _ = search.next_sphere()
        state = search.state_list[world.id]
        for age, regions in (("child", child_regions), ("adult", adult_regions)):
            ok = _escapable(world, state, age, static)
            if _safe_warp(world, state, age, ok):
                continue
            for region in regions:
                if region not in ok and not _is_pseudo(region) and region.world is world:
                    problems.append((sphere, age, region.name))
        new = [loc for loc in filled if loc not in collected and search.spot_access(loc)]
        if not new:
            break
        for loc in new:
            collected.add(loc)
            search.collect(loc.item)
        sphere += 1
    return problems
