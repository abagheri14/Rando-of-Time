"""Archipelago: the text box a location shows when it holds another player's item. It's a helper of
tools/rando/parity/archipelago.py (data/archipelago/MAILBOX.md "What the player sees").

usage: python tools/rando/parity/_archipelago_text.py --show ITEM PLAYER   each language's text, as markup
       python tools/rando/parity/_archipelago_text.py --fonts [ROMFS]      prints GLYPHS, rebuilt from the game's fonts

found_ops(label, item, player): make_patch "text" ops that add a new label to EventFlowMsg/Dm_SY_Get.msbt in every
language, "You found <item> for <player>!" translated, with the item in the game's key-word highlight (like the ice
trap's FOOL, _chests_scenes.FOOL_MARKUP). generic_ops(label): "You found an item for another world!" (no names).
Names come from other games and can be any Unicode. safe_name makes them showable, then they go in verbatim. No
game files are needed.

Languages (LANGS): there's one text archive per language, Mals/<Lang>.Product.110.sarc.zs (tools/msbt.py
archives). A text op's "lang" is that prefix, and make_patch expands "*" to every archive it finds. These ops name
their language, since each has its own translation, which follows that language's own get messages (PouchContent
Armor_Adult_Gauntlet_Gold_GetMessage: "Du hast die Goldhandschuhe gefunden!", "Vous avez trouvé les gantelets d'or !",
"Znalazłeś złote rękawice!", "Вы нашли золотые перчатки!", "金のグローブを見つけた！", "找到了金手套！", "... 발견했다!").
Polish and Russian say "for the player <name>" (dla gracza, для игрока) so a foreign name needs no case ending.
Korean picks its object particle (을/를) from the item's last syllable, or "을(를)" when that can't be told (Latin
letters). EUfr keeps its space before "!" like its vanilla text does (10,667 times) and never breaks a line there.

Fonts (GLYPHS, --fonts rebuilds it from the romfs):
- Font2/Font.Product.100.Nin_Ounce_NVN2.bfarc.zs, and Font2/Font_<Lang>... for CNzh, EUru, KRko and TWzh only, are
  SARCs of font faces (.buif, "Nintendo.Ui.ResModels.UiFontResData"). A face is a fallback chain of scalable fonts,
  each with code-point ranges and a scale. A character is drawn by the first font whose range holds it and that has
  the glyph. The default chain starts with the Latin font CetraDisplayPro over the whole range, so Japanese text
  only shows because a font without the glyph gets skipped. The message window (UI/Layout2Archive/Common,
  MessageDialog_00) names the faces Normal and NormalBgWhite, and a character counts as drawable when both have it.
- The other 12 languages (JPja too) have no archive of their own and use the default chain, where OT-UDTypos510Std
  draws the kana and kanji. I checked that every character of every vanilla EventFlowMsg/ and PouchContent message
  of each language is drawable with the chain given here (0 misses in all 16 languages).
- The fonts (Font2/Scalable/*.bfttf, *.bfotf) are TrueType/OpenType, XOR'd word by word with a6018502 after an
  8-byte header (magic, size). GLYPHS holds, per chain, each BMP character's advance in hundredths of an em, scale
  included, with 0 = not drawable. It's read from the fonts' cmap and hmtx through the Normal chain's ranges.
  Characters each chain draws:
      chain    languages             Latin-1  Lat.Ext-A  Greek  Cyrillic  kana  CJK ideographs  Hangul  emoji
      default  12 (USen ... JPja)       93/96    127/128     48        66   182            6720       0      0
      CNzh     CNzh                     23/96      8/128     48        66   169            7374       0      0
      EUru     EUru                     91/96    127/128     74       150     0               0       0      0
      KRko     KRko                     28/96     18/128     48        66   170            4620   11172      0
      TWzh     TWzh                     30/96     12/128     48        66   176           15352       0      0
  ASCII is drawable in every language. Accented Latin mostly isn't in CNzh, KRko, TWzh (their chains use Cetra for
  U+0020-U+007D and x only, then a Chinese or Korean font). Cyrillic and Greek outside EUru come from the CJK fonts
  (full width). EUru draws no kana, CJK or Hangul, only KRko draws Hangul, and nothing draws emoji or private-use
  characters. Characters above U+FFFF (1,745 rare ideographs in the CNzh and TWzh fonts) count as not drawable.

safe_name(text, limit, lang=None) -> markup-safe text:
  - NFC
  - whitespace of any kind, line breaks too, collapsed to one space
  - control, format and combining characters dropped (an emoji sequence becomes one "?")
  - a character lang's font can't draw (lang None: some language's font) becomes a plain look-alike that it can
    (fullwidth A -> A, é -> e, ł -> l, ’ -> ', – -> -), else "?"
  - cut to limit characters, ending in "…" (drawable everywhere, else "...")
  - braces doubled, the only characters tools/msbt.py's markup treats as special (null, 0x0E and 0x0F are control
    characters, so they're dropped)

Line breaks: the game's own text is broken by hand. In all 16 languages every page of EventFlowMsg/ and PouchContent
(about 22,000 each) is written with "\\n". Latin and Cyrillic pages have at most 3 lines (USen has 1,240 three-line
pages), Chinese, Japanese and Korean ones at most 2 (none of about 22,000 has 3). Measured with the fonts above,
lines stop at a width each language never passes (99.9th percentile / widest, in ems): USen 25.5 / 26.0, EUde
25.3 / 26.2, EUfr 25.2 / 26.3, EUru 25.6 / 26.4, USpt 25.4 / 26.8, JPja 23.7 / 25.3, KRko 21.9 / 22.8, CNzh
22.0 / 23.0, TWzh 22.0 / 22.1. That's the box's width, kept by hand. Nothing shows that the game wraps a long line
by itself, so we break the text here (BOX, a bit under each language's 99.9th percentile, and its line count):
  - Latin, Cyrillic, Korean and Japanese at spaces (Japanese get messages put spaces between phrases)
  - Chinese between any two characters
  - never before closing punctuation or after an opening one
  - a word wider than a line is cut by characters, on a new line unless the current one is less than half full or
    the word is Chinese or Japanese
Text beyond a box's lines goes on to a new box ({tag:0,4}). The highlight is closed and reopened around each line.
"""
import base64
import glob
import lzma
import os
import re
import struct
import sys
import unicodedata

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS

LANGS = ("CNzh", "EUde", "EUen", "EUes", "EUfr", "EUit", "EUnl", "EUpl", "EUru", "JPja", "KRko", "TWzh",
         "USen", "USes", "USfr", "USpt")
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
HL, END, PAGE = "{tag:0,3,0000}", "{tag:0,3,ffff}", "{tag:0,4}"  # the game's key-word highlight, and a new box
ITEM_LIMIT, PLAYER_LIMIT = 40, 16  # characters (Archipelago slot names are at most 16)
UNKNOWN, ELLIPSIS = "?", "…"
NBSP = "\u00a0"  # a space no line breaks at (EUfr's " !"), written as a plain space

# {item} is highlighted, {obj} is the Korean object particle for the item
FOUND = {
    "USen": "You found {item} for {player}!",
    "EUen": "You found {item} for {player}!",
    "EUde": "Du hast {item} für {player} gefunden!",
    "EUfr": "Vous avez trouvé {item} pour {player}\u00a0!",
    "USfr": "Vous avez trouvé {item} pour {player}!",
    "EUes": "¡Has encontrado {item} para {player}!",
    "USes": "¡Encontraste {item} para {player}!",
    "EUit": "Hai trovato {item} per {player}!",
    "EUnl": "Je hebt {item} voor {player} gevonden!",
    "EUpl": "Znalazłeś {item} dla gracza {player}!",
    "EUru": "Вы нашли {item} для игрока {player}!",
    "USpt": "Você encontrou {item} para {player}!",
    "JPja": "{player}の {item}を 見つけた！",
    "KRko": "{player}의 {item}{obj} 발견했다!",
    "CNzh": "找到了{player}的{item}！",
    "TWzh": "找到了{player}的{item}！",
}
GENERIC = {
    "USen": "You found an item for another world!",
    "EUen": "You found an item for another world!",
    "EUde": "Du hast einen Gegenstand für eine andere Welt gefunden!",
    "EUfr": "Vous avez trouvé un objet pour un autre monde\u00a0!",
    "USfr": "Vous avez trouvé un objet pour un autre monde!",
    "EUes": "¡Has encontrado un objeto para otro mundo!",
    "USes": "¡Encontraste un objeto para otro mundo!",
    "EUit": "Hai trovato un oggetto per un altro mondo!",
    "EUnl": "Je hebt een voorwerp voor een andere wereld gevonden!",
    "EUpl": "Znalazłeś przedmiot dla innego świata!",
    "EUru": "Вы нашли предмет для другого мира!",
    "USpt": "Você encontrou um item para outro mundo!",
    "JPja": "ほかの世界の アイテムを 見つけた！",
    "KRko": "다른 세계의 아이템을 발견했다!",
    "CNzh": "找到了其他世界的道具！",
    "TWzh": "找到了其他世界的道具！",
}

