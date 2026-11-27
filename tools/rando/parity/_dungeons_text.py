"""Dungeon items' get text names their dungeon, in OoT Randomizer's wording, in all 16 languages (dungeons plugin).

usage: python tools/rando/parity/_dungeons_text.py --show [LANG]     every message, as markup, with its widest line
       python tools/rando/parity/_dungeons_text.py --check [ROMFS]   the names against the game's, every box measured

OoTR (9.1.40, data/lang/English/property.json IMPORTANT_ITEM_MESSAGES, and its ROM's item_table.c) gives every
dungeon item a message naming its dungeon, wherever it's found, in its own dungeon too:
  "You found a Small Key for the Forest Temple!" + "It's your first one!" (total keys 0 before it),
  "You've collected N of them." (N: the total after it), "You already have enough keys." (the total had reached the
  dungeon's key count; resolve_text_small_keys, key_counts in item_effects.c, the message picked before the add);
  "You found a Small Key Ring for the Forest Temple!" / "You found a Key Ring for the Forest Temple! It includes the
  Boss Key!" (keyring_give_bk); "You got the Boss Key for the Fire Temple!"; "You found the Dungeon Map for the
  Deku Tree!"; "You found the Compass for the Deku Tree!"; the Treasure Chest Game's keys "... for the Treasure
  Box Shop!" (shuffled: with the count; unshuffled: message 0xF3, without it).
We use the same sentences, with the dungeon by the remake's own name in each language (LocationMsg/Location.msbt,
StaticMsg/Reference.msbt Treasure-ChestShop, ActorMsg/Npc.msbt for the Japanese shop's reading) and the item by the
words of the game's own get message in that language (ActorMsg/PouchContent.msbt <item>_GetMessage: "Du hast einen
kleinen Schlüssel gefunden!"). Both are in the game's key-word highlight, since OoTR colours both. The "first / N /
enough" line follows the remake's dungeon key count (dungeons_world.json "keys": the pool's own count, 4 Water
Temple keys).
German, French, Spanish, Italian, Dutch and Portuguese say "for the <place>" with the place's own article. Polish
and Russian put the place in the genitive, like the game's own running text does ("w głębi lodowej jaskini",
"глубинах храма Воды"). Japanese keeps the game's readings (ruby tags), and Korean picks 을/를 by the item's last
syllable.

The windows (GetPouchContent, because it has SystemTextNPC and the resident get scenes can call it):
- TEXT_ENTRY {MessageId}: one talk in the get window's own style (OverrideStyle 4). Used for maps, compasses, boss
  keys (their MessageId is an argument of the shared credit entries, the way vanilla talks take one: DisplayShop,
  NaviEventCommon), key rings and the Treasure Chest Game's ring.
- KEY_ENTRY {TotalName, Msg0..Msg9}: a small key's window, picked by the dungeon's key total before the key is added
  (EventQueryIsGameDataInt <arg TotalName> = 0..8, above 8 it's Msg9). The caller passes the ten messages (Msg<v> is
  the window when the total is v). The event doesn't tell dungeons apart, so no scratch save data is needed. It
  starts with the game's own 2-frame wait (a write lands a frame or two after its step, write_read_check.py),
  so a caller that added keys just before (Archipelago's ring as keys) has them counted.
- PLAIN_ENTRY: the game's own get window (OpenGetWindow, Event9 -> here -> Event60) for the generic items the game
  hands over itself in their own dungeon (vanilla chests, freestanding keys, a guard's jail key, Archipelago's
  "dungeon (current)" items). After the same 2-frame wait (the caller set the name just before) it compares
  UI_MessageTargetActorName (what the vanilla window's own GetMessage tag reads) with Item_Dungeon_SmallKey /
  BossKey / Map / Compass, then Sequence_CurrentBanc with each dungeon's map, and shows that dungeon's message
  instead of the vanilla "You found a small key!" and its caption. Then Event113 (the window's own end).
  Obj_MiniGame_SmallKey (the unshuffled Treasure Chest Game's key) shows OoTR's message 0xF3. Anything else, or a
  map that isn't a dungeon's, goes to Event60 and the vanilla windows are untouched. Every vanilla path shows the
  window before its add (GetPouchContent Event7 before Event0, Dm_SY_Treasurebox Event34 before Event23-30,
  Dm_SY_Get PouchAddItem Event40 before Event35), so the total read is the one before the key, like OoTR's.
Read-back: verify() (parity/_gaps_check.py READERS "dungeon_text").
"""
import functools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from parity import _archipelago_text as at  # noqa: E402  (fonts, box measures, languages)

DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
WORLD = json.load(open(os.path.join(HERE, "data", "rando", "dungeons_world.json"), encoding="utf-8"))
LANGS = at.LANGS
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
MSG = "EventFlowMsg/Dm_SY_Get:{}"
TEXT_FILE = "GetPouchContent"
TEXT_ENTRY = "Rando_DI_Text"
KEY_ENTRY = "Rando_DI_KeyText"
PLAIN_ENTRY = "Rando_DI_PlainGet"
TEXT_CALL, KEY_CALL = f"{TEXT_FILE}:{TEXT_ENTRY}", f"{TEXT_FILE}:{KEY_ENTRY}"
SLOTS = 10  # Msg0..Msg9: the total before the key 0..8, then 9 and above (Gerudo Training Ground: 9 keys)
TOTAL_ARG = "TotalName"
SLOT_ARGS = tuple(f"Msg{v}" for v in range(SLOTS))
TARGET = "UI_MessageTargetActorName"  # String64, unsaved: the actor the get window is for
CURRENT = "Sequence_CurrentBanc"  # String64: the map the player is on
WINDOW_START, WINDOW_REST, WINDOW_END = "Event9", "Event60", "Event113"  # GetPouchContent OpenGetWindow
TCG = "TreasureChestGame"  # the Treasure Chest Game's "area" in labels
TCG_KEYS = 6
YES, NO = 0, 1
BELOW, EQUAL, ABOVE = 0, 1, 2
TALK = {"IsWaitEnd": True, "IsCloseDialog": True, "EndDialogOption": 0, "ASName": "", "IsAnimeDriven": False,
        "IsPlayASAllSlot": False, "ChoiceNumber": 0, "ChoiceLabel1": 0, "ChoiceLabel2": 0, "ChoiceLabel3": 0,
        "ChoiceLabel4": 0, "ChoiceDefaultNo": 0, "ChoiceCancelNo": 0, "IsNotBecomeSpeaker": False,
        "ChangeMstxtForActor": False, "IsAnonymous": False, "NotPlayLipSyncAnim": False,
        "IsNotOpenIfSkipedMostRecent": False, "IsOverrideStyle": True, "OverrideStyle": 4,
        "MaintainPerformanceState": 0}  # same as GetPouchContent DefaultGetMessage Event16
GENERIC = {"Small Key": "Item_Dungeon_SmallKey", "Boss Key": "Item_Dungeon_BossKey", "Map": "Item_Dungeon_Map",
           "Compass": "Item_Dungeon_Compass"}
TCG_GENERIC = "Obj_MiniGame_SmallKey"
# dungeon area -> extra maps whose generic items count as that dungeon's (Sequence_CurrentBanc there), besides its
# own map (_dungeons_keys.banc, the hideout's cells are on GerudoFortress_Adult). It's empty because every vanilla
# dungeon item stands on its dungeon's own map (data/rewards.json: Ganon's boss-key and key chests are on
# InsideGanonCastle).
EXTRA_MAPS = {}


