"""password_lock (story plugin module)
In OoTR starting the seed is locked behind a password from the spoiler log, six presses of A and the C buttons.

OoTR draws the password in Main.make_spoiler (Spoiler.build_password: six notes 1..5 = PASSWORD_NOTES "A", "C down",
"C right", "C left", "C up", written to the spoiler log as "password") and its ROM asks for it on the file screen.
The remake has no file-screen hook, so a new file asks for it in the opening, after Navi's wake-up and before the
opening's autosave. That's OpeningEvent Event11, where the story plugin's start steps already run, and the password
goes first. Nothing is saved before it's entered.

The question is a system text box with choices, done the way the game does it. EventTalk ChoiceNumber /
ChoiceLabel1-4 take the options as the labels "0000", "0001"... of the MessageId's text file (like
Npc_Hylia_022_Shop_Child's "0000" I'll play), and GameSystemActor.EventQueryTalkChoice4/3 reads the answer (like
DisplayShop Event235). A text box takes at most four options, so each press is "A / C down / C right / More..." and,
after More, "C left / C up / Back". All six presses are asked before the check, so a wrong press isn't given away
(the wrong answers lead into a second chain of the same questions). Then a wrong password says so and starts over.

It's built as a GetPouchContent entry, since that file has SystemTextNPC and GameSystemActor and the ice-trap message
is shown the same way. Its text goes in EventFlowMsg/Dm_SY_Get.msbt as new labels in every language. OoTR's text is
English."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

OWNS = {"password_lock": (False, True)}
READERS = {"password": "verify"}
FILE, ENTRY = "GetPouchContent", "Rando_Password"
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
MSG = "EventFlowMsg/Dm_SY_Get:{}"
NOTES = ("A", "C down", "C right", "C left", "C up")  # OoTR's PASSWORD_NOTES, note n = NOTES[n - 1]
MORE, BACK = 5, 6  # option labels "0005", "0006"
FIRST = (0, 1, 2, MORE)  # option labels on the first page
SECOND = (3, 4, BACK)
PRESSES = 6
TEXT = {f"Rando_Password{k}": ("Enter this seed's password (the spoiler log's\n\"password\": six ocarina buttons).\n"
                               f"Button {k} of {PRESSES}:") for k in range(1, PRESSES + 1)}
TEXT["Rando_PasswordWrong"] = "Wrong password. Try again from the first button."
OPTIONS = {f"{i:04d}": t for i, t in enumerate(NOTES + ("More buttons...", "Back"))}


def _talk(label, choices):
    from parity._chests_scenes import TALK_PARAMS
    p = dict(TALK_PARAMS, MessageId=MSG.format(label), ChoiceNumber=len(choices))
    for k in range(4):
        p[f"ChoiceLabel{k + 1}"] = choices[k] if k < len(choices) else 0
    return {"actor": "SystemTextNPC", "action": "EventTalk", "params": p}


def graph(password):
    """(nodes, start) of the password entry for OoTR's password (six ints 1..5)."""
    if len(password) != PRESSES or not all(1 <= n <= 5 for n in password):
        raise ValueError(f"password {password!r}: six notes 1..5 expected")
    n = {}
    for chain in ("ok", "bad"):
        for i in range(PRESSES):
            def after(note, chain=chain, i=i):
                good = chain == "ok" and note == password[i]
                if i + 1 == PRESSES:
                    return None if good else "wrong"  # ending the entry resumes the opening
                return f"{'ok' if good else 'bad'}{i + 1}a"
            n[f"{chain}{i}a"] = dict(_talk(f"Rando_Password{i + 1}", FIRST), next=f"{chain}{i}aq")
            n[f"{chain}{i}aq"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice4",
                                  "cases": {0: after(1), 1: after(2), 2: after(3), 3: f"{chain}{i}b"}}
            n[f"{chain}{i}b"] = dict(_talk(f"Rando_Password{i + 1}", SECOND), next=f"{chain}{i}bq")
            n[f"{chain}{i}bq"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice3",
                                  "cases": {0: after(4), 1: after(5), 2: f"{chain}{i}a"}}
    n["wrong"] = dict(_talk("Rando_PasswordWrong", ()), next="ok0a")
    return n, "ok0a"


