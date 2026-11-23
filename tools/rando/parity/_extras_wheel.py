"""The accessory and boots wheels (D-pad gear's wheel mode): a code patch for the game's item wheel, plus the data
edits that open it from the D-pad.

Why a code patch. The remake's item wheel (the one L or R opens) already has two more categories, HeadArmor and Boot
(save data UI_CurrentShortCutCategory), and the masks, the Lens and the boots are filed under them (their
PouchContentParam Category). The code even numbers them and gives them their own right-stick controls, and the wheel's
item kinds (PlayerStatus.AssignableItem's values) list every mask, the Lens and both boots. But no row of the pouch
table names those kinds, and the wheel never opens for the gear, keeps no list for it and drops a pick
(out/wheel_evidence.md shows the code). Longshot applies a mod's exefs .pchtxt files when it builds the game
(LongshotBuilder/tools/nx2/exefs_patches.py), so the mod can add the missing parts. Addresses here are as in Longshot's
image.bin (base 0x80000000, main at 0x80020000).

What the patch does:
- The opener (0x833240E0..) carries on only for AssignableItem: it now carries on for HeadArmor and Boot too.
- The wheel never keeps a list of its own: the screen's open (0x83419500, with its own copy 0x83419630, which
  sets the number of slots) and four functions (setup, cursor info, entry build, slot drawing, copy 0x833EA6D0
  under the pouch lock) each copy the pouch manager's owned-item list ([[0x84C9E0D0]] + 0x498) and index the copy
  by slot. A node is {button, actor}: a button of one of the pouch table's arrays (UI/Pouch/PouchTable, read
  through 0x80A8F690 by array number) and one of that button's actors. The list only holds the item buttons
  (ItemArray, array 0, which 0x80A8E0D0 walks), so a stub after each copy rebuilds it for the gear wheels: every
  node back on the copy's free list, then a node for each actor of the Equipment menu's buttons (EquipmentArray,
  array 1, as the table's reader 0x833C3770 files them) that belongs to this wheel and that you have, IsGet
  (0x801A1160) and a stock of 1 or more (0x805B63E0), the two checks the game's own list makes. The masks button
  lists every mask, so each one you have gets its own slot. Accessories are Armor_* names with "Mask" or
  "GlassTruth", boots Armor_* names with "Boot" (the tunics on the same tab stay out), amiibo masks after the rest.
  The item wheel (category 0) only loses Armor_* names, so it stays as it is.
- The four functions also read each node's button from array 0: they now ask for array 1 on the gear wheels
  (a stub in place of their call to 0x80A8F690). The gear's pouch rows get item kinds on the data side, which is what
  the slots draw their icons from.
- Sort (0x8330A730) flips the saved bool 0xC6DAEA0E (0x833CBDF0 reads it): 0 "ItemType", 1 "UseOrder" (By
  Recently Selected). The game keeps the items' use order as stamps of a clock (UInt 0x994ACBB6) in a struct
  (0xF5AB6461) of the 42 items, written when an item goes on the button (0x81231C00). The gear has no stamps, so the
  pick stamps it with ours: Int rows keyed murmur3(actor name, GEAR_SEED), found with the game's own hash
  (0x801939E0, seeded murmur3), and a clock of our own (GEAR_CLOCK), read and written with the game's Int calls
  (0x80183D20, 0x80183B70). On UseOrder the rebuild orders the gear by stamp, newest first (never picked keeps the
  menu's order); on ItemType it keeps the menu's order.
- The wheel's setup only looks for the item on your button for category 0, and starts the gear wheels on the first
  slot. A stub in place of its category test (0x833E8CDC) looks for the gear chosen for the slot (0x80A91080) and
  starts the cursor there, through the setup's own "found" path (0x833E8EF4).
- A slot's look is drawn by a virtual of the slot (0x833EA110), which the wheel's list calls whenever it refreshes
  a slot, the wheel's closing included, when the category is the items' again and TUNIC_FLAG is off. A slot that
  isn't refreshed on the next open keeps that look. So the two stubs on a slot's look below go by the slot's own
  item name (is_gear: Armor_*), never by wheel_cat.
- Each slot shows the equipped look (0x833DCE60) when its item kind is the item on your button. For gear a stub in
  place of that test (0x833EA4FC) shows it on the gear chosen for the slot instead.
- A slot greys out (0x80F40400 with 1; 0 is the normal look, both played as an animation) when its item can't be used
  where Link is: in water or riding, by its pouch row's flags, or when no item can be used at all. That's the items'
  rule; the gear has none and the Equipment menu changes it anywhere. So for gear the slot's drawing (0x833EA508) and
  the pick's pass over the slots (0x833E9B08) always pass 0.
- The pick (0x833E98F0, run by SeqOneShotDoBeforeCloseShortCut with its IsBCancel) does its own checks first (B,
  the game's "can change gear now" bit 2 of [[0x84E9CFA8] + 0x58C] for categories 1/2, and 0x805941F0), then drops
  the new categories at 0x833E998C. A stub there now puts the highlighted gear on (the wheel's name buffer, controller
  +0x2B0) the way the Equipment menu does (0x833DA470): the gear already chosen for the slot is switched on
  (0x833C7760 with the pouch category, 9 accessories or 10 boots), anything else is equipped (0x80A9ACD0, mode 3),
  then marked (0x833CC230). It stamps the gear's use order and finishes through the pick's own close (0x833E9AB8):
  every slot's equipped look off, the picked slot's on with its animation, and mc_ChangeItem when the gear changed.
- The Equipment menu's mask button lists all eight masks and shows the first one you have (0x80A8EF20, the default
  path of a button with several actors), so a mask chosen elsewhere never showed there and "wear" put on another one.
  A stub at that path's start (0x80A8F084) shows the chosen mask instead when it's one of the button's and you have
  it (masks and the Lens only, by the wheels' own name rule; other buttons go the game's way at once).
- The tunic wheel (remake_dpad_gear "wheel_tunics", D-pad left): the wheel only has the categories AssignableItem,
  HeadArmor and Boot, so the D-pad edit opens the boots' one with our flag TUNIC_FLAG set, and every stub here asks
  wheel_cat, which reads 3 for that. The rebuild then lists the adult's tunics you have (Kokiri, Goron, Zora:
  Armor_Adult_* with Normal, Goron or Zora), and the pick equips one (0x80A9ACD0, as the Equipment menu does for
  armor) or leaves the worn one on. The tunics' pouch rows get a free item kind on the data side, so their slots draw
  their own icons.
- With the tunic wheel, the ocarina's D-pad left shortcut (0x8081C0B0, asked by Link's states) goes through a stub
  (oc_key) in place of its key test. When the tunic wheel can open (tunic_ready: an adult who has the Goron or Zora
  tunic, IsGet and a stock, the same rule as the D-pad edit's Rando_DpadWheel_Tunics_Exp), it reads the key's
  release instead of its press (+0x60, 0x1000 instead of +0x40, 0x10000): a tap plays the ocarina when you let go,
  and a hold opens the tunic wheel. Otherwise (a child, or no tunic to switch to) it reads the press, as the game
  does, so the ocarina comes out at once.
- A tap of D-pad up or down puts the gear on or takes it off when you let go, not when you press: the two checks in
  Link's input code (0x804D6EB0 boots, 0x804D7B20 accessories) read PlayerVirtualKeyRelease (input component +0x60)
  instead of PlayerVirtualKey (+0x40). Link's input takes the controller's release edge each frame (0x80594AB0), so
  letting go inside the wheel (the game is paused there) never reaches him, and a hold toggles nothing.
New code goes in the zero padding after main's code (0x83C661D0..0x83C67000), which the Builder translates as code.

The patch is for one build of the game's code (MAIN_BUILD_ID); check() refuses when the player's image.bin holds
other instructions at any site.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import a64  # noqa: E402
from romtools import murmur3_32  # noqa: E402

MAIN_BUILD_ID = "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
IMAGE_BASE, MAIN_BASE = 0x80000000, 0x80020000
CAVE, CAVE_END = 0x83C661D0, 0x83C67000
PATCH_FILE = "rando_of_time_gear_wheel.pchtxt"
HEAD_ARMOR, BOOT = 0xF1360E06, 0x7741490F  # murmur3 "HeadArmor", "Boot" (the category's value names)
# the game's own functions the new code calls
CATEGORY = 0x833CBED0      # 0 items, 1 HeadArmor, 2 Boot (reads UI_CurrentShortCutCategory)
UNLOCK = 0x80967300        # the pouch manager's lock (+0x3B90), unlocked
POUCH_LIST = 0x80A8F690    # (manager, array) -> the pouch table's buttons of that array, [+8] count, [+0x10] array
ITEM_TAB, GEAR_TAB = 0, 1  # ItemArray, EquipmentArray
LIST_COUNT = 0x80021A20    # a list's count (with its chained parts)
IS_GET = 0x801A1160        # (name holder) -> do you have it
STOCK = 0x805B63E0         # (manager, name holder, 1, 0) -> how many you have
ITEM_ACTORS = 0x8002A520   # button -> its actor table (loads it when needed)
ACTOR_AT = 0x80D666A0      # (table, index) -> entry
ACTOR_NAME = 0x8002A4C0    # entry -> [x0] the actor name (char *)
MANAGER = (0x84C9E000, 0xD0)  # adrp page, offset of the pointer to the pouch manager's pointer
SCREEN_COPY = 0x83419630   # the screen's open copies the owned list with this (its own container, 32 nodes)
SCREEN_SITE = 0x83419530   # bl SCREEN_COPY in the screen's open (0x83419500), x0 the copy at its sp
OPEN_ON, OPEN_SKIP = 0x8332413C, 0x83324154
# patch sites: address -> (the instruction there in the game, what replaces it)
OPENER = 0x83324138        # b.ne OPEN_SKIP, right after cmp w8 (the category) with AssignableItem
UNLOCK_SITES = {0x833E8CC4: 0x10,   # the wheel's setup, its copy at sp+0x10
                0x833E8FBC: 0x70,   # the entry info under the cursor, sp+0x70
                0x833E9EEC: 0x58,   # the wheel's entry list, sp+0x58
                0x833EA1A0: 0xB0}   # one slot's drawing, sp+0xB0
LIST_COPY = 0x833EA6D0     # the copy each site makes just before (checked, not patched)
LIST_SITES = (0x833E8C90, 0x833E8F88, 0x833E9EB8, 0x833EA16C)  # their bl POUCH_LIST, after mov x1, xzr
EQUIPMENT_READ = 0x833C37BC  # the table's reader: bl 0x80A8F790, then the name "EquipmentArray" (0x83CBCEEC)
PICK = 0x833E998C          # b.ne ITEM_PICK in the pick: ne for the item wheel with a name, w20 the category
ITEM_PICK, PICK_DONE = 0x833E99F0, 0x833E9990  # the pick's item path, and its clear-and-return
MARKERS = 0x833E9AB8       # the pick's close: equipped looks, the picked slot's, mc_ChangeItem if w20 != [x29+0x1C]
GLOBAL = (0x84C9E000, 0x2A8)  # adrp page, offset of the pointer the pick's close keeps in x23
SEEK_SITE = 0x833E8CDC     # cbnz w0 (the category), SETUP_SKIP in the wheel's setup
SETUP_ITEMS, SETUP_SKIP, SETUP_FOUND = 0x833E8CE0, 0x833E8D04, 0x833E8EF4  # its item search, first slot, found (w22)
MARK_SITE = 0x833EA4FC     # cset w1, ne in one slot's drawing: the equipped look when the slot is the button's item
CHOSEN_SITE = 0x80A8F084   # mov x26, xzr in 0x80A8EF20: a button of several actors shows the first one you have
ENTRY_DEFAULT, ENTRY_DONE = 0x80A8F088, 0x80A8EFCC  # that path's loop, and the lookup's exit with w25 the actor
GET_SORT = 0x833CBDF0      # -> 1 By Recently Selected ("UseOrder"), 0 By Type ("ItemType")
GET_INT, SET_INT = 0x80183D20, 0x80183B70  # (game data, &value, hash) -> found; (game data, value, hash)
HASH = 0x801939E0          # (char *, seed) -> murmur3_32
GEAR_CLOCK = "Rando_GearClock"  # our clock for the gear's use order
TUNIC_FLAG = "Rando_DpadWheel_Tunics"  # set by the D-pad edit when the boots' wheel opens for the tunics
TUNIC_CAT = 3              # wheel_cat's value for it
GET_BOOL = 0x8022FD90      # (game data, &value, hash) -> found
OCARINA = 0x8081C15C       # the ocarina shortcut's key test: ldr x9, [x19, #0x40] / ldrb w9, [x9, #2] / tbnz w9, #0
OCARINA_GO = 0x8081C1B8    # where it goes when D-pad left is in (x8 and x0 as the test left them)
OCARINA_NO = 0x8081C168    # where it goes when it isn't
FADE_DRAW = 0x833EA508     # and w1, w22, #1 in one slot's drawing, then mov x0, x19 / bl FADE (w22 the usable flag)
FADE_PICK = 0x833E9B08     # and w1, w8, #1 in the pick's pass over the slots, x0 the slot, then bl FADE
FADE = 0x80F40400          # (slot, 0 the normal look, 1 greyed out as not usable here)
CHILD_FLAG = "Sequence_IsChildhood"
TUNICS_TO_SWITCH = ("Armor_Adult_Goron", "Armor_Adult_Zora")  # the tunic wheel opens once you have one of these
LEFT_PRESSED, LEFT_RELEASED = (2, 0), (1, 4)  # (byte, bit) of D-pad left: 0x10000 pressed, 0x1000 released
GEAR_SEED = murmur3_32("Rando_GearUsed")  # a gear's use-order row is murmur3(actor name, GEAR_SEED)
STAMPS = 32                # the rebuild keeps this many stamps (a copy holds at most 32 nodes)
SET_TEXT = 0x80D44E50      # (game data, &text, name hash): set a text row (String64)
GAMEDATA = (0x84C9E000, 0x180)  # adrp page, offset of the pointer to the game data manager's pointer
# the Equipment menu's own steps for a piece of gear (0x833DA470), each (pouch manager, ...)
IS_EQUIPPED = 0x80A91080   # (&name) -> is it the gear chosen for its slot
SET_ACTIVE = 0x833C7760    # (pouch category, on): wear or take off the slot's chosen gear
EQUIP = 0x80A9ACD0         # (&name, 3, 0): choose and wear it
MARK = 0x833CC230          # (&name, 1)
POUCH_HEAD, POUCH_BOOT = 9, 10  # the pouch categories of accessories and boots (the D-pad's own toggles use them)
# Link's D-pad gear checks: address -> (target, base register, the test after it). The input component's +0x40 is
# PlayerVirtualKey (pressed this frame), +0x60 PlayerVirtualKeyRelease (let go this frame), both bound by name
# (0x82E8E640). Bit 2 of byte 1 is D-pad up, bit 3 D-pad down: virtual keys 0x400 and 0x800, from the controller's
# bits 0x10000 and 0x20000 (0x80594AB0).
RELEASE_SITES = {0x804D7EBC: ("x8", "x8", ("tbnz", 2, 0x804D7FD4)),    # accessories: toggle (0x804D8420)
                 0x804D6FF0: ("x8", "x21", ("tbnz", 3, 0x804D7164)),   # boots: toggle (0x83036740)
                 0x804D714C: ("x8", "x21", ("tbz", 3, 0x804D7114))}    # boots while Link is busy: toggle later
PRESSED, RELEASED = 0x40, 0x60
# words the assembler doesn't write, as the game has them (checked)
CSET_W1_NE, CCMP_W9_0_4_EQ, CCMN_W21_1_4_EQ = 0x1A9F07E1, 0x7A400924, 0x3A410AA4
AND_W1_W22_1, AND_W1_W8_1, LDR_X0_X21_POST8 = 0x120002C1, 0x12000101, 0xF84086A0
STP_X8_X0_SP = 0xA90003E8  # stp x8, x0, [sp]
# words an older version of this patch left at a site (a game built with it still fits): its ocarina check read the
# release in place
OLDER = {OCARINA: (0xF9403269,)}  # ldr x9, [x19, #0x60]


def wheel_of(name):
    """Which wheel shows an actor of the Equipment menu: 1 accessories, 2 boots, 3 the adult's tunics, None none (the
    same rule as the code's match)."""
    if not name.startswith("Armor_"):
        return None
    rest = name[len("Armor_"):]
    if "Boot" in rest:
        return 2
    if "Mask" in rest or "GlassTruth" in rest:
        return 1
    if rest.startswith("Adult_") and any(x in rest for x in ("Normal", "Goron", "Zora")):
        return TUNIC_CAT
    return None


