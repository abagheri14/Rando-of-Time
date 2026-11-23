#!/usr/bin/env python3
"""Export OoT Randomizer logic data (reference/ootr/raw/) to normalized JSON.

Static parsing only: OoTR's Python files are read with `ast.parse` and their table
literals are evaluated by the small evaluator below. Nothing from raw/ is imported
or executed. Run with:  python -I export_ootr.py
(from any working directory; paths are resolved relative to this file).

Outputs (next to this script):
  logic.json      vanilla regions + Overworld + Bosses, locations, helpers, items, tricks
  logic_mq.json   Master Quest dungeon regions + the locations they contain
  stats.json      counts and rule-language inventory used to write summary.md
"""
import ast
import json
import os
import re
import sys
import textwrap
from collections import Counter, OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
SEM = os.path.join(RAW, 'semantics')
SOURCE = {
    'repo': 'https://github.com/OoTRandomizer/OoT-Randomizer',
    'branch': 'Dev',
    'commit': '526b4c8d81b7c4023ef4573ffbaf39344e270d5b',
    'license': 'MIT (see raw/LICENSE)',
}

caveats = []


# JSON logic files
def read_logic_file(path):
    """Same transformation as OoTR's Utils.read_logic_file: drop everything after '#'
    on each line, turn newlines into spaces, collapse runs of spaces, then strict JSON."""
    parts = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts.append(line.split('#')[0].replace('\n', ' '))
    text = re.sub(' +', ' ', ''.join(parts))
    dupes = []

    def hook(pairs):
        d = OrderedDict()
        for k, v in pairs:
            if k in d:
                dupes.append(k)
            d[k] = v
        return d

    data = json.loads(text, object_pairs_hook=hook)
    for k in dupes:
        caveats.append(f'{os.path.basename(path)}: duplicate key {k!r} (last value kept, as OoTR does)')
    return data


def clean_rule(v, where):
    if not isinstance(v, str):
        caveats.append(f'{where}: non-string rule {v!r}')
        return v
    return v.strip()


KNOWN_REGION_KEYS = {'region_name', 'scene', 'dungeon', 'hint', 'alt_hint', 'time_passes',
                     'provides_time', 'is_boss_room', 'savewarp', 'events', 'locations', 'exits'}


def norm_region(r, fname):
    out = OrderedDict()
    out['name'] = r['region_name']
    out['file'] = fname
    out['scene'] = r.get('scene')
    out['dungeon'] = r.get('dungeon')
    out['hint'] = r.get('hint')
    out['time_passes'] = bool(r.get('time_passes', False))
    for k in ('alt_hint', 'provides_time', 'is_boss_room', 'savewarp'):
        if k in r:
            out[k] = r[k]
    for sect in ('events', 'locations', 'exits'):
        out[sect] = OrderedDict((k, clean_rule(v, f'{fname}/{r["region_name"]}/{sect}/{k}'))
                                for k, v in r.get(sect, {}).items())
    extra = set(r) - KNOWN_REGION_KEYS
    for k in sorted(extra):
        out[k] = r[k]
        caveats.append(f'{fname}/{r["region_name"]}: unknown region key {k!r} copied as-is')
    return out


def load_world_dir(d):
    regions = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith('.json'):
            for r in read_logic_file(os.path.join(d, fn)):
                regions.append(norm_region(r, fn))
    return regions


# Safe literal evaluator
class Unsupported(Exception):
    pass