def password_of(world):
    sp = getattr(world, "spoiler", None)
    pw = list(getattr(sp, "password", None) or [])
    if len(pw) != PRESSES or not all(pw):
        raise RuntimeError("password_lock: OoTR's spoiler has no password (create_spoiler must be on)")
    return pw


def opening(settings, world):
    """Scene calls the new-file opening makes before the story plugin's start steps (story.Plan.opening)."""
    ws = getattr(world, "settings", settings)
    return [f"{FILE}:{ENTRY}"] if getattr(ws, "password_lock", False) else []


def world_plan(settings, world):
    ws = getattr(world, "settings", settings)
    if not getattr(ws, "password_lock", False):
        return {}
    pw = password_of(world)
    nodes, start = graph(pw)
    text = [{"lang": "*", "file": MSBT, "label": k, "markup": v, "add": True, "note": "password_lock"}
            for k, v in list(TEXT.items()) + list(OPTIONS.items())]
    return {"events": [{"file": FILE, "flowchart": FILE, "add_graph": ENTRY, "nodes": nodes, "start": start}],
            "text": text,
            "_gaps": {"password": {"password": pw, "notes": [NOTES[x - 1] for x in pw]}}}


def UNTESTED(settings):
    return ["password_lock (the opening asks for the spoiler's six buttons)"] if getattr(
        settings, "password_lock", False) else []


# Read-back
def verify(patch, note, romfs):
    """Walks the built entry. The right six notes end the entry, and any one wrong note reaches the 'wrong' box and
    starts over. The opening calls the entry before anything else at Event11, and the option texts exist."""
    from romtools import Romfs, sarc_files
    from evfl import Evfl
    import msbt
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    ev = fc["events"]
    ep = fc["entry_points"].get(ENTRY)
    if ep is None:
        return [f"{FILE}: no entry {ENTRY}"]

    def prm(e, k):
        return ((e.get("params") or {}).get("items") or {}).get(k, {}).get("value")

    def run(seq):
        """Answers the boxes with the notes in seq (then the right ones) and returns how the entry ended."""
        i, e, steps, wanted = 0, ev[ep["main"]], 0, list(seq)
        while steps < 400:
            steps += 1
            if e["type"] == "action":
                a = fc["actors"][e["actor"]]["actions"][e["action"]]
                if a == "EventTalk" and str(prm(e, "MessageId")).endswith("Rando_PasswordWrong"):
                    return "wrong", i
                nxt = e["next"]
                if nxt in (None, 0xFFFF):
                    return "end", i
                e = ev[nxt]
                continue
            if e["type"] != "switch":
                return f"unexpected {e['type']}", i
            talk = next(x for x in ev if x.get("next") == ev.index(e) and x["type"] == "action")
            nxt_of = {c["value"]: c["next"] for c in e["cases"]}
            labels = [prm(talk, f"ChoiceLabel{k + 1}") for k in range(prm(talk, "ChoiceNumber"))]
            want = wanted[i] - 1 if i < len(wanted) else None
            if want in labels:
                pick, i = labels.index(want), i + 1
            elif MORE in labels:
                pick = labels.index(MORE)
            else:
                return f"note {want} not offered", i
            if nxt_of.get(pick) in (None, 0xFFFF):
                return "end", i
            e = ev[nxt_of[pick]]
        return "loop", i
    pw = note["password"]
    if run(pw) != ("end", PRESSES):
        bad.append(f"{FILE}:{ENTRY}: the password {note['notes']} doesn't end the entry ({run(pw)})")
    for k in range(PRESSES):
        wrong = list(pw)
        wrong[k] = pw[k] % 5 + 1
        if run(wrong)[0] != "wrong":
            bad.append(f"{FILE}:{ENTRY}: a wrong note {k + 1} isn't refused ({run(wrong)})")
    op = next(f for f in Evfl(fs.read("Event/EventFlow/OpeningEvent.bfevfl.zs")).flowcharts if f["name"] ==
              "OpeningEvent")
    calls = [e for e in op["events"] if e["type"] == "subflow" and e.get("flowchart") == FILE
             and e.get("entry_point") == ENTRY]
    if not calls:
        bad.append("OpeningEvent: no call of the password entry")
    sarc = sarc_files(fs.read("Mals/USen.Product.110.sarc.zs"))
    m = msbt.Msbt(sarc[MSBT])
    for label in list(TEXT) + list(OPTIONS):
        if label not in m:
            bad.append(f"USen {MSBT}: no label {label}")
    return bad