def _scan(p, src, needle, out, tag):
    """out = 1 if the string at src (a register) holds needle, else 0. Uses w9 and x10."""
    p.op("mov", out, "wzr")
    p.op("mov", "x10", src)
    p.label(f"{tag}_at")
    p.op("ldrb", "w9", "x10")
    p.op("cbz", "w9", f"{tag}_end")
    for k, ch in enumerate(needle):
        p.op("ldrb", "w9", "x10", k)
        p.op("cmp", "w9", ord(ch))
        p.op("b.ne", f"{tag}_adv")
    p.op("movz", out, 1)
    p.op("b", f"{tag}_end")
    p.label(f"{tag}_adv")
    p.op("add", "x10", "x10", 1)
    p.op("b", f"{tag}_at")
    p.label(f"{tag}_end")


def program():
    """The new code, laid out from CAVE: [(address, word)], plus the label addresses."""
    p = a64.Program(CAVE)
    # the opener: flags from cmp w8, AssignableItem; w9 is free (the code at OPEN_ON loads it again)
    p.label("opener")
    p.op("b.ne", "op_head")
    p.op("b", OPEN_ON)
    p.label("op_head")
    p.mov32("w9", HEAD_ARMOR)
    p.op("cmp", "w8", "w9")
    p.op("b.ne", "op_boot")
    p.op("b", OPEN_ON)
    p.label("op_boot")
    p.mov32("w9", BOOT)
    p.op("cmp", "w8", "w9")
    p.op("b.ne", "op_skip")
    p.op("b", OPEN_ON)
    p.label("op_skip")
    p.op("b", OPEN_SKIP)
    # the pick, past the game's own checks (B, "can change gear now", busy), in place of its b.ne ITEM_PICK: flags
    # ne for the item wheel with a name. x19 the wheel's controller, w20 the category, x29 the pick's frame. Calls
    # keep x19..x28; the name, the pouch category, whether it was chosen and the clock wait on the stack.
    def manager():
        p.op("adrp", "x9", MANAGER[0])
        p.op("ldr", "x9", "x9", MANAGER[1])
        p.op("ldr", "x0", "x9")

    def gamedata():
        p.op("adrp", "x9", GAMEDATA[0])
        p.op("ldr", "x9", "x9", GAMEDATA[1])
        p.op("ldr", "x0", "x9")
    p.label("pick")
    p.op("b.eq", "pk_gear0")
    p.op("b", ITEM_PICK)                    # the item wheel: as before
    p.label("pk_gear0")
    p.op("cbnz", "w20", "pk_name")
    p.op("b", PICK_DONE)                    # the item wheel without a name: as before
    p.label("pk_name")
    p.op("bl", "wheel_cat")                 # 3 for the tunics (the game's w20 says 2, the boots' wheel)
    p.op("mov", "w20", "w0")
    p.op("ldr", "x8", "x19", 0x2B0)         # the highlighted entry's name
    p.op("cbz", "x8", "pk_done")
    p.op("ldrb", "w9", "x8")
    p.op("cbz", "w9", "pk_done")
    p.op("sub", "sp", "sp", 32)
    p.op("str", "x8", "sp")                 # sp holds the name pointer: &name, as the menu passes it
    p.op("mov", "x0", "x8")
    p.op("mov", "w1", "w20")
    p.op("bl", "match")                     # only this wheel's gear
    p.op("cbz", "w0", "pk_out")
    p.op("movz", "w9", POUCH_HEAD)
    p.op("movz", "w10", POUCH_BOOT)
    p.op("cmp", "w20", 2)
    p.op("csel", "w9", "w10", "w9", "eq")
    p.op("str", "w9", "sp", 8)
    manager()
    p.op("mov", "x1", "sp")
    p.op("bl", IS_EQUIPPED)
    p.op("str", "w0", "sp", 12)             # chosen already?
    p.op("tbz", "w0", 0, "pk_equip")
    p.op("cmp", "w20", TUNIC_CAT)
    p.op("b.eq", "pk_mark")                 # the tunic Link wears: nothing to switch
    manager()                               # chosen already: wear it
    p.op("ldr", "w1", "sp", 8)
    p.op("movz", "w2", 1)
    p.op("bl", SET_ACTIVE)
    p.op("b", "pk_mark")
    p.label("pk_equip")
    manager()
    p.op("mov", "x1", "sp")
    p.op("movz", "w2", 3)
    p.op("mov", "w3", "wzr")
    p.op("bl", EQUIP)
    p.label("pk_mark")
    manager()
    p.op("mov", "x1", "sp")
    p.op("movz", "w2", 1)
    p.op("bl", MARK)
    # the use order: the clock goes up one and the gear takes its time
    p.op("str", "wzr", "sp", 16)
    gamedata()
    p.op("add", "x1", "sp", 16)
    p.mov32("w2", murmur3_32(GEAR_CLOCK))
    p.op("bl", GET_INT)
    p.op("ldr", "w8", "sp", 16)
    p.op("add", "w8", "w8", 1)
    p.op("str", "w8", "sp", 16)
    gamedata()
    p.op("ldr", "w1", "sp", 16)
    p.mov32("w2", murmur3_32(GEAR_CLOCK))
    p.op("bl", SET_INT)
    p.op("ldr", "x0", "sp")
    p.mov32("w1", GEAR_SEED)
    p.op("bl", HASH)
    p.op("mov", "w2", "w0")
    gamedata()
    p.op("ldr", "w1", "sp", 16)
    p.op("bl", SET_INT)
    # the pick's own close: w20 against [x29+0x1C] picks the sound, so 0 against 1 when the gear changed
    p.op("ldr", "w8", "sp", 12)
    p.op("movz", "w9", 1)
    p.op("tbz", "w8", 0, "pk_new")
    p.op("movz", "w9", 0)
    p.label("pk_new")
    p.op("str", "w9", "x29", 0x1C)
    p.op("mov", "w20", "wzr")
    p.op("add", "sp", "sp", 32)
    p.op("adrp", "x23", GLOBAL[0])
    p.op("ldr", "x23", "x23", GLOBAL[1])
    p.op("b", MARKERS)
    p.label("pk_out")
    p.op("add", "sp", "sp", 32)
    p.label("pk_done")
    p.op("b", PICK_DONE)
    # the setup, in place of cbnz w0 (the category), SETUP_SKIP: on the gear wheels, the cursor starts on the gear
    # chosen for the slot. Its copy is at its sp + 0x10, x20 its list (array 1 here); x21..x28 are its saved ones and
    # free from here on, w22 is the slot its "found" path takes
    p.label("seek")
    p.op("cbnz", "w0", "sk_gear")
    p.op("b", SETUP_ITEMS)
    p.label("sk_gear")
    p.op("mov", "x28", "sp")
    p.op("sub", "sp", "sp", 16)
    p.op("mov", "w27", "wzr")
    p.label("sk_loop")
    p.op("ldr", "w8", "x28", 0x10)
    p.op("cmp", "w27", "w8")
    p.op("b.ge", "sk_none")
    p.op("ldr", "x8", "x28", 0x18)
    p.op("add", "x8", "x8", "x27", 3)
    p.op("ldr", "x8", "x8")                 # node {button, actor}
    p.op("ldrsw", "x9", "x8")
    p.op("ldr", "w23", "x8", 4)
    p.op("cmp", "w9", 0)
    p.op("b.lt", "sk_next")
    p.op("ldr", "w10", "x20", 8)
    p.op("cmp", "w9", "w10")
    p.op("b.ge", "sk_next")
    p.op("ldr", "x10", "x20", 0x10)
    p.op("add", "x10", "x10", "x9", 3)
    p.op("ldr", "x0", "x10")
    p.op("bl", ITEM_ACTORS)
    p.op("mov", "w1", "w23")
    p.op("bl", ACTOR_AT)
    p.op("bl", ACTOR_NAME)
    p.op("ldr", "x8", "x0")
    p.op("str", "x8", "sp")
    manager()
    p.op("mov", "x1", "sp")
    p.op("bl", IS_EQUIPPED)
    p.op("tbz", "w0", 0, "sk_next")
    p.op("mov", "w22", "w27")
    p.op("add", "sp", "sp", 16)
    p.op("b", SETUP_FOUND)
    p.label("sk_next")
    p.op("add", "w27", "w27", 1)
    p.op("b", "sk_loop")
    p.label("sk_none")
    p.op("add", "sp", "sp", 16)
    p.op("b", SETUP_SKIP)
    # one slot's drawing, in place of cset w1, ne (flags: the slot's kind is the button's item): for gear (by the
    # slot's name) the equipped look goes on the gear chosen for the slot. &name is the drawing's x29 + 0x18
    p.label("mark")
    p.op("movz", "w1", 0)
    p.op("b.eq", "mk_flag")
    p.op("movz", "w1", 1)
    p.label("mk_flag")
    p.op("add", "x9", "x29", 0x18)
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("str", "x9", "sp", 16)
    p.op("str", "w1", "sp", 24)
    p.op("ldr", "x0", "x9")                 # the slot's item name
    p.op("bl", "is_gear")
    p.op("cbz", "w0", "mk_keep")
    manager()
    p.op("ldr", "x1", "sp", 16)
    p.op("bl", IS_EQUIPPED)
    p.op("mov", "w1", "wzr")
    p.op("tbz", "w0", 0, "mk_out")
    p.op("movz", "w1", 1)
    p.op("b", "mk_out")
    p.label("mk_keep")
    p.op("ldr", "w1", "sp", 24)
    p.label("mk_out")
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("ret")
    # the button lookup 0x80A8EF20, in place of mov x26, xzr at its "first one you have" path: w0 the button's actor
    # count, x20 its actors, x23 the pouch manager, x19/x21/x22 its outputs (kept). x25..x28 are set by the path
    # anyway. A button of the accessories wheel shows the chosen gear if it's one of its own and you have it
    p.label("chosen")
    p.op("mov", "w27", "w0")
    p.op("sub", "sp", "sp", 16)
    p.op("mov", "w26", "wzr")
    p.label("ch_loop")
    p.op("cmp", "w26", "w27")
    p.op("b.ge", "ch_none")
    p.op("mov", "x0", "x20")
    p.op("mov", "w1", "w26")
    p.op("bl", ACTOR_AT)
    p.op("bl", ACTOR_NAME)
    p.op("mov", "x28", "x0")
    p.op("ldr", "x0", "x28")
    p.op("movz", "w1", 1)
    p.op("bl", "match")
    p.op("cbz", "w0", "ch_none")            # not the accessories' button: the game's way
    p.op("ldr", "x8", "x28")
    p.op("str", "x8", "sp")
    p.op("mov", "x0", "x23")
    p.op("mov", "x1", "sp")
    p.op("bl", IS_EQUIPPED)
    p.op("tbz", "w0", 0, "ch_next")
    p.op("mov", "x0", "x23")
    p.op("mov", "x1", "x28")
    p.op("movz", "w2", 1)
    p.op("mov", "w3", "wzr")
    p.op("bl", STOCK)
    p.op("cmp", "w0", 1)
    p.op("b.lt", "ch_next")
    p.op("mov", "w25", "w26")
    p.op("add", "sp", "sp", 16)
    p.op("b", ENTRY_DONE)
    p.label("ch_next")
    p.op("add", "w26", "w26", 1)
    p.op("b", "ch_loop")
    p.label("ch_none")
    p.op("add", "sp", "sp", 16)
    p.op("mov", "w0", "w27")
    p.op("mov", "x26", "xzr")
    p.op("b", ENTRY_DEFAULT)
    # one stub per unlock site: unlock as before, then filter the caller's copy (at the caller's sp + off)
    for site, off in sorted(UNLOCK_SITES.items()):
        p.label(f"stub_{site:x}")
        p.op("stp", "x29", "x30", "sp", -16, "pre")
        p.op("mov", "x29", "sp")
        p.op("bl", UNLOCK)
        p.op("add", "x0", "sp", 16 + off)
        p.op("bl", "filter")
        p.op("ldp", "x29", "x30", "sp", 16, "post")
        p.op("ret")
    # filter(x0 = a copied list {count, capacity, nodes, free list}): keeps this wheel's entries, in order
    p.label("filter")
    p.op("stp", "x29", "x30", "sp", -0x60, "pre")
    p.op("mov", "x29", "sp")
    p.op("stp", "x19", "x20", "sp", 0x10)
    p.op("stp", "x21", "x22", "sp", 0x20)
    p.op("stp", "x23", "x24", "sp", 0x30)
    p.op("stp", "x25", "x26", "sp", 0x40)
    p.op("mov", "x19", "x0")
    p.op("bl", "wheel_cat")
    p.op("mov", "w20", "w0")                # 0 the item wheel (loses the gear only), 1 accessories, 2 boots, 3 tunics
    p.op("cbz", "w0", "f_items")
    p.op("mov", "x0", "x19")
    p.op("mov", "w1", "w20")
    p.op("bl", "rebuild")                   # the gear wheels: their own list
    p.op("b", "f_done")
    p.label("f_items")
    p.op("adrp", "x8", MANAGER[0])
    p.op("ldr", "x8", "x8", MANAGER[1])
    p.op("ldr", "x0", "x8")
    p.op("mov", "x1", "xzr")
    p.op("bl", POUCH_LIST)
    p.op("mov", "x21", "x0")                # the pouch items
    p.op("ldr", "x22", "x19", 8)            # the copy's nodes
    p.op("mov", "w23", "wzr")               # read position
    p.op("mov", "w24", "wzr")               # kept so far
    p.label("f_loop")
    p.op("ldr", "w8", "x19")
    p.op("cmp", "w23", "w8")
    p.op("b.ge", "f_end")
    p.op("add", "x9", "x22", "x23", 3)
    p.op("ldr", "x25", "x9")                # node: {s32 pouch index, u32 actor index}
    p.op("ldrsw", "x9", "x25")
    p.op("cmp", "w9", 0)
    p.op("b.lt", "f_odd")
    p.op("ldr", "w10", "x21", 8)
    p.op("cmp", "w9", "w10")
    p.op("b.ge", "f_odd")
    p.op("ldr", "x10", "x21", 0x10)
    p.op("add", "x10", "x10", "x9", 3)
    p.op("ldr", "x0", "x10")
    p.op("bl", ITEM_ACTORS)
    p.op("ldr", "w1", "x25", 4)
    p.op("bl", ACTOR_AT)
    p.op("bl", ACTOR_NAME)
    p.op("ldr", "x0", "x0")                 # the actor name
    p.op("mov", "w1", "w20")
    p.op("bl", "match")
    p.op("cbz", "w0", "f_drop")
    p.label("f_keep")
    p.op("add", "x9", "x22", "x24", 3)
    p.op("str", "x25", "x9")
    p.op("add", "w24", "w24", 1)
    p.op("b", "f_next")
    p.label("f_odd")                        # no such pouch item: the item wheel keeps it as before
    p.op("cbz", "w20", "f_keep")
    p.label("f_drop")                       # back on the free list (node[0] = head, head = node)
    p.op("ldr", "x9", "x19", 0x10)
    p.op("str", "x9", "x25")
    p.op("str", "x25", "x19", 0x10)
    p.label("f_next")
    p.op("add", "w23", "w23", 1)
    p.op("b", "f_loop")
    p.label("f_end")
    p.op("str", "w24", "x19")
    p.label("f_done")
    p.op("ldp", "x19", "x20", "sp", 0x10)
    p.op("ldp", "x21", "x22", "sp", 0x20)
    p.op("ldp", "x23", "x24", "sp", 0x30)
    p.op("ldp", "x25", "x26", "sp", 0x40)
    p.op("ldp", "x29", "x30", "sp", 0x60, "post")
    p.op("ret")
    # the screen's open: its copy, then the same treatment (x0 the copy, kept across the call)
    p.label("stub_screen")
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("str", "x0", "sp", 16)
    p.op("bl", SCREEN_COPY)
    p.op("ldr", "x0", "sp", 16)
    p.op("bl", "filter")
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("ret")
    # rebuild(x0 = a copied list, w1 = category 1 or 2): every node back on the free list (node[0] = head), then a
    # node for each actor of the Equipment tab's buttons that's this wheel's and that you have, in the table's order,
    # the amiibo masks after the rest, while nodes and capacity last. By Recently Selected then orders them by their
    # use-order stamp, newest first (a stable insertion sort; never picked is 0 and keeps its place). Frame: x19..x28
    # at 0x10..0x5F, the stamps at 0x60 (STAMPS words), GET_INT's value at 0xE0, this node's stamp at 0xE4, the
    # button at 0xE8
    p.label("rebuild")
    p.op("stp", "x29", "x30", "sp", -0xF0, "pre")
    p.op("mov", "x29", "sp")
    p.op("stp", "x19", "x20", "sp", 0x10)
    p.op("stp", "x21", "x22", "sp", 0x20)
    p.op("stp", "x23", "x24", "sp", 0x30)
    p.op("stp", "x25", "x26", "sp", 0x40)
    p.op("stp", "x27", "x28", "sp", 0x50)
    p.op("mov", "x19", "x0")
    p.op("mov", "w20", "w1")
    p.op("mov", "w9", "wzr")
    p.label("r_free")
    p.op("ldr", "w8", "x19")
    p.op("cmp", "w9", "w8")
    p.op("b.ge", "r_freed")
    p.op("ldr", "x10", "x19", 8)
    p.op("add", "x10", "x10", "x9", 3)
    p.op("ldr", "x11", "x10")
    p.op("ldr", "x12", "x19", 0x10)
    p.op("str", "x12", "x11")
    p.op("str", "x11", "x19", 0x10)
    p.op("add", "w9", "w9", 1)
    p.op("b", "r_free")
    p.label("r_freed")
    p.op("str", "wzr", "x19")
    manager()
    p.op("bl", GET_SORT)
    p.op("mov", "w28", "w0")                # 1: By Recently Selected
    manager()
    p.op("movz", "w1", GEAR_TAB)
    p.op("bl", POUCH_LIST)
    p.op("cbz", "x0", "r_done")
    p.op("mov", "x21", "x0")                # the Equipment menu's buttons: [+8] count, [+0x10] array
    p.op("mov", "w27", "wzr")               # pass 0: all but the amiibo masks, pass 1: the amiibo masks
    p.label("r_pass")
    p.op("mov", "w22", "wzr")               # button
    p.label("r_loop")
    p.op("ldr", "w8", "x21", 8)
    p.op("cmp", "w22", "w8")
    p.op("b.ge", "r_passed")
    p.op("mov", "w9", "w22")                # the button: in the table's order, the tunics backwards (the menu shows
    p.op("cmp", "w20", TUNIC_CAT)           # Kokiri, Goron, Zora; the table lists them Zora, Goron, Kokiri)
    p.op("b.ne", "r_button")
    p.op("sub", "w9", "w8", "w22")
    p.op("sub", "w9", "w9", 1)
    p.label("r_button")
    p.op("str", "w9", "x29", 0xE8)
    p.op("ldr", "x8", "x21", 0x10)
    p.op("add", "x8", "x8", "x9", 3)
    p.op("ldr", "x0", "x8")
    p.op("bl", ITEM_ACTORS)
    p.op("mov", "x23", "x0")                # its actors
    p.op("bl", LIST_COUNT)
    p.op("mov", "w26", "w0")
    p.op("mov", "w24", "wzr")               # actor
    p.label("r_actor")
    p.op("cmp", "w24", "w26")
    p.op("b.ge", "r_next")
    p.op("mov", "x0", "x23")
    p.op("mov", "w1", "w24")
    p.op("bl", ACTOR_AT)
    p.op("bl", ACTOR_NAME)
    p.op("mov", "x25", "x0")                # the name holder ([x25] the name)
    p.op("ldr", "x0", "x25")
    p.op("mov", "w1", "w20")
    p.op("bl", "match")
    p.op("cbz", "w0", "r_skip")
    p.op("ldr", "x8", "x25")
    _scan(p, "x8", "Amiibo", "w13", "r_ami")
    p.op("cmp", "w13", "w27")
    p.op("b.ne", "r_skip")
    p.op("mov", "x0", "x25")
    p.op("bl", IS_GET)
    p.op("tbz", "w0", 0, "r_skip")
    manager()
    p.op("mov", "x1", "x25")
    p.op("movz", "w2", 1)
    p.op("mov", "w3", "wzr")
    p.op("bl", STOCK)
    p.op("cmp", "w0", 1)
    p.op("b.lt", "r_skip")
    p.op("str", "wzr", "x29", 0xE4)         # its stamp, read only for By Recently Selected
    p.op("cbz", "w28", "r_add")
    p.op("ldr", "x0", "x25")
    p.mov32("w1", GEAR_SEED)
    p.op("bl", HASH)
    p.op("mov", "w2", "w0")
    p.op("str", "wzr", "x29", 0xE0)
    gamedata()
    p.op("add", "x1", "x29", 0xE0)
    p.op("bl", GET_INT)
    p.op("ldr", "w8", "x29", 0xE0)
    p.op("str", "w8", "x29", 0xE4)
    p.label("r_add")
    p.op("ldr", "x9", "x19", 0x10)          # a free node
    p.op("cbz", "x9", "r_sort")
    p.op("ldr", "w10", "x19")
    p.op("ldr", "w11", "x19", 4)
    p.op("cmp", "w10", "w11")
    p.op("b.ge", "r_sort")
    p.op("cmp", "w10", STAMPS)
    p.op("b.ge", "r_sort")
    p.op("ldr", "x12", "x9")
    p.op("str", "x12", "x19", 0x10)
    p.op("ldr", "w13", "x29", 0xE8)
    p.op("str", "w13", "x9")                # {button, actor}
    p.op("str", "w24", "x9", 4)
    p.op("ldr", "x12", "x19", 8)
    p.op("add", "x12", "x12", "x10", 3)
    p.op("str", "x9", "x12")
    p.op("add", "x12", "x29", 0x60)
    p.op("add", "x12", "x12", "x10", 2)
    p.op("ldr", "w13", "x29", 0xE4)
    p.op("str", "w13", "x12")
    p.op("add", "w10", "w10", 1)
    p.op("str", "w10", "x19")
    p.label("r_skip")
    p.op("add", "w24", "w24", 1)
    p.op("b", "r_actor")
    p.label("r_next")
    p.op("add", "w22", "w22", 1)
    p.op("b", "r_loop")
    p.label("r_passed")
    p.op("cbnz", "w27", "r_sort")
    p.op("movz", "w27", 1)
    p.op("b", "r_pass")
    p.label("r_sort")                       # By Recently Selected: newest stamp first, ties keep their order
    p.op("cbz", "w28", "r_done")
    p.op("ldr", "w12", "x19")               # n
    p.op("ldr", "x13", "x19", 8)            # the nodes
    p.op("add", "x14", "x29", 0x60)         # their stamps
    p.op("movz", "w9", 1)
    p.label("s_i")
    p.op("cmp", "w9", "w12")
    p.op("b.ge", "r_done")
    p.op("add", "x10", "x13", "x9", 3)
    p.op("ldr", "x15", "x10")
    p.op("add", "x10", "x14", "x9", 2)
    p.op("ldr", "w16", "x10")
    p.op("sub", "w11", "w9", 1)
    p.label("s_j")
    p.op("tbnz", "w11", 31, "s_put")
    p.op("add", "x10", "x14", "x11", 2)
    p.op("ldr", "w17", "x10")
    p.op("cmp", "w17", "w16")
    p.op("b.ge", "s_put")
    p.op("str", "w17", "x10", 4)
    p.op("add", "x10", "x13", "x11", 3)
    p.op("ldr", "x17", "x10")
    p.op("str", "x17", "x10", 8)
    p.op("sub", "w11", "w11", 1)
    p.op("b", "s_j")
    p.label("s_put")
    p.op("add", "w11", "w11", 1)
    p.op("add", "x10", "x14", "x11", 2)
    p.op("str", "w16", "x10")
    p.op("add", "x10", "x13", "x11", 3)
    p.op("str", "x15", "x10")
    p.op("add", "w9", "w9", 1)
    p.op("b", "s_i")
    p.label("r_done")
    p.op("ldp", "x19", "x20", "sp", 0x10)
    p.op("ldp", "x21", "x22", "sp", 0x20)
    p.op("ldp", "x23", "x24", "sp", 0x30)
    p.op("ldp", "x25", "x26", "sp", 0x40)
    p.op("ldp", "x27", "x28", "sp", 0x50)
    p.op("ldp", "x29", "x30", "sp", 0xF0, "post")
    p.op("ret")
    # the four functions' list: array 1 on the gear wheels, 0 otherwise (x0 the manager; x1 was 0)
    p.label("list_tab")
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("str", "x0", "sp", 16)
    p.op("bl", "wheel_cat")
    p.op("movz", "w1", ITEM_TAB)
    p.op("cmp", "w0", 1)
    p.op("b.lt", "lt_go")
    p.op("cmp", "w0", TUNIC_CAT)
    p.op("b.gt", "lt_go")
    p.op("movz", "w1", GEAR_TAB)
    p.label("lt_go")
    p.op("ldr", "x0", "sp", 16)
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("b", POUCH_LIST)
    # wheel_cat() -> w0: CATEGORY, but 3 for the boots' wheel opened with TUNIC_FLAG (the tunic wheel)
    p.label("wheel_cat")
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("bl", CATEGORY)
    p.op("cmp", "w0", 2)
    p.op("b.ne", "wc_out")
    p.op("strb", "wzr", "sp", 24)
    gamedata()
    p.op("add", "x1", "sp", 24)
    p.mov32("w2", murmur3_32(TUNIC_FLAG))
    p.op("bl", GET_BOOL)
    p.op("tbz", "w0", 0, "wc_boots")
    p.op("ldrb", "w8", "sp", 24)
    p.op("tbz", "w8", 0, "wc_boots")
    p.op("movz", "w0", TUNIC_CAT)
    p.op("b", "wc_out")
    p.label("wc_boots")
    p.op("movz", "w0", 2)
    p.label("wc_out")
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("ret")
    # tunic_ready() -> w0: the tunic wheel can open (not a child, and IsGet + a stock of the Goron or Zora tunic)
    p.label("tunic_ready")
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("strb", "wzr", "sp", 16)
    gamedata()
    p.op("add", "x1", "sp", 16)
    p.mov32("w2", murmur3_32(CHILD_FLAG))
    p.op("bl", GET_BOOL)
    p.op("tbz", "w0", 0, "tr_adult")
    p.op("ldrb", "w8", "sp", 16)
    p.op("tbnz", "w8", 0, "tr_no")          # a child
    p.label("tr_adult")
    for k, actor in enumerate(TUNICS_TO_SWITCH):
        p.op("strb", "wzr", "sp", 16)
        gamedata()
        p.op("add", "x1", "sp", 16)
        p.mov32("w2", murmur3_32(f"IsGet.{actor}"))
        p.op("bl", GET_BOOL)
        p.op("tbz", "w0", 0, f"tr_next{k}")
        p.op("ldrb", "w8", "sp", 16)
        p.op("tbz", "w8", 0, f"tr_next{k}")
        p.op("str", "wzr", "sp", 20)
        gamedata()
        p.op("add", "x1", "sp", 20)
        p.mov32("w2", murmur3_32(f"PouchData.{actor}.StockNum"))
        p.op("bl", GET_INT)
        p.op("ldr", "w8", "sp", 20)
        p.op("cmp", "w8", 1)
        p.op("b.ge", "tr_yes")
        p.label(f"tr_next{k}")
    p.label("tr_no")
    p.op("mov", "w0", "wzr")
    p.op("b", "tr_out")
    p.label("tr_yes")
    p.op("movz", "w0", 1)
    p.label("tr_out")
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("ret")
    # the ocarina's D-pad left test, in place of its ldr x9, [x19, #0x40] (x19 Link's input component): the release
    # while the tunic wheel can open, the press otherwise. x0 and x8 are the test's and go on to OCARINA_GO
    p.label("oc_key")
    p.op("stp", "x0", "x8", "sp", -32, "pre")
    p.op("str", "x30", "sp", 16)
    p.op("bl", "tunic_ready")
    p.op("mov", "w9", "w0")
    p.op("ldr", "x30", "sp", 16)
    p.op("ldp", "x0", "x8", "sp", 32, "post")
    p.op("cbz", "w9", "oc_press")
    p.op("ldr", "x10", "x19", RELEASED)
    p.op("ldrb", "w10", "x10", LEFT_RELEASED[0])
    p.op("tbnz", "w10", LEFT_RELEASED[1], "oc_in")
    p.op("b", OCARINA_NO)
    p.label("oc_press")
    p.op("ldr", "x10", "x19", PRESSED)
    p.op("ldrb", "w10", "x10", LEFT_PRESSED[0])
    p.op("tbnz", "w10", LEFT_PRESSED[1], "oc_in")
    p.op("b", OCARINA_NO)
    p.label("oc_in")
    p.op("b", OCARINA_GO)
    # the slot's fade, in place of and w1, w22, #1 (one slot's drawing, x19 the slot) and and w1, w8, #1 (the pick's
    # pass, x0 the slot): w1 = 0 (the normal look) for gear, by the name the slot holds (+0x88), the greyed-out flag's
    # bit otherwise. x0 is the slot after it (the drawing sets it next anyway); only x1 and scratch registers change
    p.label("fade_draw")
    p.op("mov", "w8", "w22")
    p.op("mov", "x0", "x19")
    p.label("fade_pick")
    p.op("stp", "x29", "x30", "sp", -32, "pre")
    p.op("mov", "x29", "sp")
    p.op("stp", "x0", "x8", "sp", 16)
    p.op("ldr", "x0", "x0", 0x88)
    p.op("bl", "is_gear")
    p.op("mov", "w9", "w0")
    p.op("ldp", "x0", "x8", "sp", 16)
    p.op("mov", "w1", "wzr")
    p.op("cbnz", "w9", "fd_out")
    p.op("tbz", "w8", 0, "fd_out")
    p.op("movz", "w1", 1)
    p.label("fd_out")
    p.op("ldp", "x29", "x30", "sp", 32, "post")
    p.op("ret")
    # is_gear(x0 = name) -> w0: an Armor_* name. Leaf, w9..w10
    p.label("is_gear")
    p.op("mov", "x9", "x0")
    p.op("mov", "w0", "wzr")
    p.op("cbz", "x9", "ig_out")
    for k, ch in enumerate("Armor_"):
        p.op("ldrb", "w10", "x9", k)
        p.op("cmp", "w10", ord(ch))
        p.op("b.ne", "ig_out")
    p.op("movz", "w0", 1)
    p.label("ig_out")
    p.op("ret")
    # match(x0 = name, w1 = category) -> w0 keep: the item wheel (0) keeps all but Armor_*, accessories (1) keep
    # Armor_* with "Mask" or "GlassTruth" and no "Boot", boots (2) Armor_* with "Boot", tunics (3) Armor_Adult_* with
    # Normal, Goron or Zora and none of the others (wheel_of is the same rule)
    p.label("match")
    p.op("mov", "w12", "wzr")               # an Armor_* name
    p.op("mov", "w11", "wzr")               # "Boot" in it
    p.op("mov", "w13", "wzr")               # "Mask" or "GlassTruth" in it
    p.op("cbz", "x0", "m_decide")
    for k, ch in enumerate("Armor_"):
        p.op("ldrb", "w9", "x0", k)
        p.op("cmp", "w9", ord(ch))
        p.op("b.ne", "m_decide")
    p.op("movz", "w12", 1)
    p.op("add", "x8", "x0", 6)
    _scan(p, "x8", "Boot", "w11", "m_boot")
    _scan(p, "x8", "Mask", "w13", "m_mask")
    _scan(p, "x8", "GlassTruth", "w14", "m_lens")
    p.op("cbz", "w14", "m_tunic")
    p.op("movz", "w13", 1)
    p.label("m_tunic")                      # w15: "Adult_" then Normal, Goron or Zora
    p.op("mov", "w15", "wzr")
    for k, ch in enumerate("Adult_"):
        p.op("ldrb", "w9", "x8", k)
        p.op("cmp", "w9", ord(ch))
        p.op("b.ne", "m_decide")
    _scan(p, "x8", "Normal", "w16", "m_normal")
    p.op("cbnz", "w16", "m_is_tunic")
    _scan(p, "x8", "Goron", "w16", "m_goron")
    p.op("cbnz", "w16", "m_is_tunic")
    _scan(p, "x8", "Zora", "w16", "m_zora")
    p.op("cbz", "w16", "m_decide")
    p.label("m_is_tunic")
    p.op("movz", "w15", 1)
    p.label("m_decide")
    p.op("cbnz", "w1", "m_gear")
    p.op("movz", "w0", 1)                   # the item wheel: everything but the gear
    p.op("cbz", "w12", "m_ret")
    p.op("mov", "w0", "wzr")
    p.op("ret")
    p.label("m_gear")
    p.op("mov", "w0", "wzr")
    p.op("cbz", "w12", "m_ret")             # not gear
    p.op("cmp", "w1", TUNIC_CAT)
    p.op("b.ne", "m_boots")
    p.op("cbnz", "w11", "m_ret")            # tunics: no boots, masks or Lens, and the tunic names
    p.op("cbnz", "w13", "m_ret")
    p.op("mov", "w0", "w15")
    p.op("ret")
    p.label("m_boots")
    p.op("cmp", "w1", 2)
    p.op("b.ne", "m_head")
    p.op("mov", "w0", "w11")
    p.op("ret")
    p.label("m_head")
    p.op("cbnz", "w11", "m_ret")            # boots
    p.op("mov", "w0", "w13")
    p.label("m_ret")
    p.op("ret")
    words = p.assemble()
    if words[-1][0] + 4 > CAVE_END:
        raise a64.AsmError("the new code doesn't fit the padding after main's code")
    return words, p.labels