# The words
# PLACE[lang][area] = (words before the name, the name). The name is how the game writes it in that language (in the
# genitive for Polish and Russian, like the game's running text has them), and the words before it are whatever
# OoTR's "for the" needs there.
_EN = {"InsideTheDekuTree": ("the ", "Great Deku Tree"), "DodongoCavern": ("", "Dodongo Cavern"),
       "InsideJabuJabuBelly": ("", "Lord Jabu-Jabu's Belly"), "ForestTemple": ("the ", "Forest Temple"),
       "FireTemple": ("the ", "Fire Temple"), "WaterTemple": ("the ", "Water Temple"),
       "ShadowTemple": ("the ", "Shadow Temple"), "SpiritTemple": ("the ", "Spirit Temple"),
       "BottomOfTheWell": ("the ", "Bottom of the Well"), "IceCavern": ("the ", "Ice Cavern"),
       "GerudoTrainingGround": ("the ", "Gerudo Proving Grounds"), "InsideGanonCastle": ("", "Ganondorf's Castle"),
       "GerudoFortress": ("", "Gerudo Fortress"), TCG: ("the ", "Treasure-Chest Shop")}
_FR = {"InsideTheDekuTree": ("le ", "Vénérable Arbre Mojo"), "DodongoCavern": ("la ", "Caverne Dodongo"),
       "InsideJabuJabuBelly": ("le ", "Ventre du grand Jabu-Jabu"), "ForestTemple": ("le ", "Temple de la Forêt"),
       "FireTemple": ("le ", "Temple du Feu"), "WaterTemple": ("le ", "Temple de l'Eau"),
       "ShadowTemple": ("le ", "Temple de l'Ombre"), "SpiritTemple": ("le ", "Temple de l'Esprit"),
       "BottomOfTheWell": ("le ", "Fond du puits"), "IceCavern": ("la ", "Caverne Polaire"),
       "GerudoTrainingGround": ("le ", "Gymnase Gerudo"), "InsideGanonCastle": ("le ", "Château de Ganondorf"),
       "GerudoFortress": ("la ", "Forteresse Gerudo"), TCG: ("la ", "chasse aux trésors")}
_ES = {"InsideTheDekuTree": ("el ", "Gran Árbol Deku"), "DodongoCavern": ("la ", "Cueva de los dodongos"),
       "InsideJabuJabuBelly": ("la ", "Tripa de Jabu-Jabu"), "ForestTemple": ("el ", "Templo del Bosque"),
       "FireTemple": ("el ", "Templo del Fuego"), "WaterTemple": ("el ", "Templo del Agua"),
       "ShadowTemple": ("el ", "Templo de las Sombras"), "SpiritTemple": ("el ", "Templo del Espíritu"),
       "BottomOfTheWell": ("el ", "Fondo del pozo"), "IceCavern": ("la ", "Caverna de hielo"),
       "GerudoTrainingGround": ("el ", "Centro de entrenamiento gerudo"),
       "InsideGanonCastle": ("el ", "Castillo de Ganondorf"), "GerudoFortress": ("la ", "Fortaleza gerudo"),
       TCG: ("", "El Cofre del Tesoro")}
_JA_RUBY = {"き": "{tag:0,0,01000300e3818d}", "どうくつ": "{tag:0,0,02000c00e381a9e38186e3818fe381a4}",
            "しんでん": "{tag:0,0,02000c00e38197e38293e381a7e38293}"}
