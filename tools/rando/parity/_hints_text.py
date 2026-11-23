"""Hint text for the remake's message boxes: OoT Randomizer text -> remake MSBT markup and plain text.

OoTR writes N64 message bytes: \\x01 new line, \\x04 new box, \\x05\\x4N colour (\\x40 white = end of colour), \\x0F the
player's name, plus codes the remake has no use for (instant text, icons, sounds, choices). Its hint strings also
use '#' to mark coloured words (GossipText colours them in order) and '&' / '^' for new line / new box.
The remake's text (tools/msbt.py) has:
  {tag:0,3,XXXX}  colour XXXX (u16 little-endian; 0000 = the game's highlight, ffff = back to normal)
  {tag:0,4}       new box (page)
  "\\n"            new line; at most 3 lines a box (data/rando/hints_targets.json "box")
Text gets re-wrapped for the remake's box, since OoTR's line breaks were made for the N64 font.

A message is rebuilt on top of its vanilla version (data/rando/hints_messages.json). The tags before its first text
(speaker, voice, style) stay, vanilla pages listed in keep_pages stay as they are, and new pages follow. Two forms
get written for each message and language:
  "markup": the whole message with colours and page breaks (needs make_patch.py support)
  "text":   what make_patch.py can write today (Msbt.set_text): one string, or one string per vanilla text run
            (the tags between runs stay where they are), so new pages go into vanilla pages' first runs.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TARGETS = os.path.join(HERE, "data", "rando", "hints_targets.json")
MESSAGES = os.path.join(HERE, "data", "rando", "hints_messages.json")
NAMES = os.path.join(HERE, "data", "rando", "hints_names.json")
_cache = {}


def _load(path):
    if path not in _cache:
        _cache[path] = json.load(open(path, encoding="utf-8"))
    return _cache[path]


def targets():
    return _load(TARGETS)


def vanilla(file, label):
    """{lang: vanilla markup} of one message."""
    key = f"{file}:{label}"
    msgs = _load(MESSAGES)["messages"]
    if key not in msgs:
        raise KeyError(f"{key} is not in data/rando/hints_messages.json: run tools/rando/parity/_hints_extract.py")
    return msgs[key]


def names(lang):
    return _load(MESSAGES)["names"][lang]


def languages():
    return sorted(_load(MESSAGES)["names"])


# OoTR names -> the remake's names (English)
def remake_names(text):
    """OoTR's English place and item names -> the remake's (data/rando/hints_names.json), in OoTR control text
    or '#' marked text. An article OoTR keeps outside the colour ("the \x05ASacred Forest Meadow") may sit
    before the colour code."""
    table = _load(NAMES)["replace"]
    # colour codes as private-use characters while replacing (their second byte, \x40-\x47, is a letter)
    text = re.sub(r"\x05([\x40-\x47])", lambda m: chr(0xE000 + ord(m.group(1))), text)
    start, end = r"(?<![A-Za-z'])", r"(?![A-Za-z])"
    for old, new in sorted(table.items(), key=lambda kv: -len(kv[0])):
        if old.startswith("_"):
            continue
        art, rest = _split_article(old)
        nart, nrest = _split_article(new)
        if art:
            rx = re.compile(start + re.escape(art) + "([-]|#)?" + re.escape(rest) + end)
            text = rx.sub(lambda m: (nart or "") + (m.group(1) or "") + nrest, text)
        else:
            text = re.sub(start + re.escape(old) + end, lambda m: new, text)
    # OoTR's "Bombchus (20 pieces)" -> the remake's "20 Bombchus"
    text = re.sub(start + r"([A-Z][A-Za-z']*(?: [A-Z][A-Za-z']*)*) \((\d+) pieces\)", r"\2 \1", text)
    return re.sub("[-]", lambda m: "\x05" + chr(ord(m.group(0)) - 0xE000), text)


def _split_article(s):
    for a in ("the ", "The ", "a ", "an "):
        if s.startswith(a):
            return a, s[len(a):]
    return "", s


# Parsing OoTR text
NL, PAGE = "\n", "\f"
SKIP_ARG = {0x05: 1, 0x06: 1, 0x07: 2, 0x0C: 1, 0x0E: 1, 0x12: 2, 0x13: 1, 0x14: 1, 0x15: 3, 0x1E: 1, 0xF0: 1, 0xF1: 1}
COLOUR_NAMES = {0x41: "Red", 0x42: "Green", 0x43: "Blue", 0x44: "Light Blue", 0x45: "Pink", 0x46: "Yellow",
                0x47: "Black"}
# OoTR's controller-button glyphs (N64 font codes 0x9F-0xAA, written as those characters or as the unicode glyphs
# of Messages.CHARACTER_MAP). Some junk hints use them. The remake's font has no such characters, so we spell them
# out with OoTR's names for them (Messages.SPECIAL_CHARACTERS, "[A]").
_BUTTON_NAMES = {0x9F: "[A]", 0xA0: "[B]", 0xA1: "[C]", 0xA2: "[L]", 0xA3: "[R]", 0xA4: "[Z]", 0xA5: "[C Up]",
                 0xA6: "[C Down]", 0xA7: "[C Left]", 0xA8: "[C Right]", 0xA9: "[Triangle]", 0xAA: "[Control Stick]"}
BUTTONS = {chr(k): v for k, v in _BUTTON_NAMES.items()}
BUTTONS.update(zip("ⒶⒷⒸⓁⓇⓏ⯅⯆⯇⯈",
                   [_BUTTON_NAMES[k] for k in range(0x9F, 0xA9)]))


def mark(text, colors=None):
    """OoTR '#' marked text (and '&' / '^') -> control text, colouring marked words like Hints.color_text."""
    colors = list(colors or [])
    out, colour = [], "Red"
    parts = text.split("#")
    for i, part in enumerate(parts):
        if i % 2 == 1 and i < len(parts) - 1:
            if colors:
                colour = colors.pop(0)
            code = {v: k for k, v in COLOUR_NAMES.items()}.get(colour)
            out.append((f"\x05{chr(code)}" if code else "") + part + ("\x05\x40" if code else ""))
        else:
            out.append(part)
    return "".join(out).replace("&", "\x01").replace("^", "\x04")


def tokens(control, player="Link"):
    """Control text -> [(text, colour name or None)], with NL and PAGE as text tokens of their own."""
    out, colour, buf = [], None, []
    control = re.sub(r"\$\{[0-9A-Fa-f ]*\}", "", control)  # raw N64 bytes in OoTR's text (sound effects)

    def flush():
        if buf:
            out.append(("".join(buf), colour))
            buf.clear()
    i = 0
    while i < len(control):
        c = control[i]
        o = ord(c)
        if o == 0x01 or c == "\n":
            flush()
            out.append((NL, None))
        elif o == 0x04:
            flush()
            out.append((PAGE, None))
        elif o == 0x05:
            flush()
            code = ord(control[i + 1]) if i + 1 < len(control) else 0x40
            colour = COLOUR_NAMES.get(code)
            i += 1
        elif o == 0x0F:
            buf.append(player)
        elif o in SKIP_ARG:
            i += SKIP_ARG[o]
        elif o < 0x20 and c not in "\t":
            pass  # end, instant text, keep open, event, choices...: nothing to show
        elif c == "\t":
            buf.append(" ")
        elif c in BUTTONS:
            buf.append(BUTTONS[c])
        else:
            buf.append(c)
        i += 1
    flush()
    return out


# Wrapping into the remake's boxes
def wrap(toks, width, lines_per_page=3):
    """Tokens -> pages. A page is a list of lines and a line is a list of (text, colour) spans. Words wrap at `width`
    characters, explicit new lines stay, and a box holds `lines_per_page` lines before a new box starts."""
    pages, page, line, length = [], [], [], 0

    def end_line():
        nonlocal line, length, page
        while line and isinstance(line[-1], tuple) and line[-1][0] == " ":
            line.pop()
        page.append(_merge(line))
        line, length = [], 0
        if len(page) == lines_per_page:
            end_page()

    def end_page():
        nonlocal page
        if page and any(page_line for page_line in page):
            pages.append(page)
        page = []

    for text, colour in toks:
        if text == NL:
            end_line()
            continue
        if text == PAGE:
            if line:
                end_line()
            end_page()
            continue
        for word in re.findall(r"\S+|\s+", text):
            if word.isspace():
                if line:
                    line.append((" ", colour))
                    length += 1
                continue
            if length and length + len(word) > width:
                # a word glued to the one before it (a full stop after a coloured name) moves with it
                group = []
                while line and line[-1][0] != " ":
                    group.insert(0, line.pop())
                if line:
                    end_line()
                line = group
                length = sum(len(t) for t, _ in group)
            line.append((word, colour))
            length += len(word)
    if line:
        end_line()
    end_page()
    return pages


def _merge(spans):
    out = []
    for t, c in spans:
        if out and out[-1][1] == c:
            out[-1] = (out[-1][0] + t, c)
        else:
            out.append((t, c))
    return out


def plain_pages(pages):
    return ["\n".join("".join(t for t, _ in line) for line in page) for page in pages]


# Remake markup
def esc(s):
    return s.replace("{", "{{").replace("}", "}}")


def markup_pages(pages, base_colour=None, page_prefix=""):
    """Pages -> markup. Colours become {tag:0,3,XXXX} (OoTR colour -> remake index, data/rando/hints_targets.json) and
    go back to the message's own colour (or ffff) after, with {tag:0,4} between pages."""
    colours = targets()["colors"]
    reset = f"{{tag:0,3,{base_colour}}}" if base_colour else "{tag:0,3,ffff}"
    out = []
    for n, page in enumerate(pages):
        text = []
        for i, line in enumerate(page):
            if i:
                text.append("\n")
            for t, c in line:
                if c and colours.get(c):
                    text.append(f"{{tag:0,3,{colours[c]}}}{esc(t)}{reset}")
                else:
                    text.append(esc(t))
        out.append((page_prefix if n else "") + "".join(text))
    return "{tag:0,4}".join(out)