def writes(tunics=False):
    """[(address, old word, new word)] of every site, then the new code (old word 0). tunics: the tunic wheel's choice,
    with the ocarina on D-pad left's release."""
    words, labels = program()
    out = [(OPENER, a64.encode("b.ne", [OPEN_SKIP], OPENER), a64.encode("b", [labels["opener"]], OPENER))]
    for site in sorted(UNLOCK_SITES):
        out.append((site, a64.encode("bl", [UNLOCK], site), a64.encode("bl", [labels[f"stub_{site:x}"]], site)))
    out.append((PICK, a64.encode("b.ne", [ITEM_PICK], PICK), a64.encode("b", [labels["pick"]], PICK)))
    out.append((SEEK_SITE, a64.encode("cbnz", ["w0", SETUP_SKIP], SEEK_SITE),
                a64.encode("b", [labels["seek"]], SEEK_SITE)))
    out.append((MARK_SITE, CSET_W1_NE, a64.encode("bl", [labels["mark"]], MARK_SITE)))
    out.append((CHOSEN_SITE, a64.encode("mov", ["x26", "xzr"]), a64.encode("b", [labels["chosen"]], CHOSEN_SITE)))
    out.append((FADE_DRAW, AND_W1_W22_1, a64.encode("bl", [labels["fade_draw"]], FADE_DRAW)))
    out.append((FADE_PICK, AND_W1_W8_1, a64.encode("bl", [labels["fade_pick"]], FADE_PICK)))
    out.append((SCREEN_SITE, a64.encode("bl", [SCREEN_COPY], SCREEN_SITE),
                a64.encode("bl", [labels["stub_screen"]], SCREEN_SITE)))
    for site in LIST_SITES:
        out.append((site, a64.encode("bl", [POUCH_LIST], site), a64.encode("bl", [labels["list_tab"]], site)))
    for site, (rt, rn, _) in sorted(RELEASE_SITES.items()):
        out.append((site, a64.encode("ldr", [rt, rn, PRESSED]), a64.encode("ldr", [rt, rn, RELEASED])))
    if tunics:
        out.append((OCARINA, a64.encode("ldr", ["x9", "x19", PRESSED]), a64.encode("b", [labels["oc_key"]], OCARINA)))
    out += [(a, 0, w) for a, w in words]
    return out