PLACE = {
    "USen": _EN, "EUen": _EN,
    "EUde": {"InsideTheDekuTree": ("den ", "Großen Deku-Baum"), "DodongoCavern": ("", "Dodongos Höhle"),
             "InsideJabuJabuBelly": ("", "Lord Jabu-Jabus Bauch"), "ForestTemple": ("den ", "Waldtempel"),
             "FireTemple": ("den ", "Feuertempel"), "WaterTemple": ("den ", "Wassertempel"),
             "ShadowTemple": ("den ", "Schattentempel"), "SpiritTemple": ("den ", "Tempel des Geistes"),
             "BottomOfTheWell": ("den ", "Grund des Brunnens"), "IceCavern": ("die ", "Eishöhle"),
             "GerudoTrainingGround": ("die ", "Gerudo-Trainingsarena"), "InsideGanonCastle": ("", "Ganondorfs Schloss"),
             "GerudoFortress": ("die ", "Gerudo-Festung"), TCG: ("den ", "Truhenspielladen")},
    "EUfr": _FR, "USfr": _FR,
    "EUes": _ES, "USes": dict(_ES, InsideJabuJabuBelly=("las ", "Entrañas de Jabu-Jabu")),
    "EUit": {"InsideTheDekuTree": ("il ", "Grande albero Deku"), "DodongoCavern": ("la ", "Caverna dei dodongo"),
             "InsideJabuJabuBelly": ("la ", "Pancia di Jabu Jabu"), "ForestTemple": ("il ", "Santuario della Foresta"),
             "FireTemple": ("il ", "Santuario del Fuoco"), "WaterTemple": ("il ", "Santuario dell'Acqua"),
             "ShadowTemple": ("il ", "Santuario dell'Ombra"), "SpiritTemple": ("il ", "Santuario dello Spirito"),
             "BottomOfTheWell": ("il ", "Fondo del pozzo"), "IceCavern": ("la ", "Caverna di ghiaccio"),
             "GerudoTrainingGround": ("la ", "Zona di addestramento Gerudo"),
             "InsideGanonCastle": ("il ", "Castello di Ganondorf"), "GerudoFortress": ("la ", "Fortezza Gerudo"),
             TCG: ("la ", "Sala della fortuna")},
    "EUnl": {"InsideTheDekuTree": ("de ", "Grote Deku-boom"), "DodongoCavern": ("de ", "Dodongo-grot"),
             "InsideJabuJabuBelly": ("", "Jabu-Jabu's buik"), "ForestTemple": ("de ", "Woudtempel"),
             "FireTemple": ("de ", "Vuurtempel"), "WaterTemple": ("de ", "Watertempel"),
             "ShadowTemple": ("de ", "Schaduwtempel"), "SpiritTemple": ("de ", "Zieltempel"),
             "BottomOfTheWell": ("de ", "Put"), "IceCavern": ("de ", "IJsgrot"),
             "GerudoTrainingGround": ("het ", "Gerudo-oefenterrein"), "InsideGanonCastle": ("", "Ganondorfs kasteel"),
             "GerudoFortress": ("het ", "Gerudo-fort"), TCG: ("de ", "Schattenshop")},
    "EUpl": {"InsideTheDekuTree": ("", "Wielkiego Drzewa Deku"), "DodongoCavern": ("", "Jaskini Dodongo"),
             "InsideJabuJabuBelly": ("", "trzewi Dżabu-Dżabu"), "ForestTemple": ("", "Świątyni Kniei"),
             "FireTemple": ("", "Świątyni Pożogi"), "WaterTemple": ("", "Świątyni Wody"),
             "ShadowTemple": ("", "Świątyni Cienia"), "SpiritTemple": ("", "Świątyni Duszy"),
             "BottomOfTheWell": ("", "dna studni"), "IceCavern": ("", "lodowej jaskini"),
             "GerudoTrainingGround": ("", "areny wyzwań Gerudo"), "InsideGanonCastle": ("", "Zamku Ganondorfa"),
             "GerudoFortress": ("", "Twierdzy Gerudo"), TCG: ("", "salonu skrzyń ze skarbami")},
    "EUru": {"InsideTheDekuTree": ("", "Великого Древа Деку"), "DodongoCavern": ("", "пещеры додонго"),
             "InsideJabuJabuBelly": ("", "утробы Джабу-Джабу"), "ForestTemple": ("", "храма Леса"),
             "FireTemple": ("", "храма Огня"), "WaterTemple": ("", "храма Воды"), "ShadowTemple": ("", "храма Тени"),
             "SpiritTemple": ("", "храма Духа"), "BottomOfTheWell": ("", "дна колодца"),
             "IceCavern": ("", "ледяной пещеры"), "GerudoTrainingGround": ("", "тренировочного плаца герудо"),
             "InsideGanonCastle": ("", "замка Ганондорфа"), "GerudoFortress": ("", "крепости герудо"),
             TCG: ("", "«Сундука удачи»")},
    "USpt": {"InsideTheDekuTree": ("a ", "Grande Árvore Deko"), "DodongoCavern": ("a ", "Caverna dos Dodongos"),
             "InsideJabuJabuBelly": ("o ", "Lorde Jabu-Jabu"), "ForestTemple": ("o ", "Templo da Floresta"),
             "FireTemple": ("o ", "Templo do Fogo"), "WaterTemple": ("o ", "Templo da Água"),
             "ShadowTemple": ("o ", "Templo das Sombras"), "SpiritTemple": ("o ", "Templo do Espírito"),
             "BottomOfTheWell": ("o ", "Fundo do poço"), "IceCavern": ("a ", "Caverna Glacial"),
             "GerudoTrainingGround": ("o ", "Centro de Treinamento Gerudo"),
             "InsideGanonCastle": ("o ", "Castelo do Ganondorf"), "GerudoFortress": ("a ", "Fortaleza Gerudo"),
             TCG: ("o ", "Baú da Sorte")},
    "JPja": {"InsideTheDekuTree": ("", "デクの{tag:0,0,01000300e3818d}樹サマ"),
             "DodongoCavern": ("", "ドドンゴの{tag:0,0,02000c00e381a9e38186e3818fe381a4}洞窟"),
             "InsideJabuJabuBelly": ("", "ジャブジャブ{tag:0,0,01000600e38195e381be}様のお{tag:0,0,01000600e381aae3818b}腹"),
             "ForestTemple": ("", "{tag:0,0,01000600e38282e3828a}森の{tag:0,0,02000c00e38197e38293e381a7e38293}神殿"),
             "FireTemple": ("", "{tag:0,0,01000900e381bbe381aee3818a}炎の{tag:0,0,02000c00e38197e38293e381a7e38293}神殿"),
             "WaterTemple": ("", "{tag:0,0,01000600e381bfe3819a}水の{tag:0,0,02000c00e38197e38293e381a7e38293}神殿"),
             "ShadowTemple": ("", "{tag:0,0,01000600e38284e381bf}闇の{tag:0,0,02000c00e38197e38293e381a7e38293}神殿"),
             "SpiritTemple": ("", "{tag:0,0,01000c00e3819fe381bee38197e38184}魂の{tag:0,0,02000c00e38197e38293e381a7e38293}神殿"),
             "BottomOfTheWell": ("", "{tag:0,0,02000600e38184e381a9}井戸の{tag:0,0,01000600e3819de38193}底"),
             "IceCavern": ("", "{tag:0,0,01000900e38193e3818ae3828a}氷の{tag:0,0,02000c00e381a9e38186e3818fe381a4}洞窟"),
             "GerudoTrainingGround": ("", "ゲルドの{tag:0,0,03001800e38197e38285e38186e3828ce38293e38198e38287e38186}修練場"),
             "InsideGanonCastle": ("", "ガノンドロフ{tag:0,0,01000900e38198e38287e38186}城"),
             "GerudoFortress": ("", "ゲルドの{tag:0,0,01000900e381a8e3828ae381a7}砦"),
             TCG: ("", "{tag:0,0,03001200e3819fe3818be38289e381b0e38193e38284}宝箱屋")},
    "KRko": {"InsideTheDekuTree": ("", "데크나무님"), "DodongoCavern": ("", "도동고의 동굴"),
             "InsideJabuJabuBelly": ("", "자부자부님의 배"), "ForestTemple": ("", "숲의 신전"),
             "FireTemple": ("", "화염의 신전"), "WaterTemple": ("", "물의 신전"), "ShadowTemple": ("", "어둠의 신전"),
             "SpiritTemple": ("", "영혼의 신전"), "BottomOfTheWell": ("", "우물 바닥"), "IceCavern": ("", "얼음 동굴"),
             "GerudoTrainingGround": ("", "겔드 수련장"), "InsideGanonCastle": ("", "가논돌프 성"),
             "GerudoFortress": ("", "겔드 요새"), TCG: ("", "보물 상자 가게")},
    "CNzh": {"InsideTheDekuTree": ("", "德库树长老"), "DodongoCavern": ("", "多东哥洞窟"),
             "InsideJabuJabuBelly": ("", "加卜加卜大人腹中"), "ForestTemple": ("", "森之神殿"),
             "FireTemple": ("", "火之神殿"), "WaterTemple": ("", "水之神殿"), "ShadowTemple": ("", "暗之神殿"),
             "SpiritTemple": ("", "魂之神殿"), "BottomOfTheWell": ("", "井底"), "IceCavern": ("", "冰之洞窟"),
             "GerudoTrainingGround": ("", "格鲁德训练场"), "InsideGanonCastle": ("", "加侬多夫城堡"),
             "GerudoFortress": ("", "格鲁德要塞"), TCG: ("", "宝箱店")},
    "TWzh": {"InsideTheDekuTree": ("", "德庫樹長老"), "DodongoCavern": ("", "多東哥洞窟"),
             "InsideJabuJabuBelly": ("", "加卜加卜大人腹中"), "ForestTemple": ("", "森之神殿"),
             "FireTemple": ("", "火之神殿"), "WaterTemple": ("", "水之神殿"), "ShadowTemple": ("", "闇之神殿"),
             "SpiritTemple": ("", "魂之神殿"), "BottomOfTheWell": ("", "井底"), "IceCavern": ("", "冰之洞窟"),
             "GerudoTrainingGround": ("", "格魯德訓練場"), "InsideGanonCastle": ("", "加儂多夫城堡"),
             "GerudoFortress": ("", "格魯德要塞"), TCG: ("", "寶箱店")},
}
# where each name comes from in the game (LocationMsg label; TCG: StaticMsg/Reference Treasure-ChestShop, JPja: the
# shopkeeper's name in ActorMsg/Npc), for check(). Polish and Russian (genitive) are checked by hand.
NAME_SOURCE = {"InsideTheDekuTree": "InsideTheDekuTree", "DodongoCavern": "DodongoCavern",
               "InsideJabuJabuBelly": "InsideJabuJabuBelly", "ForestTemple": "ForestTemple",
               "FireTemple": "FireTemple", "WaterTemple": "WaterTemple", "ShadowTemple": "ShadowTemple",
               "SpiritTemple": "SpiritTemple", "BottomOfTheWell": "BottomOfTheWell", "IceCavern": "IceCavern",
               "GerudoTrainingGround": "GerudoTrainingGround", "InsideGanonCastle": "GanonCastle",
               "GerudoFortress": "GerudoFortress"}

# The sentences. "[...]" is the highlight, {P} the place (its words, then its name highlighted), {N} the count and
# "|" a new line (OoTR's own line break before its second sentence).
_FR_S = {"key": "Vous avez trouvé une [petite clé] pour {P}\u00a0!", "first": "C'est votre [première]\u00a0!",
         "count": "Vous en avez maintenant [{N}].", "enough": "Vous avez déjà assez de clés.",
         "ring": "Vous avez trouvé un [trousseau de clés] pour {P}\u00a0!",
         "ringbk": "Vous avez trouvé un [trousseau de clés] pour {P}\u00a0!|La [grande clé] y est aussi\u00a0!",
         "boss": "Vous avez trouvé la [grande clé] pour {P}\u00a0!",
         "map": "Vous avez trouvé la [carte du donjon] pour {P}\u00a0!",
         "compass": "Vous avez trouvé la [boussole] pour {P}\u00a0!"}
_EN_S = {"key": "You found a [Small Key] for {P}!", "first": "It's your [first] one!",
         "count": "You've collected [{N}] of them.", "enough": "You already have enough keys.",
         "ring": "You found a [Small Key Ring] for {P}!",
         "ringbk": "You found a [Key Ring] for {P}!|It includes the [Boss Key]!",
         "boss": "You got the [Boss Key] for {P}!", "map": "You found the [Dungeon Map] for {P}!",
         "compass": "You found the [Compass] for {P}!"}
_ES_S = {"key": "¡Has encontrado una [llave pequeña] para {P}!", "first": "¡Es la [primera]!",
         "count": "Ya tienes [{N}].", "enough": "Ya tienes suficientes llaves.",
         "ring": "¡Has encontrado un [llavero] para {P}!",
         "ringbk": "¡Has encontrado un [llavero] para {P}!|¡También lleva la [gran llave]!",
         "boss": "¡Has encontrado la [gran llave] para {P}!",
         "map": "¡Has encontrado el [mapa de la mazmorra] para {P}!",
         "compass": "¡Has encontrado la [brújula] para {P}!"}