# the text box: (width in ems, lines) per language (see "Line breaks" above)
BOX = dict({lang: (25.0, 3) for lang in LANGS}, JPja=(23.5, 2), KRko=(21.5, 2), CNzh=(21.5, 2), TWzh=(21.5, 2))
BREAK_ANYWHERE = ("CNzh", "TWzh")  # lines may break between any two Chinese characters
NO_START = set("!?,.:;)]}%、。，．！？：；）］｝」』】〕〉》’”…‥ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜～・")
NO_END = set("([{¡¿（［｛「『【〔〈《‘“")

# font chains (GLYPHS order) and their archives; every language not listed uses "default"
CHAINS = ("default", "CNzh", "EUru", "KRko", "TWzh")
FACES = ("Normal", "NormalBgWhite")  # the message window's faces (widths: Normal)
SKIN_TONES = range(0x1F3FB, 0x1F400)  # emoji modifiers: part of the emoji before them
LOOKALIKE = {"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ħ": "h", "Ħ": "H", "ı": "i", "ß": "ss",
             "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D",
             "‘": "'", "’": "'", "‚": ",", "‛": "'", "′": "'", "“": '"', "”": '"', "„": '"', "″": '"',
             "«": '"', "»": '"', "‹": "'", "›": "'", "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
             "−": "-", "ー": "—", "×": "x", "•": "·", "·": "-"}  # tried in a chain: ー, then —, then -


# What the fonts draw
_tables = {}


def _table(chain):
    if not _tables:
        raw = lzma.decompress(base64.b85decode("".join(GLYPHS.split())))
        for i, name in enumerate(CHAINS):
            _tables[name] = raw[i << 16:(i + 1) << 16]
    return _tables[chain]


def chain_of(lang):
    if lang not in LANGS:
        raise KeyError(f"unknown language {lang!r}; have: {', '.join(LANGS)}")
    return lang if lang in CHAINS else "default"


def advance(ch, lang):
    """How wide ch is in lang's text box, in ems (0: its font can't draw it)."""
    cp = ord(ch)
    return _table(chain_of(lang))[cp] / 100 if cp < 0x10000 else 0.0


def drawable(ch, lang=None):
    """Whether lang's font draws ch (lang None: every language's font does)."""
    cp = ord(ch)
    if cp >= 0x10000:
        return False
    chains = [chain_of(lang)] if lang else CHAINS
    return all(_table(c)[cp] for c in chains)


# Names
def esc(text):
    """Text for tools/msbt.py markup: braces doubled."""
    return text.replace("{", "{{").replace("}", "}}")


def safe_name(text, limit, lang=None):
    """A name from another game, ready for markup in lang's text (lang None: in every language's)."""
    return esc(clean_name(text, limit, lang))


def clean_name(text, limit, lang=None):
    """safe_name before its braces are doubled: the text as the box shows it."""
    chars = list(" ".join(unicodedata.normalize("NFC", str(text or "")).split()))
    out, i = [], 0
    while i < len(chars):
        c = chars[i]
        if _invisible(c):
            i += 1
        elif c == " " or drawable(c, lang):
            out.append(c)
            i += 1
        else:
            out.append(_lookalike(c, lang) or UNKNOWN)
            i = _cluster_end(chars, i) if out[-1] == UNKNOWN else i + 1
    return _cut(" ".join("".join(out).split()) or UNKNOWN, limit, lang)


def _invisible(c):
    """Characters that show nothing of their own: controls, format characters (zero-width, joiners, direction
    marks), combining marks and emoji modifiers. Combining marks are the ones left over after NFC, and a mark on a
    letter the font draws gets dropped."""
    return unicodedata.category(c) in ("Cc", "Cf", "Mn", "Me") or ord(c) in SKIN_TONES


def _cluster_end(chars, i):
    """After a character shown as "?", skips what belongs to it (marks, modifiers, a joined emoji, a flag's second
    half), so an emoji sequence is one "?"."""
    j = i + 1
    while j < len(chars):
        c = chars[j]
        if c == "\u200d" and j + 1 < len(chars):
            j += 2
        elif unicodedata.category(c) in ("Cf", "Mn", "Mc", "Me") or ord(c) in SKIN_TONES:
            j += 1
        elif j == i + 1 and all(0x1F1E6 <= ord(x) <= 0x1F1FF for x in (chars[i], c)):
            j += 1
        else:
            break
    return j