def lit(node, env):
    """Evaluate a literal-ish AST node without executing anything."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [lit(e, env) for e in node.elts]
    if isinstance(node, ast.Dict):
        return OrderedDict((lit(k, env), lit(v, env)) for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -lit(node.operand, env)
    if isinstance(node, ast.BinOp):
        a, b = lit(node.left, env), lit(node.right, env)
        if not (isinstance(a, int) and isinstance(b, int)):
            raise Unsupported(ast.unparse(node))
        ops = {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
               ast.BitOr: lambda: a | b, ast.LShift: lambda: a << b}
        if type(node.op) not in ops:
            raise Unsupported(ast.unparse(node))
        return ops[type(node.op)]()
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in env:
        return env[node.value.id][node.attr]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'float'
            and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).lower() in ('inf', 'infinity')):
        return 'Infinity'
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'shop_address'
            and len(node.args) == 2):
        # Re-implementation of LocationList.shop_address (not executed from the source)
        shop_id, shelf_id = lit(node.args[0], env), lit(node.args[1], env)
        return 0xC71ED0 + (0x40 * shop_id) + (0x08 * shelf_id)
    raise Unsupported(ast.unparse(node))


def lit_or_expr(node, env, where):
    try:
        return lit(node, env)
    except Unsupported as e:
        caveats.append(f'{where}: non-literal value kept as source text: {e}')
        return {'expr': str(e)}


def find_assign(tree, name):
    for st in tree.body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in st.targets):
            return st.value
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.target.id == name:
            return st.value
    raise KeyError(name)


def parse_py(path):
    with open(path, encoding='utf-8') as f:
        return ast.parse(f.read(), filename=os.path.basename(path))


# LocationList / ItemList / tricks
def to_hex(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return f'0x{v:X}'
    if isinstance(v, list):
        return [to_hex(x) for x in v]
    return v


def load_locations():
    tree = parse_py(os.path.join(RAW, 'LocationList.py'))
    call = find_assign(tree, 'location_table')
    assert isinstance(call, ast.Call) and isinstance(call.args[0], ast.List)
    table = OrderedDict()
    for elt in call.args[0].elts:
        name = lit(elt.elts[0], {})
        fields = elt.elts[1].elts
        typ, scene, default, addrs, vanilla, cats = [lit_or_expr(f, {}, f'LocationList[{name}]') for f in fields]
        if isinstance(cats, str):
            cats = [cats]
        table[name] = OrderedDict([
            ('type', typ),
            ('scene_id', scene),
            ('scene_hex', None if scene is None else f'0x{scene:02X}'),
            ('default', default),
            ('vanilla_item', vanilla),
            ('categories', cats or []),
            ('n64_rom_addresses', to_hex(addrs)),
        ])
    return table


def load_items():
    tree = parse_py(os.path.join(RAW, 'ItemList.py'))
    gi = {}
    for st in tree.body:
        if isinstance(st, ast.ClassDef) and st.name == 'GetItemId':
            for a in st.body:
                if isinstance(a, ast.Assign) and isinstance(a.value, ast.Constant):
                    gi[a.targets[0].id] = a.value.value
    env = {'GetItemId': gi}
    node = find_assign(tree, 'item_table')
    items = OrderedDict()
    for k, v in zip(node.keys, node.values):
        name = lit(k, env)
        typ, adv, gid, special = [lit_or_expr(f, env, f'ItemList[{name}]') for f in v.elts]
        items[name] = OrderedDict([('type', typ), ('advancement', adv), ('get_item_id', gid),
                                   ('special', special), ('rule_name', escape_name(name))])
    return items


def load_tricks():
    tree = parse_py(os.path.join(RAW, 'SettingsListTricks.py'))
    tricks = OrderedDict()
    for table, advanced in (('logic_tricks', False), ('advanced_logic_tricks', True)):
        try:
            node = find_assign(tree, table)
        except KeyError:
            continue
        for display, info in lit(node, {}).items():
            tricks[info['name']] = OrderedDict([
                ('display_name', display),
                ('tags', info.get('tags', [])),
                ('tooltip', textwrap.dedent(info.get('tooltip', '')).strip()),
                ('advanced_logic_only', advanced),
            ])
    return tricks


_escape = re.compile(r"['()[\]-]")


def escape_name(name):
    return _escape.sub('', name.replace(' ', '_'))


def class_member_names(path, cls, kind):
    tree = parse_py(path)
    names = set()
    for st in tree.body:
        if isinstance(st, ast.ClassDef) and st.name == cls:
            for a in st.body:
                if kind == 'def' and isinstance(a, ast.FunctionDef):
                    names.add(a.name)
                elif kind == 'attr' and isinstance(a, ast.Assign):
                    names.update(t.id for t in a.targets if isinstance(t, ast.Name))
                elif kind == 'attr' and isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name):
                    names.add(a.target.id)
    return names


# Area inference
def infer_areas(regions):
    """Give each region an 'area': its dungeon, else its hint area, else the nearest
    hint area found by walking incoming exits backwards (how interiors get grouped)."""
    by_name = {r['name']: r for r in regions}
    incoming = defaultdict(list)
    for r in regions:
        for tgt in r['exits']:
            incoming[tgt].append(r['name'])
    skip = {'Root', 'Root Exits'}

    def own(r):
        if r.get('dungeon'):
            return r['dungeon']
        if r.get('hint') and r['hint'] != 'ROOT':
            return r['hint']
        return None

    for r in regions:
        a = own(r)
        if a:
            r['area'] = a
            continue
        seen, frontier, found = {r['name']}, [r['name']], None
        while frontier and not found:
            nxt = []
            for n in frontier:
                for src in incoming.get(n, []):
                    if src in seen or src in skip or src not in by_name:
                        continue
                    seen.add(src)
                    if own(by_name[src]):
                        found = found or own(by_name[src])
                    nxt.append(src)
            frontier = nxt
        r['area'] = found or ('ROOT' if r['name'] in skip or 'Warp' in r['name'] or 'Spawn' in r['name'] else None)
        r['area_inferred'] = True


# Rule inventory
PARSER_BUILTINS = {'at', 'here', 'at_day', 'at_night', 'at_dampe_time'}
KWARGS = {'age', 'spot', 'tod'}


class Inventory:
    def __init__(self, ctx):
        self.ctx = ctx
        self.c = defaultdict(Counter)
        self.errors = []
        self.compares = Counter()
        self.at_regions = Counter()

    def classify_name(self, n):
        ctx = self.ctx
        if n in ('True', 'False', 'None'):
            return 'constant'
        if n in PARSER_BUILTINS:
            return 'parser_builtin'
        if n in ctx['helpers']:
            return 'helper'
        if n in ctx['tricks']:
            return 'trick'
        if n in ctx['settings']:
            return 'setting'
        if n in ctx['world_attrs']:
            return 'world_attribute'
        if n in ctx['event_items'] or n in ctx['events']:
            return 'event'
        if n in ctx['items']:
            return 'item'
        if n in ctx['state_methods']:
            return 'state_method'
        if n in KWARGS or n == 'TimeOfDay':
            return 'eval_kwarg'
        if re.match(r'[A-Z]\w+', n):
            return 'event_undeclared'
        return 'unknown'

    def classify_string(self, s):
        esc = escape_name(s)
        if s in self.ctx['region_names']:
            return 'region'
        if esc in self.ctx['events'] or esc in self.ctx['event_items']:
            return 'event'
        if esc in self.ctx['items']:
            return 'item'
        return 'setting_value_or_other'

    def add(self, rule, where, params=()):
        try:
            tree = ast.parse(rule, mode='eval')
        except SyntaxError as e:
            self.errors.append(f'{where}: {e.msg}: {rule!r}')
            return
        call_funcs, special = set(), {}
        for node in ast.walk(tree):
            # names that RuleParser treats as plain symbols rather than lookups
            if isinstance(node, ast.Subscript):
                for n in ast.walk(node.slice):
                    if isinstance(n, ast.Name):
                        special[id(n)] = 'subscript_key'
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id not in PARSER_BUILTINS):
                kind = ('helper_call_symbol_arg' if node.func.id in self.ctx['helper_funcs']
                        else 'state_call_symbol_arg')
                for a in node.args:
                    if (isinstance(a, ast.Name) and a.id not in self.ctx['items']
                            and a.id not in self.ctx['helpers'] and a.id not in self.ctx['settings']
                            and a.id not in self.ctx['world_attrs'] and a.id not in params):
                        special[id(a)] = kind
            if isinstance(node, ast.Compare) and params:
                sides = [node.left] + list(node.comparators)
                if any(isinstance(s, ast.Name) and s.id in params for s in sides):
                    for s in sides:
                        if isinstance(s, ast.Name) and s.id not in params and s.id not in self.ctx['settings']:
                            special[id(s)] = 'param_compare_symbol'
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                call_funcs.add(id(node.func))
                f = node.func.id
                if f in PARSER_BUILTINS:
                    kind = 'parser_builtin'
                elif f in self.ctx['helper_funcs']:
                    kind = 'helper_func'
                elif f in self.ctx['state_methods']:
                    kind = 'state_method'
                else:
                    kind = 'unknown_func'
                self.c['call:' + kind][f] += 1
                if f == 'at' and node.args and isinstance(node.args[0], ast.Constant):
                    self.at_regions[node.args[0].value] += 1
            elif isinstance(node, ast.Compare):
                left = ast.unparse(node.left)
                for op, comp in zip(node.ops, node.comparators):
                    self.compares[f'{left} {type(op).__name__} {ast.unparse(comp)}'] += 1
                self.c['syntax']['compare:' + ','.join(type(o).__name__ for o in node.ops)] += 1
            elif isinstance(node, ast.Tuple):
                self.c['syntax']['tuple (item, count)'] += 1
            elif isinstance(node, ast.Subscript):
                self.c['syntax']['subscript'] += 1
                self.c['subscript'][ast.unparse(node)] += 1
            elif isinstance(node, ast.BinOp):
                self.c['syntax']['binop:' + type(node.op).__name__] += 1
            elif isinstance(node, ast.UnaryOp):
                self.c['syntax']['unary:' + type(node.op).__name__] += 1
            elif isinstance(node, ast.BoolOp):
                self.c['syntax']['bool:' + type(node.op).__name__] += 1
            elif isinstance(node, ast.IfExp):
                self.c['syntax']['ifexp'] += 1
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.c['string:' + self.classify_string(node.value)][node.value] += 1
            elif isinstance(node, (ast.Attribute, ast.Lambda, ast.ListComp, ast.GeneratorExp, ast.Starred)):
                self.c['syntax']['other:' + type(node).__name__] += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and id(node) not in call_funcs:
                if node.id in params:
                    continue
                kind = special.get(id(node)) or self.classify_name(node.id)
                self.c['name:' + kind][node.id] += 1


def main():
    vanilla = load_world_dir(os.path.join(RAW, 'World'))
    mq = load_world_dir(os.path.join(RAW, 'World_MQ'))
    helpers = read_logic_file(os.path.join(RAW, 'LogicHelpers.json'))
    loc_table = load_locations()
    items = load_items()
    tricks = load_tricks()
    settings = class_member_names(os.path.join(SEM, 'SettingsList.py'), 'SettingInfos', 'attr')
    state_methods = class_member_names(os.path.join(SEM, 'State.py'), 'State', 'def')

    infer_areas(vanilla)
    infer_areas(mq + [r for r in vanilla if r['file'] in ('Overworld.json', 'Bosses.json')])

    # ---- join locations with regions
    where_v, where_mq = defaultdict(list), defaultdict(list)
    for r in vanilla:
        for loc in r['locations']:
            where_v[loc].append(r)
    for r in mq:
        for loc in r['locations']:
            where_mq[loc].append(r)
    for name in list(where_v) + list(where_mq):
        if name not in loc_table:
            caveats.append(f'world location {name!r} has no LocationList entry')

    def loc_entry(name, where):
        e = OrderedDict(loc_table[name])
        rs = where.get(name, [])
        e['regions'] = [r['name'] for r in rs]
        e['region'] = rs[0]['name'] if len(rs) == 1 else None
        areas = sorted({r.get('area') or '?' for r in rs})
        e['area'] = areas[0] if len(areas) == 1 else (areas or None)
        e['logic_file'] = rs[0]['file'] if rs else None
        return e

    locations_v, locations_mq = OrderedDict(), OrderedDict()
    for name in loc_table:
        if name in where_mq:
            locations_mq[name] = loc_entry(name, where_mq)
        if name in where_v or name not in where_mq:
            locations_v[name] = loc_entry(name, where_v)

    # ---- sanity: exit targets / at() targets / savewarps
    all_names = {r['name'] for r in vanilla} | {r['name'] for r in mq}
    for r in vanilla + mq:
        for tgt in r['exits']:
            if tgt not in all_names:
                caveats.append(f'{r["file"]}/{r["name"]}: exit target {tgt!r} is not a region')

    # ---- rule inventory
    helper_funcs, helper_names, helper_params = set(), set(), set()
    for k in helpers:
        if '(' in k:
            fn, args = k[:-1].split('(', 1)
            helper_funcs.add(fn)
            helper_params.update(a.strip() for a in args.split(','))
        else:
            helper_names.add(k)
    events = set()
    for r in vanilla + mq:
        for ev in r['events']:
            events.add(escape_name(ev))
    world_attrs = set()
    for node in ast.walk(parse_py(os.path.join(SEM, 'World.py'))):
        tgt = node.target if isinstance(node, ast.AnnAssign) else None
        tgts = node.targets if isinstance(node, ast.Assign) else ([tgt] if tgt is not None else [])
        for t in tgts:
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                world_attrs.add(t.attr)
    ctx = dict(helpers=helper_names, helper_funcs=helper_funcs,
               tricks=set(tricks), settings=settings, world_attrs=world_attrs - settings,
               items={i['rule_name'] for i in items.values()},
               event_items={i['rule_name'] for i in items.values() if i['type'] == 'Event'},
               events=events, state_methods=state_methods, region_names=all_names)

    stats = OrderedDict()
    for label, regs in (('vanilla', vanilla), ('mq', mq)):
        inv = Inventory(ctx)
        n = 0
        for r in regs:
            for sect in ('events', 'locations', 'exits'):
                for k, rule in r[sect].items():
                    inv.add(rule, f'{r["file"]}/{r["name"]}/{sect}/{k}')
                    n += 1
        stats[label] = dict(rule_count=n, inv=inv)
    inv_h = Inventory(ctx)
    for k, rule in helpers.items():
        params = ()
        if '(' in k:
            params = tuple(a.strip() for a in k[:-1].split('(', 1)[1].split(','))
        inv_h.add(rule, f'LogicHelpers/{k}', params)
    stats['helpers'] = dict(rule_count=len(helpers), inv=inv_h)
    for label in stats:
        caveats.extend(stats[label]['inv'].errors)
    for label in ('vanilla', 'mq'):
        for reg in stats[label]['inv'].at_regions:
            if reg not in all_names:
                caveats.append(f'at() target {reg!r} ({label}) is not a region')

    # ---- outputs
    def dump(path, obj):
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
            f.write('\n')

    notes = [
        'Rule strings are OoTR\'s, unchanged except that comments were dropped and whitespace '
        'collapsed exactly as OoTR\'s own loader (Utils.read_logic_file) does, then trimmed.',
        'Rule language = a Python expression subset interpreted by raw/semantics/RuleParser.py.',
        'locations[*].default: chest/collectible flag, or (room, scene setup, actor index) tuples '
        'for pots/crates/freestanding/wonderitems; meaning depends on type (see LocationList.py header).',
        'locations[*].n64_rom_addresses are N64 ROM offsets (useless for the remake; kept for completeness).',
        'regions[*].area is the dungeon, else the hint area, else (area_inferred) the nearest hint area '
        'reached by walking incoming exits backwards.',
    ]
    dump(os.path.join(HERE, 'logic.json'), OrderedDict([
        ('source', SOURCE), ('notes', notes),
        ('regions', vanilla), ('locations', locations_v), ('helpers', helpers),
        ('items', items), ('tricks', tricks),
    ]))
    dump(os.path.join(HERE, 'logic_mq.json'), OrderedDict([
        ('source', SOURCE),
        ('notes', notes + ['MQ dungeons only. Combine with Overworld/Bosses regions, helpers, items '
                           'and tricks from logic.json.']),
        ('regions', mq), ('locations', locations_mq),
    ]))

    # ---- stats for summary.md
    ITEMLESS = {'Event', 'Drop', 'Hint', 'HintStone'}
    out = OrderedDict()
    out['type_all'] = Counter(e['type'] for e in loc_table.values())
    out['type_vanilla_logic'] = Counter(loc_table[n]['type'] for n in where_v if n in loc_table)
    out['type_mq_logic'] = Counter(loc_table[n]['type'] for n in where_mq if n in loc_table)
    out['not_in_any_world_file'] = sorted((loc_table[n]['type'], n) for n in loc_table
                                          if n not in where_v and n not in where_mq)
    area_type = defaultdict(Counter)
    for n, rs in where_v.items():
        if n not in loc_table or loc_table[n]['type'] in ITEMLESS:
            continue
        area = rs[0].get('area') or '?'
        area_type[area][loc_table[n]['type']] += 1
    out['area_type_vanilla'] = {a: dict(c) for a, c in area_type.items()}
    mq_area_type = defaultdict(Counter)
    for n, rs in where_mq.items():
        if n not in loc_table or loc_table[n]['type'] in ITEMLESS:
            continue
        mq_area_type[rs[0].get('area') or '?'][loc_table[n]['type']] += 1
    out['area_type_mq'] = {a: dict(c) for a, c in mq_area_type.items()}
    cat = Counter()
    for n in where_v:
        if n in loc_table:
            cat.update(loc_table[n]['categories'])
    out['categories_vanilla'] = cat
    out['multi_region_locations'] = {n: [r['name'] for r in rs] for n, rs in where_v.items() if len(rs) > 1}
    out['regions'] = {'vanilla': len(vanilla), 'mq': len(mq)}
    out['helpers'] = len(helpers)
    out['tricks_total'] = len(tricks)
    out['tricks_advanced_only'] = sum(1 for t in tricks.values() if t['advanced_logic_only'])
    for label in ('vanilla', 'mq', 'helpers'):
        inv = stats[label]['inv']
        out['rules_' + label] = OrderedDict(
            count=stats[label]['rule_count'],
            **{k: dict(v.most_common()) for k, v in sorted(inv.c.items())},
            compares=dict(inv.compares.most_common()),
            at_regions=dict(inv.at_regions.most_common()),
        )
    out['time_passes_regions'] = [r['name'] for r in vanilla if r['time_passes']]
    out['provides_time_regions'] = {r['name']: r['provides_time'] for r in vanilla + mq if 'provides_time' in r}
    out['unassigned_area_regions'] = [r['name'] for r in vanilla + mq if not r.get('area')]
    out['caveats'] = caveats
    dump(os.path.join(HERE, 'stats.json'), out)

    print(f'vanilla regions {len(vanilla)}, mq regions {len(mq)}, locations {len(loc_table)}, '
          f'logic.json locations {len(locations_v)}, logic_mq.json locations {len(locations_mq)}, '
          f'helpers {len(helpers)}, items {len(items)}, tricks {len(tricks)}, caveats {len(caveats)}')
    for c in caveats:
        print('CAVEAT', c)


if __name__ == '__main__':
    main()
