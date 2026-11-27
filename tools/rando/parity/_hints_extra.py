"""Hints beyond OoT Randomizer's (Ship of Harkinian's static hints, the 3DS randomizer's fishing hint) for the hints
plugin (hints.py, remake setting remake_extra_hints). Each hint is a page added to (or written into) a line the NPC
says anyway, naming an item and where it is, in every language. The sentence frames below are translated for every
language the game ships, and the item and place names are the game's own (PouchContent and LocationMsg names, per
language, from data/rando/hints_messages.json). The targets and their vanilla text are in
data/rando/hints_extra.json (built by `python tools/rando/parity/_hints_extra.py ROMFS`).

Modes:
- "append" adds the hint page after the vanilla pages.
- "prepend" puts it first (for choice prompts, so the choice stays on the last page).
- "replace" writes the whole message. That's for lines that name the vanilla prize in fixed text, which would be
  wrong once the prize is shuffled.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(HERE, "data", "rando", "hints_extra.json")
HI, LO = "{tag:0,3,0000}", "{tag:0,3,ffff}"
PAGE = "{tag:0,4}"

# hint -> the vanilla lines it goes on: (file, label, mode)
TARGETS = {
    "mido": [("EventFlowMsg/Npc_Kokiri_Mido_Child.msbt", lb, "append")
             for lb in ("Talk_20", "Talk_03", "Talk_09", "Talk_18", "Talk_19")],
    "saria": [("EventFlowMsg/Dm_SY_Ocarina.msbt", "Talk_10", "append"),
              ("EventFlowMsg/Npc_Kokiri_Saria_Child_SacredForestMeadow.msbt", "Talk_004", "append")],
    "sheik": [("EventFlowMsg/Npc_Hylia_Sheik_Adult.msbt", lb, "append") for lb in ("Talk_00", "Talk_01", "Talk_02",
                                                                                 "Talk_03")],
    "biggoron": [("EventFlowMsg/Npc_Goron_Biggoron_Adult.msbt", lb, "append") for lb in ("Talk_16", "Talk_17",
                                                                                       "Talk_12")],
    "malon": [("EventFlowMsg/MiniGame_HorseRace.msbt", lb, "append") for lb in ("Talk_14", "Talk_52")],
    "anju": [("EventFlowMsg/Npc_Hylia_049_Child.msbt", lb, "replace") for lb in ("Talk_21", "Talk_12")],
    "archery": [("EventFlowMsg/Npc_Gerudo_008.msbt", "Talk_16", "replace"),
                ("EventFlowMsg/Npc_Gerudo_008.msbt", "Talk_17", "replace")],
    "fishing": [("EventFlowMsg/MiniGame_Fishing.msbt", "Talk_153", "replace"),
                ("EventFlowMsg/MiniGame_Fishing.msbt", "Talk_154", "replace")],
    "merchants": [("EventFlowMsg/Npc_Goron_Medigoron_Adult.msbt", lb, "append") for lb in ("Talk_01", "Talk_09",
                                                                                         "Talk_17")]
                 + [("EventFlowMsg/Npc_Hylia_053_Adult.msbt", "Talk_101", "replace"),
                    ("EventFlowMsg/Npc_Hylia_047_Child.msbt", "Talk_00", "append")],
}
# hints that are already OoTR misc hints (hints.py writes them). remake_extra_hints turns them on without misc_hints.
MISC_ALIASES = {"poe_collector": "big_poes", "skulltula_100": "100_skulltulas", "carpet_merchant": "unique_merchants"}
HINTS = sorted(set(TARGETS) | set(MISC_ALIASES) | {"fishing_pole"})

# language archive -> sentence-frame key
LANG = {"USen": "en", "EUen": "en", "EUde": "de", "EUes": "es", "USes": "es", "EUfr": "fr", "USfr": "fr", "EUit": "it",
        "EUnl": "nl", "EUpl": "pl", "EUru": "ru", "USpt": "pt", "JPja": "ja", "KRko": "ko", "CNzh": "zh_cn",
        "TWzh": "zh_tw"}
CJK = ("ja", "ko", "zh_cn", "zh_tw")
# where an item is: {item} and {area} are highlighted names
WHERE = {
    "en": "{item}...\nyou'll find it here: {area}.",
    "de": "{item}...\ndas findest du hier: {area}.",
    "fr": "{item}...\nça se trouve ici : {area}.",
    "es": "{item}...\nse encuentra aquí: {area}.",
    "it": "{item}...\nsi trova qui: {area}.",
    "nl": "{item}...\ndat vind je hier: {area}.",
    "pt": "{item}...\nfica aqui: {area}.",
    "pl": "{item}...\nznajdziesz to tutaj: {area}.",
    "ru": "{item}...\nэто можно найти здесь: {area}.",
    "ja": "{item}は\n{area}に あるらしいよ。",
    "ko": "{item}은(는)\n{area}에 있대.",
    "zh_cn": "听说{item}\n在{area}。",
    "zh_tw": "聽說{item}\n在{area}。",
}
# what a task gives: {what} is a plain phrase (below), {item} highlighted
REWARD = {
    "en": "{what}...\nthe reward: {item}!",
    "de": "{what}...\ndie Belohnung: {item}!",
    "fr": "{what}...\nla récompense : {item} !",
    "es": "{what}...\nla recompensa: ¡{item}!",
    "it": "{what}...\nla ricompensa: {item}!",
    "nl": "{what}...\nde beloning: {item}!",
    "pt": "{what}...\na recompensa: {item}!",
    "pl": "{what}...\nnagroda: {item}!",
    "ru": "{what}...\nнаграда: {item}!",
    "ja": "{what}…\nごほうびは {item}！",
    "ko": "{what}…\n보상은 {item}!",
    "zh_cn": "{what}……\n奖励是{item}！",
    "zh_tw": "{what}……\n獎勵是{item}！",
}
# Granny's offer is a choice prompt we rewrite whole, since her vanilla "ultimate potion" would be wrong once her item
# is shuffled. The price is the 100 rupees her shuffled sale takes (songs_trade.py).
SPECIAL_PRICE = {
    "en": "Today's special: {item}!\nIt's yours for 100 rupees.",
    "de": "Heutiges Angebot: {item}!\nFür 100 Rubine gehört es dir.",
    "fr": "L'offre du jour : {item} !\nC'est à toi pour 100 rubis.",
    "es": "La oferta de hoy: ¡{item}!\nEs tuyo por 100 rupias.",
    "it": "L'offerta di oggi: {item}!\nÈ tuo per 100 rupie.",
    "nl": "Aanbieding van vandaag: {item}!\nVoor 100 rupees is het van jou.",
    "pt": "A oferta de hoje: {item}!\nÉ seu por 100 rupias.",
    "pl": "Dzisiejsza oferta: {item}!\nTwoje za 100 rupii.",
    "ru": "Сегодня в продаже: {item}!\nОтдам за 100 рупий.",
    "ja": "本日の 品物: {item}！\n100ルピーで どうだい？",
    "ko": "오늘의 상품: {item}!\n100루피에 어때?",
    "zh_cn": "今日商品：{item}！\n100卢比卖给你吧？",
    "zh_tw": "今日商品：{item}！\n100盧比賣給你吧？",
}
SPECIAL = {
    "en": "Today's special:\n{item}!", "de": "Heutiges Angebot:\n{item}!", "fr": "L'offre du jour :\n{item} !",
    "es": "La oferta de hoy:\n¡{item}!", "it": "L'offerta di oggi:\n{item}!", "nl": "Aanbieding van vandaag:\n{item}!",
    "pt": "A oferta de hoje:\n{item}!", "pl": "Dzisiejsza oferta:\n{item}!", "ru": "Сегодня в продаже:\n{item}!",
    "ja": "本日の 品物:\n{item}！", "ko": "오늘의 상품:\n{item}!", "zh_cn": "今日商品：\n{item}！",
    "zh_tw": "今日商品：\n{item}！",
}
WHAT = {
    "claim_check": None,  # the game's own name of the Claim Check (PouchContent Item_ClaimCheck_Name)
    "obstacle_course": {
        "en": "A new obstacle course record", "de": "Ein neuer Rekord im Hindernisparcours",
        "fr": "Un nouveau record du parcours d'obstacles", "es": "Un nuevo récord en la carrera de obstáculos",
        "it": "Un nuovo record nel percorso a ostacoli", "nl": "Een nieuw record op de hindernisbaan",
        "pt": "Um novo recorde na pista de obstáculos", "pl": "Nowy rekord toru przeszkód",
        "ru": "Новый рекорд на полосе препятствий", "ja": "障害物レースの 新記録", "ko": "장애물 코스 신기록",
        "zh_cn": "障碍赛的新纪录", "zh_tw": "障礙賽的新紀錄"},
    "cuccos": {
        "en": "All seven cuccos back in the pen", "de": "Alle sieben Hühner zurück im Gehege",
        "fr": "Les sept cocottes ramenées", "es": "Los siete cucos de vuelta", "it": "Tutte e sette le galline",
        "nl": "Alle zeven kippen terug", "pt": "As sete galinhas de volta", "pl": "Wszystkie siedem kur",
        "ru": "Все семь кур", "ja": "コッコ 7羽", "ko": "꼬꼬 일곱 마리", "zh_cn": "七只咕咕鸡",
        "zh_tw": "七隻咕咕雞"},
    "points_750": {
        "en": "750 points", "de": "750 Punkte", "fr": "750 points", "es": "750 puntos", "it": "750 punti",
        "nl": "750 punten", "pt": "750 pontos", "pl": "750 punktów", "ru": "750 очков", "ja": "750点",
        "ko": "750점", "zh_cn": "750分", "zh_tw": "750分"},
    "points_1400": {
        "en": "1,400 points", "de": "1.400 Punkte", "fr": "1 400 points", "es": "1.400 puntos", "it": "1.400 punti",
        "nl": "1.400 punten", "pt": "1.400 pontos", "pl": "1400 punktów", "ru": "1400 очков", "ja": "1400点",
        "ko": "1,400점", "zh_cn": "1400分", "zh_tw": "1400分"},
    "fishing_prize": {
        "en": "A big enough fish", "de": "Ein großer Fisch", "fr": "Un poisson assez gros", "es": "Un pez bien grande",
        "it": "Un pesce abbastanza grande", "nl": "Een flinke vis", "pt": "Um peixe grande o bastante",
        "pl": "Wystarczająco duża ryba", "ru": "Достаточно большая рыба", "ja": "大物の 魚", "ko": "큰 물고기",
        "zh_cn": "够大的鱼", "zh_tw": "夠大的魚"},
    "ocarina_gift": {
        "en": "Zelda's gift by the castle moat", "de": "Zeldas Geschenk am Burggraben",
        "fr": "Le cadeau de Zelda près des douves", "es": "El regalo de Zelda junto al foso",
        "it": "Il dono di Zelda al fossato", "nl": "Zelda's geschenk bij de slotgracht",
        "pt": "O presente de Zelda junto ao fosso", "pl": "Dar Zeldy przy fosie", "ru": "Дар Зельды у рва",
        "ja": "お堀での ゼルダの 贈り物", "ko": "해자에서 젤다가 주는 선물", "zh_cn": "护城河边塞尔达的礼物",
        "zh_tw": "護城河邊薩爾達的禮物"},
    "ocarina_song": {
        "en": "The song by the castle moat", "de": "Das Lied am Burggraben", "fr": "La mélodie près des douves",
        "es": "La canción junto al foso", "it": "La melodia del fossato", "nl": "Het lied bij de slotgracht",
        "pt": "A canção junto ao fosso", "pl": "Melodia przy fosie", "ru": "Мелодия у рва",
        "ja": "お堀で 教わる 曲", "ko": "해자에서 배우는 노래", "zh_cn": "护城河边的乐曲", "zh_tw": "護城河邊的樂曲"},
}
ICE_TRAP = {"en": "Ice Trap", "de": "Eisfalle", "fr": "Piège de glace", "es": "Trampa de hielo",
            "it": "Trappola di ghiaccio", "nl": "IJsval", "pt": "Armadilha de gelo", "pl": "Lodowa pułapka",
            "ru": "Ледяная ловушка", "ja": "氷のワナ", "ko": "얼음 함정", "zh_cn": "冰冻陷阱", "zh_tw": "冰凍陷阱"}
DUNGEON_AREA = {"Deku Tree": "DEKU_TREE", "Dodongos Cavern": "DODONGOS_CAVERN", "Jabu Jabus Belly": "JABU_JABUS_BELLY",
                "Forest Temple": "FOREST_TEMPLE", "Fire Temple": "FIRE_TEMPLE", "Water Temple": "WATER_TEMPLE",
                "Shadow Temple": "SHADOW_TEMPLE", "Spirit Temple": "SPIRIT_TEMPLE",
                "Bottom of the Well": "BOTTOM_OF_THE_WELL", "Ice Cavern": "ICE_CAVERN",
                "Gerudo Training Ground": "GERUDO_TRAINING_GROUND", "Ganons Castle": "INSIDE_GANONS_CASTLE",
                "Thieves Hideout": "THIEVES_HIDEOUT", "Treasure Chest Game": "MARKET"}

_cache = {}


def _load(path):
    if path not in _cache:
        _cache[path] = json.load(open(path, encoding="utf-8"))
    return _cache[path]


def _names(lang):
    return _load(os.path.join(HERE, "data", "rando", "hints_messages.json"))["names"][lang]


def _areas():
    return _load(os.path.join(HERE, "data", "rando", "hints_names.json"))["areas"]


def vanilla(file, label):
    key = f"{file}:{label}"
    msgs = _load(DATA)["messages"]
    if key not in msgs:
        raise KeyError(f"{key} is not in data/rando/hints_extra.json: run tools/rando/parity/_hints_extra.py ROMFS")
    return msgs[key]


# Names
def actor_of(item):
    """The remake actor the player is given for OoTR item `item` (what the hint should name), or None."""
    if item is None:
        return None
    prog = _load(os.path.join(HERE, "config", "progressive.json"))["items"]
    if item in prog:
        return prog[item]["tiers"][0]
    im = _load(os.path.join(HERE, "config", "item_map.json"))
    if item in im["items"]:
        return im["items"][item]
    fixes = {"Fishing Pole": "Item_FishingRod", "Master Sword": "Weapon_Sword_Master",
             "Broken Sword": "Item_BrokenSword"}
    if item in fixes:
        return fixes[item]
    return im["junk_for"].get(item)


def item_name(item, ui_lang):
    """The game's own name for what the player gets, in `ui_lang` (archive name, e.g. EUde)."""
    key = LANG[ui_lang]
    if item == "Ice Trap":
        return ICE_TRAP[key]
    m = re.fullmatch(r"(Small Key|Boss Key|Map|Compass|Small Key Ring) \((.+)\)", item or "")
    actor = actor_of(item)
    names = dict(_names(ui_lang)["item"])
    names.update({k: v for k, v in _load(DATA).get("item_names", {}).get(ui_lang, {}).items() if _plain(v)})
    name = None
    pouch = _load(os.path.join(HERE, "data", "rando", "pouch_actors.json"))["actors"].get(actor or "", [None])[0]
    mask = "Armor_Child_" + actor[5:] if (actor or "").startswith("Item_Mask_") else None
    for a in (actor, (actor or "").replace("TBox_", "Obj_"), (actor or "").replace("TBox_", "Item_"), pouch, mask):
        if a and _plain(names.get(a)):
            name = names[a]
            break
    if name is None:
        name = item
    name = _plain(name)
    if m and m.group(2) in DUNGEON_AREA:
        place = area_name(DUNGEON_AREA[m.group(2)], ui_lang)
        if place:
            name = f"{name} ({place})"
    return name