def context(tunics=False):
    """Words around the sites that must be the game's too: the compare before the opener's branch and each list
    copy before its unlock."""
    ctx = [(OPENER - 4, a64.encode("cmp", ["w8", "w9"]))]
    for site in sorted(UNLOCK_SITES):
        ctx.append((site - 8, a64.encode("bl", [LIST_COPY], site - 8)))
    # the pick: B goes to PICK_DONE first, then the category test and the name's first byte set the flags
    ctx += [(0x833E9968, a64.encode("tbnz", ["w21", 0, PICK_DONE], 0x833E9968)),
            (0x833E9974, a64.encode("cmp", ["w20", 0])), (PICK - 8, a64.encode("ldrb", ["w9", "x8"])),
            (PICK - 4, CCMP_W9_0_4_EQ), (ITEM_PICK, a64.encode("adrp", ["x23", GLOBAL[0]], ITEM_PICK)),
            (ITEM_PICK + 8, a64.encode("ldr", ["x23", "x23", GLOBAL[1]])),
            (MARKERS, a64.encode("ldr", ["x8", "x19", 0x68])), (PICK_DONE, a64.encode("adrp", ["x8", 0x84C9D000], PICK_DONE))]
    # the setup: the category comes from CATEGORY, the item search starts with adrp x26, both other paths with x19's +0x68
    ctx += [(SEEK_SITE - 4, a64.encode("bl", [CATEGORY], SEEK_SITE - 4)),
            (SETUP_ITEMS, a64.encode("adrp", ["x26", 0x84C9E000], SETUP_ITEMS)),
            (SETUP_SKIP, a64.encode("ldr", ["x0", "x19", 0x68])), (SETUP_FOUND, a64.encode("ldr", ["x0", "x19", 0x68]))]
    # one slot's drawing: cmp w20, w21 / ccmn w21, #1 set the flags, then x19's equipped look (0x833DCE60) takes w1
    ctx += [(MARK_SITE - 8, a64.encode("cmp", ["w20", "w21"])), (MARK_SITE - 4, CCMN_W21_1_4_EQ),
            (MARK_SITE + 4, a64.encode("mov", ["x0", "x19"])), (MARK_SITE + 8, a64.encode("bl", [0x833DCE60], MARK_SITE + 8))]
    # the fades: the slot (x19, or x0 from the pick's list) and the call after each
    ctx += [(FADE_DRAW + 4, a64.encode("mov", ["x0", "x19"])), (FADE_DRAW + 8, a64.encode("bl", [FADE], FADE_DRAW + 8)),
            (FADE_PICK - 4, LDR_X0_X21_POST8), (FADE_PICK + 4, a64.encode("bl", [FADE], FADE_PICK + 4))]
    # the button lookup: the path's own start (tbnz before, then w25 and w27 = w0) and its exit
    ctx += [(CHOSEN_SITE - 4, a64.encode("tbnz", ["w8", 0, 0x80A8F224], CHOSEN_SITE - 4)),
            (ENTRY_DEFAULT, a64.encode("mov", ["w25", "wzr"])), (ENTRY_DEFAULT + 4, a64.encode("mov", ["w27", "w0"])),
            (ENTRY_DONE, a64.encode("cbz", ["x21", ENTRY_DONE + 8], ENTRY_DONE))]
    for site, (rt, rn, (test, bit, target)) in sorted(RELEASE_SITES.items()):  # the byte and bit each check tests
        ctx += [(site + 4, a64.encode("ldrb", ["w8", rt, 1])), (site + 8, a64.encode(test, ["w8", bit, target], site + 8))]
    ctx += [(SCREEN_SITE - 4, a64.encode("add", ["x1", "x8", 0x498])),
            (SCREEN_SITE + 4, a64.encode("ldr", ["w1", "sp", 0]))]
    ctx += [(site - 12, a64.encode("mov", ["x1", "xzr"])) for site in LIST_SITES]
    # array 1 is the Equipment menu's: 0x80A8F690 sends it to 0x80A8F790, which the table's reader files as
    # "EquipmentArray"
    ctx += [(0x80A8F6B8, a64.encode("b", [0x80A8F790], 0x80A8F6B8)),
            (EQUIPMENT_READ, a64.encode("bl", [0x80A8F790], EQUIPMENT_READ)),
            (EQUIPMENT_READ + 4, a64.encode("adrp", ["x8", 0x83CBC000], EQUIPMENT_READ + 4)),
            (EQUIPMENT_READ + 8, a64.encode("add", ["x8", "x8", 0xEEC]))]
    ctx += [(0x804D7EB8, a64.encode("ldr", ["x8", "x8", 0x358])), (0x804D7FD4, a64.encode("bl", [0x804D8420], 0x804D7FD4)),
            (0x804D716C, a64.encode("bl", [0x83036740], 0x804D716C))]
    if tunics:  # the ocarina's test: Link's input component (+0x358), the miss path and the hit
        ctx += [(0x8081C0D0, a64.encode("ldr", ["x19", "x8", 0x358])),
                (OCARINA - 4, a64.encode("cbz", ["x8", 0x8081C180], OCARINA - 4)),
                (OCARINA_NO, a64.encode("mov", ["w0", "wzr"])), (OCARINA_GO, STP_X8_X0_SP)]
    return ctx