SENTENCES = {
    "USen": _EN_S, "EUen": _EN_S,
    "EUde": {"key": "Du hast einen [kleinen Schlüssel] für {P} gefunden!", "first": "Es ist dein [erster]!",
             "count": "Du hast jetzt [{N}] davon.", "enough": "Du hast schon genug Schlüssel.",
             "ring": "Du hast einen [Schlüsselbund] für {P} gefunden!",
             "ringbk": "Du hast einen [Schlüsselbund] für {P} gefunden!|Daran hängt auch der [große Schlüssel]!",
             "boss": "Du hast den [großen Schlüssel] für {P} gefunden!",
             "map": "Du hast die [Dungeon-Karte] für {P} gefunden!",
             "compass": "Du hast den [Kompass] für {P} gefunden!"},
    "EUfr": _FR_S, "USfr": {k: v.replace("\u00a0", "") for k, v in _FR_S.items()},
    "EUes": _ES_S,
    "USes": {k: v.replace("Has encontrado", "Encontraste").replace("mapa de la mazmorra", "mapa del calabozo")
             for k, v in _ES_S.items()},
    "EUit": {"key": "Hai trovato una [piccola chiave] per {P}!", "first": "È la tua [prima]!",
             "count": "Ora ne hai [{N}].", "enough": "Hai già abbastanza chiavi.",
             "ring": "Hai trovato un [mazzo di chiavi] per {P}!",
             "ringbk": "Hai trovato un [mazzo di chiavi] per {P}!|C'è anche la [grande chiave]!",
             "boss": "Hai trovato la [grande chiave] per {P}!", "map": "Hai trovato la [mappa del dungeon] per {P}!",
             "compass": "Hai trovato la [bussola] per {P}!"},
    "EUnl": {"key": "Je hebt een [kleine sleutel] voor {P} gevonden!", "first": "Het is je [eerste]!",
             "count": "Je hebt er nu [{N}].", "enough": "Je hebt al genoeg sleutels.",
             "ring": "Je hebt een [sleutelbos] voor {P} gevonden!",
             "ringbk": "Je hebt een [sleutelbos] voor {P} gevonden!|De [grote sleutel] zit er ook aan!",
             "boss": "Je hebt de [grote sleutel] voor {P} gevonden!",
             "map": "Je hebt de [kerkerkaart] voor {P} gevonden!", "compass": "Je hebt het [kompas] voor {P} gevonden!"},
    "EUpl": {"key": "Znalazłeś [kluczyk] do {P}!", "first": "To twój [pierwszy]!", "count": "Masz ich już [{N}].",
             "enough": "Masz już dość kluczyków.", "ring": "Znalazłeś [pęk kluczyków] do {P}!",
             "ringbk": "Znalazłeś [pęk kluczyków] do {P}!|Jest na nim też [klucz do bossa]!",
             "boss": "Znalazłeś [klucz do bossa] {P}!", "map": "Znalazłeś [mapę] {P}!",
             "compass": "Znalazłeś [kompas] {P}!"},
    "EUru": {"key": "Вы нашли [маленький ключ] от {P}!", "first": "Это ваш [первый]!",
             "count": "Теперь у вас их [{N}].", "enough": "У вас уже достаточно ключей.",
             "ring": "Вы нашли [связку ключей] от {P}!",
             "ringbk": "Вы нашли [связку ключей] от {P}!|В ней есть и [ключ к боссу]!",
             "boss": "Вы нашли [ключ к боссу] {P}!", "map": "Вы нашли [карту] {P}!", "compass": "Вы нашли [компас] {P}!"},
    "USpt": {"key": "Você encontrou uma [chave pequena] para {P}!", "first": "É a sua [primeira]!",
             "count": "Agora você tem [{N}].", "enough": "Você já tem chaves suficientes.",
             "ring": "Você encontrou um [molho de chaves] para {P}!",
             "ringbk": "Você encontrou um [molho de chaves] para {P}!|Ele também tem a [grande chave]!",
             "boss": "Você encontrou a [grande chave] para {P}!",
             "map": "Você encontrou o [mapa da masmorra] para {P}!",
             "compass": "Você encontrou a [bússola] para {P}!"},
    "JPja": {"key": "{P}の [{tag:0,0,01000600e381a1e38184}小さなカギ]を {tag:0,0,01000300e381bf}見つけた！",
             "first": "[はじめて]の カギだ！", "count": "これで [{N}]{tag:0,0,01000600e381bbe38293}本目だ！",
             "enough": "カギは もう じゅうぶんだ！",
             "ring": "{P}の [カギの{tag:0,0,01000600e3819fe381b0}束]を {tag:0,0,01000300e381bf}見つけた！",
             "ringbk": "{P}の [カギの{tag:0,0,01000600e3819fe381b0}束]を {tag:0,0,01000300e381bf}見つけた！|"
                       "[ボス{tag:0,0,02000600e381b9e38284}部屋のカギ]も ついている！",
             "boss": "{P}の [ボス{tag:0,0,02000600e381b9e38284}部屋のカギ]を {tag:0,0,01000300e381bf}見つけた！",
             "map": "{P}の [ダンジョンマップ]を {tag:0,0,01000300e381bf}見つけた！",
             "compass": "{P}の [コンパス]を {tag:0,0,01000300e381bf}見つけた！"},
    "KRko": {"key": "{P}의 [작은 열쇠]를 발견했다!", "first": "[첫 번째] 열쇠다!", "count": "지금까지 [{N}]개 모았다.",
             "enough": "이미 열쇠가 충분하다.", "ring": "{P}의 [열쇠 꾸러미]를 발견했다!",
             "ringbk": "{P}의 [열쇠 꾸러미]를 발견했다!|[보스 방의 열쇠]도 달려 있다!",
             "boss": "{P}의 [보스 방의 열쇠]를 발견했다!", "map": "{P}의 [던전 맵]을 발견했다!",
             "compass": "{P}의 [나침반]을 발견했다!"},
    "CNzh": {"key": "找到了{P}的[小钥匙]！", "first": "这是[第一把]！", "count": "已经收集了[{N}]把。",
             "enough": "钥匙已经足够了。", "ring": "找到了{P}的[钥匙串]！",
             "ringbk": "找到了{P}的[钥匙串]！|上面还有[首领室钥匙]！", "boss": "找到了{P}的[首领室钥匙]！",
             "map": "找到了{P}的[迷宫地图]！", "compass": "找到了{P}的[罗盘]！"},
    "TWzh": {"key": "找到了{P}的[小鑰匙]！", "first": "這是[第一把]！", "count": "已經收集了[{N}]把。",
             "enough": "鑰匙已經足夠了。", "ring": "找到了{P}的[鑰匙串]！",
             "ringbk": "找到了{P}的[鑰匙串]！|上面還有[首領室鑰匙]！", "boss": "找到了{P}的[首領室鑰匙]！",
             "map": "找到了{P}的[迷宮地圖]！", "compass": "找到了{P}的[羅盤]！"},
}
KINDS = ("key", "first", "count", "enough", "ring", "ringbk", "boss", "map", "compass")
if set(PLACE) != set(LANGS) or set(SENTENCES) != set(LANGS):
    raise RuntimeError("_dungeons_text: a language without its words")
for _lang in LANGS:
    if set(SENTENCES[_lang]) != set(KINDS) or set(PLACE[_lang]) != set(_EN):
        raise RuntimeError(f"_dungeons_text: {_lang} misses a sentence or a place")


# Layout (the Archipelago text's measures)
TAG = re.compile(r"\{tag:[^}]*\}")


def _tokens(s):
    """Template text -> [(char or whole tag, highlighted)]."""
    out, hl, i = [], False, 0
    while i < len(s):
        m = TAG.match(s, i)
        if m:
            out.append((m.group(0), hl))
            i = m.end()
            continue
        c = s[i]
        if c == "[":
            hl = True
        elif c == "]":
            hl = False
        else:
            out.append((c, hl))
        i += 1
    return out


