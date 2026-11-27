"""Read and write the game's text: MSBT message files (LMS "MsgStdBn"), for item-get messages and hints.

usage:
  python tools/msbt.py ROMFS                       list the language archives
  python tools/msbt.py ROMFS LANG                  list the archive's .msbt files with their message counts
  python tools/msbt.py ROMFS LANG FILE             list a file's labels with their text
  python tools/msbt.py ROMFS LANG FILE LABEL       print one message, tags shown as {tag:group,type,hex}
  python tools/msbt.py ROMFS LANG --find TEXT      every message whose text contains TEXT (case-insensitive)
FILE is a member path (EventFlowMsg/Npc_X.msbt) or a unique part of one (Npc_X).
Files saved in ./original (vanilla copies of anything we patched) are read instead of the live ones.

Text lives in one zstd-compressed SARC per language, Mals/<Lang>.Product.110.sarc.zs (USen, EUen, JPja, ...),
540 .msbt files each (EventFlowMsg/<event flow>.msbt, ActorMsg/, LayoutMsg/, StaticMsg/, ...). You read one
with read_archive, change files with Msbt and write it back with romtools.sarc_write (it repacks the vanilla
archive byte for byte) and Romfs.zs.compress(data, 1). If the archive grows, its resource size table entry
Mals/<Lang>.Product.110.sarc has to be raised.

Where the randomizer's text is
  ActorMsg/PouchContent.msbt   per item actor: <Actor>_Name, _GetMessage ("You found the Longshot!"), _GetCaption
                               (its description), _Caption (inventory), _ShopCaption, and _SecondGetMessage /
                               _SecondGetCaption (..._FourthGetCaption) for repeat gets of upgrades
  EventFlowMsg/GossipStone.msbt  GOSSIP_<AREA>_NN rumors; a stone shows the label named like its placement
                               instance (Name: GOSSIP_KOKIRI_FOREST_01), child and adult placements alike

Format (every file in this game: version 3, UTF-8, little-endian, sections LBL1 + TXT2)
  header    "MsgStdBn", byte order mark, encoding (0 UTF-8, 1 UTF-16, 2 UTF-32), version, section count, file size
  section   magic, body size, 8 reserved bytes, body; padded with 0xAB to 16 bytes (the last one too)
  LBL1      hash table: bucket count, (label count, offset) per bucket, then each bucket's labels as
            (u8 length, name, u32 message index), in message order; bucket = label_hash(name) % bucket count
            (see default_buckets). The game finds a message by "File:Label" (event flow MessageId
            'EventFlowMsg/GossipStone:Talk_12', or a placement's instance name for gossip stones).
  TXT2      message count, offsets, then the messages, each ending with a null character. Inside a message a
            tag is 0x0E group type size params (u16 fields, size in bytes) and a close tag 0x0F group type
            (no close tags in this game). Characters are in the file's encoding, tag fields in its byte order.
Other sections (ATR1, TSY1, NLI1, ...) are kept as raw bytes; this game has none.
"""
import glob
import os
import re
import struct
import sys

HASH_MUL = 0x492
PAD = b"\xab"
ENCODINGS = {0: "utf-8", 1: "utf-16", 2: "utf-32"}
UNIT = {0: 1, 1: 2, 2: 4}


def label_hash(name, buckets):
    h = 0
    for c in name.encode("utf-8"):
        h = (h * HASH_MUL + c) & 0xFFFFFFFF
    return h % buckets


def default_buckets(count):
    """The bucket count Nintendo's tool picks for a label count, which is the smallest prime above count / 2, at
    most 101 (true for all 8640 files). Msbt keeps a file's own count when labels are added. The game reads it
    from the file so any count works, but set m.buckets = default_buckets(len(m.labels)) to match a fresh build."""
    p = count // 2 + 1
    while any(p % d == 0 for d in range(2, int(p ** 0.5) + 1)) or p < 2:
        p += 1
    return min(p, 101)