# Building on a vanilla message
RUBY = (0, 0)  # {tag:0,0,...}: furigana over the next characters (Japanese and Chinese text)


def split_vanilla(markup):
    """Vanilla markup -> (leading tags, [page markup...], trailing tags, base colour, page prefix tags)."""
    import msbt
    segs = msbt.from_markup(markup)
    first = next((i for i, s in enumerate(segs) if isinstance(s, str)), len(segs))
    while first > 0 and isinstance(segs[first - 1], msbt.Tag) and (segs[first - 1].group, segs[first - 1].type) == RUBY:
        first -= 1  # a ruby (furigana) tag belongs to the characters after it, not to the message's set-up
    last = max((i for i, s in enumerate(segs) if isinstance(s, str)), default=len(segs) - 1)
    lead, body, trail = segs[:first], segs[first:last + 1], segs[last + 1:]
    pages, cur = [], []
    for s in body:
        if isinstance(s, msbt.Tag) and (s.group, s.type) == (0, 4):
            pages.append(cur)
            cur = []
        else:
            cur.append(s)
    pages.append(cur)
    base = None  # a colour the whole message is in (Gossip Stones, muttered lines): set first, never ended
    ends = any(isinstance(s, msbt.Tag) and (s.group, s.type) == (0, 3) and s.params.hex() == "ffff" for s in segs)
    for s in lead:
        if isinstance(s, msbt.Tag) and (s.group, s.type) == (0, 3) and s.params.hex() != "ffff" and not ends:
            base = s.params.hex()
    prefix = []
    if len(pages) > 1:  # a style tag vanilla repeats at the top of every page ({tag:1,2} in Dampe's diary)
        for s in pages[1]:
            if isinstance(s, str):
                break
            if (s.group, s.type) == (1, 2):
                prefix.append(s)
    return (msbt.to_markup(lead), [msbt.to_markup(p) for p in pages], msbt.to_markup(trail), base,
            msbt.to_markup(prefix))