def _w(tok, lang):
    if tok.startswith("{"):
        return 0.0
    return at.advance(" " if tok == at.NBSP else tok, lang) or 1.0


def width(tokens, lang):
    return sum(_w(t, lang) for t, _ in tokens)


def _units(tokens, lang):
    """Tokens -> units with no line break inside (words, or in Chinese one character with its punctuation kept with
    it). A space is a unit of its own. A tag (Japanese reading) stays with the character after it."""
    units, cur = [], []
    for t, hl in tokens:
        if t == " ":
            if cur:
                units.append(cur)
            units.append([(t, hl)])
            cur = []
            continue
        if (lang in at.BREAK_ANYWHERE and cur and not cur[-1][0].startswith("{") and len(t) == 1
                and (at._cjk(t) or at._cjk(cur[-1][0])) and t not in at.NO_START and cur[-1][0] not in at.NO_END):
            units.append(cur)
            cur = []
        cur.append((t, hl))
    if cur:
        units.append(cur)
    return _keep_names(units, lang)


def _keep_names(units, lang):
    """A highlighted name of several words (a place, "Small Key") is one unit when it fits on a line, so a line never
    breaks inside it (as the silver rupees' text keeps its highlighted words whole)."""
    out, i = [], 0
    while i < len(units):
        u = units[i]
        j = i
        if all(h for _, h in u) and u[0][0] != " ":  # (a word ending the name may carry its "!" or "の")
            while j + 2 < len(units) and units[j + 1][0] == (" ", True) and units[j + 2][0][1] and \
                    all(h for _, h in units[j]):
                j += 2
        merged = [t for x in units[i:j + 1] for t in x]
        if j > i and width(merged, lang) <= at.BOX[lang][0]:
            out.append([(at.NBSP if t == " " else t, h) for t, h in merged])
            i = j + 1
        else:
            out.append(u)
            i += 1
    return out


def _lines(tokens, lang):
    box = at.BOX[lang][0]
    lines, line, space = [], [], None
    for u in _units(tokens, lang):
        if u[0][0] == " ":
            space = u[0] if line else None
            continue
        joined = line + ([space] if space else []) + u
        space = None
        if width(joined, lang) <= box:
            line = joined
        elif width(u, lang) <= box:
            lines.append(line)
            line = list(u)
        else:
            raise ValueError(f"{lang}: {''.join(t for t, _ in u)!r} is wider than a line")
    if line:
        lines.append(line)
    return lines


def _line_markup(line):
    out, run, hl = [], [], None
    for t, h in line + [("", None)]:
        if h != hl and run:
            text = "".join(x if x.startswith("{") else at.esc(x) for x in run).replace(at.NBSP, " ")
            out.append(f"{at.HL}{text}{at.END}" if hl else text)
            run = []
        run.append(t)
        hl = h
    return "".join(out)


@functools.lru_cache(maxsize=None)  # the font tables in _archipelago_text are fixed, so layout is a pure function
# in_game_check lays out the same 2,000 messages in 16 languages over and over
def layout(text, lang):
    """Sentences ("|" between them, each on new lines) -> markup for lang's get window. Lines are at most the box's
    width, and a new box ({tag:0,4}) starts when the next sentence doesn't fit the lines left (a sentence longer than
    a box gets split)."""
    per = at.BOX[lang][1]
    boxes, cur = [], []
    for sentence in text.split("|"):
        lines = _lines(_tokens(sentence), lang)
        if cur and len(cur) + len(lines) > per:
            boxes.append(cur)
            cur = []
        for ln in lines:
            if len(cur) == per:
                boxes.append(cur)
                cur = []
            cur.append(ln)
    if cur:
        boxes.append(cur)
    return at.PAGE.join("\n".join(_line_markup(ln) for ln in box) for box in boxes)


def _fill(lang, kind, area, n=None):
    words, name = PLACE[lang][area]
    s = SENTENCES[lang][kind]
    return s.replace("{P}", f"{words}[{name}]").replace("{N}", str(n) if n is not None else "")


def sentence(lang, kind, area, n=None):
    """The template text (before layout) of one message: "key" + "first" / "count" / "enough", or a single kind."""
    if kind in ("first", "count", "enough"):
        return _fill(lang, "key", area) + "|" + _fill(lang, kind, area, n)
    return _fill(lang, kind, area)


# Labels
def key_label(area, n):
    """The small key's window when it's the n-th of the dungeon's keys. 1 is the first, and n > the dungeon's keys
    gives 'More', OoTR's 'already enough'."""
    return f"Rando_DT_Key_{area}_{n}"


def key_more(area):
    return f"Rando_DT_Key_{area}_More"


def label(kind, area):
    """Label for ring, ringbk, boss, map or compass, or 'plain' for the unshuffled Treasure Chest Game key (OoTR's
    0xF3, no count)."""
    return f"Rando_DT_{kind.title() if kind != 'ringbk' else 'RingBK'}_{area}"


def dungeons():
    """{OoTR dungeon: its row of data/rando/dungeons_world.json} (the Thieves' Hideout included)."""
    return WORLD["dungeons"]


def max_keys(area):
    if area == TCG:
        return TCG_KEYS
    d = next(v for v in dungeons().values() if v["area"] == area)
    return max(d["keys"], d["doors"])


def key_slots(area):
    """{Msg0..Msg9: MessageId}, the window when the dungeon's key total is v before the key. Like OoTR, v = 0 is
    'first', v below the dungeon's keys is 'N = v + 1 collected' and from there on it's 'already enough'."""
    top = max_keys(area)
    return {a: MSG.format(key_label(area, v + 1) if v < top else key_more(area)) for v, a in enumerate(SLOT_ARGS)}


def messages():
    """{label: {lang: markup}} for every message, every dungeon and kind, whatever the settings. The plain items'
    windows need all of them, and a seed's credits pick theirs."""
    out = {}

    def add(lb, kind, area, n=None):
        out[lb] = {lang: layout(sentence(lang, kind, area, n), lang) for lang in LANGS}
    areas = {v["area"]: v for v in dungeons().values()}
    for area, d in sorted(areas.items()):
        if d["keys"]:
            for n in range(1, max_keys(area) + 1):
                add(key_label(area, n), "first" if n == 1 else "count", area, n)
            add(key_more(area), "enough", area)
            add(label("ring", area), "ring", area)
        if d["boss_key"]:
            add(label("boss", area), "boss", area)
            if area != "InsideGanonCastle":  # OoTR: Ganon's Castle's ring never carries its boss key
                add(label("ringbk", area), "ringbk", area)
        if d["map"]:
            add(label("map", area), "map", area)
            add(label("compass", area), "compass", area)
    for n in range(1, TCG_KEYS + 1):
        add(key_label(TCG, n), "first" if n == 1 else "count", TCG, n)
    add(key_more(TCG), "enough", TCG)
    add(label("ring", TCG), "ring", TCG)
    add(label("plain", TCG), "key", TCG)
    return out


def text_ops(only=None):
    """make_patch text ops that add the messages (new labels in EventFlowMsg/Dm_SY_Get.msbt), each language its own.
    `only` is the labels to add (default all)."""
    msgs = messages()
    return [{"lang": lang, "file": MSBT, "label": lb, "markup": m, "add": True}
            for lb in sorted(msgs) if only is None or lb in only for lang, m in sorted(msgs[lb].items())]


def plan_labels():
    """The labels the dungeons plugin adds: all but the Treasure Chest Game key's count messages, which the chests
    plugin adds under its own labels when its keys are shuffled (tcg_count_texts)."""
    tcg = {key_label(TCG, n) for n in range(1, TCG_KEYS + 1)} | {key_more(TCG)}
    return sorted(set(messages()) - tcg)


TCG_COUNT_LABELS = ({n: f"Rando_TcgKey{n}" for n in range(1, TCG_KEYS + 1)}, "Rando_TcgKeyMore")  # _chests_tcg's