def misplaced_labels(data):
    """Labels of a written .msbt that a lookup wouldn't find, either not in the bucket their hash points to or
    pointing at a message that doesn't exist. Reads the label table directly, so it's a check independent of Msbt."""
    e = "<" if data[8:10] == b"\xff\xfe" else ">"
    nsec = struct.unpack_from(e + "H", data, 0x0E)[0]
    p, sections = 0x20, {}
    for _ in range(nsec):
        n = struct.unpack_from(e + "I", data, p + 4)[0]
        sections[data[p:p + 4]] = data[p + 0x10:p + 0x10 + n]
        p = (p + 0x10 + n + 15) & ~15
    b, count = sections[b"LBL1"], struct.unpack_from(e + "I", sections[b"TXT2"], 0)[0]
    nb, bad = struct.unpack_from(e + "I", b, 0)[0], []
    for k in range(nb):
        cnt, off = struct.unpack_from(e + "II", b, 4 + 8 * k)
        for _ in range(cnt):
            n = b[off]
            name = b[off + 1:off + 1 + n].decode("utf-8")
            if label_hash(name, nb) != k or struct.unpack_from(e + "I", b, off + 1 + n)[0] >= count:
                bad.append(name)
            off += 5 + n
    return bad


class Tag:
    """A control tag inside a message, kept as raw bytes so it writes back exactly.
    close=True is an end tag (0x0F group type, no parameters)."""
    __slots__ = ("group", "type", "params", "close")

    def __init__(self, group, type_, params=b"", close=False):
        self.group, self.type, self.params, self.close = group, type_, bytes(params), close
        if close and self.params:
            raise ValueError("a close tag has no parameters")

    def __eq__(self, o):
        return isinstance(o, Tag) and self._key() == o._key()

    def __hash__(self):
        return hash(self._key())

    def _key(self):
        return self.group, self.type, self.params, self.close

    def markup(self):
        if self.close:
            return f"{{/tag:{self.group},{self.type}}}"
        return f"{{tag:{self.group},{self.type}{',' + self.params.hex() if self.params else ''}}}"

    __repr__ = markup


# Markup: text with tags as {tag:g,t,hex}
_MARKUP = re.compile(r"\{\{|\}\}|\{(/?)tag:(\d+),(\d+)(?:,([0-9a-fA-F]*))?\}|[{}]")


def to_markup(segments):
    """Message segments as one string: tags as {tag:group,type,hex} / {/tag:group,type}, braces doubled."""
    return "".join(s.markup() if isinstance(s, Tag) else s.replace("{", "{{").replace("}", "}}") for s in segments)


def from_markup(text):
    """Inverse of to_markup."""
    out, pos = [], 0
    for m in _MARKUP.finditer(text):
        out.append(text[pos:m.start()])
        tok = m.group(0)
        if tok in ("{{", "}}"):
            out.append(tok[0])
        elif tok in ("{", "}"):
            raise ValueError(f"lone {tok!r} at {m.start()} in markup (write {tok * 2} for a literal brace)")
        else:
            close, g, t, hx = m.groups()
            if close and hx:
                raise ValueError(f"close tag with parameters: {tok}")
            out.append(Tag(int(g), int(t), bytes.fromhex(hx or ""), close=bool(close)))
        pos = m.end()
    out.append(text[pos:])
    return _merge(out)


def _merge(segments):
    """Join neighbouring strings and drop empty ones (the shape a parsed message has)."""
    out = []
    for s in segments:
        if isinstance(s, str):
            if not s:
                continue
            if out and isinstance(out[-1], str):
                out[-1] += s
                continue
        elif not isinstance(s, Tag):
            raise TypeError(f"message segment must be str or Tag, not {type(s).__name__}")
        out.append(s)
    return out


def plain(segments):
    return "".join(s for s in segments if isinstance(s, str))