def area_name(hint_area_name, ui_lang):
    label = _areas().get(hint_area_name)
    if label is None:
        return None
    return _plain(_names(ui_lang)["location"].get(label) or "") or None


def location_area(world, location_name, ui_lang):
    from Hints import HintArea
    loc = world.get_location(location_name)
    area = HintArea.at(loc)
    name = area_name(area.name, ui_lang)
    if name:
        return name
    return area.text(world.language, True).replace("#", "")


def _declined(m):
    """{tag:201,10,HEX} holds a name in every grammatical case (Polish), each as a u16 byte count and UTF-8 text. The
    first one is the nominative."""
    raw = bytes.fromhex(m.group(1))
    n = int.from_bytes(raw[:2], "little")
    return raw[2:2 + n].decode("utf-8", "replace")


def _plain(s):
    """A name as plain text. A declined name gives its nominative, and gender and article tags ({tag:201,...}) and other
    tags are dropped."""
    s = re.sub(r"\{tag:201,10,([0-9a-f]+)\}", _declined, s or "")
    return re.sub(r"\{tag:[^}]*\}", "", s).strip()


# Text
def _width(s):
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _wrap_line(words_line, key, limit=46):
    """Word wrap (CJK: by character) to a display width; highlighted names (\x01..\x02) never split."""
    out, cur = [], ""
    if key in CJK:
        tokens = re.findall(r"\x01[^\x02]*\x02|.", words_line)
    else:
        tokens = re.findall(r"\x01[^\x02]*\x02|\S+|\s+", words_line)
    for t in tokens:
        if not cur and t.isspace():
            continue
        if cur and _width((cur + t).replace("\x01", "").replace("\x02", "")) > limit and not t.isspace():
            out.append(cur.rstrip())
            cur = t
        else:
            cur += t
    if cur.strip():
        out.append(cur.rstrip())
    return out