def tcg_count_texts(labels=None, more=None):
    """{label: {lang: markup}} for the Treasure Chest Game key's count messages under the chests plugin's labels
    (parity/_chests_tcg.py after_graph: its count after the key, 1..6, then 'more')."""
    labels, more = labels or TCG_COUNT_LABELS[0], more or TCG_COUNT_LABELS[1]
    msgs = messages()
    out = {labels[n]: msgs[key_label(TCG, n)] for n in labels}
    out[more] = msgs[key_more(TCG)]
    return out


# Events (GetPouchContent)
def talk(message_id, nxt=None):
    return {"actor": "SystemTextNPC", "action": "EventTalk", "params": dict(TALK, MessageId=message_id), "next": nxt}


def _str_query(name, value, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
            "params": {"Index": -1, "GameDataName": name, "Value": value}, "cases": {YES: yes, NO: no}}


def text_graph():
    return TEXT_ENTRY, {"talk": talk({"arg": "MessageId"})}, "talk"


def key_graph():
    """KEY_ENTRY. The key total before the key, 0..8, picks Msg<v> (Int queries answer 0 below, 1 equal, 2 above).
    It starts with the game's own 2-frame wait, so a caller that added keys just before has its write landed when
    the total is read. Archipelago's ring given as keys does that: it adds all but one, then calls the key's
    credit entry."""
    from write_read_check import settle
    n = {"settle": settle("q0")}
    for v in range(SLOTS - 1):
        n[f"q{v}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                      "params": {"Index": -1, "GameDataName": {"arg": TOTAL_ARG}, "Value": v},
                      "cases": {BELOW: "t0", EQUAL: f"t{v}", ABOVE: f"q{v + 1}" if v + 1 < SLOTS - 1 else f"t{SLOTS - 1}"}}
    for v in range(SLOTS):
        n[f"t{v}"] = talk({"arg": SLOT_ARGS[v]})
    return KEY_ENTRY, n, "settle"


def key_window(params, here=False):
    """A small key's window step (a call of KEY_ENTRY). `params` is {TotalName, Msg0..Msg9} (values or {"arg": ...}).
    `here` means it's called from GetPouchContent itself (":" + KEY_ENTRY, like the game's own calls inside a file)."""
    return {"call": f":{KEY_ENTRY}" if here else KEY_CALL, "params": {k: params[k] for k in (TOTAL_ARG,) + SLOT_ARGS}}


def text_window(message_id):
    return {"call": TEXT_CALL, "params": {"MessageId": message_id}}


def maps_of(area):
    from parity import _dungeons_keys as keys
    return (keys.banc(area),) + EXTRA_MAPS.get(area, ())


def plain_graph():
    """PLAIN_ENTRY: OpenGetWindow's window for the generic dungeon items, by the map the player is on."""
    n, kinds = {}, [("sk", "Small Key"), ("bk", "Boss Key"), ("mp", "Map"), ("cp", "Compass")]
    areas = {v["area"]: v for v in dungeons().values()}
    have = {"Small Key": lambda d: d["keys"], "Boss Key": lambda d: d["boss_key"], "Map": lambda d: d["map"],
            "Compass": lambda d: d["map"]}
    for i, (p, kind) in enumerate(kinds):
        nxt_kind = kinds[i + 1][0] if i + 1 < len(kinds) else "tcg"
        maps = [(m, a) for a, d in sorted(areas.items()) if have[kind](d) for m in maps_of(a)]
        n[p] = _str_query(TARGET, GENERIC[kind], f"{p}_m0", nxt_kind)
        for j, (m, a) in enumerate(maps):
            n[f"{p}_m{j}"] = _str_query(CURRENT, m, f"{p}_w{j}", f"{p}_m{j + 1}" if j + 1 < len(maps) else
                                        f"@{WINDOW_REST}")
            if kind == "Small Key":
                n[f"{p}_w{j}"] = dict(key_window(dict(key_slots(a), TotalName=f"DungeonInfo.{a}.SmallKeyTotalNum"),
                                                 here=True), next=f"@{WINDOW_END}")
            else:
                n[f"{p}_w{j}"] = talk(MSG.format(label({"Boss Key": "boss", "Map": "map", "Compass": "compass"}[kind],
                                                       a)), f"@{WINDOW_END}")
    n["tcg"] = _str_query(TARGET, TCG_GENERIC, "tcg_w", f"@{WINDOW_REST}")
    n["tcg_w"] = talk(MSG.format(label("plain", TCG)), f"@{WINDOW_END}")
    # The caller set the window's actor just before (SetForGetWindow, SetOwnNameToMessage), and a game-data write lands
    # a frame or two later (tools/rando/write_read_check.py). So the name is read after the game's own wait.
    from write_read_check import settle
    n["settle"] = settle("sk")
    return PLAIN_ENTRY, n, "settle"


def events():
    """The plan's event edits: TEXT_ENTRY, KEY_ENTRY, PLAIN_ENTRY and OpenGetWindow's step into it."""
    out = [{"file": TEXT_FILE, "flowchart": TEXT_FILE, "add_graph": e, "nodes": n, "start": s}
           for e, n, s in (text_graph(), key_graph(), plain_graph())]
    out.append({"file": TEXT_FILE, "flowchart": TEXT_FILE, "event": WINDOW_START, "next": f"{PLAIN_ENTRY}_settle"})
    return out


NOTE = {"text_entry": TEXT_CALL, "key_entry": KEY_CALL, "plain_entry": f"{TEXT_FILE}:{PLAIN_ENTRY}"}


# Read-back
def box_problems(lb, lang, markup):
    """Checks the message fits lang's get window (lines and width, using the Archipelago text's measures from the
    game's fonts) and every character is drawable (same checks as tools/trade_slot.py text_problems)."""
    out = []
    box, per = at.BOX[lang]
    for p, page in enumerate(markup.split(at.PAGE)):
        rows = page.split("\n")
        if len(rows) > per:
            out.append(f"{lb} {lang}: box {p + 1} has {len(rows)} lines, the window holds {per}")
        for r in rows:
            plain = TAG.sub("", r).replace("{{", "{").replace("}}", "}")
            if width([(c, None) for c in plain], lang) > box:
                out.append(f"{lb} {lang}: {plain!r} is wider than the window ({width([(c, None) for c in plain], lang):.1f} "
                           f"> {box} ems)")
            if any(not at.drawable(c, lang) for c in plain):
                out.append(f"{lb} {lang}: {plain!r} has a character the font can't draw")
    return out


def check(romfs=DEFAULT_ROMFS):
    """Problems for a name that isn't the game's own in that language (the nominative languages, against LocationMsg
    and the Treasure-Chest Shop's reference name) and for a message that doesn't fit its box."""
    import msbt
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    bad = []
    strip = (lambda s: re.sub(r"\{tag:201,[^}]*\}", "", s))
    for lang in LANGS:
        files = msbt.read_archive(fs, lang)
        loc = msbt.Msbt(files["LocationMsg/Location.msbt"])
        ref = msbt.Msbt(files["StaticMsg/Reference.msbt"])
        npc = msbt.Msbt(files["ActorMsg/Npc.msbt"])
        if lang in ("EUpl", "EUru"):
            continue
        for area, (_w_, name) in PLACE[lang].items():
            if area == TCG:
                game = npc.markup("Npc_Hylia_022_Shop_Child_Name") if lang == "JPja" else ref.markup("Treasure-ChestShop")
            else:
                game = loc.markup(NAME_SOURCE[area])
            game = strip(game)
            if lang == "EUde" and area == "InsideTheDekuTree":
                game = "Großen Deku-Baum"  # (its declension table, tag 201,10: the accusative after "für den")
            ok = name == game or (area in ("InsideTheDekuTree", "InsideJabuJabuBelly") and lang in
                                  ("JPja", "KRko", "CNzh", "TWzh") and game.startswith(name)) or \
                (lang in ("EUes", "USes") and area == TCG and name == game)
            if not ok:
                bad.append(f"{lang} {area}: {name!r} is not the game's {game!r}")
    for lb, per_lang in messages().items():
        for lang, m in per_lang.items():
            bad += box_problems(lb, lang, m)
    return bad