# MSBT
class Msbt:
    """One .msbt file. labels is {label: message index} in file order, and messages holds a list of segments
    (str and Tag) per message. dump() writes the file back, and unchanged files come back byte for byte."""

    def __init__(self, data):
        if data[:8] != b"MsgStdBn":
            raise ValueError(f"not an MSBT file: {data[:8]!r}")
        self.bom = data[8:10]
        if self.bom not in (b"\xff\xfe", b"\xfe\xff"):
            raise ValueError(f"bad byte order mark {self.bom!r}")
        self.e = e = "<" if self.bom == b"\xff\xfe" else ">"
        self.unk_0a, self.encoding, self.version, nsec, self.unk_10, _size = struct.unpack_from(e + "HBBHHI", data, 0x0A)
        self.reserved = data[0x16:0x20]
        if self.encoding not in ENCODINGS:
            raise ValueError(f"unknown text encoding {self.encoding}")
        self.unit = UNIT[self.encoding]
        order = "little" if e == "<" else "big"
        self.codec = ENCODINGS[self.encoding] + ("" if self.unit == 1 else "-le" if e == "<" else "-be")
        self.errors = "surrogateescape" if self.unit == 1 else "surrogatepass"  # keep odd bytes / lone surrogates
        self._ctl = {c: c.to_bytes(self.unit, order) for c in (0, 0x0E, 0x0F)}
        self._ctl_re = re.compile(b"|".join(re.escape(v) for v in self._ctl.values()))

        self.sections = []  # [magic, reserved 8 bytes, raw body (None for LBL1/TXT2, rebuilt on dump)]
        self.buckets, self.labels, self.messages = 0, {}, []
        p = 0x20
        for _ in range(nsec):
            magic = data[p:p + 4].decode("ascii")
            n = struct.unpack_from(e + "I", data, p + 4)[0]
            body = data[p + 0x10:p + 0x10 + n]
            if len(body) != n:
                raise ValueError(f"section {magic} runs past the end of the file")
            raw = body
            if magic == "LBL1":
                self._read_lbl1(body)
                raw = None
            elif magic == "TXT2":
                self._read_txt2(body)
                raw = None
            self.sections.append([magic, data[p + 8:p + 0x10], raw])
            p = (p + 0x10 + n + 15) & ~15
        if not any(s[0] == "TXT2" for s in self.sections):
            raise ValueError("no TXT2 section")
        if any(not 0 <= i < len(self.messages) for i in self.labels.values()):
            raise ValueError("a label points past the last message")

    # Read
    def _read_lbl1(self, b):
        e = self.e
        self.buckets = struct.unpack_from(e + "I", b, 0)[0]
        for k in range(self.buckets):
            cnt, off = struct.unpack_from(e + "II", b, 4 + 8 * k)
            for _ in range(cnt):
                n = b[off]
                name = b[off + 1:off + 1 + n].decode("utf-8")
                if name in self.labels:
                    raise ValueError(f"label {name!r} appears twice")
                self.labels[name] = struct.unpack_from(e + "I", b, off + 1 + n)[0]
                off += 5 + n

    def _read_txt2(self, b):
        cnt = struct.unpack_from(self.e + "I", b, 0)[0]
        self.messages = [self._decode(b, o) for o in struct.unpack_from(f"{self.e}{cnt}I", b, 4)]

    def _decode(self, b, p):
        u, e, out, start = self.unit, self.e, [], p
        while True:
            m = self._ctl_re.search(b, p)
            if not m:
                raise ValueError("message without a terminating null")
            p = m.start()
            if (p - start) % u:  # matched across two characters, look again one byte on
                p += 1
                continue
            if p > start:
                out.append(b[start:p].decode(self.codec, self.errors))
            c = m.group(0)
            if c == self._ctl[0]:
                return out
            if c == self._ctl[0x0E]:
                g, t, n = struct.unpack_from(e + "HHH", b, p + u)
                out.append(Tag(g, t, b[p + u + 6:p + u + 6 + n]))
                p += u + 6 + n
            else:
                g, t = struct.unpack_from(e + "HH", b, p + u)
                out.append(Tag(g, t, close=True))
                p += u + 4
            start = p

    # Write
    def _encode(self, segments):
        e, out = self.e, bytearray()
        for s in segments:
            if isinstance(s, Tag):
                if s.close:
                    out += self._ctl[0x0F] + struct.pack(e + "HH", s.group, s.type)
                else:
                    out += self._ctl[0x0E] + struct.pack(e + "HHH", s.group, s.type, len(s.params)) + s.params
            else:
                out += s.encode(self.codec, self.errors)
        return bytes(out + self._ctl[0])

    def _lbl1(self):
        e, n = self.e, self.buckets
        slots = [[] for _ in range(n)]
        for name, idx in self.labels.items():
            slots[label_hash(name, n)].append((name.encode("utf-8"), idx))
        head, body = bytearray(struct.pack(e + "I", n)), bytearray()
        for s in slots:
            head += struct.pack(e + "II", len(s), 4 + 8 * n + len(body))
            for name, idx in s:
                body += bytes([len(name)]) + name + struct.pack(e + "I", idx)
        return bytes(head + body)

    def _txt2(self):
        blobs = [self._encode(m) for m in self.messages]
        out = bytearray(struct.pack(self.e + "I", len(blobs)))
        off = 4 + 4 * len(blobs)
        for b in blobs:
            out += struct.pack(self.e + "I", off)
            off += len(b)
        return bytes(out) + b"".join(blobs)

    def dump(self):
        e = self.e
        out = bytearray(0x20)
        for magic, reserved, raw in self.sections:
            body = self._lbl1() if magic == "LBL1" else self._txt2() if magic == "TXT2" else raw
            out += magic.encode("ascii") + struct.pack(e + "I", len(body)) + reserved + body
            out += PAD * (-len(out) % 16)
        out[:0x20] = struct.pack(e + "8s2sHBBHHI10s", b"MsgStdBn", self.bom, self.unk_0a, self.encoding, self.version,
                                 len(self.sections), self.unk_10, len(out), self.reserved)
        return bytes(out)

    # Editing
    def __contains__(self, label):
        return label in self.labels

    def __len__(self):
        return len(self.messages)

    def label_of(self, index):
        return next((k for k, v in self.labels.items() if v == index), None)

    def get(self, label):
        """The message's segments, as a copy (change it with set)."""
        return list(self.messages[self.labels[label]])

    def text(self, label):
        """The message's text without its tags."""
        return plain(self.messages[self.labels[label]])

    def markup(self, label):
        """The message with its tags as {tag:group,type,hex} (see to_markup)."""
        return to_markup(self.messages[self.labels[label]])

    def set(self, label, segments):
        self.messages[self.labels[label]] = self._checked(segments)

    def set_markup(self, label, text):
        self.set(label, from_markup(text))

    def set_text(self, label, text):
        """Changes a message's text and keeps its tags.

        text as a list of strings: one per text run of the message (the text between its tags), in order.
          Every tag stays where it is. runs(label) gives the current ones.
        text as a string: the tags before the first text run (speaker, animation and voice setup) and after
          the last one stay. The tags between runs (colour, pauses, page breaks) get dropped, because there's
          no telling where they belong in new text. Use runs or set_markup to keep or place them."""
        segs = self.messages[self.labels[label]]
        if isinstance(text, str):
            first = next((i for i, s in enumerate(segs) if isinstance(s, str)), len(segs))
            last = max((i for i, s in enumerate(segs) if isinstance(s, str)), default=len(segs) - 1)
            self.set(label, segs[:first] + [text] + segs[last + 1:])
            return
        text = list(text)
        n = len(self._runs(segs))
        if len(text) != n:
            raise ValueError(f"{label}: {len(text)} strings given for {n} text runs")
        it = iter(text)  # a run is the text before the first tag, then the text after each tag
        out = [next(it)]
        for s in segs:
            if isinstance(s, Tag):
                out += [s, next(it)]
        self.set(label, out)

    @staticmethod
    def _runs(segs):
        runs = [""]
        for s in segs:
            if isinstance(s, Tag):
                runs.append("")
            else:
                runs[-1] += s
        return runs

    def runs(self, label):
        """The message's text runs: the text before its first tag, then the text after each tag (often "")."""
        return self._runs(self.messages[self.labels[label]])

    def add(self, label, value=""):
        """Adds a message under a new label (value is a string in markup form, or segments) and returns its index.
        The label table gets rebuilt on dump with the file's bucket count."""
        if label in self.labels:
            raise ValueError(f"label {label!r} exists")
        name = label.encode("utf-8")
        if not 0 < len(name) < 256:
            raise ValueError(f"label must be 1 to 255 bytes: {label!r}")
        extra = [s[0] for s in self.sections if s[0] not in ("LBL1", "TXT2", "NLI1")]
        if extra:  # per-message sections (attributes, styles) would need a matching entry
            raise NotImplementedError(f"adding a message to a file with {', '.join(extra)} sections")
        if not any(s[0] == "LBL1" for s in self.sections):
            raise ValueError("file has no label section")
        segs = self._checked(from_markup(value) if isinstance(value, str) else value)
        self.messages.append(segs)
        self.labels[label] = len(self.messages) - 1
        return self.labels[label]

    def _checked(self, segments):
        segs = _merge(segments)
        for s in segs:
            if isinstance(s, str) and any(c in s for c in "\x00\x0e\x0f"):
                raise ValueError(f"text contains a control character (null, 0x0E or 0x0F): {s!r}")
            if isinstance(s, Tag) and (not 0 <= s.group < 0x10000 or not 0 <= s.type < 0x10000 or len(s.params) > 0xFFFF):
                raise ValueError(f"tag out of range: {s!r}")
        return segs