def _into_cave(word, at):
    """Is this word a b or bl into the padding (a hook of ours, from any version of the patch)?"""
    if word >> 26 not in (0x05, 0x25):
        return False
    off = word & 0x3FFFFFF
    off -= (1 << 26) if off & (1 << 25) else 0
    return CAVE <= at + 4 * off < CAVE_END


def check(image_path, tunics=False):
    """Problems ([] when the patch fits): every site and context word as expected, the padding still zero. The
    game's image.bin is what Longshot built, so once a player has built the game with this mod it holds our own
    patch, of this version or an older one: a site then holds our word or a branch into the padding, and the padding
    our code. The Builder patches the game's code as it ships, so that's fine."""
    if not os.path.exists(image_path):
        return [f"{image_path}: missing (build the game once in Longshot first)"]
    bad = []
    with open(image_path, "rb") as f:
        def word(a):
            f.seek(a - IMAGE_BASE)
            return struct.unpack("<I", f.read(4))[0]
        ours = _into_cave(word(OPENER), OPENER)  # built with our patch before
        for a, old, new in writes(tunics):
            if old == 0:
                continue
            w = word(a)
            if w != old and not (ours and (w == new or _into_cave(w, a) or w in OLDER.get(a, ()))):
                bad.append(f"main+{a - MAIN_BASE:X}: {w:08X}, the patch expects {old:08X} (another game build?)")
        for a, want in context(tunics):
            if word(a) != want:
                bad.append(f"main+{a - MAIN_BASE:X}: {word(a):08X}, expected {want:08X} (another game build?)")
        f.seek(CAVE - IMAGE_BASE)
        if not ours and f.read(CAVE_END - CAVE) != bytes(CAVE_END - CAVE):
            bad.append("the padding after main's code isn't empty (another mod's code there?)")
    return bad