def verify(patch, note, romfs):
    """Read the built patch back: every message in every language (the text archives), the three GetPouchContent
    entries and OpenGetWindow's step into the plain one, each plain branch's message for its map, and every dungeon
    item's credit entry in Dm_SY_GetInEvent showing its own dungeon's message (parity/dungeons.py text_problems)."""
    import msbt
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    msgs = messages()
    want = {lb: msgs[lb] for lb in plan_labels()}
    tcg = tcg_count_texts()  # only in the patch with the Treasure Chest Game's keys shuffled, so checked when there
    for lang, rel in msbt.archives(romfs).items():
        files = msbt.read_archive(fs, lang)
        m = msbt.Msbt(files[MSBT])
        for lb, per_lang in list(want.items()) + [(k, v) for k, v in tcg.items() if k in m]:
            if lb not in m:
                bad.append(f"{lang} {MSBT}: no {lb}")
            elif m.markup(lb) != per_lang[lang]:
                bad.append(f"{lang} {MSBT}:{lb} is {m.markup(lb)!r}, want {per_lang[lang]!r}")
            else:
                bad += box_problems(lb, lang, m.markup(lb))
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{TEXT_FILE}.bfevfl.zs")).flowcharts if f["name"] == TEXT_FILE)
    bad += _plain_problems(fc)
    bad += _entry_problems(fc)
    bad += credit_problems(fs, patch)
    return bad


ROW = re.compile(r"DungeonInfo\.(\w+)\.(\w+)$")
ROW_KIND = {"IsGetMap": "map", "IsGetCompass": "compass", "IsGetBossKey": "boss"}
LABEL = re.compile(r"EventFlowMsg/Dm_SY_Get:Rando_DT_(Key|Ring|RingBK|Boss|Map|Compass|Plain)_([A-Za-z]+)(?:_\w+)?$")
HOST = "Dm_SY_GetInEvent"