def page_markup(text, key):
    """Frame text with \x01name\x02 marks -> pages of at most 3 lines, names highlighted."""
    lines = []
    for part in text.split("\n"):
        lines += _wrap_line(part, key)
    pages = [lines[i:i + 3] for i in range(0, len(lines), 3)]
    mk = PAGE.join("\n".join(p) for p in pages)
    return mk.replace("\x01", HI).replace("\x02", LO)


def where_text(item, area, ui_lang):
    key = LANG[ui_lang]
    return WHERE[key].format(item=f"\x01{item}\x02", area=f"\x01{area}\x02")


def reward_text(what_key, item, ui_lang, what=None):
    key = LANG[ui_lang]
    w = what if what is not None else WHAT[what_key][key]
    return REWARD[key].format(what=w, item=f"\x01{item}\x02")


def special_text(item, ui_lang, price=False):
    return (SPECIAL_PRICE if price else SPECIAL)[LANG[ui_lang]].format(item=f"\x01{item}\x02")


def _lead(markup):
    """The speaker style and voice tags ({tag:3,...}, {tag:4,...}) before a message's first text. Furigana, colour
    and other tags there belong to the vanilla words and are dropped."""
    m = re.match(r"(\{tag:[^}]*\})*", markup)
    return "".join(t for t in re.findall(r"\{tag:[^}]*\}", m.group(0) if m else "")
                   if t.startswith(("{tag:3,", "{tag:4,")))