def _lookalike(c, lang):
    """A plain stand-in that lang's font draws, or None when there's none. That's the compatibility form (fullwidth
    letters, ligatures, "…" -> "..."), the letter without its accents, or LOOKALIKE."""
    tries = [unicodedata.normalize("NFKC", c),
             "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))]
    alt = LOOKALIKE.get(c)
    while alt and alt not in tries:
        tries.append(alt)
        alt = LOOKALIKE.get(alt)
    for alt in tries:
        if alt and alt != c and all(drawable(x, lang) and not _invisible(x) for x in alt):
            return alt
    return None


def _cut(text, limit, lang):
    if len(text) <= limit:
        return text
    tail = ELLIPSIS if drawable(ELLIPSIS, lang) else "..."
    return text[:max(limit - len(tail), 1)].rstrip() + tail


def object_particle(word):
    """The Korean object particle after word: 을 after a final consonant, 를 after a vowel, and 을(를) when the
    word's end can't be read (Latin letters, symbols)."""
    last = word.rstrip()[-1:]
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    if last and last in "0123456789":  # the Korean readings of 0-9: 영 일 이 삼 사 오 육 칠 팔 구
        return "를" if last in "2459" else "을"
    return "을(를)"


# The text box
def _cjk(c):
    """A Chinese or Japanese character (lines may break around it in BREAK_ANYWHERE languages); Hangul is not."""
    cp = ord(c)
    hangul = 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F or 0xAC00 <= cp <= 0xD7A3
    return unicodedata.east_asian_width(c) in ("W", "F") and not hangul


def _width(chars, lang):
    return sum(advance(" " if c == NBSP else c, lang) or 1.0 for c, _ in chars)


def _units(spans, lang):
    """(text, highlighted) spans -> units with no line breaks inside. A unit is a word, or one Chinese character with
    the punctuation that has to stay with it, and a space is a unit of its own ([(" ", hl)])."""
    units, cur = [], []
    for text, hl in spans:
        for c in text:
            if c == " ":
                if cur:
                    units.append(cur)
                units.append([(c, hl)])
                cur = []
                continue
            if c in NO_START and not cur and len(units) > 1 and units[-2][0][0] != " ":  # "Toto !": no break
                space = units.pop()
                cur = units.pop() + space
            if (lang in BREAK_ANYWHERE and cur and (_cjk(c) or _cjk(cur[-1][0])) and c not in NO_START
                    and cur[-1][0] not in NO_END):
                units.append(cur)
                cur = []
            cur.append((c, hl))
    if cur:
        units.append(cur)
    return units


def _lines(units, lang):
    """Units -> lines (lists of (char, hl)) at most BOX width wide. A unit wider than a line is cut by characters,
    on a new line unless the current one is less than half full or the unit is Chinese or Japanese."""
    width = BOX[lang][0]
    lines, line, space = [], [], None
    for u in units:
        if u[0][0] == " ":
            space = u[0] if line else None
            continue
        joined = line + ([space] if space else []) + u
        space = None
        if _width(joined, lang) <= width:
            line = joined
        elif _width(u, lang) <= width:
            lines.append(line)
            line = list(u)
        else:
            if line and _width(line, lang) > width / 2 and not _cjk(u[0][0]):
                lines.append(line)
                joined = list(u)
            line = _cut_word(joined, lines, lang)
    if line:
        lines.append(line)
    return lines


def _cut_word(chars, lines, lang):
    """Cuts chars, which are wider than a line, by characters. The full lines go to lines and the rest is returned.
    A character that can't start a line takes the one before it along, and that one's too if it can't either. Two at
    most, so a run of such characters ("??????") still fills its line."""
    width = BOX[lang][0]
    line = []
    for ch in chars:
        if line and _width(line + [ch], lang) > width:
            carry = []
            while (carry or [ch])[0][0] in NO_START and len(carry) < 2 and len(line) > 1 and line[-1][0] != " ":
                carry.insert(0, line.pop())
            lines.append(line[:-1] if line[-1][0] == " " else line)
            line = carry
        if line or ch[0] != " ":
            line.append(ch)
    return line


def _line_markup(line):
    out, run, hl = [], "", None
    for c, h in line + [("", None)]:
        if h != hl and run:
            out.append(f"{HL}{esc(run)}{END}" if hl else esc(run))
            run = ""
        run, hl = run + c, h
    return "".join(out).replace(NBSP, " ")


def layout(spans, lang):
    """(text, highlighted) spans -> markup with line breaks for lang's text box, a new box after its last line."""
    lines = _lines(_units(spans, lang), lang)
    per_box = BOX[lang][1]
    boxes = [lines[i:i + per_box] for i in range(0, len(lines), per_box)]
    return PAGE.join("\n".join(_line_markup(line) for line in box) for box in boxes)


def found_markup(lang, item, player, item_limit=ITEM_LIMIT, player_limit=PLAYER_LIMIT):
    """lang's "You found <item> for <player>!" as markup. The names come in raw and get made safe here."""
    item, player = clean_name(item, item_limit, lang), clean_name(player, player_limit, lang)
    fill = {"{item}": (item, True), "{player}": (player, False), "{obj}": (object_particle(item), False)}
    spans = [fill.get(part, (part, False)) for part in re.split(r"(\{item\}|\{player\}|\{obj\})", FOUND[lang])]
    return layout([s for s in spans if s[0]], lang)


def generic_markup(lang):
    return layout([(GENERIC[lang], False)], lang)


def found_ops(label, item, player, item_limit=ITEM_LIMIT, player_limit=PLAYER_LIMIT):
    """make_patch text ops for a new label `label` in EventFlowMsg/Dm_SY_Get.msbt in every language, saying the
    location held `item` (its name as Archipelago gives it) for `player` (the slot name)."""
    return [{"lang": lang, "file": MSBT, "label": label, "add": True,
             "markup": found_markup(lang, item, player, item_limit, player_limit)} for lang in LANGS]


def generic_ops(label):
    """make_patch text ops: a new label saying the location held an item for another world (no names)."""
    return [{"lang": lang, "file": MSBT, "label": label, "add": True, "markup": generic_markup(lang)}
            for lang in LANGS]


# GLYPHS from the game's fonts (--fonts)
FONT_KEY = 0xA6018502


def _font_archive(chain):
    return f"Font2/{'Font' if chain == 'default' else 'Font_' + chain}.Product.100.Nin_Ounce_NVN2.bfarc.zs"


def _sfnt(data):
    """A .bfttf / .bfotf as its TrueType / OpenType file (words after the 8-byte header XOR'd with FONT_KEY)."""
    n = (len(data) - 8) // 4
    words = struct.unpack_from(f">{n}I", data, 8)
    return struct.pack(f">{n}I", *(x ^ FONT_KEY for x in words))[:struct.unpack_from(">I", data, 4)[0] ^ FONT_KEY]


def _sfnt_table(f, tag):
    for i in range(struct.unpack_from(">H", f, 4)[0]):
        t, _, off, _ = struct.unpack_from(">4sIII", f, 12 + 16 * i)
        if t == tag:
            return off
    raise ValueError(f"font without a {tag!r} table")


def _cmap(f):
    """{code point: glyph id} from the Unicode cmap (format 12 if there is one, else format 4)."""
    off = _sfnt_table(f, b"cmap")
    subs = []
    for i in range(struct.unpack_from(">H", f, off + 2)[0]):
        pid, eid, so = struct.unpack_from(">HHI", f, off + 4 + 8 * i)
        subs.append((struct.unpack_from(">H", f, off + so)[0], (pid, eid), off + so))
    fmt, _, p = max(s for s in subs if s[0] == 12 or (s[0] == 4 and s[1] in ((3, 1), (0, 3), (0, 4))))
    out = {}
    if fmt == 12:
        for k in range(struct.unpack_from(">I", f, p + 12)[0]):
            start, end, gid = struct.unpack_from(">III", f, p + 16 + 12 * k)
            out.update((c, gid + c - start) for c in range(start, end + 1))
        return {c: g for c, g in out.items() if g}
    seg2 = struct.unpack_from(">H", f, p + 6)[0]
    seg = seg2 // 2
    ends = struct.unpack_from(f">{seg}H", f, p + 14)
    starts = struct.unpack_from(f">{seg}H", f, p + 16 + seg2)
    deltas = struct.unpack_from(f">{seg}h", f, p + 16 + 2 * seg2)
    roff = p + 16 + 3 * seg2
    for k in range(seg):
        ro = struct.unpack_from(">H", f, roff + 2 * k)[0]
        for c in range(starts[k], min(ends[k], 0xFFFE) + 1):
            g = struct.unpack_from(">H", f, roff + 2 * k + ro + 2 * (c - starts[k]))[0] if ro else c
            if g:
                out[c] = (g + deltas[k]) & 0xFFFF
    return {c: g for c, g in out.items() if g}


def _advances(f):
    """{code point: advance in ems} of a font."""
    per_em = struct.unpack_from(">H", f, _sfnt_table(f, b"head") + 18)[0]
    n = struct.unpack_from(">H", f, _sfnt_table(f, b"hhea") + 34)[0]
    hmtx = _sfnt_table(f, b"hmtx")
    adv = [struct.unpack_from(">H", f, hmtx + 4 * i)[0] / per_em for i in range(n)]
    return {c: adv[min(g, n - 1)] for c, g in _cmap(f).items()}


def _chain(buif):
    """A font face's chain: [(font name, [(first, last) code point], horizontal scale)]."""
    def u32(o):
        return struct.unpack_from("<I", buif, o)[0]
    b = buif.index(b"BUIF")
    out = []
    for i in range(u32(b + 0x18)):
        p = u32(b + 0x28 + 8 * i)
        name = buif[u32(p):buif.index(b"\0", u32(p))].decode()
        ranges = [struct.unpack_from("<II", buif, u32(u32(p + 8) + 8 * k)) for k in range(u32(p + 16))]
        out.append((name, ranges, struct.unpack_from("<f", buif, u32(p + 0x18) + 4)[0]))
    return out


def build_glyphs(romfs):
    """GLYPHS's text. Per chain (CHAINS order) it's 65,536 bytes, each BMP character's advance in hundredths of an em
    in the Normal face (0 unless both FACES draw it, and never controls, surrogates or private use), then lzma and
    base85."""
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    fonts, raw = {}, bytearray()

    def font(name):
        if name not in fonts:
            path, = glob.glob(os.path.join(romfs, "Font2", "Scalable", name + ".*.zs"))
            fonts[name] = _advances(_sfnt(fs.read(os.path.relpath(path, romfs).replace("\\", "/"))))
        return fonts[name]

    def width(chain, cp):
        for name, ranges, scale in chain:
            if any(a <= cp <= b for a, b in ranges) and cp in font(name):
                return font(name)[cp] * scale
        return 0.0

    for chain in CHAINS:
        faces = sarc_files(fs.read(_font_archive(chain)))
        normal, *others = [_chain(faces[f + ".buif"]) for f in FACES]
        table = bytearray(0x10000)
        for cp in range(0x20, 0x10000):
            if 0x7F <= cp < 0xA0 or 0xD800 <= cp < 0xF900:
                continue
            w = width(normal, cp)
            if w and all(width(o, cp) for o in others):
                table[cp] = min(255, max(1, round(w * 100)))
        raw += table
    text = base64.b85encode(lzma.compress(bytes(raw), preset=9 | lzma.PRESET_EXTREME)).decode("ascii")
    return "\n".join(text[i:i + 116] for i in range(0, len(text), 116))


# python tools/rando/parity/_archipelago_text.py --fonts (see the module docstring)
GLYPHS = """
{Wp48S^xk9=GL@E0stWa8~^|S5YJf5<p2LST3rADZWw5$hJe3-Fw|OfW#Hr=?mKz_qzLuPs|4~B);w{8xCL$`Y)z@K&X%&&tw1x+3uZy*167abvW=TD1
@`!Fg0ih*FIXCz^_Cj=7o8Y<%zv|gmG3z{P0gZMp=LS{U|zdDcV)hP=p;$o2HE%vXfBvCQyaC<mLaa6DZt;BjVVa5(EtzXxO%rQcB*sf_i?x&Bkz{^fT
y`W-&59OKVo;Z;e@t_iEA4eV}x&xTcF)@T{2$@QZh*2q5+z~!(`X9k(X+BKjvzuo2l`dg)3tY<3@iRo&q7AYJP|}u;R8^vz5zmURaB$HcNZTbj}w}y>w
(Kq&t7l*#&LR@?@nS{Oe9hf`UB9$&t~%g$>NQv}*m*O6nW<GbDcM@>LJP9T2tykQnM5wPT_m!&ofrY2;rzco~)He9mHu&^$xc{G+N7Q7mRLM50R`_B?4
sE{aRdTSGZ^G_rsVj!%a0(vc~go-Syp)HujWJ9Jb(_gexv1J~jkXR-^#ojMbMfmVa*>5>CgLFENxrBSht5yqLEq(i=QTo|^)PzaC5Ky*1m^imQSznHW8
*R0yX6~HN<tw7>B#2xUR*LLtL#)r4{56<q6OgGZw^*W|MjT@6+#mjI#rb!Lo5$Ia=(h@ti7=mky*;XS5+R+y?)&pm1R$%GPWU?Y#5e8E=fOV`|N=xJd#
L)qs#jk@emG5x;6ac!XxrgTW^1)`eKuDrHQ%|lPaNgsHS+4M>Am+VK1!ZvPm;SBe{)827O+gx5fyd?{ptLYOekIIyjdb-ex%5~fX>Lm#o`!XDz0Vln-M
`-S8q2pH9L25<TLRWzIM8dmP%mgAY<lQ+gwe{~gs(lhz*UAAO3>}%Q}RVx0x4VBX73c0*_lfPGjzxX!3TX%yXm=LODMi2lc=2`@w<VvB%d9&+)9N$h+N
|H<(PX@mYiZ&N1(}O9W+EPtRUNgMoaZQZ+UrKq9B@`kGzXLC46m`J8qi*&A*VmHpv>X;0F>aLg>BEktWFpL=+=Wea;Up%ywMts(wHMLpS9%Uql0wA?8y
Sf&k=P*?^D}#2hE-3-No!@H~)|jQnpdGIfyOIsKx^T|py~MtFi*B$-H#_R>6T9L@L3zss9nFFW4^kRA&UaQGPqR6;aqn#MoL!=tLY-Ll~Ug4J@S23?rM
i0UMsI}zYmcL|`lC_y&o;M1_;1;XO#hq9NMV_l#RjQY#Ots<(=12h*-GG?R3X;!ZpxgVh44{(K#yE<J9phQ&0NXE2rs?5C@*!KWlmlaGJtd8@ehHgpz9
&-vW9gHu&o^Wt74Felugfn{Lv9hofp{ylckaY$*MJFCVn8*hLH7mIY$IY)9S_nhEgzCk85k^X2=Zbwox_*2juU>lVd9F%WxYNu9(2(9myD{$~&u0$rZP
<-Ju(?#4w%whoUCDKlW`+5nkk#yA^Lkhim3)0s#wgA1XR)uveJ(LsSuL_#0{tBQh;7ik(lH0E1zJ^CJX~q014U`~u#V!`fpFx{-y^mZI)u5zmhC=8-zm
ztgna!yb#Byi`tg<_cHM{_gJ4f(6OB0Zs8z5BxSu!t$(e%)EVyH(Tfowfe!ojJ?>3KMM=XM5b?yD}UdWm!zC;uo`^oAxVlV08j$W^3-?Xmg?S<Jj_G2A
W$kyiiM&Rr91Hv0u-<&daZ36$xb-aL^H-&_JY@#t%+Wf5!i3uCAdwt+~F}bn}lKYdz|6DL(UeGx77FxO{$n2uidV9bjMtpMUV>Dy48_cXoWbj)D;Nyw1
(xCE&l`1EvlE%I?(DiS*{Yg*3o)yJ|n{Xdkb2wrGExx*v`v*jlRSAEx{oQK;pAtY{%rtLBLEtla3B1>jJRHv^;&&ar!OmWZjK|P7RC(<}zr`So3q;8Vp
F4FdOHo8x@AZ~FCYdK?;X8)e245JsD2$T9UT9Jxlu(txPbu$YI$&zAY=JndD>;!tOSaoZ6etHtDplFixpjXf8c%9j*)kmBi0fz#F{-_OE!+>iM=c;#M!
G<8#+(t!e%9cZ^LMS*RAQotghW(HN6!9g;1V*V>-T_Tl0gp^NUN3n*}j}tx!XzfJ3CB6x313u+@!_CnNi{Rfj)E3bDc8&mP4Ul(oH-iZid{KIg&pTGSB
>y&Q5lPN;q@q8CJq3I9CDqqD^z*<`_81wL2T+k?7@+y)#W7v8<hnK#{mI&J+intu?gF#S{t}oxuMQ{~*z@$O!gal`p*aW1;8fvvW8e!GB$(s9ulk9jm9
#U&fc_bc!dEY0NB}XT|SbpkJ{9er?U@&!F5}InY$Vl4jvh4$~J`qDRPz<DNOZ=9DqwHi?pzlo!^zj1E73e&-SPR^YH(hvDNDq@_8U9uG3}h(|g`E>%0`
z`|E|;lj35Xb-+qE6^bGE_&S^2B61U`&g6VV9{VuE{Z+NN8d3yaZ|z{v=A@!XZA4J1I80g%{vm;qzbh2sLzA#tPoyzFtC{;zD(vzHSQ0TDi%<<!LM*BJ
_u(^o^LJJX>!p)!QJgrV)p|Vg-EreLi#rAq$65}BECp9X3n(`g-K7|U@k!~5abl1Qc+Nr7?Dmh?1Re`{0-yYWtuc<o<@8Jl2JlK)9k4@rVb=%XQdcqCR
m*Oj90Aze((V2ha0k;VS39ul6q6?RJ6$M6*tv{{Vgt4B*x!Y&K5m}p<NXF`m6Kf7eOC)a3FUHd%Dmq<RnG7A)g@=AN^@ULCtjP=wCi318(w9Q}z|jI1(
Tn3{Ck1;m{(<wAZ3>K;G&0br1?4lI|kkLbo%);~86-k1n}e^s|TwB6u%w{yz#1cN`CNMy@Qd^SNOl{15JjJcUCK@%@dG;L%v&(WanyX9^7LVDt~#%<6{
20pFVU-7Iu=!Zy-9h=74qfbC8`tlj=O!0*{8#wGl0xifk^JmxBPBVT};#;Q#)UN&db=YyIJMG`0rs5x^If~*2A8^f%+%wYn1J5v96VEN8>OnnkQXjt1j
n34xB;X!2qo{;{qw~k_Gt~#xfOSv7|ImB=4jUJq*Q%!RGci`Io7IwQs*JZ)~cSv_uz`X_ysAk<jOU#_&1NNZY75Kx^PI=!)K>^_jA&+&wbxn(&PV}%+;
rzzDOYi&c<ThR$qvP7OP)XIoX@*G3{fH9DX09zDPdTnF+K=_`z9aW2$fN-7v-Q_uV|lDm%D7L;jn51%5Pp$EF$MLcVaAl0!1Rl+RQC8E)-OUIbs_LZ)j
J5UK>V07Va!Lc6(*dhB4rkKJ2RpH&r+?GH4x;(Al|NEu483|zMvtqB)BlW<x6@D*3U_s%zV6fT%G?1eLLrjo?wZt_gRujMZ0Qp_C83XzDo@$w3wcJ0CC
5ql$|fraE~Vww(L#cMZT9A#mRN6l)Cldc?s5)PSNW-K#Yr$-Vx5OD<#Opc&yaT{_>?Y{+IQ8o;0$V?InA|r+-lDANKYbrD$>^N9m`jY5@}-W+!FdR)*;
E#Ce)TM?QrNo3SHHzUZ=88Y?naN?US#oFlZ^yhG>UW1(=4ak~m2K;=KY!LXa>^D@WZon`I$a>kW+N+TIl+Qc{v`qt3Kf0&g9V8Z-VD|qvCER<&<Ori8+
@tI+{7P2D>$#W`pH75)9g?5q&&h)DQLPAvKa!ShLk*j;879}t&2pbMikeZ0jo)!MaiC$)H$C*$MmX=hZ-Fb9mfgOjVqJr_0F<<rq{OAMSYP_2tq42^sh
cXikX*_AFXb<fYIEVcV4==mT$mq2Zf^4mpk<QR2!b=c<)PaRSTcL~pB=ug_Y>nAMObCH3Ebia@oEJ8mJ)n0jl%S5xDPR*eg==#3v%1{NQjvvd@;yuX;N
<P^i$?`rJoL2mH>O<4bOXy49<oGeHzytVlaEfVuX&&nXd!`u*h8ac8%KX|{zRG&lgYmGT%Sf(TI6CU^~;O$FJJC8H?m*o$KaZ-(R{A^HnchRF;-1*BQu
<W5dJrb7t$ZChY8?4nDQ2Q-cN2AjpGe`(xQ6H3`ATb@E4y5+6|RVGeF|+4Frg~nft&8#b5YRJ{+Dtb<*w!?r$GjuV#*X+Jf0N8$C-)WC{sDg_4GIhaFc
4M{*Si7<u*KUAH6a<+jL46kYT70W(!mZn<^?-O%fC)zvrtoZkq8z%clpK;-hN9z(ej`bN3^W=k*3{a?k!)rX%b<Bx@6pVFi={0%#tM~<EJt)GkGUFfO&
P56sK)#zLGjkO2o#!*VfFIe-tQ@B0R8ZQUh&g`KtmMK-<4-}>7-{deaoO72@!N>TabyqOA4ap~){;6&h;kb2m%@b8GRhmH4JPozCOAXB*3O^y8Ge^wjA
2>HfBIIy!hsjos;x*mfKY)`PHB%FAQhT0xR*faz7uZ53hz6^GKa{+pI(Gb<UAvpKdK_@u9M+uEQm!EI1FEKA|85@>2~ef*^%cO~_*J3L3`@3#u1^Ls4u
Yt{jw(%*sYAlcA`LxSNq^Qqm7e&OKq*|y4rENf1~8Q@1tyRt_*w&whjS#tN`#NJ-+r8G#t@k}d<CUowU20_Cp}N)o!pr~IvePXEGPp?IV;+m)X+xv5}$
*vnm^);A(NzorOsnCq);0^dtDNtD4A_1*Na-|;4(x^Jzl1Rm4E=S)QlnAP*v=(#73;u!S`e<=}c_v)>MT7bBa596LYEtOT`FTw|zv>UwmJ5EpQ8`mQ`Q
d#barJV9u+k)AMCqO5H<p?)`$D5f0$UAVF}<Ef!Lsw<<Lr@bgktOPcpRznZKg`rXe-(jRQY5YTR8@g5D(AX{*9oMqzGRAn$HX{1)h*M0OOav?_?JYfQb
33=I(WzSd`tULriq_d<SXazd$4erN>r5>4x2M;xaf=B;#j2<e7xyWH6h~^C79o;&N2>Nm#pE&EEbJ=;L9qFcO1PcnS;bkUqb@F!M&FWG<P?z>5a#A9ux
MlM3=Po^JYEuSnvQySk4QCgA8q2wpLm<fwJb#=#xFtiy(&6q23;PszA(m$+RpX*2DON)}f+%&;;6MnRO?z>DBlbJxMBay7(4Q~&rE!(w)M?9G9S-FP70
84fV7yh{&($azD(X<~41M>83UX-oA6B)2YeM@`DhGjF!MEdToR(ZW!}ef)Fs-v9m?U&$90>;!t12crV5t$KOxk=F{oT#)F$B$HX#|=jF%QN4vSW^OaN-
;l5uR6-$eIYVk`pIrt!WXFVsCoGWvul3DyBtV48b;I<x82)n5JC}tqMOP6=++2ourj<VeLdeLmt(Yw%*T!m1#RHqVQC+wlL?IpE`r7OiWVZMb?jYPS=u
$jCKngFgk&i3EK`Nt%88Y!AH6G>lRwuHv%!HG@jEPuREED!UReKALWXe_n~12>w6nhWb9dhZ_;^!xH}#ZJ26c7`S;~pKH7L-H6C*J(XRG+iBAPLdJZkc
__Y_fYNS=FI!F{iKTo{)aj%H`JzYcoob>rq*;eoqlVNUn)OX@RDTOMV=BmB<)Hp~K`(YSEHX6SCquHqjX`69cq?nB_#|$kuo9bQ9^9td+{^X0Pkw=&3Z
AP5Hs5u#pj6-ZglzGXawHM&=`s;?<dtNwdS8L>$Qnyf#C!k4+mOkRDC^dRxPh{09ZBZ2v>uV@8lHZrOtLc%ClQ&|09yS1%JrA|maTd6IOwvZsyZbf=C&
GUI8?vV(?@~tVL~A401Ou@(GYd<}`&8a{PS9N^I_-oVIyu%gX<l4os-YkZVU};)ttxUTbPTK;>p9-+wBV=Vgtf6{x7^|`k4kIibvgC9zMx1tPp2ErlI)
0yj|(#S`E7Y5)&j%vWp9>L#z`||fbMZSO5}`Hb;+91CgXXHx1=r)+D|4<$W7kZF?tC9jLSMiM67LZpDJy9aeibWkiN$TdToH)(34y=f<~oPxHAB;x-*)
iTJ;v}3L@t`rwcS_a;v#L;6TClYc#qPkT~&0C9EUo_;|2TQMw1j?GjGuDh2M<F)(^0^XrRLs%&FW;BLIL0zRlLauZ1Zf6O($+$*gH(<3YjT<IP}YfESX
KI#7hJ{M^zu4~k<C?m&^uNfb&KtbQ9&&X>Bh2iCZY!%RTe^P`Il@Mf)F}K^e27U*H*04y>G<yYXQVOSs(l3*SDuwAi$#JMrbts;@cFVqtK1s@|>7YjFi
z=K~qA#cEu*PSogtajajua)u2X^UPMxF){AYNYo#XHk^w?#*!dFtiE+-ywp>!u<0&PnNJP~YTN6rFo^XSG#<4=d9Zsw+2eSPlW)5+@ErUVr=o1f^q+5K
Ok6n3h1TTXMEw3^`gL+`m<B0l2sfn9n)n_$<=%mtEUiWt4P8;FgbbM=Z9a0r41`*U9kpNQm!R$TJb}cLfN_B^Tv`=BPDU)c(k!WiMh$$mt8#83d}dSIw
6Yo!pF1V22qQe%ARc$>*1(^B!;z7@emg!p6Pgor=59;Qir(JWhCdP}yt^&NP)m_WlY+qYuXG={p2=rTWod<3fj(c}O?^5zqR(WAfM!cC3Vl3zjqP^4ZH
(|NgwX)UJ;YOqwW%eN_XFuR2&$RswSvpmv*BE4-ydtjD{-@=!P9DFw~4<O~o-OsW^@`3sv2b77y4d5k3;RvO5W27uBRp>aIwiQdCGJM1mmw%s17Vw-EA
$C<A536snghXVdOV%Rci@0syb&##Ld(B#XYV~w06YH^Ys0Q_Xt@`reVSrx~8FD+{IHL0r)6v|siKn&705pHsA#i3jA;j7Zc=*JqfAzSR>yunbAiY+THC
Qtk`YsKbZYO^zX7IGF3ND=A;tETI4+)BDWqW48WXPtge$&_m_`k^6sA>iOk;pGHjV3QpP2KU)_@xl@zu_cp;8Tq?kp<QxVB3^83jr~wr4oBMndDE}Smb
=_d=?(&sDls&mc>AGp)S03aS9^s@FLeoKl+N8Fy}AAQIMvcxu%?5YB=j)Om2s>4`Ty$iu(4dv^11cr#x7@7QuPY0fNUvzefoXdx6NKuG277>>OeCGQ09
V~oeOqvzs7n>T#BYHi8&#Dl4w7q0wo1?UuXTpPyT~l4X&6bdV<-jt>|x>Y<WQl#mXAIXeo~u_|HihmB8t?F4R`K&L6UMdNfUDbrZw3)W9#j!vDk7?e*p
E>+NYEE7M#L=EsVIv(lfPHX>qbf{zMB;Vk#*(q}Ht(3tmqNoXL6%0)I?BEgk;vcH;2gk)-_xLy{jJ(W3;gH0W!4B5#%Lh>EA$p!0VrwSEoFoK8L5dS_p
>-sF{L7WmUN62I5{E1!G-K3BEUpaG6A7-e*ld7Q5qTkg{=;Nzo=xp}mGeFF>V6)v=<JJ51PP(4wnNb061u!C`q5tj8sdADbhrKWX_`p0axud~JN!fvnl
zUnI$$1I;iHa0-5b+)=p$RdKE8-RP{ivImq~2QmsJ>Yw6rR@{xQg3PLOt$;3r+~ymJqf1tCIgYV=Wv$SvUei#GC}H#8Iw;h`#U-%gO!^2Wt{KMA_;{E;
{j|6iDJGNZW{U)0!P25_c~D2l3DN5jqEMoNODx&UnD)J~MP&-IV+<K%TZfM+zbgIXnxeilajSxA@&p{3c>-$;uCApXmL%z=uq~eD*kR=b3%DWBw|i;&w
lyThoGs!MIQ|I3;=>0t$u<zIH@$2?tslWFM6#lwDhN{ugwLwz&SQ1rf<fIY4@~`y|>n;8Sz%Y;kcd5f+#WX_x)7_c}ceDyo*ts5_MSGQtRA3^H-ZPNVt
&JByw>_{5jL2K4t*W1Aj*E#!siR#k&Gd-+70br_`voZa(@lj?g8>O!rr<doYzi#3%u2-$b4c3m0z#7(y+E_iSle7juksi@i;N*A83zl?Y7l*QorWq1F0
KkE|COU)DM#Xz>wRwW+?A{<!;J;aIpYazXRjd_C?)M#{nbodgIMe}_G-A2PA+ET8Fi@PF=%c><z8LH_nZAVo7f9W8%&inNMK0eR$k=a~6QNZ!53}D3<D
NHjk`5<^cUM02WFp=-xF6q0L=jh8sX^if$yHFwe+OKvaEY{8gEvekvs>45BN>|JY$nMFZiGcwo+j653Z{iRk-}6|Lp8Xa!86_I2Vj+A__HM!eqjN@hni
%lc^I_JHQHqHd@4<D_^{VF6LgYGzqU=o!``_wPusqmyt8(@pEv7CNOW?O>$Bdlhlp<}#Rg^AfMOBanON^P`e`}!=Pj)06>`t0yOm-F@(6!f{a`Co@qLa
QklS3ajs@m6~KJoP3(dJ5~TAG;5Cd-y_U@F}UUVl#J$Y&=xT;HzuHCZYc57pp6gf){hPA-sVy1GclmQTThZCTJ$j1I>qt$GH0YF^v<$UHrUJR{LlzAhR
(xZEfw9*>|OJ*<*H!XMt`Pd`NUPQot9+~W2Mun|#&{T}Wy2QE@Pr7!F%3XsiZ5^sKZtnQYB77IVm742QP`WIuGN&^Lh;92k!2^7)=Ex>3?CAYqN#qFBw
-qbSP9N(tOEP6AVApN%q8ni>lr*t1z_?hOG%N+aMgNpKA+&tin6NwjBS*jq0Mp!8}a_kpBVMzQ_cYMYP=Ddm<V?x;zTMR^eTEvIu6Sqn2Q2s(LKpvKT|
8WdPT4s((z~L0)=6k{ya=)y(CwyUap?)bJx0Lo4AwxsJx>NfeV!zhiUX&cMG>nMatf0i{_p*7|iBpj0?j0&fnqko!bt1NuULRW=o;Ao(6Cc~%hI5(q0~
-3ex#Occ0a;E8$x0aaZ^=Q)>mnu}px*Rwcr-rr#`&?k<#YEeXhfRg*rYUPbyz@h&7a2-S#nC;60n4Lu(QfpKt8ey=Ar>EhHV#_B+v=3fjvsC1A9&^who
O=Z<B8bC<01S__Fq=Jl33rkuLSl1FKnQQp)S7|1W#9>%ZKc)Z9~v+|6W(i2kSfb9IVqS>xWQA5o^Qi(Y1pan@3cq7-OR0L?`LXL-NJO)Rh3`Qd`$8=>W
ZmYp-MGJFYYdfjDc1}@&ho#Uszue*@Asfr@~JeVLqZ*MdF3l)tc8#rO088b=4>x39)C04g<#zDc)p?;PP^4LMg{JbmtD-|P_V;B${U(ncMnFb~+f21Ef
`XHQ!^5gj6`?hDdyXR~jKlzsFU`R<t_!K6@&Aep8pd0M;3@#nD(w}PHL`yz49+FDciRWXCvsw<0PY&@NlVOwUZn&@06o{IATobt5=^o0l=`m};#X!|Q+
}9H<)+%s3R1+lh;7>yi7O^$`=cjC5E!ZT*+h>d8vw>cRDNSx2Ee0^ptq7iBkaF0UKp=KFW8k;AXbk2oUTrr9IN3%)zH|=TV1-J>(|h5v8+lX|ji=u=`z
GHUa)`m=nv!#Wry)-^L`jY9+K|25!e9Wp>d|CEg?*Wco&9<c#-hooDjYhHgX-+|qPeb_!_(cNe=i?3)+tjJwds~tPq5-0jM65AuBW5I+A2EOA<`?fF!)
f+40v{gCikkd^&WhVh9zyq2@$lIu6_R92S#|ENqNPlYn!)2$JK4MUfS#NV=<A1XSPo9<uTTB@s{xB?jTQ8sbsT`PbNyqe(!tKjriyFwaN?mK9IId!PvB
ey~#Ic<Aj|ulNV15um>YpmT6gZv3fcp4tB{MnWLzv(*5r2H<YeyF;mCm(T=yPFE@Dg55Z=j4jA>1lWH$OOl>tpVDPd$Lf}F3I7s1!joCuh=oN03?H|1T
FRDY7Dn=6XO?nPpW0r$jS7qlip3wl23j|~T1gXmWw?4a_OkeJJ@_`bbM4Hqo!uUF#y>z>hW#EiY!|yFixhOqvIRj47f)%Tv6z!Ck3UPQFeN3VELCc`$o
rs=}qD)ZTb7~<zYY@52jQamxVkVXi3AP~BJx%GYZV^tb^Q`JzENpUs=;n~nxuH4l)<K->0QLwJz&KO|?P-Ubt!KiM$v$hwC2fUkh>(}pe@qoVCh^z&lW
Xc9;gOnY;I7o;Vp|3C2jwlR6Lc_II9A$sySF9xj%S+O>b5x(jy_j}UkQ_kNM6Df`R9IyV)}mO22=?;uoD0do%A{RNtSYRo4u#f24dDWIHle4lH;;$bzm
>wM#0Sd;jMzm$f~*B%}hGrgS|CV1EE5-D2Wu|n+Ul=)FPmFj9Ug`jT?99t!&+&yY#lLlSM&^zYoZj3LZfCIL)HxYb^B_-#Op`(%Kbovh1jM8g7F>af}s
T+nkdrSDP@s+**aQxOV(s&}Z}3Zgf#GYxedP5sUF}^TL2C${3giq2fsBXX?vCD5-G%&$|GXYD8}?m&g7UrL3o?-KgLn)6{k&X#_Q!W~lI((Tv3!yWEfE
^vftU65>V`V_*_}2aH@e)t5x;e=n8TMotDB`eWkBQW$&;o|lzNn@J;V$860!b?t(ux5ml}*Ci2z(p&L}P=k<?<8q&_KI9h8$0DQ^BjEAs7Pf`IJ5fn%b
fkx70Bg?Ve6gBZIU1vwl~Jc4t>Mr<0VI6o8^Yb{;nCjIp-j~3%{dCj7}9Q@(%sjVO}FE#@t!iFv~}bZfJ$Hegq7es&g+5v>}NNS<0|<Cmo22K0bv05((
)phttNGyBRfy}=kN0G^1du-Bfd!^iZG}D{Kw6Ymk`)0b|bG4kzjit>GQy1GJNRa%^bW8;FFs&hov(b?{7DlAvk8EDPwJxqBvTA$CGz())jIJbj)KK^e0
O6^mwV1-^lds+=PJ|Ew8OFamZE9PTtZ>P$m-270ws^LXTTwDsjiH7`9scg2;7x?&<OH!lXyQgC~UgGl&sDZWD{;XsP_8R{k_!AORS|Zkf^T<(x1%FpOj
5BX0ad@4RXiWw&!!v{FsoZ1kA@>^LcV;UJaTreOtN+P{R?wjr6bS|w_*v#tPAr=z8C7MR8~uK<0U{Od;|?k4LmKd5<~5M)aM#4mjVOt@}|8yR8}h0Zz0
(J#5Qrf3gG3I&GK)5eaLxyC1KykdYlFt~tP>sd0?faW!BJ-ZG0f>?%v>!r9#iwx?D^r=T(&W>RN`^8e!NuO0@jTxHx;v(KSE5RbK9SRe*&pJ^c9_dD2B
`4}fZJ<%CfPtk3G-?sBLNfJ__5JkLeo2%OHiA(vHjbw&VRf#X=7)Cke$2R6H?PA+${WapL3{*&?rE4p(<&J>S|f<^qCQddnhN#L>b~BC()N{pCr*9(j^
YNZBg!wzGdOXDK(4#Bvv>F#_A#s#t=bEqOWkvqkqUHbl&C!KIS_02wbdV&I=J|Eu4fBo0v>(DJ3Nvhc}G|@Gc&yiyXgINxEM0#ID~O52Qel-!lj*6O1o
WtbASmqOY+!Z^qW=p&PhxeL`USBfEf!_6`nK)3DnEu)jbHb^pxd|^c=rOc*8AMxjVIYxF@h5vXTKN+2?~Wlb(9aFc4Y#BwJ;~q%z{6dyt!Bl}~#u)0$(
m`)G^|yN1UHO}xteOYtbReEvCO*J`m}9=Ou=q%z(7RmPkmedH!#mORgw_leRd?6_Bv2p|C2?L5)YycOtV;&=s3LB!`Q8G|=xeaH~u_EW;(iE6RdXO=Q(
6uFfyBAD)*7IHlj4WJWa5B}4MWTQT6?Yu4kD3#+mghw^4i7_^JB{&)6oKn|b`DD;%-3HS$_Qgbo5EMToHrxm~%!3X{>dpd|IyM2HkM?i&JZVB?T6e?!9
p4X#<_sKRn~*^cfHwKPbo^vhq`hCO2D1TyJw&4VS|8&{-Q9P;52SBFMTohmggEnOM}QPGP7#yg{e<_FLA?4Ae%pH&xt1}geXV_Sb*)$=cuY91S%I)A>t
4FRUjoEiiC)yheb@Bw2oJ;FhwJG6BOkOMj1%}Jz`ZK8kNx@R69-pGe<q6$26J*iwZFgPBS^(4F4uT>5Gz)IAkOV`m&2==(~!(%wleu--<}thIf&f8+j7
L3>k2{k7hTCg!S8+N2CbHCC;*YV)6>u54tbV1*;r`|Xij2%>0*DUCXnCv_RgkA!j!B80dVS$kcT($IxjePLGcU>dyWTdyi!Rp^ASyh?wm28*1I<Fo3aD
vtYino_|iG81j}r%D*p^bWBI0*EfF`@b?`Gxm9eI+9uxCbeit9-z=m5|lf#^G-(8Oaso^{gyw^ndZI|w;1jx{F)iuyo{XWF-q`CmLagAmW<d6ZeJB$(X
`EV$71xkLpm|BgKNec5jV<<H1PK&h(CE9cVLrNeNr=1Xrf7)NFW1WF1?;!BibKn{_S=VC({-pmD8Xh&JdT#-$>D12sl~=pMDc^RBquHK=$MnLJ-t^nZg
1Z+#?@8R8DnC-Cju0FOB})({X<<bL&*=MGfm}l#Op>c<0%@MbgEh@;q>Z13wPX0BH3X1sO%?jON9+=3kX+`2mu!kM8T1h0oz(2GC(7b~2Nt*-zm*xYcK
Nv`l|0DGP;5Y9$&9cu7|veDZ45=?3IU_%cglK&$vnFxMEX~Sdk$VXoDpew(`p>Fs8*gNocE&Vdj;)Ss>ktx%B?0f+^-N7V1ZQyJr~-)LD^61pR#G=);3
poC1qvSbDTe|-o7^~`Av1ufQ#W<K2O=yoWA6LK$ZJp=uUyUjLe6C2GskJ+yu-?<wILXtCur+;3FRMa{#I5mPzh0Gu?8*;&t!j1d9msT7r~#TqRZ-PM<)
?msjhvbIrA*vE94qw@8XblK!fg%BiGM4k(34MviRu1sLWYM>%sK>9_f!EOjyE5+I3Ml!O`bLIBY8gmyl%@u$h56M43xSmSIu%RrX7+hzQ=4aR~BJiPg4
N&$5l9D5{_4tG~j=!pFuftDR2qlDI9@k+_5fUY8jWr*_6;sNA<EB-;CFb$L*Q{4;P-n9BRy~VlA=UuAV^Th&1CiTMN5#o2Qf5ZJuN%~Tn;ldo|HWF2VL
ULgD4hHw;Ao(X(#uqq(_iWms+&yb;A?$W)lPjvQ`+9~YoVnbEaX@>(znV%s<>s!eT`s_h>xYaD_PA%Z>4XZyaE-{z)B|s$ivM93qF=W?`ENZV0-L5yFG
B=YUE7wx#dzc$5~UR;YxaHR=f@SkzG0?PEsODd2ZF&=BrWx0hbl8G@WjPS(x=T3K~B3E9^?jf{B#XP^6UjLB4AnSm1KS-*-CP~Uj0ms+}w~q0$TUVp&c
e}iJ{Ex<flLqyo}xT88&Y=1W0>p9PDP)y8bdYJWc}r!K=~ATOVHbR42S*u!wG}Rjke9S+W#l7O!VZOBJbjAB^zy0g;Ng_IHq1Q~m{Ls|7ztE}mEk^gzK
TVuXG^;=2zR;p9P}fpEGX;<^A$z%1QxTBz)(8dDsR1hcpY07YdiL4)-Pf=>LMJZv|!4_f<-5RiUC!&ei#E@`)_Ok7p;x2)L8`)qYXVnwpcAvsqL!iQS+
%SZ<j(^Bf-hw;gr_)dw?w+eY(t2lHA_iuI4j3F-RN0qmN+NMcu3-#utH{2w44VC}K6-Pb!_3TT!Ssf5_=T{-(rC9{uDA08I<=-fmmJcK+ad_v@$+T;03
uo^L|AYvF)BbKZX*ID@j(KgswvO7?L4q5#+X_*TgEt-aL4<9La12$w-Z*#L;-v#mU2+lq@JNw?94oaDxstkO0&lkp)j|&v-4N~^1t^*RomnuDE4x{)%P
I_;znz<DCW!gCji_ZzT0Ey_K}!O$GnlD~?R?Y_W*+^UGS7-cwGEy;G~t&`NJ3D<V{y{eC(p?zy#%n)f0AvTA4CF`DP4t@fTA|?Br^q_Dxn%?!QFdrCj!
uo5A80)L)ZXC5NZqMk`o=U40l!t^R1&oXhbu{Jx5jWntM3wpMwH4V~3loG&9m9Y}?HA-x>5<bt?e_`SE9V^_90f1O=K9{xqaY#+yN4QKZnThQ-bsAB5#
zlxAD^GyYt+drPF$DRy)#p;{>R{wLNy^3tvTKunZcq`>*17?bLnNAE`r&}BcLElHt%SX}fQSNlM76e{q>!yg|Ms2Sg5UFF{`E3q}WUmTNoU46iLt456P
xpd1WUa7KcedySHa?(nX=Rul;DMVrCFZ0o|=}3DH%b9e&8?-Rwwy%kn&~k;R@jr4bO6q-co2l$iwSM?|wd*v02ga#pK;ub97q$D7Sp5U+R8R?Ipkyj3<
L!%J1y*jy^<1kb1^afL5!<+<vn`5J+IT#~La)zIUm^$@G5Gw4P52}X+MVn2bvjkTe?wS%3vkk7f#O0R;?y-J{pAuHTmty}R`ck%WL^|p;Yp(an*R8T6g
IEcK?E^5`$f0l)z15YY_xxl7Nc4-?`}1dA$N5GOahCI5W#<s@*oU(P4GLrj(6v`QTg91+9`Uak9<n7{U_TsXQ&n-k~kz~uvUl)d%1UJZ~>YDEp2%!;!(
_w(+z8(WuM_e9IdFVEL@?*Asb*kBxMMf4v#Ts%U=k1uGz-}AiYKPH2N==>vl1Xi;>VDlnMKy%Gq|%(^n2)rDorAvAepVgS6hyZAp4mzZC;42FQs9lfo$
yMrY2q-7ek<&Xj0t!yd0&1iZ}UXBkf;NAZ3(FO!IwSlygJ>cVr%Uc#=H(&Uw23731GHfkW&QrgzA!YU9rgf}%`6K3i~=gZm1b0JwnOO)DnGPJ0poo`B}
Ia)&vbhN|HyB8aG*q~&`_8x96dmtnZfN_B#`f5&A_R|mohVHHGY>O8+FWiN}c|`#jKr5^2x*){;fh8L&NuSV}>hn4P1B*Mn{N%#~T=Mlwd+{2$MPB;$p
%!C%p<Om!dxaSS(yIUk*q1&Wr~LQIG%y}lWX$0MB6qS}MUf2O!<9rw0$DvjF=yfQZSeMW_A}D8b>r-F&&=Kz)QIGD83dYXlB4<ouoAi`E}>el+JMavOE
<&xjf>#wa7cBrnvKSKBy&j`7IW;GyP+ued>P{5H9o-pyol_w!j%(Mc~6yXO{?#<S-+WOIvSP?C@}ud(%KbnIv&;KsDy`{oP*_|Um{ya8-Vz%5cme_J*j
E0tI@lax(_hcdTlGTNlwkpSv>Qb)9`3B?>1t8i4+cOavi9=zJdhz`GGmk*c=)g#T~T(J6sA}eUpY|Xn|aIYhBl<a~17}4D4*hS+%Gqe_I>FAX4!=&w|@
VQN^<~<YM{5a8kdeUi65_H~dW*00!y9G%xUB?qb^7Xl94IRE2E=1RO3u$~YwJhz<j9(=$LGr7E~Ypv+;Ajj$qS;~VswGhp6ZSPM}{3z09!=`N*%n_ACP
rnd{k)QOyha1E`h7e%yeBN*D`(3A1^YoB^GZuisj$6%i%hCPii-;2n`ZP;wOgKzQVc&qhpxIqaCTczc;RP+;K*JC*`UQ^NswDdn7PrcB_=?S`!ylV?`#
2I-|+TLjV?dmrarV+N-glw752)h|4#v@2C#<+bJS=fUN47D1~uw$WPKR?UaTveCye8gHHTV_pJqt?fI$N`ThWW+XP=Q1^yaNWE$8lzxyXbItmGqJi;!g
LvDmEk*FM)A*(V<n&dsj7m3`g=H|q~vc_9jGaB9KRtYDj~VL?+#yBq{3>wwn_PxwD@8oZ~_p9!PTSn!Tm9k(ZgX&{t$)k={9iKiy!E(@(Q#&l%a5#+%3
;F_2l%mqn|Wiuw~^=7?%soa+9~XJg%L{o`*UCfA<XJX^Eb!VA^;K0xt?nd!oLpM@&PqV8gdLMRT!{3XK(v)cm9BnD}Itfh<C_^KPx`n9|F%K(RWooTj7
XY0KCeCESqrd|{JW^w`=AQ<poWHyUrwk4XBy9_ELd?R+RwX~pwR71nsJpLg_t*zBfFVAbpii@z%G88un0@zGz0OS+t^-3~VghiXA2*SO346)7;SMG=*c
kQYeQVYmda5*E$4jxFW~o(v)FF1O%{x8|br8AUZ36a<W0z{w5NyC7>QyF&E_X~3kFTiqY^STOej@;GFu;tVtfS^Md{=w7Z<yP=uzimNIAR|?zk)*FTVf
T$^W)Y`aknZcAqgj4tv_pnX;AxLGU#Y3t|L7e_k8Xr&&p_$6&@RTRO?j+{u;LnoZy%$Hf1By1a;>BB$zsw!|sKgMhrioF-li$=s@BoFC{P|(ZYEUaki&
RgTg16hLc(H~H(0qdZ2L-wT-C^KG0;@-eXXCRTzPzqq*Ards%JhnpX*n|Z#Kk>xsrAr$)29xM0wek|*vRLLJ}yOe+G5B6oqVj`lJnGW<oEF_<uO(93d)
d0AK;`2Ww3}+T5qcGJl@sm#JhODL%f}3qLlZ_!o!%2g`e88R8iy|@mGqMLn+`1_;ZfRLS+zN;F#I*D*@erDt$uiL~MiznM`9JRM=tHHm9$w6W!CjaH*1
}0=wwWiLBMQr4tQOEtSf}nD=l_Gk27xa2l7rF^OTxhd^Zp+41FT=n5rG1XYW@Umn+sFg9a^ISbua4OSR~YO3dL4gFIwp!=r4V;o^^n4>J$w;9_?w_v7l
4<w33GpBKi&Gk_mW;HASF;!xJ1p)vrB@mH*x0n1DCm{e=$=YZ;Yp}bEZ@RiL<aQNl-8K>m0!?i}N3d~MrX%ugx1Y}aE~Df^k;$a9V(B@8?Hf02fe>p^2
Q9!qIW9x`MImnIB8-LE$OR{S`Q|g}AMW99Qk13-Gk_Y~PRZWCF15j!^OROsQJt{BK>hQCw;!+^<rWO!zQk8>>^gEG(W015Dx@3hSw`EN);EQcKNJdaP_
ymiDNS{)+HXxj5LcyWqC(0u#;=n<$*2O=qCAab-$Au9^=j01!=Jq!D=+4~I=Ni~FSvr66-@tBQcAnJYo~4+6!_D_Y5~XaDAtLfY2?rVaQ|Q%vNYxmAJP
CbBIF+#CTBv;>qeae5%RI%(VEBA0mFb6K)J)Xi0gg==7D_vMSZV`{!?kI+{5$}#NPW-mF-LkBEsBguW{|fdtj8>{X;a4o-XlXKVqEw@J=>P(&79pQb94
LHfiyVj<fG{B~g%eKjUzL&JfFOat`!2HOJs@3D5@F+7}!wi!rK}etW4ea4!*TIi0|MWP;*u6xxJ_wdm2Q9Hd;<Aq5%Qq2vPl(2*-lG!l%9QK-qIC+Fx+
?6rhskAu%@ftHxToh*}Rb}dIpwP;N)&t5IIiZ+d5&rao$$7gTiqvG2yh=Ees`2nC{!1gYf2pY>ztUTkz27mogLO<U?Bdt;Ss>B5%9R>4=n@pz_Qbew3w
9@dCg=$)ufS(cs^9e>LDX_^@?p%&*;n5P1{4J5McJ>W!0jK2IH{il<u;%VkCWTrH7if(qkh4@YX)ptI=@NhO%ALo;X;UXX^f|5}hdAQY1gas71=+PX)E
h`9BSqP0QVDIE;@rdOxw$A9Q6$~$QZV~HpOwi$?Qb{)5hPl_8YG#FE9jC8ipNnX#L{@Lz;B8jB0KXlt)Jj4Wl{&yCs@x;U({6N!18xw>Sod0v*1D9=c-
e6?K9p#HfbCE6e$2WaXZ*k!33vcJ+?vDgTSND+7}^9^$iQh+LIwf3wlG~QO9H07K^s3T~hsvMG2hXbrmv=y?<Oju{p@kyfMwKLO>3GnkDg<DlIrIFA}u
4%o2;MWBe+3+LNz}Ou`f!YTI}GEn{UyjwDR%7VnIa$L_$w*_>CqPi0TcFLc&d!eBo`nb+g!^J=5-zmW71ykv(E!!hk07CX5!%y=-A?AY?ysY*E8F5bp!
-*0|v!8D6CvMg!Q>yCTD05~`^Xu0+}D#@2e!)z=Vqmu97V3^mJ^&bRx@hA)ZzRTL~SW&$qbFu<Drlv;!Plbk>FrD2smXytELG@>~1{|PAw29IyqW`LS-
d^`v9U>GI(s9V3qMI_#(~I?BquX*zAB?{s>ruM4vc)VtjR#vd^F>G#EOHXaT_F|)CqHq3c$RKzsU8`a$+cgPAC@B)w8wC|DF5~+ymQVlMILCYD*_fbsI
KU7q#B-d0+EZY1scCJL}D@XOGInu-FG=jo!k!_qN20=q<0O>&C&KZo5G*@n;&fbV;oxOb%6<9$5^&JC6u(V7<W^UL!|YJ7KqbH34ryyr%gth27lh3swm
UTvt#_=GR(vM`=I^Xx;V}#G1Nuva=L`3Gb8?Qj1{zvX4^RH6SH=}ZM+OWb#g!}1p9{7BLU3Yop%kYD~#0117NWv@*&AyDJOZat~t{Fh|tFI6AWFvdle;
+p-UMPEonC8f1Ua%NTF&+)(_7&v;kI4?$T~knkdPuCSWXenq2ix`-v5dfZ0=#xTi;k?Wbo&NMjICj4j>%>C2_}I~rJ)cT0nFiv4$8i#6&AQyuZ~5?p&u
InYYKTH+cvs8sTa5%PMOAHY#0qMW{WLox@f7n^CoFGSt}u2p2C7a<Xq?N(<<p!%p!xRf(L8p{g;w=B&fdmHj6%f`KP-;eh02BryF3BplB7f^`(7H<q5p
&GR(0^38=iTm73o$3*MgI;7$8brl%v(=NvyM`-!P0t8_+;ecd8rurOdR60@{(*#L+5;+`sE{)=mwQDj-#hn~0XfA3Ly)@xD4zWI+&U;c+P&U_@!l_cg(
i_Ll$f1F*&`(Ixng9xF5I7*+<N&KoH#q`1*r}kQWpB>J<MP12(~(DR#<eLZzq85{}}Gm{gYb*>kUO^&6Y-+<18l9UYr*bF9WPOJ*Ig5Dqh_W=1!IU2Du
QR4*&oF5cWkg8HfaL00H)HfPfSL8=YPRvBYQl0ssI200dcD
"""


def main(argv):
    if argv[:1] == ["--fonts"]:
        print(f'GLYPHS = """\n{build_glyphs(argv[1] if len(argv) > 1 else DEFAULT_ROMFS)}\n"""')
    elif argv[:1] == ["--show"] and len(argv) == 3:
        for lang in LANGS:
            print(f"{lang}  {found_markup(lang, argv[1], argv[2])!r}")
        for lang in LANGS:
            print(f"{lang}  {generic_markup(lang)!r}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