# Archives
def archives(romfs):
    """{language: romfs-relative path of its newest text archive}."""
    out = {}
    for p in sorted(glob.glob(os.path.join(romfs, "Mals", "*.Product.*.sarc.zs")),
                    key=lambda p: int(os.path.basename(p).split(".")[2])):
        out[os.path.basename(p).split(".")[0]] = "Mals/" + os.path.basename(p)
    return out


def read_archive(fs, lang):
    """{member name: .msbt bytes} of a language's text archive (fs: romtools.Romfs)."""
    from romtools import sarc_files
    rel = archives(fs.root).get(lang)
    if not rel:
        raise SystemExit(f"no text archive for {lang!r}; have: {', '.join(archives(fs.root))}")
    return sarc_files(fs.read(rel))


# CLI
def _one_line(s, width=100):
    s = s.replace("\n", "\\n")
    return s if len(s) <= width else s[:width - 3] + "..."


def _member(files, name):
    if name in files:
        return name
    hits = [n for n in files if name.lower() in n.lower()]
    exact = [n for n in hits if os.path.splitext(os.path.basename(n))[0].lower() == name.lower()]
    if len(exact) == 1 or len(hits) == 1:
        return (exact or hits)[0]
    raise SystemExit(f"{name!r} matches {len(hits)} files" + (": " + ", ".join(sorted(hits)[:20]) if hits else ""))


