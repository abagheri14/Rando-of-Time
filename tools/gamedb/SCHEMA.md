# Game-logic index: record shapes

This is the contract between the builders, `db.py` and the audits. The builders write
`cache/gamedb/<tag>/<section>.json` in the format `common.py` defines:
`{"meta", "by_file": {rel: record}, "summary", "errors"}`. Add fields whenever you need them, but keep the names and
fields below as they are, so `db.py` and the audits can still read the cache.

- 64-bit placement hashes are **decimal strings** (`"9829790505452123995"`). 32-bit GameData hashes are ints.
- `rel` is the romfs-relative path with forward slashes (`Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs`).
- Empty or default fields are left out.
- A **ref** to an event step is `{"file": rel, "fc": flowchart, "entry": entry point, "event": event name}`. A ref to
  a logic node is `{"file": rel, "node": i}`, and a ref to a placement is `{"file": rel, "hash": h}`.
- A **formula** (a boolean condition) is a string in prefix form, like
  `OR(flag:HavePlayedEvent.Dm_WaterTemple_0000, AND(step:SageOfWater>=Step05, NOT(boots:1)))`. The leaves are
  `flag:<GameData bool or BoolExp>`, `int:<name><op><value>`, `step:<Challenge><op><Step>` (op `>` IsAfter, `<`
  IsBefore, `=` IsEqual), `node:<i>.<output>` (an unresolved node output, like an actor output such as `Dead`, or a
  timer), `player:<check>`, `time:<...>`, `const:true|false` and `unknown:<node name>`.

## levels.json (build_levels.py)