def runs_of(markup):
    import msbt
    return msbt.Msbt._runs(msbt.from_markup(markup))


def build(markup, new_pages, keep_pages=(), replace_pages=None, width=50, leftover="spread"):
    """One language's message, vanilla markup plus new pages (wrapped pages, so lists of lines of spans).
    keep_pages are the vanilla pages kept before the new ones, and the others go. With replace_pages only those
    vanilla pages give way to the new ones (the new pages take the first one's place) and every other page stays.
    Returns (markup, text for make_patch today, warning or None)."""
    lead, vpages, trail, base, prefix = split_vanilla(markup)
    if replace_pages is not None:
        order = []
        for i in range(len(vpages)):
            if i == replace_pages[0]:
                order.append(("new", None))
            elif i not in replace_pages:
                order.append(("old", i))
    else:
        order = [("old", i) for i in keep_pages if i < len(vpages)] + [("new", None)]
    parts = []
    for n, (kind, i) in enumerate(order):
        if kind == "old":
            parts.append(vpages[i])
        else:
            parts.append(("" if n == 0 else prefix) + markup_pages(new_pages, base, prefix))
    full = lead + "{tag:0,4}".join(p for p in parts if p != "") + trail
    text, warning = fallback(markup, vpages, order, plain_pages(new_pages), width, leftover)
    return full, text, warning