def pchtxt(tunics=False):
    """The IPSwitch text Longshot's Builder reads (offsets into main, offset_shift 0x100 cancels the NSO header)."""
    lines = [f"@nsobid-{MAIN_BUILD_ID}", "@flag offset_shift 0x100", "",
             "// Rando of Time: the accessory and boots wheels (D-pad gear). Made by tools/rando/parity/_extras_wheel.py.",
             "@enabled"]
    run, start = b"", None
    for a, _, new in writes(tunics) + [(None, 0, 0)]:
        if run and (a is None or a != start + len(run)):
            lines.append(f"{start - MAIN_BASE:08X} {run.hex().upper()}")
            run, start = b"", None
        if a is not None:
            start = a if start is None else start
            run += struct.pack("<I", new)
    lines += ["@stop", ""]
    return "\n".join(lines)


def image_path(romfs):
    """The game's code image next to its romfs (Longshot's game folder)."""
    return os.path.join(os.path.dirname(os.path.normpath(romfs)), "image.bin")


def check_here(tunics=False):
    """check() on this PC's Longshot game when there is one, else [] (a seed made elsewhere, an Archipelago host say,
    gets checked when its patch is built and read back on the player's game)."""
    try:
        import romtools
        romfs = romtools.longshot_romfs()
    except Exception:
        return []
    path = image_path(romfs) if romfs else ""
    return check(path, tunics) if path and os.path.exists(path) else []