`by_file[rel]` for `Banc/<Area>/<Level>_<Layer>.bcett.byml.zs`:
```
{"area", "level", "layer", "age": "child"|"adult"|null, "variant"?: "Alternative"|...,
 "actors": [{"hash", "gyaml", "name"?, "pos": [x,y,z], "presence"?: {"flag", "neg": bool, "lazy": bool},
             "links"?: [{"dst", "name", ...}], "dyn"?: {key: value}, "room"?: int,
             "flag_keys"?: [dyn keys whose value is a GameData name], "event_keys"?: [dyn keys naming an event]}],
 "ai_groups": [{"hash", "logic": "Logic/<file>.ainb", "refs": {reference Id: placement hash}, "subs"?: [nested
                module instances], "paths"?: {...}}],
 "far_delete_groups"?: [[hash]], "simultaneous_groups"?: [[hash]], "plg_gd"?: [{guid, flag, type}],
 "placement_groups"?: [...], "rails"?: count}
```
The `refs` keys are the reference Id, which the module's nodes use as their `InstanceName`. Where an Id repeats in
one group (nested prefabs), the key is the reference Path instead, with `#2` added if even that repeats.
Actors can also have `rot`, `scale`, `presence.type` (the flag's GameDataList table),
`links` = `{dst, src, name, gyaml}`, `b64` / `b64_x2` (the hash / hash^2 has a Bool64bitKey row), `rails`, `phive_id`
(only when it differs), `phive_group`, `constraint` and `force_active`. The link names are Reference,
EventProxyRequestLink, ForSale, Scaffold, BreakTarget, FloorOmen, FrozenInIce, RespawnFlagSyncLink and ActorHold.
Banc/BancBasedResource files are `{"kind": "resource", ...}`.

## events.json (build_events.py)

`by_file[rel]` for `Event/EventFlow/*.bfevfl.zs`, every version of each (`summary.newest[base]` is the one the game
reads):
```
{"base", "ver", "flowcharts": [{"name", "actors": [names],
   "events": [{"i", "name", "type", "call"?: "Actor.ActionOrQuery" | "Flow:Entry", "params"?: {path: value},
               "next"?: name, "cases"?: [[value, name]], "forks"?: [names], "join"?: name}],
   "entries": {ep: {"main": name, "sub_flow_events"?: [names], "reach": [event names],
                    "reads": [op], "writes": [op], "gives": [op], "item_queries": [op], "calls": ["Flow:Entry"],
                    "actors": [names]}}}]}
```
`op` = `{"event", "kind", "flag"?, "value"?, "challenge"?, "step"?, "ignore_completed"?, "item"?, "guards"?}`. Its
`guards` are the switch decisions on the shortest path from the entry to that event, as `[{"event", "call",
"params", "case"}]`. The kinds are `bool`, `int`, `step` (quest step request), `step_query`, `exp`, `isget`, `pouch`,
`played` (a HavePlayedEvent read), ...

`summary`: `{"newest": {base: rel}, "setters": {flag: [ref+op]}, "readers": {flag: [ref+op]},
"step_requests": {challenge: [ref+op]}, "gives": {item: [ref+op]}, "item_readers": {item: [ref+op]},
"calls_catalogue": {...}, "unclassified": [...], "settings": {EventSetting name: {"flow", "entry", ...}}}`.

## logic.json (build_logic.py)

`by_file[rel]` for `Logic/*.ainb`, `Sequence/*.ainb`, `AI/*.ainb`:
```
{"kind": "logic"|"sequence"|"ai", "name",
 "nodes": [{"i", "name", "type", "props"?: {}, "in"?: {name: value | {"node", "out", "flagged": bool}},
            "out"?: {name: flagged bool}}],
 "actors": {InstanceName: {"node", "class", "gates": {input name: formula}}},
 "reads": [{"flag", "kind", "node", ...}], "writes": [{"flag", "value", "node", "when": formula}],
 "unflagged_reads": [{"node", "input", "src", "out"}], "dead_outputs"?: [...]}
```
`Component/AIScheduleParam/*.bgyml`: `{"kind": "schedule", "actor", "states": [{"cond", "events": [{"type",
"setting"}], ...}], "rule": "last true wins"}`.
`summary`: `{"setters": {flag: [ref]}, "readers": {flag: [ref]}, "actor_gates": {InstanceName: [ref]}}`.

## actors.json (build_actors.py)

`by_file[rel]` for `Pack/Actor/<Actor>.pack.zs`:
```
{"actor", "parents": [actor param chain], "holdup": {"event_object_base": bool, "as_getdemo": bool,
 "animation_param": bool}, "lift"?: {...}, "damage"?: {...}, "saves"?: [{"flag"|"key", "how", ...}],
 "ai"?: [inner ainb paths], "components"?: {type: inner path}}
```
`summary`: `{"pouch": {actor: PouchActorInfo row}, "lift_grades": {...}, "breakers": {...}}`.

## gamedata.json (build_gamedata.py)

`by_file["GameData/GameDataList.Product.110.byml.zs"]`:
```
{"keys": {name or "#<hash>": {"type", "default"?, "reset", "save"?, "size"?, "values"?: enum values,
          "exp"?: formula (BoolExp)}},
 "b64": [placement hashes with a Bool64bitKey row], "unnamed": count}
```
`summary`: `{"challenges": {name: {"steps": [step names in order], ...}}, "reset_types": {value: meaning}}`.

## More fields and kinds (the builders' docstrings have the details)

**events:** the op kinds are `bool` (also `played` / `isget` / `talked` by name), `bool_array`, `exp`, `step_query`,
`enum`, `int`, `float`, `string`, `copy`, `compare`, `elapsed`, `timestamp`, `talk_flag`, `choice`, `step` (with
`step_index`, `wait_end`, `ignore_ui`), `step_rollback`, `give` / `take`, `pouch`, `can_add`, `equip`, `bottle`,
`count`, `item_info`, `played_get`, `rupees`, `time`, `age`, `warp` (`dest`), `play` and `event_bool`. A `play` op has
flag `HavePlayedEvent.<setting>` and `implicit: true`, since the engine sets that flag when a *setting* plays, not
when its entry is called as a sub-flow. Ops whose value is a caller's `<arg X>` get indexed again at each call site,
with ref = the call site, `via` = the op in the callee and guards = both. Step requests, gives and takes in entries
that other flows call carry `called_from` (the call sites with their guards). The summary adds `step_queries`,
`takes`, `warps`, `plays`, `event_bools`, `time_sets`, `timeline_calls`, `classification`, `played_flags` and
`counts`. In the summary,
`settings[name]` = `{flow, entry, file, timeline, movie, children, resident, start_flag, alias/challenge/step}`.
AISchedule EventNames are EventSetting row ids.

**logic:** the formula combinators are `AND`, `OR`, `NOT`, `LATCH(x)`, `PULSE`, `ONCE`, `ONCEIF`, `DELAY` and
`count{...}`. `LATCH(x)` is true from the first time x is true, and `LATCH(set, hold)` is for feedback loops. The
extra leaf kinds are `hit:<actor>@<areas>` (sensor observers), `arg:<Name>` (a module input), `bb:<Key>` and `game:`
(unnamed autogen data). `int:` covers compares and enums, and there are `time:day|night|A-C` and
`player:child|adult|boots=N|bag:|stock:|equip:|...` leaves. An input linked to an unflagged output reads as
`const:false` and is listed in `unflagged_reads` (vanilla has none). Writes with flag `@step:<Challenge>` are
TriggerChallengeSetStep nodes. Records also carry `commands`, `bb`, `modules`, `inputs` / `outputs` (a module's
interface), `selectors` and `deps`, and reads carry `outs` / `dead`. `kind: "schedule_pack"` is Pack/AIScheduleParam,
the per-quest-step NPC schedules `<Challenge>_<Step>_<Actor>` with `schedules: {path: schedule}`. Schedules follow
"last true wins", and the data confirms it. The summary adds `item_readers`, `player_time_gates`, `schedule_rule` and
`totals`.

**actors:** `holdup` adds `getdemo_event` (the EventPerformer AI with the item-get commands), `complete` and `proof`.
`damage` = `{life, rates, immune, exceptions, invincible, sensor, hammer, fall_break, death, chemical, breakers, how}`.
Records also have `lift` (grade None, Low = Goron Bracelet, Middle = Silver, High = Golden), `lifter`, `pouch`,
`attacks`, `gamedata_refs` and `push`. Kind `pouch_table` is UI/Pouch/PouchTable and BottleTable, and the actors
under one menu button share that slot. The summary adds `holdup_risk`, `holdup_parts`, `shared_pouch_slots`,
`breaker_notes`, `attack_model` and `bottle_contents`. A patch holding AI/, Pack/AI.Global, the death tables,
UI/Pouch or GameDataList re-indexes every pack (`REBUILD_ON`).