def fallback(markup, vpages, order, new_plain, width=50, leftover="spread"):
    """What make_patch.py writes today: Msbt.set_text with one string per vanilla text run (the tags between runs stay).
    Kept pages keep their runs. Each new page goes into one vanilla page we give up, into its main run (the first
    uncoloured run with text), and the page's other runs get emptied. Pages with a font-size tag are used last, since
    the size would carry over to the hint.
    If there are more new pages than free ones, the rest joins the last one as one paragraph. If there are fewer,
    leftover "spread" spreads the lines over the free pages ("..." when there are fewer lines than pages), and leftover
    "vanilla" leaves the unused free pages as they are (a diary's other entries). With no free page the new text joins
    the last kept page.
    Returns (text, warning when a box gets > 3 lines)."""
    import msbt
    nl = chr(10)
    segs = msbt.from_markup(markup)
    _, _, _, base, _ = split_vanilla(markup)
    runs = [{"page": 0, "coloured": False, "text": "", "sized": False, "after": None}]
    page, coloured, sized = 0, False, False
    for s in segs:
        if isinstance(s, msbt.Tag):
            if (s.group, s.type) == (0, 4):
                page, sized = page + 1, False
            elif (s.group, s.type) == (0, 3):
                coloured = s.params.hex() not in ("ffff", base or "ffff")
            elif (s.group, s.type) == (0, 2):
                sized = True
            runs.append({"page": page, "coloured": coloured, "text": "", "sized": sized,
                         "after": (s.group, s.type)})
        else:
            runs[-1]["text"] += s
    kept = [i for kind, i in order if kind == "old"]
    free = [p for p in range(len(vpages)) if p not in kept]
    out = [r["text"] for r in runs]
    page_sized = {p: any(r["sized"] and r["text"].strip() for r in runs if r["page"] == p) for p in free}

    def main_run(p):
        mine = [i for i, r in enumerate(runs) if r["page"] == p]
        # Ruby tags put furigana over the characters after them, so the hint goes before the first ruby tag to keep
        # that reading off it. Without ruby it goes in the first uncoloured run with text.
        if not any(runs[i]["after"] == RUBY for i in mine):
            for i in mine:
                if runs[i]["text"].strip() and not runs[i]["coloured"]:
                    return i
        # else the run right after the page's set-up tags (speaker, voice), before its first furigana or text
        first_text = next((i for i in mine if runs[i]["text"].strip() or runs[i]["after"] == RUBY), mine[-1])
        setup = [i for i in mine if i <= first_text and runs[i]["after"] != RUBY and not runs[i]["coloured"]]
        return setup[-1] if setup else mine[0]
    if not free:
        page_no = kept[-1] if kept else 0
        last = max(i for i, r in enumerate(runs) if r["page"] == page_no)
        joined = rewrap(new_plain, width)
        out[last] = out[last].rstrip() + nl + joined
        boxes = ["".join(r["text"] for r in runs if r["page"] == page_no) + nl + joined]
    else:
        if leftover == "vanilla" and len(new_plain) < len(free):
            use = sorted(sorted(free, key=lambda p: page_sized[p])[:len(new_plain)])
        else:
            use = free
        boxes = distribute(new_plain, len(use), width)
        for k, p in enumerate(use):
            target = main_run(p)
            for i, r in enumerate(runs):
                if r["page"] == p:
                    out[i] = boxes[k] if i == target else ""
    warning = None
    worst = max(b.count(nl) + 1 for b in boxes)
    if worst > 3:
        warning = f"{worst} lines in one box until make_patch.py writes markup (needs in shared code)"
    return (out[0] if len(out) == 1 else out), warning


def distribute(pages, n, width=50):
    """n boxes from the new pages. Extra pages join the last box as one paragraph. With fewer pages than boxes the lines
    get spread over the boxes, and "..." fills boxes past the last line."""
    nl = chr(10)
    if len(pages) >= n:
        return pages[:n - 1] + [rewrap(pages[n - 1:], width) if len(pages) > n else pages[n - 1]]
    lines = nl.join(pages).split(nl)
    if len(lines) <= n:
        return lines + ["..."] * (n - len(lines))
    size, extra = divmod(len(lines), n)
    out, i = [], 0
    for k in range(n):
        take = size + (1 if k < extra else 0)
        out.append(nl.join(lines[i:i + take]))
        i += take
    return out


def rewrap(pages, width):
    """Several pages' plain text as one box, in as few lines as it can. Prose pages get re-flowed together as one
    paragraph, and list pages (every line "name: place") keep their lines.
    TODO: make_patch.py can't add page breaks today."""
    out, words = [], []

    def flush():
        line = ""
        for w in words:
            if line and len(line) + 1 + len(w) > width:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}" if line else w
        if line:
            out.append(line)
        words.clear()
    for p in pages:
        lines = p.split(chr(10))
        if all(": " in ln for ln in lines):
            flush()
            out.extend(lines)
        else:
            words.extend(p.replace(chr(10), " ").split())
    flush()
    return chr(10).join(out)