def main(argv):
    sys.path.insert(0, os.path.dirname(__file__))
    from romtools import Romfs
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    romfs = argv[0]
    if len(argv) == 1:
        for lang, rel in archives(romfs).items():
            print(f"{lang}  {rel}")
        return
    fs = Romfs(romfs, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "original"))
    files = read_archive(fs, argv[1])
    if len(argv) == 2:
        for name in sorted(files):
            print(f"{len(Msbt(files[name])):5}  {name}")
        print(f"{len(files)} files")
        return
    if argv[2] == "--find":
        if len(argv) < 4:
            raise SystemExit("usage: msbt.py ROMFS LANG --find TEXT")
        want = " ".join(argv[3:]).lower()
        for name in sorted(files):
            m = Msbt(files[name])
            for label, i in m.labels.items():
                if want in plain(m.messages[i]).lower():
                    print(f"{name}  {label}\n    {_one_line(to_markup(m.messages[i]), 300)}")
        return
    name = _member(files, argv[2])
    m = Msbt(files[name])
    if len(argv) == 3:
        print(f"{name}: {len(m)} messages, {m.buckets} label buckets, version {m.version}, "
              f"{ENCODINGS[m.encoding]}, sections {' '.join(s[0] for s in m.sections)}")
        for label, i in sorted(m.labels.items(), key=lambda kv: kv[1]):
            print(f"{i:4}  {label:40} {_one_line(plain(m.messages[i]))}")
        return
    label = argv[3]
    if label not in m:
        raise SystemExit(f"no label {label!r} in {name}")
    print(m.markup(label))


if __name__ == "__main__":
    main(sys.argv[1:])