def message_ops(file, label, mode, frames_for, note):
    """Text ops for one message in every language. frames_for(lang) -> [frame text, ...] (one page set each)."""
    ops = []
    for lang, markup in sorted(vanilla(file, label).items()):
        key = LANG[lang]
        new = PAGE.join(page_markup(t, key) for t in frames_for(lang))
        lead = _lead(markup)
        if mode == "append":
            full = markup + PAGE + new
        elif mode == "prepend":
            full = lead + new + PAGE + markup[len(lead):]
        else:
            full = lead + new
        plain = re.sub(r"\{tag:0,4\}", "\n", full)
        plain = re.sub(r"\{tag:[^}]*\}", "", plain)
        ops.append({"lang": lang, "file": file, "label": label, "markup": full, "text": plain, "note": note})
    return ops


# Build
def build(romfs):
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import msbt
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    wanted = sorted({(f, lb) for ts in TARGETS.values() for f, lb, _m in ts})
    messages = {}
    choices = {}
    item_names = {}
    for lang in msbt.archives(romfs):
        if lang not in LANG:
            raise SystemExit(f"{lang}: no sentence frames for this language")
        files = msbt.read_archive(fs, lang)
        pc = msbt.Msbt(files["ActorMsg/PouchContent.msbt"])
        # item names with their tags (declined Polish names, gender tags): _plain reads the nominative
        item_names[lang] = {k[:-5]: pc.markup(k) for k in pc.labels if k.endswith("_Name")}
        for f, lb in wanted:
            m = msbt.Msbt(files[f])
            if lb not in m.labels:
                raise SystemExit(f"{lang}: no message {f}:{lb}")
            messages.setdefault(f"{f}:{lb}", {})[lang] = m.markup(lb)
    # hint pages only get appended when the line is never used as a choice prompt
    from evfl import Evfl
    shown = {}
    d = os.path.join(romfs, "Event", "EventFlow")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bfevfl.zs"):
            continue
        ev = Evfl(fs.read("Event/EventFlow/" + fn))
        for fc in ev.flowcharts:
            for e in fc["events"]:
                items = ((e.get("params") or {}).get("items") or {})
                for pname, pv in items.items():
                    mid = (pv or {}).get("value")
                    if not (pname.startswith("MessageId") and isinstance(mid, str)
                            and mid.startswith("EventFlowMsg/")):
                        continue
                    # the talk step's own choices. A message handed to a sub-entry counts as no choice, like the bean
                    # salesman's SellBeans MessageId_01, which a talk with ChoiceNumber 0 shows there.
                    n = (items.get("ChoiceNumber") or {}).get("value") or 0 if pname == "MessageId" else 0
                    shown.setdefault(mid, set()).add((fn, e["name"], n))
    for ts in TARGETS.values():
        for f, lb, mode in ts:
            key = f"{f[:-5]}:{lb}"
            uses = shown.get(key, set())
            if not uses:
                raise SystemExit(f"{key}: no flow step shows it")
            if mode == "append" and any(n for _f, _e, n in uses):
                # the choice comes after the last page, so a choice prompt takes a page in front, or a rewrite that
                # ends with the offer itself (Granny's)
                raise SystemExit(f"{key}: shown as a choice prompt ({sorted(uses)}); a page can only go first")
            choices[key] = sorted(f"{a}:{b}" for a, b, _n in uses)
    out = {"_about": "Vanilla text of every line remake_extra_hints writes (tools/rando/parity/_hints_extra.py, "
                     "built from the game files with ./original copies winning), per language.",
           "messages": messages, "shown_by": choices, "item_names": item_names}
    json.dump(out, open(DATA, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(messages)} messages x {len(next(iter(messages.values())))} languages -> {os.path.relpath(DATA, HERE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