def _reach(fc, start):
    """Steps reachable from `start`, nearest first."""
    seen, order, todo = set(), [], [start]
    while todo:
        i = todo.pop(0)
        if i in (None, 0xFFFF) or i in seen:
            continue
        seen.add(i)
        order.append(i)
        e = fc["events"][i]
        todo += [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks") or [])
    return order


def _key_params_problem(where, p):
    m = ROW.match(str(p.get(TOTAL_ARG)))
    if not m or m.group(2) != "SmallKeyTotalNum":
        return f"{where}: {TOTAL_ARG} {p.get(TOTAL_ARG)!r} is no dungeon's key total"
    want = key_slots(m.group(1))
    wrong = [a for a in SLOT_ARGS if p.get(a) != want[a]]
    return f"{where}: {m.group(1)}'s key window passes {wrong} not as {want[wrong[0]]!r}..." if wrong else None


def credit_problems(fs, patch):
    """Checks every dungeon item's give shows its own dungeon's message.
    - Each call of the shared credit entries (Rando_DI_Key / Rando_DI_Flag / Rando_DI_BossKey, _Big; call entries,
      chest scenes, other files) passes the messages of the dungeon its save-data rows name.
    - The shared entries' windows take them from their arguments.
    - The key rings' windows name their own dungeon (with its boss key when the ring sets it).
    - Every window called with fixed messages (the resident get scenes' copies in the air or water) names the
      dungeon its credit steps write.
    - No dungeon item's entry still shows the model's vanilla window."""
    import glob
    from evfl import Evfl
    bad, count = [], {"key": 0, "flag": 0, "window": 0}
    names = sorted({os.path.basename(p).split(".")[0]
                    for p in glob.glob(os.path.join(patch, "Event", "EventFlow", "*.bfevfl.zs"))})
    host = None
    for name in names:
        for fc in Evfl(fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts:
            if fc["name"] == HOST:
                host = fc
            for i, e in enumerate(fc["events"]):
                if e["type"] != "subflow":
                    continue
                target = (e.get("flowchart") or fc["name"], e.get("entry_point") or "")
                p = {k: _val(e, k) for k in _items(e)}
                fixed = not any(isinstance(v, tuple) for v in p.values())
                where = f"{fc['name']}:{e['name']}"
                if target[0] == HOST and re.fullmatch(r"Rando_DI_Key(_Big)?", target[1]) and fixed:
                    count["key"] += 1
                    bad += [x for x in [_key_params_problem(where, p)] if x]
                elif target[0] == HOST and re.fullmatch(r"Rando_DI_(Flag|BossKey)(_Big)?", target[1]) and fixed:
                    count["flag"] += 1
                    m = ROW.match(str(p.get("GameDataName")))
                    if not m or m.group(2) not in ROW_KIND:
                        bad.append(f"{where}: {target[1]} with {p.get('GameDataName')!r}")
                    elif p.get("MessageId") != MSG.format(label(ROW_KIND[m.group(2)], m.group(1))):
                        bad.append(f"{where}: {m.group(1)}'s {ROW_KIND[m.group(2)]} shows {p.get('MessageId')!r}")
                elif target == (TEXT_FILE, KEY_ENTRY) or target == (TEXT_FILE, TEXT_ENTRY):
                    if not fixed:
                        continue  # (a shared entry forwarding its arguments: checked below)
                    count["window"] += 1
                    if target[1] == KEY_ENTRY:
                        x = _key_params_problem(where, p)
                        area = ROW.match(str(p.get(TOTAL_ARG))).group(1) if not x else None
                        bad += [x] if x else []
                    else:
                        lm = LABEL.match(str(p.get("MessageId")))
                        area = lm.group(2) if lm else None
                        if lm is None or p["MessageId"].split(":")[-1] not in set(plan_labels()):
                            bad.append(f"{where}: window {p.get('MessageId')!r} is none of the dungeon item messages")
                    # the credit after it writes the same dungeon's rows (the air/water copies, the ring entries)
                    for j in _reach(fc, e.get("next"))[:40]:
                        r = ROW.match(str(_val(fc["events"][j], "GameDataName") or ""))
                        if r:
                            if area and r.group(1) != area:
                                bad.append(f"{where}: window for {area}, then {r.group(0)} written")
                            break
    if host is None:
        return bad + [f"{HOST}: not in the patch"]
    eps = host["entry_points"]
    shared = {"Rando_DI_Key": KEY_ENTRY, "Rando_DI_Flag": TEXT_ENTRY, "Rando_DI_BossKey": TEXT_ENTRY}
    for ep in sorted(eps):
        base = re.sub(r"_Big$", "", ep)
        if not (base in shared or base.startswith("Rando_DI_KeyRing_")):
            continue
        steps = [host["events"][i] for i in _reach(host, _entry(host, ep))]
        calls = [(s.get("flowchart") or HOST, s.get("entry_point"), s) for s in steps if s["type"] == "subflow"]
        if any(c[:2] == (TEXT_FILE, "DisplayGetByActorName") for c in calls):
            bad.append(f"{HOST}:{ep} still shows the model's vanilla window")
        wins = [c[2] for c in calls if c[:2] in ((TEXT_FILE, KEY_ENTRY), (TEXT_FILE, TEXT_ENTRY))]
        if len(wins) != 1:
            bad.append(f"{HOST}:{ep}: {len(wins)} dungeon item windows, want 1")
            continue
        w = wins[0]
        if base == "Rando_DI_Key":
            if w.get("entry_point") != KEY_ENTRY or any(_val(w, a) != ("arg", a) for a in (TOTAL_ARG,) + SLOT_ARGS):
                bad.append(f"{HOST}:{ep}: its window doesn't take the key's rows and messages from its arguments")
        elif base in shared:
            if w.get("entry_point") != TEXT_ENTRY or _val(w, "MessageId") != ("arg", "MessageId"):
                bad.append(f"{HOST}:{ep}: its window doesn't show its MessageId argument")
        else:
            area = base[len("Rando_DI_KeyRing_"):]
            bk = any(_val(s, "GameDataName") == f"DungeonInfo.{area}.IsGetBossKey" for s in steps)
            want = MSG.format(label("ringbk" if bk else "ring", TCG if area == TCG else area))
            if _val(w, "MessageId") != want:
                bad.append(f"{HOST}:{ep}: window {_val(w, 'MessageId')!r}, want {want!r}")
    CREDITS_CHECKED.update(count)
    return bad


CREDITS_CHECKED = {}  # (the last verify's counts, for the report)


def _items(e):
    return (e.get("params") or {}).get("items") or {}


def _val(e, k):
    it = _items(e).get(k) or {}
    return ("arg", it.get("value")) if it.get("type") == "argument" else it.get("value")


def _step(fc, i):
    return fc["events"][i] if i not in (None, 0xFFFF) else None


def _case(e, value):
    return next((c["next"] for c in e.get("cases", []) if c["value"] == value), None)


def _entry(fc, name):
    ep = fc["entry_points"].get(name)
    if ep is None:
        return None
    return ep.get("main", ep.get("event", ep.get("start"))) if isinstance(ep, dict) else ep


def _query(fc, e):
    return fc["actors"][e["actor"]]["queries"][e["query"]] if e and e["type"] == "switch" else None


def _action(fc, e):
    return fc["actors"][e["actor"]]["actions"][e["action"]] if e and e["type"] == "action" else None


def run_key_entry(fc, total):
    """The MessageId argument KEY_ENTRY talks with when the total is `total`, as ("arg", "Msg<v>"). None if it reads
    the total before a 2-frame wait, or talks with nothing."""
    e = _step(fc, _entry(fc, KEY_ENTRY))
    settled = False
    for _ in range(SLOTS + 3):
        if e is None:
            return None
        if _action(fc, e) == "EventWait":
            settled = settled or (_val(e, "Frames") or 0) >= 2
            e = _step(fc, e.get("next"))
            continue
        if e["type"] == "switch":
            v = _val(e, "Value")
            if _query(fc, e) != "EventQueryIsGameDataInt" or _val(e, "GameDataName") != ("arg", TOTAL_ARG) or \
                    not settled:
                return None
            e = _step(fc, _case(e, BELOW if total < v else EQUAL if total == v else ABOVE))
            continue
        return _val(e, "MessageId") if _action(fc, e) == "EventTalk" else None
    return None


def _entry_problems(fc):
    bad = []
    e = _step(fc, _entry(fc, TEXT_ENTRY))
    if e is None or _action(fc, e) != "EventTalk" or _val(e, "MessageId") != ("arg", "MessageId") or \
            _val(e, "OverrideStyle") != 4:
        bad.append(f"{TEXT_FILE}:{TEXT_ENTRY} is not one talk of its MessageId argument in the get window's style")
    for total in range(0, SLOTS + 3):
        got = run_key_entry(fc, total)
        want = ("arg", SLOT_ARGS[min(total, SLOTS - 1)])
        if got != want:
            bad.append(f"{TEXT_FILE}:{KEY_ENTRY}: a key total of {total} talks with {got}, want {want}")
    return bad


def run_plain(fc, target, banc, total=0):
    """What OpenGetWindow shows for the generic item `target` on map `banc` (key total `total` before the key):
    ("message", MessageId), ("vanilla", step name) or a problem string."""
    e = _step(fc, _entry(fc, "OpenGetWindow"))
    if e is None or _action(fc, e) != "EventCloseMessageDialog":
        return "OpenGetWindow no longer starts with its close step"
    e = _step(fc, e.get("next"))
    settled = False
    for _ in range(200):
        if e is None:
            return "the window's step ends nowhere"
        if e["name"] == WINDOW_REST:
            return ("vanilla", WINDOW_REST)
        if _action(fc, e) == "EventWait":  # (the wait that lets the caller's name land before it is read)
            settled = settled or (_val(e, "Frames") or 0) >= 2
            e = _step(fc, e.get("next"))
            continue
        if e["type"] == "switch" and _val(e, "GameDataName") == TARGET and not settled:
            return f"{e['name']} reads {TARGET} before a 2-frame wait (the caller's write may not have landed)"
        if e["type"] == "switch" and _query(fc, e) == "EventQueryIsGameDataString64":
            name = _val(e, "GameDataName")
            have = target if name == TARGET else banc if name == CURRENT else None
            if have is None:
                return f"{e['name']} compares {name}"
            e = _step(fc, _case(e, YES if have == _val(e, "Value") else NO))
            continue
        if _action(fc, e) == "EventTalk":
            nxt = _step(fc, e.get("next"))
            if nxt is None or nxt["name"] != WINDOW_END:
                return f"{e['name']} goes on to {nxt and nxt['name']}, not {WINDOW_END}"
            return ("message", _val(e, "MessageId"))
        if e["type"] == "subflow" and (e.get("flowchart") or "") in ("", TEXT_FILE) and e.get("entry_point") == KEY_ENTRY:
            nxt = _step(fc, e.get("next"))
            if nxt is None or nxt["name"] != WINDOW_END:
                return f"{e['name']} goes on to {nxt and nxt['name']}, not {WINDOW_END}"
            got = run_key_entry(fc, total)
            if got is None or got[0] != "arg":
                return f"{KEY_ENTRY} picks {got}"
            if _val(e, TOTAL_ARG) is None:
                return f"{e['name']} passes no {TOTAL_ARG}"
            return ("message", _val(e, got[1]), _val(e, TOTAL_ARG))
        return f"{e['name']}: unexpected step"
    return "the window's steps loop"


def _plain_problems(fc):
    bad = []
    areas = {v["area"]: v for v in dungeons().values()}
    for kind, actor in GENERIC.items():
        for area, d in sorted(areas.items()):
            has = {"Small Key": d["keys"], "Boss Key": d["boss_key"], "Map": d["map"], "Compass": d["map"]}[kind]
            for banc in maps_of(area):
                for total in ((0, 1, max_keys(area) - 1, max_keys(area), 9) if kind == "Small Key" else (0,)):
                    got = run_plain(fc, actor, banc, total)
                    if not has:
                        want = ("vanilla", WINDOW_REST)
                    elif kind == "Small Key":
                        n = total + 1
                        want = ("message", MSG.format(key_label(area, n) if n <= max_keys(area) else key_more(area)),
                                f"DungeonInfo.{area}.SmallKeyTotalNum")
                    else:
                        want = ("message", MSG.format(label({"Boss Key": "boss", "Map": "map", "Compass": "compass"}
                                                            [kind], area)))
                    if got != want:
                        bad.append(f"OpenGetWindow: {actor} on {banc} (key total {total}) shows {got}, want {want}")
        got = run_plain(fc, actor, "HyruleField")
        if got != ("vanilla", WINDOW_REST):
            bad.append(f"OpenGetWindow: {actor} outside a dungeon shows {got}, want the vanilla window")
    got = run_plain(fc, TCG_GENERIC, "Market_Child")
    if got != ("message", MSG.format(label("plain", TCG))):
        bad.append(f"OpenGetWindow: {TCG_GENERIC} shows {got}, want OoTR's Treasure-Chest Shop key message")
    for other in ("Obj_Rupee_Red", "Item_Bottle", "Item_Hookshot"):
        if run_plain(fc, other, "ForestTemple") != ("vanilla", WINDOW_REST):
            bad.append(f"OpenGetWindow: {other} no longer reaches the vanilla window")
    return bad


def main(argv):
    if argv[:1] == ["--show"]:
        langs = argv[1:2] or list(LANGS)
        for lb, per_lang in messages().items():
            for lang in langs:
                m = per_lang[lang]
                print(f"{lb} {lang}: {m}")
        return 0
    if argv[:1] == ["--check"]:
        bad = check(*(argv[1:2] or [DEFAULT_ROMFS]))
        for b in bad:
            print(b)
        n = len(messages())
        print(f"{n} messages x {len(LANGS)} languages: {len(bad)} problems")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
