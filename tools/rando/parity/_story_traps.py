"""Game-state traps that another remake randomizer's players (OotrR) hit in game, fixed in every seed (story plugin).
TODO: none of this has been seen in game yet.

Quests that move back (findings B1-B4, B7). The remake's EventExecuteProgressChallengeStep applies at any step, even
"Complete" when IsIgnoreCompletedChallenge is False, so a scene played out of the vanilla order moves its quest back.
- Every progress request of Get_StoneOfFire, DoorOfTime, Get_StoneOfWater and SageOfWater in any scene file
  (story_data.json "requests", 58 requests) is skipped once its quest is at or past the requested step. That uses
  the game's own "<quest>_IsAfter_<step before>_Exp" expressions, plus one new expression where the game has none.
  In the vanilla order every request moves its quest forward, so the vanilla game plays as before. This covers the
  Door of Time (Zelda's Step01, Impa's send-off Step02, Zelda's and Saria's Srep2_1_1, the stone checks), the Fire
  stage (the send-off's KakarikoVillageNpc, the first Kakariko -> trail arrival's DeathMtTrailNpc, Saria's lesson,
  Darunia's gift), King Zora (the first river -> domain arrival, Impa, the river owl, the diving game, Ruto's Letter
  found or read again) and the Water Sage (the Serenade after Morpha, the lake arrivals).
- The stone check's Step03 (DoorOfTime Event37) is skipped and ends the check, otherwise it would raise the
  drawbridge again.
- Dm_Goron_0030 (Darunia's gift) has no save-data actor, so its DodongoCavernOpne request moves into a new entry of
  Get_StoneOfFire and gets guarded there.
- Impa's send-off runs the stone check again (DoorOfTime_CheckStoneNum) when a stone stage is complete and the Door
  of Time isn't at Step03 yet (OotrR validated it in game).
- Rauru (DoorOfTime:Event93) only completes the Door of Time quest once the Song of Time lesson is done (past
  Step04). With an open door the first trip can come before Zelda's escape, whose drawbridge area needs exactly
  Step03. With a non-vanilla door the lesson then completes it, once the first trip is done (Dm_TimeTemple_0040
  played).
Side and later quests: every progress request of SageOfFire,
  SageOfSpirit and Get_Epona, the Kakariko burning's two SageOfShadow requests and the last sage's AllSage Step02
  are skipped once their quest is past the requested step ("<quest>_IsAfter_<step>_Exp"). A request at its own
  step still runs like in vanilla, so boss and race retries are left alone. Adult Malon's GuideToLonLonRanchAdult
  (Npc_Hylia_Malon_Adult Event177) isn't one of them: it moves ReadyForGetEponaSong back on purpose, for an adult who
  never met Epona as a child. It's skipped once child Malon's Epona intro has played (EPONA_BACK).
Darunia's gift (B5): after the dance, Get_StoneOfFire Event39 sends a quest past SariaMelodyPlay to the plain talk.
The owls (OWLS_STAY): the Death Mountain Trail and Lake Hylia owls leave for good once the Spirit Temple's walk back
to the Temple of Time plays (HavePlayedEvent.Dm_TimeTemple_0086). In OoT they stay, and OoTR's logic flies a child
from the summit onto Impa's rooftop any time, so they stay here too.
  Now it plays the gift scene while HavePlayedEvent.Dm_Goron_0030 is false (Dodongo's Cavern finished first).
Malon (B6): SubEvent_GetEponaSong Event36 sends Malon back to the castle (second visit, Talon awake there, the egg
  Malon gone) once Dodongo's Cavern is done and Jabu-Jabu isn't. Now that only happens once Talon's wake-up scene
  has played, otherwise the flag gets cleared.
The clock (A1): HyruleField_ArriveEntrance is true on a new file (OotrR issue #57, confirmed in game). The clock is
  held at 06:00 and the Sun's Song does nothing until Kaepora's first field talk sets it, and skip_child_zelda and
  remake_skip_talon delete that talk. The owl still plays where it would, its trigger doesn't read the flag.
Great Fairies (D4a/D4b): Zelda's Lullaby calls every fairy (TriForcePoint Event8, which waited for
  IsGet.Item_DinFire for five of them). Each fairy has her own saved flag (RandoGreatFairy_<name>), set at the start
  of her reward cut, and every "already given" test of her vanilla item in the six fountain flows and
  TriForcePoint's six-fairy count reads it. Before, they read IsGet.<item>, which gets set wherever that item is
  found.
Refill scrubs (G6): Unopened_Check hides each good Link can't use. When all three are hidden the first one is shown
  (the purchase keeps its vanilla checks).
Also, each with its own comment below: Impa's send-off flag at the start (U2), the adult 20:00 clock stop (U3), the
  quest-menu presentation after Gohma (U13), open_kakariko open's Fire stage (U15), Link the Goron's tunic (B8), the
  Temple of Time Sheik on the pedestal's prompt (C2), the Kokiri schedules (E1-E3), the Dodongo's Cavern boulder and
  Link's bombs (F1), the Lake Hylia tree's hookshot wall (F4), the cucco count (H1), and the Kokiri Forest rock ring
  and its centre rock (one layout for every story state). The story plugin's Plan also sends a guard's skip
  into the next step's own hooks when that step is hooked too (story.Plan.assemble)."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

ORDERED = ("Get_StoneOfFire", "DoorOfTime", "Get_StoneOfWater", "SageOfWater")
# Requests the order guard leaves alone:
# - the Door of Time scene's Step06. story.door_of_time ends it with a non-vanilla door, and the vanilla chain sets it
#   at Step05.
# - Rauru's Complete (rauru_after_lesson)
# - Zelda's Step01 (Goto_HyruleCastle Event32). Impa's Zelda's Lullaby lesson is DoorOfTime Step01's participant
#   schedule (RSDB/Challenge). A stone dungeon done before Zelda moved the quest past Step01, and then the guard lost
#   the lesson for good. Instead the stone check waits for the lesson
#   (STONE_COUNT_GATE) and Impa's send-off counts the stones again (send_off_recheck).
UNGUARDED = {("DoorOfTime", "Event57"), ("DoorOfTime", "Event93"), ("Goto_HyruleCastle", "Event32"),
             ("Npc_Hylia_Malon_Adult", "Event177")}
# Requests another plugin already guards. We leave them to it, since a second guard would sit between its own and the
# request. That's Dampe's race's SageOfForest Step02 (Event97) and Step03 (Event132), parity/_chests_dampe.py
# "already past" guards.
GUARDED_ELSEWHERE = {("MiniGame_DampeRace", "Event97"), ("MiniGame_DampeRace", "Event132")}
# Quests only guarded from going back. They're skipped once past the requested step, and a request at its own step
# runs like in vanilla. The audit's rows:
# - SageOfFire_CityIn / _CityIn_CrackWall Event4 (one step, both entries), an adult in Goron City after the temple
# - SageOfSpirit's head carpenter's stop (Npc_Hylia_012_Adult Event121), the fourth carpenter (Event146) and the
#   Colossus hand chest (Event21) after the temple
# - Get_Epona's child Malon guides (Event345/Event424), her first ranch talk (Event346), the song (Dm_MelodyGet_Epona
#   Event82), adult Malon's Epona talk (Event86) and the race-won scene (Dm_LonLon_0040 Event108) after Epona is won.
#   Adult Malon's Event177 is on purpose (UNGUARDED above).
# SageOfForest too, the gamedb audit caught it. The Master Sword's first pull chain (DoorOfTime_Draw ->
# SageRoom_MeetGanondorf -> SageRoom_MeetRauru -> AllSage:Market_Adult_AllSage_Start) set it back to Step01 when
# replayed later (Event19). The Forest Temple's own scenes (Dm_ForestTemple_0010/0015/0017, SageOfForest
# Event5/Event59) and Dampe's race moved it back when played after a later step.
PAST_ORDERED = ("SageOfFire", "SageOfSpirit", "Get_Epona", "SageOfForest")
# Wrong states from only these requests. The Kakariko burning
# (Dm_SY_BancChangeArrive:KakarikoVillage_MelodyGet_Shadow, plays on the adult arrival once Forest, Fire and Water are
# complete) set GoToDungeon / GotGlassTruth even after an early Shadow Temple. The last sage's room
# (AllSage:SageRoom_AllSage_LastSage Event20) set Step02 after a non-vanilla lacs had completed AllSage, which armed
# the Light Arrow scene's trigger again (Market_Adult_Prefab_c668, AllSage = Step02).
PAST_ONLY = {"SageOfShadow": {("Dm_SY_BancChangeArrive", "Event49"), ("Dm_SY_BancChangeArrive", "Event176")},
             "AllSage": {("AllSage", "Event20"), ("AllSage", "Event18")}}  # Event18 is the same Step01 replay
# the audit rows these guards answer. The read-back checks each one is guarded on "past its step".
QUEST_ROWS = (("SageOfFire", "Event4"), ("Npc_Hylia_012_Adult", "Event121"), ("SageOfSpirit", "Event146"),
              ("SageOfSpirit", "Event21"), ("Get_Epona", "Event345"), ("Get_Epona", "Event424"),
              ("Dm_LonLon_0040", "Event108"), ("Dm_SY_BancChangeArrive", "Event176"),
              ("Dm_SY_BancChangeArrive", "Event49"), ("AllSage", "Event20"), ("AllSage", "Event18"),
              ("AllSage", "Event19"), ("Dm_ForestTemple_0010", "Event2"), ("Dm_ForestTemple_0015", "Event14"),
              ("Dm_ForestTemple_0017", "Event45"), ("SageOfForest", "Event5"), ("SageOfForest", "Event59"))
# DoorOfTime_CheckStoneNum (Event38, run at the Dodongo's Cavern / Jabu-Jabu ends and after Impa's send-off) does
# nothing until Impa's lesson has played or the castle story is complete (skip_child_zelda starts it complete). Before
# Zelda the Door of Time stays below Step01, so her Step01 and Impa's lesson always come, and then the send-off's
# recount gives Step2_x / Step03. For logic the moat items need Zelda met, same as OotrR's rule.
STONE_COUNT_GATE = ("DoorOfTime", "Event38", "Rando_DoorOfTime_StoneCountOpen_Exp",
                    [[0, "HavePlayedEvent.Dm_MelodyGet_Zelda"], [10, "Goto_HyruleCastle_IsCompleted_Exp"], [4]])
# Kaepora's first field talk (Goto_HyruleCastle_Kaepora_00) does more than the clock.
# It clears HyruleField_ChangeENV, the field's pinned
# first-visit light that Saria's bridge sets (Event218). It marks its panorama played, and the field theme is muted
# until HavePlayedEvent.Dm_HrlField_0000 (Bootup BGMGeneralParam). It also shows the field on the pause map and opens
# the quest menu.
# Saria's bridge doesn't set the light anymore (Event44 goes on past Event218). Where the owl can't play anymore, its
# lasting effects are set instead. The talk is deleted once Goto_HyruleCastle is past Step01, so that's
# skip_child_zelda / remake_skip_talon from a new file, or Talon woken before the owl.
OWL_ENV = ("Goto_HyruleCastle", "Event44", "Event218", "Event42")
# The first field visit's sunrise. On the first Hyrule Field entry the time of day went from day to night and then
# day again really quickly. The owl's first field talk (Goto_HyruleCastle_Kaepora_00) sets CLOCK_FLAG (Event153),
# then plays the field panorama Dm_HrlField_0000 (Event3). The panorama's Event29 (Event_SetTimeForFlowchart, ToHour
# 7 ToMin 30, TransitionSec 22) runs the clock forward to 07:30 over 22 seconds.
# Vanilla holds the clock at the new file's 06:00 until this talk, so that's a 1.5-hour sunrise. With CLOCK_FLAG on
# from the new file (A1) the clock has been running, so at the first field entry it's past 07:30 and the 22 seconds
# run a whole day and night to the next 07:30. A starting_tod later than 07:30 did the same in vanilla's hold.
# Now the talk sets the clock to 06:00 right before the panorama, so the panorama is vanilla's sunrise again. That's
# EventTrigger_SetTime like OpeningEvent's Event9 does, a frame, then the env palette rebuilt like the talk's own
# Event221 does. The time after the talk is unchanged, the scenes end it at 07:30 (Dm_HrlField_0000 Event52 07:00,
# then Dm_HrlField_0005_Env 07:30).
OWL_SUNRISE = ("Goto_HyruleCastle", "Event153", "Event3", "Dm_HrlField_0000", "Event29", 6, 0,
               "Rando_Traps_OwlSunrise")
OWL_PLAYED = "HavePlayedEvent.Dm_HrlField_0010"  # the owl's last scene, its trigger runs while this is unplayed
OWL_EFFECTS = {"HavePlayedEvent.Dm_HrlField_0000": True, "IsVisitLocation.HyruleField": True,
               "UI_IsFinishChallengeMenuOpenEvent": True}
OWL_LOST_AT = ("Dm_HrlCastle_0020", "Event121")  # Talon's wake-up: Goto_HyruleCastle Step04 at any step
# The Death Mountain summit owl only flies Link down with IsGet.Item_DinFire (Event4), but OoTR's flight is
# free.
DMT_OWL = ("Npc_Kaepora_DeathMountainTrail", "Event4", 1, "Event18")
# The Hyrule Field grotto scrub only sells his heart piece once HaveReadHrlField_Note07 is set, and that note
# is only on the adult map (FirstTalk_Secret Event715/Event633). Now his password question always comes, and wrong
# answers can retry.
SCRUB_NOTE = ("Enemy_Scrub_Business_Common", (("Event715", 1, "Event638"), ("Event633", 1, "Event664")))
# Dodongo's Cavern room 16. Both shutters lock from inside until the room is
# clear, and the two Lizalfos (nodes 0/1) are only created by node 18 = OR(the east shutter's IsPlayingEvent, the
# saved DodongoCavern_AppearLizalfos_2F). The east shutter is node 11, from room 15. Coming through the west shutter
# (node 10, from the far bridge) shut Link in an empty room. Node 18 now also reads node 10's IsPlayingEvent (one
# more multi-input source, its output flagged, the query list following), so entering from either side starts the
# fight.
DC_LIZALFOS = ("Logic/Gimmick_DodongoCavern_MiddleBoss02_6dee.logic.module.ainb", 18, "BoolMulti", 10, "IsPlayingEvent")
# The Kakariko windmill heart piece and OoTR's child Boomerang route. The Boomerang is a lifter (Weapon_Boomerang
# LifterParam, binds to Bind_A) and fetches anything with a LiftableParam, which is every pickup (rupees, hearts,
# tokens, keys... 35 packs hold Obj_Item_Base's LiftableParam). Obj_Heart_Piece's ActorParam sets LiftableRef to "",
# but its root AI already handles being carried (QueryLiftableIsBindState -> rigid-body layer change, like
# DropItem.root). Now its LiftableRef names Obj_Item_Base's LiftableParam, the value its parent Obj_Item_Base gives
# every pickup, so in effect the override is gone. The file is copied into its pack from Obj_Rupee_Green's, same
# bytes. Then every Obj_Heart_Piece placement, and the randomizer's item looks built on it, can be fetched like OoT's
# freestanding items. The two variants holding the same ActorParam (Obj_GerudoValley_Heart_Piece,
# Obj_Heart_Piece_Digging_Hole) override LiftableRef to "" in their own ActorParam and stay as they are.
#
# The rock ring by Mido's house. One logic module serves both ages' layouts. For an adult before
# Phantom Ganon (node 32 = AND(Adulthood, SageOfForest_IsBefore_Step08)) it deleted the 8 rocks the child always has
# (logic Rocks 5, 9, 12, 15, 18, 23, 24, 29) and created 4 others (Rocks 7, 14, 20, 27) instead. After Phantom Ganon
# the adult ring became the child's. Going by the rocks' own collision hulls (Obj_LiftRock_A_01 Physical polytope,
# each placement's rotation), 1345, 39ec and f726 stand inside e464, 79ff and 4151 (overlap 0.35, 0.08, 0.12 m), and
# b2db stands on its own (0.19 m from b129, 0.40 m from f107).
# Now the 8 are never deleted and the 3 inside them are never created (Logic_Create False, the game's own form for an
# actor that's never created). b2db is always created for an adult (its Create reads Adulthood alone), so no rock
# spot leaves the world. The Bool is read elsewhere too (KokiriForest_Level_Area_01_Prefab_054c), so only these
# inputs change.
KF_RING = ("Logic/KokiriForest_Common_Level_All_01_6aaf.logic.module.ainb",
           {0: "4079", 1: "4151", 2: "6b1c", 3: "79ff", 4: "ab49", 5: "b129", 6: "e464", 7: "f107"},  # never deleted
           {34: "1345", 35: "39ec", 37: "f726"},  # never created
           (36, "b2db", 31, "Adulthood"))  # created for an adult always
# The ring's centre (logic Rock 19). Before Gohma a fixed rock stands there (Obj_LiftRock_A_02_2143, no LiftableParam,
# no drops), and after Gohma it's the liftable Obj_LiftRock_A_01_0de2 at the same spot. Both read node 3 =
# Get_StoneOfForest_IsCompleted_Exp. Now it's always the liftable one and never the fixed one.
KF_CENTRE = ("Logic/KokiriForest_Child_Level_All_02_6960.logic.module.ainb", (1, "Obj_LiftRock_A_01_0de2"),
             (0, "Obj_LiftRock_A_02_2143"))
# ... and the Kokiri on it. I couldn't lift Rock 19 before Gohma.
# Npc_Kokiri_008_Child (#1144806972662031190, 0.78 m from the rock, IsBasePositionToActorPos) waits at his base before
# Gohma. His DefaultSchedule has no ActionType and plays Act_Lift_Rock there, crouched on the centre rock. After Gohma
# (ConditionalSchedule[0], Get_StoneOfForest_IsCompleted_Exp) he takes Action2, AnchorAction2 7.4 m east, looking far
# off (Act_Lookfar), and after the castle Action3 (5.9 m away). Vanilla never has him and the liftable rock together.
# Now [0]'s ConditionFlag is always true (KF_BOY[2], the Deku Tree done or not), so from a new file he stands at
# AnchorAction2 like after Gohma. [1] (the castle state, E1-E3's Rando_Kokiri_CastleAfterDeku_Exp) still wins when
# true, since the last true ConditionFlag wins. His talk (Npc_Kokiri_008_Child: Talk / C1_T, Near / DC0C1_NNN) is the
# same event in every schedule, and its pre-Gohma steps that played the rock don't anymore:
#   - PlayAct_Lift_Rock_To_Stand (Event129 Act_Lift_Rock_To_Stand, its 60-frame wait Event157) and
#     PlayAct_Stand_To_Lift_Rock (Event81 Act_Lift_Rock_To_Crouch, wait Event163) play "Wait" for 1 frame (their
#     flag steps stay as they are)
#   - LiftRock_AllBroken_TalkAndStand's call (Event62) passes no ASName, like the module's other four calls
#   - the "Near" grunts while he strains at the rock ("Ugh." / "So heavy...", Event36's not-done case -> Event155)
#     show nothing
# The ring reward and its talk are unchanged (8 rocks broken, KokiriForest_Common_Level_All_01_6aaf node 10 ANDs
# exactly the 8 ring rocks, not the centre one). I checked with npc_overlap for every NPC base or schedule anchor
# within 3 m of an object the story traps force present (KF_RING, KF_CENTRE, DMT_ROCKS, night Gold Skulltulas by
# day), and it's only this boy.
KF_BOY = ("Npc_Kokiri_008_Child", "Get_StoneOfForest_IsCompleted_Exp", "Rando_Kokiri008_OffRock_Exp")
KF_BOY_EXP = [[10, KF_BOY[1]], [10, KF_BOY[1]], [5], [4]]  # (done) OR NOT (done): always true
KF_BOY_STEPS = (("Event129", "ASName", "Wait"), ("Event157", "Frames", 1), ("Event81", "ASName", "Wait"),
                ("Event163", "Frames", 1), ("Event62", "ASName", ""))
KF_BOY_NEAR = ("Event36", 1, None)  # (switch, case value: Get_StoneOfForest not complete, new target)
# Death Mountain Rocks 7/8 (merged locations). DeathMountainTrail_Child_Prefab_0821 deletes two rocks (_504b, _eeb2)
# and creates two others (_23f6, _a313) once Get_StoneOfFire is complete (node 4, read by these four only). Each pair
# is one spot, exactly the same position and rotation (#3302088556978088009 / #11074416093858939225 at (-19.74,
# 128.65, 13.98), #11138816988756551783 / #6087670250388905572 at (-20.29, 128.65, 14.62)). Each copy kept its own
# save flag, so a merged location gave its item once per copy. Now the first pair is never deleted and the second
# never created, so it's one rock per spot and one item. The second pair's vanilla bomb drop after King Dodongo goes.
DMT_ROCKS = ("Logic/DeathMountainTrail_Child_Prefab_0821.logic.module.ainb",
             {1: "Obj_Pot_A_03_504b", 3: "Obj_Pot_A_03_eeb2"},  # never deleted (the instances keep a pot's name)
             {0: "Obj_Pot_A_03_23f6", 2: "Obj_Pot_A_03_a313"})  # never created
HEART_PIECE_LIFT = ("Actor/Obj_Heart_Piece.engine__actor__ActorParam.bgyml",
                    "?Component/LiftableParam/Obj_Item_Base.game__component__LiftableParam.bgyml",
                    "Component/LiftableParam/Obj_Item_Base.game__component__LiftableParam.bgyml",
                    "Pack/Actor/Obj_Heart_Piece.pack.zs", "Pack/Actor/Obj_Rupee_Green.pack.zs",
                    ("Pack/Actor/Obj_GerudoValley_Heart_Piece.pack.zs", "Pack/Actor/Obj_Heart_Piece_Digging_Hole.pack.zs"))
# The jailed carpenters. Their rescue runs on SageOfSpirit Step01's participant schedules (RSDB/Challenge, Step01:
# Npc_Hylia_013..016_Adult [GerudoFortress] -> SageOfSpirit_Step01_Npc_Hylia_0xx_Adult_GerudoFortress). That's the talk
# that brings the first thief, the calls for help and the talk after the fight. At any other step a carpenter falls
# back to his actor's own schedule, a plain talk, and the cell door only starts a fight once you hold another cell's
# key. The Spirit Temple sets later steps (the child's arrival Step07_00, Nabooru Step06, the Silver Gauntlets tip
# Step05_02/03), so going there first with Requiem left all four carpenters stuck and the card gone. Now each one's own
# schedule is his Step01 schedule, so he acts the same at every step until he's freed (GerudoFortress_Saved_* deletes
# him). These four adult actors are only placed in the fortress. The Escaped carpenters in Gerudo Valley inherit the
# adult actor, so they name their old schedule themselves (the child carpenters already name their own). Vanilla
# points three NPCs (Npc_Goron_005_Child, Npc_Goron_007_Child, Npc_Hylia_Soldier_003) at schedules that only live in
# Pack/AIScheduleParam, same as these. (actor param, its new schedule, Escaped's actor param, the old schedule)
CARPENTER_SCHEDULE = {c: (f"Actor/Npc_Hylia_{c}_Adult.engine__actor__ActorParam.bgyml",
                          f"?Component/AIScheduleParam/SageOfSpirit_Step01_Npc_Hylia_{c}_Adult_GerudoFortress"
                          ".game__component__AIScheduleParam.bgyml",
                          f"Actor/Npc_Hylia_{c}_Adult_Escaped.engine__actor__ActorParam.bgyml",
                          f"?Component/AIScheduleParam/Npc_Hylia_{c}_Adult.game__component__AIScheduleParam.bgyml")
                      for c in ("013", "014", "015", "016")}
# The jail Gerudo who shows up in a cleared cell (Npc_Gerudo_001, CarpenterSet_0x) leaves once SageOfSpirit is past
# Step01, and the fortress one (Common_58a8) arrives then. The card scene (SageOfSpirit:Meet_FourCarpenter_ClearEvent)
# takes "an Npc_Gerudo_001" and moves the quest to Step02, so in the vanilla order they swap right there. With the step
# jumped early they swapped before any rescue. Both also wait for the card scene now (CARD_PLAYED, which the scene
# sets and nothing in vanilla reads). (file, the AND node, a bool-reader node to copy for it)
CARD_PLAYED = "HavePlayedEvent.Meet_FourCarpenter_ClearEvent"
JAIL_GERUDO = tuple((f"Logic/GerudoFortress_Common_Level_CarpenterSet_0{i}_{h}.logic.module.ainb", 2, 1)
                    for i, h in ((1, "e139"), (2, "9477"), (3, "c7f2"), (4, "e9a4"))) + (
    ("Logic/GerudoFortress_Common_58a8.logic.module.ainb", 3, 1),)
STONE_CHECK_STEP03 =("DoorOfTime", "Event37")  # skipped: the check ends (no second drawbridge raise)
CLOCK_FLAG = "HyruleField_ArriveEntrance"
FAIRY_FLAG = "RandoGreatFairy_"
# fountain flow -> (its vanilla item, the dev-comment step that opens her reward cut (entry C15-01), the give step)
FAIRIES = {"Din": ("Item_DinFire", "Event403", "Event212"), "Power": ("Item_FairyBless_MP", "Event154", "Event141"),
           "Frore": ("Item_FaroreWind", "Event147", "Event174"),
           "Wisdom": ("Item_FairyBless_MPDouble", "Event124", "Event144"),
           "Courage": ("Item_FairyBless_DefenseDouble", "Event131", "Event144"),
           "Nayru": ("Item_NayruLove", "Event136", "Event163")}
FAIRY_ENTRY = "C15-01"
FAIRY_CALL = ("TriForcePoint", "Event8", "Event26")  # the Lullaby call gate, its "call the fairy" step
SCRUB = ("Enemy_Scrub_Business_Common", ("Event192", "Event334"), "Event119",
         ("Enemy_Scrub_Business_Unopened01", "Enemy_Scrub_Business_Unopened02", "Enemy_Scrub_Business_Unopened03"))
DARUNIA = ("Get_StoneOfFire", "Event39", "Event42", "Event31", "HavePlayedEvent.Dm_Goron_0030")
MALON = ("SubEvent_GetEponaSong", "Event36", "IsMalonAppear_HyruleCastleSecondTime", "HavePlayedEvent.Dm_HrlCastle_0020")
# Malon's Friend could get stuck for good. Nintendo's 1.1.2 update fixed "an issue where the event "Malon's Friend"
# could not be progressed" without saying what caused it; this is the dead end the 1.1.1 files have. Child Malon's
# Epona intro (her EponaCamera: IsNpc_Hylia_Malon_Child_Talk_00_Played, then Get_Epona ReadyForGetEponaSong) only ever
# plays once, and the song lesson only works at exactly ReadyForGetEponaSong (its Forbid_MelodyGet_Epona area in
# Logic/LonLonRanch_Child_NoTerrain_Prefab_5286 is only there at that step). Adult Malon's Action5 talk (after you
# lose Ingo's race on another horse: LonLonRanch_GambleRaceLoseOtherThanEpona) moves the quest back to
# GuideToLonLonRanchAdult while it isn't past ReadyForGetEponaSong (Event179 -> Event177). So a child who met Epona,
# left without the song (no Ocarina yet, say), then lost that race and talked to adult Malon could never learn it, and
# Song from Malon was lost. Now the step back is skipped once the intro has played. Nothing else can take the quest
# back below the lesson: its other requests are order-guarded.
EPONA_BACK = ("Npc_Hylia_Malon_Adult", "Event177", "IsNpc_Hylia_Malon_Child_Talk_00_Played")
FIRST_TRIP = "HavePlayedEvent.Dm_TimeTemple_0040"
# Link the Goron's tunic (findings B8). He only gives it in his SageOfFire TalkDaruniaJr talk, and entering the adult
# crater (Logic/DeathMountainCrater_Adult_Prefab_a0e2: MeetSheik) or the Fire Temple (MeetDarunia) first moves the
# quest past that step for good. A saved flag marks the give, set right after his thanks (SageOfFire Event396, a step
# no reward edit touches). While it's unset and the quest is past TalkDaruniaJr, his talk runs the tunic talk instead.
# Past the quest's own steps his base schedule (Component/AIScheduleParam/Npc_Goron_DaruniaJr_Adult) never rolls,
# because the rolling ActionType 1644798398 is only in the Ready/StopDaruniaJr step schedules. It offers one of two
# talks, the plain "Talk" (no bomb hit, default) or "SageOfFire_IsCompleted_Exp_Talk" (quest complete, or arrived
# from the crater or the trail, last true state wins), and both are hooked.
LINK_GORON = ("SageOfFire", "Event396", "Npc_Goron_DaruniaJr_Adult",
              {"Talk": "Event99", "SageOfFire_IsCompleted_Exp_Talk": "Event0"}, "Rando_LinkGoronTunicGiven",
              "SageOfFire_IsAfter_TalkDaruniaJr_Exp", "SageOfFire:Step02_Npc_Goron_DaruniaJr_Adult_Talk")
SEND_OFF_PLAYED = "HavePlayedEvent.Dm_HrlField_0020"  # U2: with CLOCK_FLAG the Sun's Song brings night (OotrR #57)
ADULT_CLOCK = ("Dm_TimeTemple_0055", "Ready", "Event252", "Event1")  # U3: the entry, its flag step, the step after
STONE_MENU = ("Dm_Kokiri_0130", "Event56", "Event52")  # U13: the wait before the quest-menu presentation, the menu
FIRE_OPEN_KAKARIKO = "KakarikoVillageLetter"  # U15: the step the guard's letter reading sets

# Same-size 32-bit edits of uncompressed level-logic modules (offset, new, vanilla), read back word by word. Bit 31 of
# an output word = "Is Output", and a node only computes those.
# Link's own bombs break the Dodongo's Cavern boulder (OotrR qol_patches.let_bombs_break_dc_boulder, validated in
# their game). The cutscene request (node 2) follows the observers' OR (node 5) instead of AND(bomb flower, OR). Node
# 5 watches node 20 (Item_Bomb, the three areas, left unconnected in vanilla) in place of node 18 (bomb fruit, third
# area), and the query lists, plug and output flags follow.
DC_BOULDER = ("Logic/DeathMountainTrail_Child_Prefab_ffa7.logic.module.ainb", [
    (0x2C24, 0x00010005, 0x0001000E),   # node 2 EventRequestTrigger <- (5, 1) was (14, 1)
    (0x35F0, 5, 14),                    # node 2 query list: q5 was q14
    (0xD04, 5, 14),                     # node 2 plug: node 5 was 14
    (0x3554, 0x00000014, 0x00000012),   # node 5 multi-input 3rd entry: (20, 0) was (18, 0)
    (0x35FC, 20, 18),                   # node 5 query list 3rd entry: q20 was q18
    (0x3268, 0x800004BC, 0x000004BC),   # node 20 IsHit flagged
    (0x3258, 0x000004BC, 0x800004BC)])  # node 18 IsHit no longer read
# The cucco pen (Logic/MiniGame_CatchCucco_c69b, findings H1). Node 17 compares Int_A = 7 with node 9's count of the
# seven cage flags and node 18 reads Equal. With chicken_count N it compares N - 1 and node 18 reads A_Smaller
# (N - 1 < count, so count >= N), flagged (OotrR PR #74).
CUCCO = "Logic/MiniGame_CatchCucco_c69b.logic.module.ainb"
CUCCO_INT_A, CUCCO_MULTI, CUCCO_SMALLER = 0x4BD8, 0x5D30, 0x56A8
# The Temple of Time Sheik (Logic/Market_Adult_Prefab_7f43, findings C2). He's only deleted once the Prelude is
# taught, so from the first adult arrival to Phantom Ganon he stands 1.4 m from the pedestal and takes its put-in
# prompt. Now he's deleted once the Prelude is taught OR (the first adult arrival is over AND the Prelude isn't due
# yet). The remake's Prelude trigger, Market_Adult_Prefab_edc2, reads SageOfForest_IsCompleted_Exp. Node 2 (the
# module's spare expression reader) reads the new expression and feeds the NPC's Logic_Delete.
SHEIK = ("Logic/Market_Adult_Prefab_7f43.logic.module.ainb", 2, 0, "Rando_SheikTempleGone_Exp")
SHEIK_EXP = [[0, "Market_Adult_GetLightPrelude"], [10, "AllSage_IsAfter_Ready_Exp"],
             [10, "SageOfForest_IsCompleted_Exp"], [5], [3], [4]]
# Kokiri schedules (Component/AIScheduleParam, the last true ConditionFlag wins, findings E1-E3). Their castle state
# (Goto_HyruleCastle_IsCompleted_Exp) and Mido's story states come before the Deku Tree when Zelda is met first or
# skipped. Then Mido and the exit guard walk away without the talk that lowers their wall.
SCHEDULE = "Component/AIScheduleParam/{}.game__component__AIScheduleParam.bgyml"
CASTLE = "Goto_HyruleCastle_IsCompleted_Exp"
DEKU_DONE = "Get_StoneOfForest_IsCompleted_Exp"
MIDO_WALL = "KokiriForest_Npc_Kokiri_Mido_Child_Blocker"
EXIT_WALL = "KokiriForest_Npc_Kokiri_007_Child_Blocker_00"
KOKIRI_CASTLE = ("Npc_Kokiri_003_Child", "Npc_Kokiri_004_Child", "Npc_Kokiri_005_Child", "Npc_Kokiri_008_Child",
                 "Npc_Kokiri_009_Child", "Npc_Kokiri_010_Child", "Npc_Kokiri_011_Child", "Npc_Kokiri_012_Child",
                 "Npc_Kokiri_013_Child", "Npc_Kokiri_Fado_Child")
# The Lake Hylia island tree (findings F4). A FldObj_AirWall_Hookshot covers it for adult until the Water Temple's
# Longshot chest (Presence: WaterTemple_Room07_00 negated), but OoTR's LH GS Tree only needs the Longshot and night.
# Its Presence becomes "child" in the adult map, so it's never there (OotrR's lake_tree_wall_edits).
LAKE_TREE_WALL = ("Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs", "9829790505452123995",
                  {"FlagName": "Sequence_IsChildhood", "IsCheckLazy": False, "IsNegation": False})
# The Water Temple gate switch (tools/gamedb). A FldObj_AirWall_All (1.5 m cube)
# encloses Obj_LakeHrl_SwitchHit_A_01 until SageOfWater_IsAfter_Step03_Exp, so Step04+, and only the Ice Cavern
# Serenade scene gives that (King Zora's thaw only sets Step05 once the Serenade is had). That's the vanilla
# Ice-Cavern-first order. OoTR's Water Temple needs no Ice Cavern, so the adult map's wall is never there (same as the
# lake tree wall). It's safe without it. The temple's own chain doesn't need Step06, because opening the boss door at
# any earlier step sets Step07_1_Safety, whose event leads to Morpha (Logic/WaterTemple_Level_Room_23_Prefab_eb85).
# The child map's copy (#10539271334350898185) stays, since a child could hit the switch with seeds or the Boomerang
# and play the gate scene.
GATE_SWITCH_WALL = ("Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs", "2935529029587700987",
                    {"FlagName": "Sequence_IsChildhood", "IsCheckLazy": False, "IsNegation": False})
# Village Saria (Logic/KokiriForest_Child_Level_Npc_Kokiri_Saria_Child_a766, findings E3). Node 11 (Saria) is deleted
# on OR(..., node 15 Goto_HyruleCastle_IsCompleted_Exp, ...), so after Zelda she's in the meadow. Vanilla only meets
# Zelda after the Deku Tree, but skip_child_zelda (castle complete from a new file) took her out of the village
# before it. Node 15 now reads the castle AND the Deku Tree, like the Kokiri schedules.
VILLAGE_SARIA = ("Logic/KokiriForest_Child_Level_Npc_Kokiri_Saria_Child_a766.logic.module.ainb", 15,
                 "GameDataNameBoolExp", "Goto_HyruleCastle_IsCompleted_Exp", "Rando_Kokiri_CastleAfterDeku_Exp")
# The child owls (tools/gamedb gates): Npc_Kaepora_DeathMountainTrail's and Npc_Kaepora_LakeHylia's placements are
# there only while HavePlayedEvent.Dm_TimeTemple_0086 is unplayed (SageOfSpirit's WalkBackTimeTemple /
# OcarinaBackTimeTemple), and the lake owl's Logic_Create also reads it (node 4). The placements lose the Presence and
# node 4 reads the ending's flag instead (Defeat_Ganon, only in the final battle), which the game never sets before.
OWLS_STAY = (("Banc/DeathMountainTrail/DeathMountainTrail_Child_Static.bcett.byml.zs", "12462382357514187119"),
             ("Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs", "8515476870752834170"))
OWLS_GONE = "HavePlayedEvent.Dm_TimeTemple_0086"
LAKE_OWL_LOGIC = ("Logic/HyruleField_LakeHylia_Child_Prefab_32f1.logic.module.ainb", 4, "GameDataNameBool",
                  "HavePlayedEvent.Dm_Ending_0000")
MIDO_STATES = ("Meet_DekuTree_IsAfter_Step02_Exp", "Meet_DekuTree_IsCompleted_Exp",
               "Get_StoneOfForest_IsAfter_DefeatBoss_Exp", "Get_StoneOfForest_Complete_Mido_TalkEnd", CASTLE)


def _data():
    from parity import story
    return story.DATA


def _murmur(name):
    from romtools import murmur3_32
    return murmur3_32(name)


# The order guards
def past(ch, step):
    """(expression name, its steps if the game has no such expression) true once quest `ch` is past `step`."""
    from parity import _story_conditions as C
    if step in _data()["after_exp"][ch]:
        return f"{ch}_IsAfter_{step}_Exp", None
    return f"Rando_{ch}_IsAfter_{step}_Exp", C.enum_after(f"Step_{ch}", step)


def at_or_past(ch, step):
    """(expression name, its steps if the game has no such expression) true once quest `ch` is at `step` or later."""
    steps = _data()["enums"][ch]
    return past(ch, steps[steps.index(step) - 1])


def order_requests():
    """[(quest, request info, expression, new expression steps or None, skip target)] for every guarded request."""
    out = []
    data = _data()
    for ch in ORDERED + PAST_ORDERED + tuple(PAST_ONLY):
        for r in data["requests"].get(ch, []):
            where = (r["file"], r["event"])
            if r["step"] == "Complete" or where in UNGUARDED or where in GUARDED_ELSEWHERE or (ch in PAST_ONLY and where not in PAST_ONLY[ch]):
                continue
            exp, steps = at_or_past(ch, r["step"]) if ch in ORDERED else past(ch, r["step"])
            skip = None if where == STONE_CHECK_STEP03 else r["next"]
            out.append((ch, r, exp, steps, skip))
    return out


def host(ch):
    """The flow a request runs from when its own flow has no GameDataActor. That's its quest's flow, and vanilla scenes
    call back into the flow that started them too (e.g. Dm_MelodyGet_Water into SageOfWater)."""
    if not any(r["file"] == ch and r["has_gamedata"] for r in _data()["requests"].get(ch, [])):
        raise ValueError(f"{ch}: its own flow has no GameDataActor to host a guarded request")
    return ch


def hosted_entry(ch, r):
    return f"Rando_Traps_{ch}_{r['step']}"


def new_expressions():
    return {exp: steps for _, _, exp, steps, _ in order_requests() if steps}


def _guard_nodes(exp, skip):
    return {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp", "params": {"GameDataName": exp},
                  "cases": {0: f"@{skip}" if skip else None, 1: "NEXT"}}}


def order_guards(p):
    """Skips every ordered quest's requests once the quest is at or past their step (see the module doc)."""
    hosted, entries = [], set()
    for ch, r, exp, _, skip in order_requests():
        if r["has_gamedata"]:
            g = _guard_nodes(exp, skip)
            if any(frag == g for frag, _ in p.pre.get((r["file"], r["event"]), [])):
                continue  # the story plugin already guards this request on the same expression (gate_fixes)
            p.pre_hook(r["file"], r["event"], g, "g")
            continue
        # No GameDataActor in that flow, so the request runs from a new entry of the quest's own flow and gets
        # guarded there.
        hf, entry = host(ch), hosted_entry(ch, r)
        if (hf, entry) in entries:
            raise ValueError(f"{hf}:{entry} twice")
        entries.add((hf, entry))
        from parity.story import progress
        request = progress(ch, r["step"])  # the vanilla request's own parameters
        request["params"].update({k: r["params"][k] for k in ("IsWaitEnd", "IsIgnoreCompletedChallenge",
                                                              "IsIgnoreChallengeProgressUI") if k in r["params"]})
        p.events.append({"file": hf, "flowchart": hf, "add_graph": entry, "start": "g",
                         "nodes": {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                                         "params": {"GameDataName": exp}, "cases": {0: None, 1: "p"}},
                                   "p": dict(request, next=None)}})
        p.pre_hook(r["file"], r["event"], {"c": {"call": f"{hf}:{entry}",
                                                 "next": f"@{r['next']}" if r["next"] else None}}, "c")
        hosted.append([r["file"], r["event"], hf, entry, exp])
    return hosted


def send_off_recheck(p):
    """Impa's send-off (DoorOfTime Event62's step) runs the stone check again when a stone stage is complete and the
    Door of Time is before Step03."""
    p.pre_hook("DoorOfTime", "Event62", {
        "d": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
              "params": {"GameDataName": "DoorOfTime_IsAfter_Step2_2_Exp"}, "cases": {0: "NEXT", 1: "f"}},
        "f": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
              "params": {"GameDataName": "Get_StoneOfFire_IsCompleted_Exp"}, "cases": {0: "c", 1: "w"}},
        "w": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
              "params": {"GameDataName": "Get_StoneOfWater_IsCompleted_Exp"}, "cases": {0: "c", 1: "NEXT"}},
        "c": {"call": ":DoorOfTime_CheckStoneNum", "next": "NEXT"}}, "d")


def rauru_after_lesson(p, door_value):
    """Rauru only completes DoorOfTime past Step04. With a non-vanilla door the lesson (Event14, Step05) completes it
    once the first trip is done."""
    from parity.story import progress
    p.skip_unless("DoorOfTime", "Event93", "DoorOfTime_IsAfter_Step04_Exp")
    if door_value == "stones_oot_sot":
        return False
    nxt = _data()["hooks"]["DoorOfTime"]["steps"]["Event14"]["next"]
    p.events.append({"file": "DoorOfTime", "flowchart": "DoorOfTime", "add_graph": "Rando_Traps_LessonDone",
                     "start": "q", "nodes": {
                         "q": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                               "params": {"GameDataName": FIRST_TRIP, "Index": -1},
                               "cases": {0: "c", 1: f"@{nxt}"}},
                         "c": dict(progress("DoorOfTime", "Complete"), next=f"@{nxt}")}})
    p.events.append({"file": "DoorOfTime", "flowchart": "DoorOfTime", "event": "Event14",
                     "next": "Rando_Traps_LessonDone_q"})
    return True


def darunia_gift(p):
    f, ev, talk, gift, played = DARUNIA
    p.events.append({"file": f, "flowchart": f, "add_graph": "Rando_Traps_DaruniaGift", "start": "q", "nodes": {
        "q": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
              "params": {"GameDataName": played, "Index": -1}, "cases": {0: f"@{talk}", 1: f"@{gift}"}}}})
    p.events.append({"file": f, "flowchart": f, "event": ev, "case": 0, "next": "Rando_Traps_DaruniaGift_q"})


def epona_lesson_kept(p):
    f, ev, intro = EPONA_BACK
    p.pre_hook(f, ev, {"k": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                             "params": {"GameDataName": intro, "Index": -1}, "cases": {0: None, 1: "NEXT"}}}, "k")


def malon_after_talon(p):
    f, ev, flag, talon = MALON
    from parity.story import set_bool
    p.pre_hook(f, ev, {"t": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                             "params": {"GameDataName": talon, "Index": -1}, "cases": {0: "NEXT", 1: "x"}},
                       "x": dict(set_bool(flag, False), next=None)}, "t")


def link_goron_tunic(p):
    from parity.story import set_bool
    f, after_thanks, npc, talks, flag, exp, call = LINK_GORON
    p.pre_hook(f, after_thanks, {"s": dict(set_bool(flag, True), next="NEXT")}, "s")
    for talk in talks.values():
        p.pre_hook(npc, talk, {
            "g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                  "params": {"GameDataName": flag, "Index": -1}, "cases": {0: "NEXT", 1: "a"}},
            "a": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp", "params": {"GameDataName": exp},
                  "cases": {0: "c", 1: "NEXT"}},
            "c": {"call": call, "next": None}}, "g")


def stone_count_gate(p):
    f, ev, exp, _ = STONE_COUNT_GATE
    p.pre_hook(f, ev, {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                             "params": {"GameDataName": exp}, "cases": {0: "NEXT", 1: None}}}, "g")


def owl_effects_at_talon(p):
    from parity.story import set_bool
    f, ev = OWL_LOST_AT
    nodes = {"o": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                   "params": {"GameDataName": OWL_PLAYED, "Index": -1}, "cases": {0: "NEXT", 1: "e0"}}}
    names = list(OWL_EFFECTS)
    for i, flag in enumerate(names):
        nodes[f"e{i}"] = dict(set_bool(flag, True), next=f"e{i + 1}" if i + 1 < len(names) else "NEXT")
    p.pre_hook(f, ev, nodes, "o")


def owl_gone_from_start(settings, world):
    """The owl's first field talk can't play on a new file: the castle story starts past Step01."""
    remake = getattr(settings, "remake", None) or getattr(getattr(world, "settings", None), "remake", None) or {}
    return bool(getattr(world, "skip_child_zelda", False) or remake.get("remake_skip_talon"))


def hooks(p, settings, world):
    """story.world_plan's hook for the steps that go through its Plan (pre-hooks on story steps)."""
    ws = getattr(world, "settings", settings)
    send_off_recheck(p)  # before the order guard of the same step (runs first)
    p.traps_hosted = order_guards(p)
    p.traps_lesson = rauru_after_lesson(p, ws.open_door_of_time)
    darunia_gift(p)
    malon_after_talon(p)
    epona_lesson_kept(p)
    link_goron_tunic(p)
    stone_count_gate(p)
    owl_effects_at_talon(p)


# Plan sections (story.py merges them)
def fairy_plan():
    events, add = [], {}
    tests = {f"IsGet.{item}": FAIRY_FLAG + name for name, (item, _, _) in FAIRIES.items()}
    queries = _fairy_queries()
    for (file, ev), flag in sorted(queries.items()):
        events.append({"file": file, "flowchart": file, "event": ev, "param": "GameDataName", "value": tests[flag]})
    for name, (item, comment, _) in FAIRIES.items():
        f = f"Dm_FairyFountain_{name}"
        add[FAIRY_FLAG + name] = False
        events.append({"file": f, "flowchart": f, "add_graph": "Rando_Traps_FairyGiven", "start": "s", "nodes": {
            "s": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                  "params": {"GameDataName": FAIRY_FLAG + name, "Index": -1, "Value": True}, "next": f"@{comment}"}}})
        events.append({"file": f, "flowchart": f, "entry": FAIRY_ENTRY, "next": "Rando_Traps_FairyGiven_s"})
    f, gate, call = FAIRY_CALL
    events.append({"file": f, "flowchart": f, "event": gate, "case": 1, "next": call})
    return events, add, {f"{a}:{b}": tests[v] for (a, b), v in queries.items()}


_FAIRY_QUERIES = {
    # the "already given" tests of the vanilla fairy items (read from the game files, checked by the read-back)
    ("Dm_FairyFountain_Din", "Event28"): "IsGet.Item_FairyBless_MP",
    ("Dm_FairyFountain_Din", "Event48"): "IsGet.Item_FaroreWind",
    ("Dm_FairyFountain_Din", "Event49"): "IsGet.Item_FairyBless_MPDouble",
    ("Dm_FairyFountain_Din", "Event50"): "IsGet.Item_NayruLove",
    ("Dm_FairyFountain_Din", "Event51"): "IsGet.Item_FairyBless_DefenseDouble",
    ("Dm_FairyFountain_Din", "Event78"): "IsGet.Item_DinFire",
    ("Dm_FairyFountain_Din", "Event91"): "IsGet.Item_FairyBless_MP",
    ("Dm_FairyFountain_Din", "Event93"): "IsGet.Item_FaroreWind",
    ("Dm_FairyFountain_Din", "Event94"): "IsGet.Item_FairyBless_MPDouble",
    ("Dm_FairyFountain_Din", "Event95"): "IsGet.Item_NayruLove",
    ("Dm_FairyFountain_Din", "Event96"): "IsGet.Item_FairyBless_DefenseDouble",
    ("Dm_FairyFountain_Power", "Event11"): "IsGet.Item_FairyBless_MP",
    ("Dm_FairyFountain_Frore", "Event11"): "IsGet.Item_FaroreWind",
    ("Dm_FairyFountain_Wisdom", "Event10"): "IsGet.Item_FairyBless_MPDouble",
    ("Dm_FairyFountain_Courage", "Event11"): "IsGet.Item_FairyBless_DefenseDouble",
    ("Dm_FairyFountain_Nayru", "Event10"): "IsGet.Item_NayruLove",
    ("TriForcePoint", "Event136"): "IsGet.Item_FairyBless_MP",
    ("TriForcePoint", "Event137"): "IsGet.Item_DinFire",
    ("TriForcePoint", "Event138"): "IsGet.Item_FaroreWind",
    ("TriForcePoint", "Event139"): "IsGet.Item_FairyBless_MPDouble",
    ("TriForcePoint", "Event140"): "IsGet.Item_NayruLove",
    ("TriForcePoint", "Event141"): "IsGet.Item_FairyBless_DefenseDouble",
}


def _fairy_queries():
    return dict(_FAIRY_QUERIES)


def scrub_plan():
    f, lasts, choice, hidden = SCRUB
    nodes = {"show": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                      "params": {"GameDataName": hidden[0], "Index": -1, "Value": False}, "next": f"@{choice}"}}
    following = "show"
    for i in (2, 1, 0):  # all three hidden -> show the first; any shown -> the vanilla choice
        nodes[f"h{i + 1}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                              "params": {"GameDataName": hidden[i], "Index": -1},
                              "cases": {0: following, 1: f"@{choice}"}}
        following = f"h{i + 1}"
    events = [{"file": f, "flowchart": f, "add_graph": "Rando_Traps_ScrubKeepOne", "start": following,
               "nodes": nodes}]
    events += [{"file": f, "flowchart": f, "event": ev, "next": f"Rando_Traps_ScrubKeepOne_{following}"}
               for ev in lasts]
    return events


def _s32(v):
    return v - (1 << 32) if v >= 1 << 31 else v


def binary_edits(ws):
    """[(file, offset, new, vanilla)] for the Dodongo's Cavern boulder (every seed) and the cucco pen (chicken_count <
    7)."""
    out = [(DC_BOULDER[0], off, new, old) for off, new, old in DC_BOULDER[1]]
    n = cucco_count(ws)
    if n != 7:
        out += [(CUCCO, CUCCO_INT_A, n - 1, 7), (CUCCO, CUCCO_MULTI, 0x00010011, 0x00020011),
                (CUCCO, CUCCO_SMALLER, 0x800004AF, 0x000004AF)]
    return out


def cucco_count(ws):
    """The count Anju asks for: world_settings' / story.py's (0 counts as 1: "not started" and "done" alike)."""
    return max(1, int(getattr(ws, "chicken_count", 7)))


# Anju's four lines naming the count (EventFlowMsg/Npc_Hylia_049_Child.msbt). The number opens a coloured span, as a
# word or a digit (and classifier) depending on the language. With chicken_count N it becomes N in the same form, the
# cardinal before her (plural) noun. Polish and Russian also use collective numerals ("całą siódemkę", "всех
# семерых"), and Polish 2-4 take the nominative plural (noun and verb fixed around the span). Talk_21 is written by
# the hints plugin instead when its Anju hint replaces that line (one writer per label, anju_hint_owns_talk21).
CUCCO_FILE = "EventFlowMsg/Npc_Hylia_049_Child.msbt"
CUCCO_LINES = ("Talk_19", "Talk_21", "Talk_21_1", "Talk_40")
SPAN_ON, SPAN_OFF = "{tag:0,3,0000}", "{tag:0,3,ffff}"
# archive language -> {vanilla number word: [the words for 1..6]}
_CARD = {"en": ["one", "two", "three", "four", "five", "six"], "de": ["ein", "zwei", "drei", "vier", "fünf", "sechs"],
         "fr": ["une", "deux", "trois", "quatre", "cinq", "six"], "it": ["un", "due", "tre", "quattro", "cinque", "sei"],
         "nl": ["één", "twee", "drie", "vier", "vijf", "zes"], "pt": ["uma", "duas", "três", "quatro", "cinco", "seis"],
         "pl": ["jeden", "dwa", "trzy", "cztery", "pięć", "sześć"],
         "ru": ["одна", "два", "три", "четыре", "пять", "шесть"]}  # кокко is feminine, "этих проказниц"
CUCCO_WORDS = {
    "en": {"seven": _CARD["en"]}, "de": {"sieben": _CARD["de"]}, "fr": {"sept": _CARD["fr"]},
    "it": {"sette": _CARD["it"]}, "nl": {"zeven": _CARD["nl"]}, "pt": {"sete": _CARD["pt"]},
    "pl": {"siedem": _CARD["pl"],
           "siódemkę": ["jedynkę", "dwójkę", "trójkę", "czwórkę", "piątkę", "szóstkę"],
           "siódemka": ["jedynka", "dwójka", "trójka", "czwórka", "piątka", "szóstka"]},
    "ru": {"семь": _CARD["ru"], "семерых": ["одного", "двоих", "троих", "четверых", "пятерых", "шестерых"]},
    "es": {"7 cucos": ["1 cuco"] + [f"{n} cucos" for n in range(2, 7)]},
    "ja": {"7": [str(n) for n in range(1, 7)]}, "ko": {"7": [str(n) for n in range(1, 7)]},
    "zh_cn": {"7": [str(n) for n in range(1, 7)]}, "zh_tw": {"7": [str(n) for n in range(1, 7)]}}
# Polish 2-4: the noun (and Talk_19's verb) after the number take the nominative plural
CUCCO_PL_FEW = (("powinno być " + SPAN_ON, "powinny być " + SPAN_ON), (SPAN_OFF + "\nkukuraków,", SPAN_OFF + "\nkukuraki,"),
                (SPAN_OFF + "\nprzecudnych kukuraków", SPAN_OFF + "\nprzecudne kukuraki"))
# the hints plugin's Anju hint ("all seven cuccos back in the pen", _hints_extra.WHAT["cuccos"]) with N
CUCCO_HINT = {"en": "All {} cuccos back in the pen", "de": "Alle {} Hühner zurück im Gehege",
              "fr": "Les {} cocottes ramenées", "es": "Los {} cucos de vuelta", "it": "Tutti e {} i coccò",
              "nl": "Alle {} kippen terug", "pt": "As {} galinhas de volta", "pl": "Wszystkie {} kur",
              "ru": "Все {} кур", "ja": "コッコ {}羽", "ko": "꼬꼬 {}마리", "zh_cn": "{}只咕咕鸡", "zh_tw": "{}隻咕咕雞"}
CUCCO_HINT_FEW = {"pl": "Wszystkie {} kury", "ru": "Все {} курицы"}  # 2-4
ON, OFF = SPAN_ON, SPAN_OFF
P50, P51 = "{tag:5,0}", "{tag:5,1}"
# chicken_count 1 puts the noun, its verb, adjective and pronouns in the singular, per language and line (like Polish
# 2-4). Each entry is (old, new), or ((old, new), (old, new)...) alternatives for the EU/US variants, applied after the
# number substitution. Each one must match, so a game update that changes her lines stops the build.
CUCCO_ONE = {
    "en": {
        "Talk_19": [(OFF + " cuccos inside this pen, but\nthey all flitter-fluttered", OFF + " cucco inside this pen, but\nit flitter-fluttered"),
                    ("I saw where some of 'em flew off to," + P50 + " at least the\ngeneral direction they went",
                     "I saw where it flew off to," + P50 + " at least the\ngeneral direction it went"),
                    ("handlin' them on my own.", "handlin' it on my own.")],
        "Talk_21": [("return all " + ON + "one" + OFF + " cuccos for me", "return my " + ON + "cucco" + OFF + " for me"),
                    ("my darling birds!", "my darling bird!")],
        "Talk_21_1": [("I have a total of " + ON + "one" + OFF + " darling cuccos." + P51 + " Think you\ncould catch every last one of them and bring 'em\nback here?",
                       "I have just " + ON + "one" + OFF + " darling cucco." + P51 + " Think you\ncould catch it and bring it\nback here?")],
        "Talk_40": [("All " + ON + "one" + OFF + " of my darling cuccos are back!", "My " + ON + "darling cucco" + OFF + " is back!"),
                    ("these feathery scamps!", "this feathery scamp!")]},
    "de": {
        "Talk_19": [("In diesem Gehege sollten sich ", "In diesem Gehege sollte sich "),
                    (OFF + "\nHühner befinden, aber sie sind alle fortgeflattert,", OFF + "\nHuhn befinden, aber es ist fortgeflattert,"),
                    ("Bei einigen weiß ich, wohin sie geflogen sind," + P50 + "\nzumindest die ungefähre Richtung, aber die\nanderen...",
                     "Ich weiß ungefähr, wohin es geflogen ist," + P50 + "\nzumindest die Richtung, aber..."),
                    ("so gut mit ihnen fertig.", "so gut mit ihm fertig.")],
        "Talk_21": [("Wenn du alle " + ON, "Wenn du " + ON), (OFF + " Hühner einsammelst", OFF + " Huhn einsammelst"),
                    ("meine geliebten Hühner!", "mein geliebtes Huhn!")],
        "Talk_21_1": [("Ich habe " + ON, "Ich habe nur " + ON),
                      (OFF + " Hühner." + P51 + " Kannst du sie alle\neinsammeln", OFF + " Huhn." + P51 + " Kannst du es\neinsammeln")],
        "Talk_40": [("Alle " + ON + "ein" + OFF + " meiner kleinen Lieblinge sind zurück!",
                     "Mein " + ON + "kleiner Liebling" + OFF + " ist zurück!"),
                    ("um die gefiederten\nSchlingel", "um den gefiederten\nSchlingel")]},
    "fr": {
        "Talk_19": [(OFF + " cocottes dans\nl'enclos, mais elles se sont toutes envolées", OFF + " cocotte dans\nl'enclos, mais elle s'est envolée"),
                    ("J'ai vu dans quelle direction elles partaient,\n" + P50 + "en tout cas quelques-unes, mais...",
                     "J'ai vu dans quelle direction elle partait,\n" + P50 + "en gros, mais..."),
                    ("pour aller les chercher...", "pour aller la chercher...")],
        "Talk_21": [("ramener mes " + ON + "une " + OFF + "cocottes", "ramener " + ON + "une " + OFF + "cocotte")],
        "Talk_21_1": [(OFF + "cocottes en tout. Si tu les trouves,\nramène-les", OFF + "cocotte en tout. Si tu la trouves,\nramène-la")],
        "Talk_40": [("Mes " + ON + "une" + OFF + " cocottes sont de retour", "Ma " + ON + "cocotte" + OFF + " est de retour"),
                    ("pour ces chipies", "pour cette chipie")]},
    "es": {
        "Talk_19": [(("pero se han ido todos volando.", "pero se ha ido volando."), ("pero todos se fueron volando.", "pero se fue volando.")),
                    (("Me hago una idea de dónde encontrar\na la mayoría,", "Me hago una idea de dónde encontrarlo,"),
                     ("Creo que sé dónde encontrar a la mayoría,", "Creo que sé dónde encontrarlo,"))],
        "Talk_21": [("Mis pequeñines tienen la mala costumbre", "Mi pequeñín tiene la mala costumbre"),
                    (("En cuanto uno alza el vuelo,\nel resto van detrás.", "En cuanto alza el vuelo,\nno hay quien lo pare."),
                     ("En cuanto uno alza el vuelo,\nel resto lo sigue.", "En cuanto alza el vuelo,\nno hay quien lo pare.")),
                    (("¿Podrías traérmelos de vuelta?", "¿Podrías traérmelo de vuelta?"),
                     ("¿Podrías buscarlos y traerlos de vuelta?", "¿Podrías buscarlo y traerlo de vuelta?"))],
        "Talk_21_1": [("Mis pequeñines tienen la mala costumbre", "Mi pequeñín tiene la mala costumbre"),
                      (("En cuanto uno alza el vuelo,\nel resto van detrás.", "En cuanto alza el vuelo,\nno hay quien lo pare."),
                       ("En cuanto uno alza el vuelo,\nel resto lo sigue.", "En cuanto alza el vuelo,\nno hay quien lo pare.")),
                      ("¿Podrías traérmelos de vuelta?", "¿Podrías traérmelo de vuelta?")],
        "Talk_40": [("mis " + ON + "1 cuco" + OFF, "mi " + ON + "cuco" + OFF),
                    (("¡Cómo los echaba de menos!", "¡Cómo lo echaba de menos!"), ("¡Cómo los extrañaba!", "¡Cómo lo extrañaba!")),
                    (("me tenían\nestos liantes!", "me tenía\neste liante!"), ("me tenían\nestos sinvergüenzas!", "me tenía\neste sinvergüenza!"))]},
    "it": {
        "Talk_19": [("Dovrebbero esserci " + ON, "Dovrebbe esserci " + ON),
                    ("ma sono scappati via senza neanche", "ma è scappato via senza neanche"),
                    ("Ho fatto in tempo a vedere dove sono finiti\nalcuni di loro," + P50 + " o perlomeno in che direzione\nsono volati...",
                     "Ho fatto in tempo a vedere dove è finito," + P50 + "\no perlomeno in che direzione\nè volato..."),
                    ("a maneggiarli di persona.", "a maneggiarlo di persona.")],
        "Talk_21": [("tutti e " + ON + "un" + OFF + " i coccò,", "il mio " + ON + "coccò" + OFF + ","),
                    ("i miei adorati...", "il mio adorato...")],
        "Talk_21_1": [(OFF + " adorabili coccò." + P51 + " Potresti trovarli\ne riportarli tutti qui?",
                       OFF + " adorabile coccò." + P51 + " Potresti trovarlo\ne riportarlo qui?")],
        "Talk_40": [("I miei " + ON + "un" + OFF + " coccò sono tornati tutti nel loro\nrecinto! Ero così in pena per loro!",
                     "Il mio " + ON + "coccò" + OFF + " è tornato nel suo\nrecinto! Ero così in pena per lui!")]},
    "nl": {
        "Talk_19": [("er zouden " + ON, "er zou " + ON),
                    (OFF + " cucco's binnen deze\nomheining moeten zijn, maar ze zijn allemaal\nweggefladderd",
                     OFF + " cucco binnen deze\nomheining moeten zijn, maar hij is\nweggefladderd"),
                    ("welke kant ze op gingen", "welke kant hij op ging"), ("hoe ik ze moet aanpakken.", "hoe ik hem moet aanpakken.")],
        "Talk_21": [("Als je alle " + ON + "één" + OFF + " cucco's voor me", "Als je " + ON + "één" + OFF + " cucco voor me"),
                    ("dat je al mijn schatjes zult vinden!", "dat je mijn schatje zult vinden!")],
        "Talk_21_1": [("Ik heb in totaal " + ON + "één" + OFF + " cucco's." + P51 + " Denk je dat je ze\nallemaal kunt terugbrengen?",
                       "Ik heb maar " + ON + "één" + OFF + " cucco." + P51 + " Denk je dat je hem\nkunt terugbrengen?")],
        "Talk_40": [("Al mijn " + ON + "één" + OFF + " cucco's zijn er weer!", "Mijn " + ON + "cucco" + OFF + " is er weer!"),
                    ("om dat stelletje eigenwijze\nkakelkoppen!", "om die eigenwijze\nkakelkop!")]},
    "pt": {
        "Talk_19": [(OFF + "coricós\nnesse cercadinho, mas elas saíram voando", OFF + "coricó\nnesse cercadinho, mas ela saiu voando"),
                    ("Consegui ver para onde algumas foram,", "Consegui ver para onde ela foi,"),
                    ("lidar com elas sozinha.", "lidar com ela sozinha.")],
        "Talk_21": [("as minhas\n" + ON + "uma " + OFF + "coricós,", "a minha\n" + ON + "coricó" + OFF + ","),
                    ("para você achar as\nminhas pequenas!", "para você achar a\nminha pequena!")],
        "Talk_21_1": [(OFF + "lindas coricós." + P51 + " Acha que consegue\nencontrar todas elas e trazê-las",
                       OFF + "linda coricó." + P51 + " Acha que consegue\nencontrá-la e trazê-la")],
        "Talk_40": [(ON + "Todas " + OFF + "as minhas coricós estão de volta!", ON + "A minha coricó" + OFF + " está de volta!"),
                    ("com essas fujonas!", "com essa fujona!")]},
    "pl": {
        "Talk_19": [("powinno być " + ON + "jeden" + OFF + "\nkukuraków, ale niespodziewanie wszystkie\nodfrunęły",
                     "powinien być " + ON + "jeden" + OFF + "\nkukurak, ale niespodziewanie\nodfrunął"),
                    ("Kilka z nich dostrzegłam", "Dostrzegłam go"), ("gdzie ich szukać", "gdzie go szukać"),
                    ("z chwytaniem ich", "z chwytaniem go")],
        "Talk_21": [(ON + "jeden" + OFF + "\nprzecudnych kukuraków", ON + "jednego" + OFF + "\nprzecudnego kukuraka"),
                    (", że jeden wyfrunie poza zagrodę,\na reszta idzie w jego ślady!", ", że wyfrunie poza zagrodę\ni już go nie ma!"),
                    (" Może schwytasz\ni sprowadzisz tu całą " + ON + "jedynkę" + OFF + "?", " Może go schwytasz\ni sprowadzisz tu z powrotem?"),
                    ("Jeśli wszystkie do mnie wrócą,", "Jeśli do mnie wróci,")],
        "Talk_21_1": [(ON + "jeden" + OFF + "\nprzecudnych kukuraków", ON + "jednego" + OFF + "\nprzecudnego kukuraka"),
                      (", że jeden wyfrunie poza zagrodę,\na reszta idzie w jego ślady!", ", że wyfrunie poza zagrodę\ni już go nie ma!"),
                      (" Może schwytasz\ni sprowadzisz tu całą " + ON + "jedynkę" + OFF + "?", " Może go schwytasz\ni sprowadzisz tu z powrotem?")],
        "Talk_40": [("Cała " + ON + "jedynka" + OFF + " moich słodkich kukuraków znów", "Mój " + ON + "słodki kukurak" + OFF + " znów"),
                    ("o tych uciekinierów!", "o tego uciekiniera!")]},
    "ru": {
        "Talk_19": [("В загоне должно быть " + ON + "одна" + OFF + " кокко, но все они\nвзмахнули крыльями и улетели",
                     "В загоне должна быть " + ON + "одна" + OFF + " кокко, но она\nвзмахнула крыльями и улетела"),
                    (" куда примерно полетели\nнекоторые из них, но...", " куда примерно она\nполетела, но..."),
                    ("брать их в руки.", "брать её в руки.")],
        "Talk_21": [("вернуть всех\n" + ON + "одного" + OFF + " кокко", "вернуть мою\n" + ON + "кокко" + OFF),
                    ("моих любимых пташек!", "мою любимую пташку!")],
        "Talk_21_1": [(OFF + " милых кокко.", OFF + " милая кокко."), ("поймать их всех", "поймать её")],
        "Talk_40": [("Все " + ON + "одна" + OFF + " моих любимых кокко вернулись!", "Моя " + ON + "любимая кокко" + OFF + " вернулась!"),
                    ("за этих проказниц!", "за эту проказницу!")]},
    "ja": {
        "Talk_21": [("{tag:0,0,02000c00e3819ce38293e38184e38293}全員 ", "を ")],
        "Talk_21_1": [("{tag:0,0,02000900e3819ce38293e381b6}全部で ", ""), (OFF + "いるの", OFF + "しか いないの"),
                      ("どんどん", "")],
        "Talk_40": [("コッコ{tag:0,0,01000600e3819fe381a1}達が", "コッコが")]},
    "ko": {
        "Talk_21": [(OFF + "를 모두 우리 안에", OFF + "를 우리 안에")],
        "Talk_21_1": [("꼬꼬는 모두 합쳐 ", "꼬꼬는 "), ("팍팍 ", "")],
        "Talk_40": [("꼬꼬들이", "꼬꼬가"), (OFF + " 모두 돌아왔어", OFF + " 돌아왔어")]},
    "zh_cn": {
        "Talk_19": [("它们啪塔啪塔都飞走了", "它啪塔啪塔飞走了"), ("记得它们往哪里飞了", "记得它往哪里飞了")],
        "Talk_21": [(OFF + "都放进栅栏里了", OFF + "放进栅栏里了")],
        "Talk_21_1": [("一共有" + ON, "只有" + ON), ("找到它们，麻烦都放进", "找到它，麻烦放进")],
        "Talk_40": [("咕咕鸡\n都平安回来了", "咕咕鸡\n平安回来了")]},
    "zh_tw": {
        "Talk_19": [("全部都拍拍翅膀逃走了", "拍拍翅膀逃走了"), ("知道牠們跑去哪裡", "知道牠跑去哪裡")],
        "Talk_21": [(OFF + "全部抓回柵欄裡", OFF + "抓回柵欄裡")],
        "Talk_21_1": [("一共有" + ON, "只有" + ON), ("找到牠們", "找到牠")],
        "Talk_40": [("咕咕雞\n都回來了", "咕咕雞\n回來了")]},
}
CUCCO_HINT_ONE = {"en": "One cucco back in the pen", "de": "Ein Huhn zurück im Gehege", "fr": "La cocotte ramenée",
                  "es": "El cuco de vuelta", "it": "Il coccò riportato", "nl": "De kip terug", "pt": "A galinha de volta",
                  "pl": "Jedna kura", "ru": "Одна курица", "ja": "コッコ 1羽", "ko": "꼬꼬 1마리", "zh_cn": "1只咕咕鸡",
                  "zh_tw": "1隻咕咕雞"}
_HINT_CARD = {"es": ["un", "dos", "tres", "cuatro", "cinco", "seis"],
              "it": ["uno", "due", "tre", "quattro", "cinque", "sei"]}


def _cucco_lang(archive):
    from parity import _hints_extra as X
    return X.LANG[archive]


def cucco_markup(markup, archive, n, label=None):
    """Her line `markup` (archive language) rewritten to name `n` cuccos. Returns (new markup, numbers replaced)."""
    import re
    key = _cucco_lang(archive)
    words = sorted(CUCCO_WORDS[key].items(), key=lambda kv: -len(kv[0]))
    count = 0

    def span(m):
        nonlocal count
        body = m.group(1)
        for old, new in words:
            if body.startswith(old) and not (old == "7" and body[1:2].isdigit()):
                count += 1
                return SPAN_ON + new[n - 1] + body[len(old):] + SPAN_OFF
        return m.group(0)
    out = re.sub(re.escape(SPAN_ON) + "(.*?)" + re.escape(SPAN_OFF), span, markup)
    if key == "pl" and 2 <= n <= 4:
        for old, new in CUCCO_PL_FEW:
            out = out.replace(old, new)
    if n == 1 and label is not None:
        for rule in CUCCO_ONE.get(key, {}).get(label, []):
            hit = False
            for old, new in (rule if isinstance(rule[0], tuple) else (rule,)):
                if old in out:
                    out, hit = out.replace(old, new), True
            if not hit:
                raise RuntimeError(f"{archive} {CUCCO_FILE} {label}: no {rule[0] if not isinstance(rule[0], tuple) else rule[0][0]!r} "
                                   "(her line changed: check CUCCO_ONE)")
            count += 1
    return out, count


def cucco_hint_what(archive, n):
    """_hints_extra.WHAT["cuccos"] for `n` cuccos (hints.py's Anju hint), in archive language `archive`."""
    key = _cucco_lang(archive)
    if n == 1:
        return CUCCO_HINT_ONE[key]
    digits = key in ("ja", "ko", "zh_cn", "zh_tw")
    word = str(n) if digits else (_HINT_CARD.get(key) or _CARD[key])[n - 1]
    return (CUCCO_HINT_FEW.get(key) if 2 <= n <= 4 and key in CUCCO_HINT_FEW else CUCCO_HINT[key]).format(word)


def anju_hint_owns_talk21(settings, world):
    """True if the hints plugin replaces Talk_21 with its Anju hint, and then it writes the count there."""
    from parity import hints
    return "anju" in set(hints.extra_hints(settings)) and hints._held(world, "Kak Anju as Child") is not None


def cucco_text_ops(settings, world, n):
    """Text ops for her lines naming `n` cuccos in every language (none for 7). Returns (ops, note)."""
    if n == 7:
        return [], {}
    import re
    import msbt
    from romtools import Romfs, sarc_files
    romfs = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    labels = [lb for lb in CUCCO_LINES if not (lb == "Talk_21" and anju_hint_owns_talk21(settings, world))]
    ops, note = [], {}
    for archive, rel in sorted(msbt.archives(romfs).items()):
        m = msbt.Msbt(sarc_files(fs.read(rel))[CUCCO_FILE])
        for lb in labels:
            new, k = cucco_markup(m.markup(lb), archive, n, lb)
            if not k:
                continue  # pt Talk_40 names no number
            plain = re.sub(r"\{tag:[^}]*\}", "", re.sub(r"\{tag:0,4\}", "\n", new))
            ops.append({"lang": archive, "file": CUCCO_FILE, "label": lb, "markup": new, "text": plain,
                        "note": f"chicken_count {n}"})
            note[f"{archive}:{lb}"] = new
    return ops, note


def _and_not(flag, exp_or_bool, extra=()):
    """BoolExp steps: `exp_or_bool` (a BoolExp or Bool name) AND every name in `extra` AND NOT `flag`."""
    def term(name):
        return [10 if name.endswith("_Exp") else 0, name]
    steps = [term(exp_or_bool)]
    for e in extra:
        steps += [term(e), [3]]
    if flag:
        steps += [[0, flag], [5], [3]]
    return steps


def owl_sunrise_events():
    """OWL_SUNRISE's steps: the clock to 06:00 between the owl's Event153 and the panorama (Event3)."""
    f, before, scene_step, scene, scene_time, hour, minute, graph = OWL_SUNRISE
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(), os.path.join(HERE, "original"))
    fc = Evfl(fs.read(f"Event/EventFlow/{f}.bfevfl.zs")).flowcharts[0]
    by = _ev(fc)
    if before not in by or _name(fc, by[before].get("next")) != scene_step or \
            _p(by[before], "GameDataName") != CLOCK_FLAG or _p(by[scene_step], "EventName") != scene:
        raise RuntimeError(f"{f}: {before} no longer sets {CLOCK_FLAG} right before {scene_step} plays {scene} "
                           f"(game update?)")
    pc = Evfl(fs.read(f"Event/EventFlow/{scene}.bfevfl.zs")).flowcharts[0]
    st = _ev(pc).get(scene_time)
    if st is None or _what(pc, st) != "Event_SetTimeForFlowchart" or (_p(st, "ToHour"), _p(st, "ToMin")) != (7, 30):
        raise RuntimeError(f"{scene}: {scene_time} no longer runs the clock to 07:30 (game update?)")
    return [{"file": f, "flowchart": f, "add_graph": graph, "start": "t", "nodes": {
                "t": {"actor": "EventWorldManagerController", "action": "EventTrigger_SetTime",
                      "params": {"TimeHour": hour, "TimeMin": minute}, "next": "w"},
                "w": {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
                      "next": "r"},
                "r": {"actor": "EventWorldManagerController", "action": "Event_RebuildConditionEnvTimePalette",
                      "next": f"@{scene_step}"}}},
            {"file": f, "flowchart": f, "event": before, "next": f"{graph}_t"}]


def kf_boy_events():
    """KF_BOY's talk: the rock animations played as a 1-frame Wait, no ASName to the reward talk, no grunts."""
    fc = _boy_flow()
    by = {e["name"]: e for e in fc["events"]}
    out = [{"file": KF_BOY[0], "flowchart": KF_BOY[0], "event": ev, "param": k, "value": v} for ev, k, v in KF_BOY_STEPS]
    ev, value, to = KF_BOY_NEAR
    case = next(i for i, c in enumerate(by[ev]["cases"]) if c["value"] == value)
    out.append({"file": KF_BOY[0], "flowchart": KF_BOY[0], "event": ev, "case": case, "next": to})
    return out


def _boy_flow(fs=None):
    """The ring Kokiri's event flow: vanilla (checked against what KF_BOY edits), or as Romfs `fs` (a patch) has it."""
    from romtools import Romfs
    from evfl import Evfl
    vanilla = fs is None
    if vanilla:
        fs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(),
                   os.path.join(HERE, "original"))
    fc = Evfl(fs.read(f"Event/EventFlow/{KF_BOY[0]}.bfevfl.zs")).flowcharts[0]
    if vanilla:
        by = {e["name"]: e for e in fc["events"]}
        want = {"Event129": "Act_Lift_Rock_To_Stand", "Event81": "Act_Lift_Rock_To_Crouch", "Event157": 60,
                "Event163": 60, "Event62": "Act_Lift_Rock_To_Stand"}
        for ev, k, _ in KF_BOY_STEPS:
            if ev not in by or _p(by[ev], k) != want[ev]:
                raise RuntimeError(f"{KF_BOY[0]}: {ev} {k} is no longer {want[ev]!r} (game update?)")
        e36 = by.get(KF_BOY_NEAR[0])
        if e36 is None or _p(e36, "GameDataName") != KF_BOY[1]:
            raise RuntimeError(f"{KF_BOY[0]}: {KF_BOY_NEAR[0]} no longer tests {KF_BOY[1]} (game update?)")
    return fc


def schedule_plan():
    """(byml ops, new expressions, note) for the Kokiri schedules (findings E1-E3)."""
    ops, exps, note = [], {}, []
    castle = "Rando_Kokiri_CastleAfterDeku_Exp"
    exps[castle] = _and_not(None, CASTLE, (DEKU_DONE,))
    for npc in KOKIRI_CASTLE:
        ops.append((npc, CASTLE, castle))
    for i, st in enumerate(MIDO_STATES):
        name = f"Rando_Mido_State{i}_Exp"
        exps[name] = _and_not(MIDO_WALL, st, (DEKU_DONE,) if st == CASTLE else ())
        ops.append(("Npc_Kokiri_Mido_Child", st, name))
    exit_castle = "Rando_KokiriExit_Castle_Exp"
    exps[exit_castle] = _and_not(EXIT_WALL, CASTLE)
    ops.append(("Npc_Kokiri_007_Child", CASTLE, exit_castle))
    exps[KF_BOY[2]] = KF_BOY_EXP  # the ring's centre Kokiri off the rock from a new file (KF_BOY)
    ops.append((KF_BOY[0], KF_BOY[1], KF_BOY[2]))
    byml = []
    for npc, old, new in ops:
        byml.append({"file": SCHEDULE.format(npc),
                     "set": {f"ConditionalSchedule.[ConditionFlag={old}].ConditionFlag": new}})
        note.append([SCHEDULE.format(npc), old, new])
    return byml, exps, note


def world_plan(settings, world):
    """Plan sections for every seed, merged after story.py's own plan. The story-step hooks go through hooks()."""
    ws = getattr(world, "settings", settings)
    fairy_events, fairy_bools, fairy_tests = fairy_plan()
    exps = new_expressions()
    sched_byml, sched_exps, sched_note = schedule_plan()
    exps.update(sched_exps)
    exps[SHEIK[3]] = SHEIK_EXP
    exps[STONE_COUNT_GATE[2]] = STONE_COUNT_GATE[3]
    defaults = {CLOCK_FLAG: True, SEND_OFF_PLAYED: True}
    owl_gone = owl_gone_from_start(settings, world)
    if owl_gone:
        defaults.update(OWL_EFFECTS)
    if getattr(ws, "open_kakariko", "closed") == "open":
        defaults["Step_Get_StoneOfFire"] = FIRE_OPEN_KAKARIKO
    if getattr(ws, "gerudo_fortress", "normal") == "open":  # the fortress starts cleared (story.py), card scene and all
        defaults[CARD_PLAYED] = True
    gamedata =[{"defaults": defaults}, {"add_bools": dict(fairy_bools, **{LINK_GORON[4]: False})},
                {"add_boolexp": exps}]
    f, entry, _, after = ADULT_CLOCK
    extra_events = [{"file": f, "flowchart": f, "entry": entry, "next": after},
                    {"file": STONE_MENU[0], "flowchart": STONE_MENU[0], "event": STONE_MENU[1], "next": None},
                    {"file": OWL_ENV[0], "flowchart": OWL_ENV[0], "event": OWL_ENV[1], "next": OWL_ENV[3]},
                    {"file": DMT_OWL[0], "flowchart": DMT_OWL[0], "event": DMT_OWL[1], "case": DMT_OWL[2],
                     "next": DMT_OWL[3]}]
    extra_events += [{"file": SCRUB_NOTE[0], "flowchart": SCRUB_NOTE[0], "event": ev, "case": k, "next": to}
                     for ev, k, to in SCRUB_NOTE[1]]
    extra_events += kf_boy_events()
    extra_events += owl_sunrise_events()
    binary = [{"file": fl, "offset": off, "i32": _s32(new), "expect": _s32(old), "note": "story_traps"}
              for fl, off, new, old in binary_edits(ws)]
    ainb_ops = [{"file": SHEIK[0], "edits": [
        {"set_input": {"node": SHEIK[1], "name": "GameDataNameBoolExp", "value": SHEIK[3]}},
        {"feed": {"from": SHEIK[1], "output": "Bool", "to": SHEIK[2], "input": "Logic_Delete"}}]},
                {"file": KF_RING[0], "edits": [
                    {"cut": {"node": n, "input": "Logic_Delete", "value": False, "default": True}} for n in KF_RING[1]]
                    + [{"cut": {"node": n, "input": "Logic_Create", "value": False}} for n in KF_RING[2]]
                    + [{"feed": {"from": KF_RING[3][2], "output": KF_RING[3][3], "to": KF_RING[3][0],
                                 "input": "Logic_Create"}}]},
                {"file": KF_CENTRE[0], "edits": [
                    {"cut": {"node": KF_CENTRE[1][0], "input": "Logic_Create", "value": True, "default": True}},
                    {"cut": {"node": KF_CENTRE[1][0], "input": "Logic_Delete", "value": False, "default": True}},
                    {"cut": {"node": KF_CENTRE[2][0], "input": "Logic_Create", "value": False}},
                    {"cut": {"node": KF_CENTRE[2][0], "input": "Logic_Delete", "value": False, "default": True}}]},
                {"file": DMT_ROCKS[0], "edits": [
                    {"cut": {"node": n, "input": "Logic_Delete", "value": False, "default": True}} for n in DMT_ROCKS[1]]
                    + [{"cut": {"node": n, "input": "Logic_Create", "value": False}} for n in DMT_ROCKS[2]]},
                {"file": DC_LIZALFOS[0], "edits": [{"add_source": {"to": DC_LIZALFOS[1], "input": DC_LIZALFOS[2],
                                                                    "from": DC_LIZALFOS[3], "output": DC_LIZALFOS[4]}}]},
                {"file": VILLAGE_SARIA[0], "edits": [
                    {"set_input": {"node": VILLAGE_SARIA[1], "name": VILLAGE_SARIA[2], "value": VILLAGE_SARIA[4]}}]},
                {"file": LAKE_OWL_LOGIC[0], "edits": [
                    {"set_input": {"node": LAKE_OWL_LOGIC[1], "name": LAKE_OWL_LOGIC[2], "value": LAKE_OWL_LOGIC[3]}}]}]
    ainb_ops += [{"file": fl, "edits": [
        {"copy": {"from": {"file": fl}, "nodes": [reader], "label": "card", "follow": False}},
        {"set_input": {"node": f"card:{reader}", "name": "GameDataNameBool", "value": CARD_PLAYED}},
        {"add_source": {"to": and_node, "input": "BoolMulti", "from": f"card:{reader}", "output": "Bool"}}]}
        for fl, and_node, reader in JAIL_GERUDO]
    carpenter_packs = []
    for ap, new, esc, old in CARPENTER_SCHEDULE.values():
        carpenter_packs += [{"pack": "*", "file": ap, "set": {"Components.AIScheduleRef": new}},
                            {"pack": "*", "file": esc, "set": {"Components.AIScheduleRef": old}}]
    note = {
        "guards": [[r["file"], r["event"], exp, skip, ch, r["step"]]
                   for ch, r, exp, _, skip in order_requests() if r["has_gamedata"]],
        "hosted": [[r["file"], r["event"], host(ch), hosted_entry(ch, r), exp]
                   for ch, r, exp, _, skip in order_requests() if not r["has_gamedata"]],
        "new_expressions": {k: v for k, v in exps.items()},
        "send_off_recheck": True,
        "rauru": "DoorOfTime_IsAfter_Step04_Exp",
        "lesson_completes": ws.open_door_of_time != "stones_oot_sot",
        "darunia": list(DARUNIA), "malon": list(MALON), "epona_back": list(EPONA_BACK),
        "clock": CLOCK_FLAG,
        "fairy_tests": fairy_tests, "fairy_flags": sorted(fairy_bools),
        "fairy_entries": {f"Dm_FairyFountain_{n}": [FAIRY_FLAG + n, c] for n, (_, c, _) in FAIRIES.items()},
        "fairy_call": list(FAIRY_CALL),
        "scrub": [SCRUB[0], list(SCRUB[1]), SCRUB[2], list(SCRUB[3])],
        "defaults": defaults,
        "adult_clock": list(ADULT_CLOCK), "stone_menu": list(STONE_MENU),
        "binary": [[fl, off, new, old] for fl, off, new, old in binary_edits(ws)],
        "sheik": list(SHEIK), "sheik_exp": SHEIK_EXP,
        "schedules": sched_note, "schedule_exps": sched_exps,
        "link_goron": list(LINK_GORON), "village_saria": list(VILLAGE_SARIA),
        "stone_count_gate": list(STONE_COUNT_GATE),
        "owl": {"env": list(OWL_ENV), "lost_at": list(OWL_LOST_AT), "played": OWL_PLAYED, "effects": OWL_EFFECTS,
                "from_start": owl_gone},
        "dmt_owl": list(DMT_OWL), "scrub_note": [SCRUB_NOTE[0], [list(x) for x in SCRUB_NOTE[1]]],
        "kf_ring": [KF_RING[0], {str(k): v for k, v in KF_RING[1].items()}, {str(k): v for k, v in KF_RING[2].items()},
                    list(KF_RING[3])],
        "kf_centre": [KF_CENTRE[0], list(KF_CENTRE[1]), list(KF_CENTRE[2])],
        "kf_boy": [list(KF_BOY), [list(x) for x in KF_BOY_STEPS], list(KF_BOY_NEAR)],
        "owl_sunrise": list(OWL_SUNRISE),
        "dmt_rocks": [DMT_ROCKS[0], {str(k): v for k, v in DMT_ROCKS[1].items()},
                      {str(k): v for k, v in DMT_ROCKS[2].items()}],
        "dc_lizalfos": list(DC_LIZALFOS), "heart_piece_lift": [HEART_PIECE_LIFT[0], HEART_PIECE_LIFT[1],
                                                                HEART_PIECE_LIFT[2], HEART_PIECE_LIFT[3],
                                                                HEART_PIECE_LIFT[4], list(HEART_PIECE_LIFT[5])],
    }
    text_ops, note["cucco_text"] = cucco_text_ops(settings, world, cucco_count(ws))
    placements = [{"file": w[0], "hash": w[1], "set": {"Presence": dict(w[2])}} for w in (LAKE_TREE_WALL, GATE_SWITCH_WALL)]
    placements += [{"file": f, "hash": h, "remove": ["Presence"]} for f, h in OWLS_STAY]
    note["owls_stay"] = {"placements": [list(x) for x in OWLS_STAY], "gone": OWLS_GONE, "logic": list(LAKE_OWL_LOGIC)}
    note["lake_tree_wall"] = [LAKE_TREE_WALL[0], LAKE_TREE_WALL[1], LAKE_TREE_WALL[2]]
    note["gate_switch_wall"] = [GATE_SWITCH_WALL[0], GATE_SWITCH_WALL[1], GATE_SWITCH_WALL[2]]
    note["carpenters"] = {"schedules": {c: list(v) for c, v in CARPENTER_SCHEDULE.items()},
                          "jail_gerudo": [list(x) for x in JAIL_GERUDO], "card_played": CARD_PLAYED}
    return {"gamedata": gamedata, "events": fairy_events + scrub_plan() + extra_events, "binary": binary,
            "ainb": ainb_ops, "byml": sched_byml, "placements": placements, "text": text_ops,
            "packs": [{"pack": "*", "file": HEART_PIECE_LIFT[0], "set": {"Components.LiftableRef": HEART_PIECE_LIFT[1]}},
                      {"pack": HEART_PIECE_LIFT[3], "file": HEART_PIECE_LIFT[2], "from_pack": HEART_PIECE_LIFT[4]}]
            + carpenter_packs,
            "_gaps": {"story_traps": note}}


READERS = {"story_traps": "verify"}


def UNTESTED(settings):
    return ["story traps (OotrR findings): quests never move back (Fire, Door of Time, Water, Water Sage, Fire Sage, "
            "Spirit Sage, Epona; the Kakariko burning after an early Shadow Temple, the last sage after an early "
            "Light Arrow scene), the stone "
            "check after Impa's send-off, Rauru after the lesson, Darunia's gift, Malon after Talon, the clock from "
            "a new file, Great Fairies (every fairy answers, own reward flags), refill scrubs never empty, Link the "
            "Goron's tunic after the crater, the Temple of Time Sheik off the pedestal, Mido / the exit guard / the "
            "Kokiri wait for the Deku Tree, Link's bombs break the Dodongo's Cavern boulder, the Lake Hylia tree wall, "
            "the cucco count, the adult 20:00 clock stop, no stone menu after Gohma, the Kokiri Forest rock ring "
            "(the child's 8 rocks and Rock 27 for an adult always, Rock 19 from the start), one rock per Death "
            "Mountain spot"]


# Read-back (parity/_gaps_check.py)
def _flows(fs, base, romfs):
    """[(file name, flowchart)] for every version of event file `base` (make_patch edits each one)."""
    import re
    from evfl import Evfl
    rx = re.compile(re.escape(base) + r"(\.\d{3})?\.bfevfl\.zs$")
    names = sorted(f for f in os.listdir(os.path.join(romfs, "Event", "EventFlow")) if rx.match(f))
    return [(n, Evfl(fs.read(f"Event/EventFlow/{n}")).flowcharts[0]) for n in names]


def _ev(fc):
    return {e["name"]: e for e in fc["events"]}


def _name(fc, i):
    return fc["events"][i]["name"] if i is not None and i < len(fc["events"]) else None


def _cases(fc, e):
    """{case value: target step name}, None for the end (also through evfl_build's do-nothing step)."""
    from evfl_build import CASE_END_NAME
    return {c["value"]: (None if _name(fc, c["next"]) == f"{CASE_END_NAME}_w" else _name(fc, c["next"]))
            for c in e.get("cases", [])}


def _what(fc, e):
    a = fc["actors"][e["actor"]]
    return a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]]


def _p(e, key):
    c = (e.get("params") or {}).get("items", {}).get(key)
    return None if c is None else c.get("value")


def _leads_to(fc, start, target, hops=8):
    """Name `start` reaches step `target` through at most `hops` steps (any branch)."""
    by = _ev(fc)
    todo, seen = [(start, 0)], set()
    while todo:
        n, d = todo.pop()
        if n == target:
            return True
        if n is None or n in seen or d > hops or n not in by:
            continue
        seen.add(n)
        e = by[n]
        nxt = [e.get("next")] if e.get("next") not in (None, 0xFFFF) else []
        nxt += [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
        todo += [(_name(fc, i), d + 1) for i in nxt]
    return False


def _pred_targets(fc, kind, where, k):
    by = _ev(fc)
    if kind == "entry":
        m = fc["entry_points"][where]["main"]
        return _name(fc, m)
    e = by[where]
    if kind == "next":
        return _name(fc, e.get("next"))
    if kind == "case":
        return _name(fc, e["cases"][k]["next"])
    return _name(fc, e["forks"][k])


NOTE_KEYS = ("guards", "hosted", "new_expressions", "send_off_recheck", "rauru", "lesson_completes", "darunia", "malon",
             "epona_back",
             "clock", "fairy_tests", "fairy_flags", "fairy_entries", "fairy_call", "scrub", "defaults", "adult_clock",
             "stone_menu", "binary", "sheik", "sheik_exp", "schedules", "schedule_exps", "link_goron", "lake_tree_wall")


def verify(patch, note, romfs):
    # Older plans can be missing these fixes and their notes. We report that here so the other patch checks still
    # run.
    missing = [k for k in NOTE_KEYS if k not in note]
    if missing:
        return [f"story traps: the plan has no {', '.join(missing)} (made before these fixes: regenerate it)"]
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
    exps = {e["Hash"] for e in gd["BoolExp"]}
    bools = {e["Hash"]: e for e in gd["Bool"]}
    data = _data()
    infos = {(r["file"], r["event"]): r for v in data["requests"].values() for r in v}
    # The order guards. Every predecessor of the request now reaches a switch on the expression, whose "true" case
    # skips the request and whose "false" case leads to it.
    cache = {}

    def flow(base):
        if base not in cache:
            cache[base] = _flows(fs, base, romfs)
        return cache[base]
    for file, ev, exp, skip, ch, step in note["guards"]:
        if _murmur(exp) not in exps:
            bad.append(f"{file}:{ev}: no expression {exp} in the GameDataList")
        r = infos[(file, ev)]
        for vname, fc in flow(file):
            by = _ev(fc)
            if ev not in by:
                bad.append(f"{vname}: no step {ev}")
                continue
            guards = [e for e in fc["events"] if e["type"] == "switch" and _p(e, "GameDataName") == exp
                      and e["name"].startswith(f"Rando_Story_{ev}_")]
            def skips(t):  # to the request's next step, or into that step's own hooks (story.Plan.assemble)
                return t == skip or (skip is not None and (t or "").startswith(f"Rando_Story_{skip}_")
                                     and _leads_to(fc, t, skip))
            ok = [g for g in guards if _cases(fc, g).get(1) and _leads_to(fc, _cases(fc, g)[1], ev)
                  and skips(_cases(fc, g).get(0))]
            if not ok:
                bad.append(f"{vname}: {ev} ({ch} {step}) has no guard on {exp} skipping to {skip}")
                continue
            for kind, where, k in r["preds"]:
                t = _pred_targets(fc, kind, where, k)
                if t == ev or not (t or "").startswith(f"Rando_Story_{ev}_"):
                    bad.append(f"{vname}: {kind} {where} still leads straight to {ev} ({t})")
    for file, ev, host, entry, exp in note["hosted"]:
        for vname, fc in flow(file):
            by = _ev(fc)
            calls = [e for e in fc["events"] if e["type"] == "subflow" and e.get("entry_point") == entry
                     and e.get("flowchart") == host]
            if not calls:
                bad.append(f"{vname}: no call to {host}:{entry} in front of {ev}")
            for kind, where, k in infos[(file, ev)]["preds"]:
                if _pred_targets(fc, kind, where, k) == ev:
                    bad.append(f"{vname}: {kind} {where} still leads straight to {ev}")
        for vname, fc in flow(host):
            ep = fc["entry_points"].get(entry)
            g = ep and fc["events"][ep["main"]]
            if not g or g["type"] != "switch" or _p(g, "GameDataName") != exp:
                bad.append(f"{vname}: entry {entry} doesn't start with a test of {exp}")
                continue
            q = _ev(fc).get(_cases(fc, g).get(1))
            if not q or _what(fc, q) != "EventExecuteProgressChallengeStep" or _cases(fc, g).get(0) is not None:
                bad.append(f"{vname}: entry {entry} doesn't run the request only before its step")
    # The quests guarded on "past their step". The audit's rows are among them, each on <quest>_IsAfter_<its step>,
    # and the step back that's on purpose (UNGUARDED) has no guard.
    guarded = {(f, e): (exp, ch, step) for f, e, exp, _, ch, step in note["guards"]}
    hosted_at = {(f, e): exp for f, e, _, _, exp in note["hosted"]}
    for f, e in QUEST_ROWS:
        if (f, e) not in guarded and (f, e) not in hosted_at:
            bad.append(f"{f}:{e}: the audit's quest regression has no guard")
    for f, e in UNGUARDED:
        if (f, e) in guarded or (f, e) in hosted_at:
            bad.append(f"{f}:{e}: guarded, but the game moves its quest there on purpose")
    for (f, e), (exp, ch, step) in guarded.items():
        if ch not in ORDERED and not exp.endswith(f"{ch}_IsAfter_{step}_Exp"):
            bad.append(f"{f}:{e} ({ch} {step}): guard {exp} isn't 'past its step'")
    for (f, e), exp in hosted_at.items():
        r = infos[(f, e)]
        ch = r["params"].get("ChallengeName")
        if ch not in ORDERED and not exp.endswith(f"{ch}_IsAfter_{r['step']}_Exp"):
            bad.append(f"{f}:{e} ({ch} {r['step']}): hosted guard {exp} isn't 'past its step'")
    for name in note["new_expressions"]:
        if _murmur(name) not in exps:
            bad.append(f"GameDataList: new expression {name} missing")
    # send-off: the stone check runs in front of Event62
    for vname, fc in flow("DoorOfTime"):
        calls = [e for e in fc["events"] if e["type"] == "subflow" and e.get("entry_point") == "DoorOfTime_CheckStoneNum"
                 and e["name"].startswith("Rando_Story_Event62_")]
        if not calls or not _leads_to(fc, calls[0]["name"], "Event62"):
            bad.append(f"{vname}: Impa's send-off doesn't run the stone check again before Event62")
        rauru = [e for e in fc["events"] if e["name"].startswith("Rando_Story_Event93_") and e["type"] == "switch"
                 and _p(e, "GameDataName") == note["rauru"]]
        if not rauru or _cases(fc, rauru[0]).get(0) is None or not _leads_to(fc, _cases(fc, rauru[0])[0], "Event93"):
            bad.append(f"{vname}: Rauru's Complete (Event93) doesn't wait for {note['rauru']}")
        e14 = _ev(fc)["Event14"]
        lesson = _name(fc, e14.get("next")) == "Rando_Traps_LessonDone_q"
        if lesson != bool(note["lesson_completes"]):
            bad.append(f"{vname}: the lesson's Complete step is {'there' if lesson else 'missing'}")
    f, ev, talk, gift, played = note["darunia"]
    for vname, fc in flow(f):
        e = _ev(fc)[ev]
        q = _ev(fc).get(_cases(fc, e).get(0))
        if not q or _p(q, "GameDataName") != played or _cases(fc, q) != {0: talk, 1: gift}:
            bad.append(f"{vname}: {ev} past SariaMelodyPlay doesn't test {played} -> {talk}/{gift}")
    f, ev, flag, talon = note["malon"]
    for vname, fc in flow(f):
        t = [e for e in fc["events"] if e["name"].startswith(f"Rando_Story_{ev}_") and _p(e, "GameDataName") == talon]
        if not t or _cases(fc, t[0]).get(0) != ev:
            bad.append(f"{vname}: Malon's second visit ({ev}) doesn't wait for {talon}")
    if "epona_back" not in note:
        bad.append("story traps: the plan has no epona_back (made before this fix: regenerate it)")
    else:
        f, ev, intro = note["epona_back"]
        for vname, fc in flow(f):
            k = [e for e in fc["events"] if e["name"].startswith(f"Rando_Story_{ev}_") and _p(e, "GameDataName") == intro]
            if not k or _cases(fc, k[0]) != {0: None, 1: ev}:
                bad.append(f"{vname}: adult Malon's step back ({ev}) doesn't wait for child Malon's Epona intro")
            elif not any(_cases(fc, e).get(1) == k[0]["name"] for e in fc["events"] if e["type"] == "switch"):
                bad.append(f"{vname}: nothing leads to the Epona intro check before {ev}")
    # the clock
    row = bools.get(_murmur(note["clock"]))
    if row is None or row["DefaultValue"] is not True:
        bad.append(f"GameDataList: {note['clock']} is not true on a new file ({row and row['DefaultValue']})")
    # Great Fairies
    for name in note["fairy_flags"]:
        row = bools.get(_murmur(name))
        if row is None or row["DefaultValue"] is not False or row.get("SaveFileIndex") != 0:
            bad.append(f"GameDataList: no saved Bool {name} (false on a new file)")
    for key, flag in note["fairy_tests"].items():
        f, ev = key.split(":")
        for vname, fc in flow(f):
            e = _ev(fc).get(ev)
            if not e or e["type"] != "switch" or _p(e, "GameDataName") != flag:
                bad.append(f"{vname}: {ev} doesn't test {flag}")
    left = []
    for f in list(note["fairy_entries"]) + ["TriForcePoint"]:
        for vname, fc in flow(f):
            for e in fc["events"]:
                if e["type"] == "switch" and str(_p(e, "GameDataName")).startswith("IsGet.Item_") and \
                        _p(e, "GameDataName").split(".")[1] in {v[0] for v in FAIRIES.values()} and \
                        not (f, e["name"]) == tuple(note["fairy_call"][:2]):
                    left.append(f"{vname}:{e['name']}")
    if left:
        bad.append(f"fairy item tests left on IsGet: {left}")
    for f, (flag, comment) in note["fairy_entries"].items():
        for vname, fc in flow(f):
            s = _ev(fc).get(_name(fc, fc["entry_points"][FAIRY_ENTRY]["main"]))
            if not s or s["type"] != "action" or _p(s, "GameDataName") != flag or _p(s, "Value") is not True or \
                    _name(fc, s.get("next")) != comment:
                bad.append(f"{vname}: entry {FAIRY_ENTRY} doesn't set {flag} before {comment}")
    f, gate, call = note["fairy_call"]
    for vname, fc in flow(f):
        if set(_cases(fc, _ev(fc)[gate]).values()) != {call}:
            bad.append(f"{vname}: the Lullaby gate {gate} doesn't call every fairy ({_cases(fc, _ev(fc)[gate])})")
    # refill scrubs
    f, lasts, choice, hidden = note["scrub"]
    for vname, fc in flow(f):
        by = _ev(fc)
        for ev in lasts:
            chain, n = [], _name(fc, by[ev].get("next"))
            while n and n.startswith("Rando_Traps_ScrubKeepOne_") and by[n]["type"] == "switch":
                chain.append(_p(by[n], "GameDataName"))
                if _cases(fc, by[n]).get(1) != choice:
                    bad.append(f"{vname}: {n} doesn't go on to the choice when its good shows")
                n = _cases(fc, by[n]).get(0)
            s = by.get(n)
            if sorted(chain) != sorted(hidden) or not s or _p(s, "GameDataName") != hidden[0] or _p(s, "Value") is not False \
                    or _name(fc, s.get("next")) != choice:
                bad.append(f"{vname}: after {ev} the three hidden goods don't bring the first back ({chain}, {n})")
    bad += _verify_more(fs, note, gd, flow, romfs)
    # Vanilla sends none of its 27,789 switch cases straight to the flowchart end, so we check that
    # evfl_build.route_end_cases gave each patched case its do-nothing step.
    from evfl_build import end_cases
    edir = os.path.join(patch, "Event", "EventFlow")
    for fn in sorted(os.listdir(edir)) if os.path.isdir(edir) else []:
        if fn.endswith(".bfevfl.zs"):
            ends = end_cases(fs.read(f"Event/EventFlow/{fn}"))
            if ends:
                bad.append(f"{fn}: {len(ends)} switch case(s) point at the flowchart's end, e.g. {ends[0]}")
    return bad


def _exp_values(gd, name):
    row = next((e for e in gd["BoolExp"] if e["Hash"] == _murmur(name)), None)
    return None if row is None else [[int(v) for v in st] for st in row["Values"]]


def _want(steps):
    return [[_murmur(x) if isinstance(x, str) else int(x) for x in st] for st in steps]


def _verify_more(fs, note, gd, flow, romfs):
    """New-file defaults, the adult clock, the stone menu, the AINB words and wiring, the Kokiri schedules."""
    import struct
    from romtools import byml_load
    import ainb
    bad = []
    rows = {}
    for sec in ("Bool", "Enum"):
        for e in gd[sec]:
            rows[e["Hash"]] = (sec, e)
    for name, want in note["defaults"].items():
        sec, row = rows.get(_murmur(name), (None, None))
        got = None if row is None else row["DefaultValue"]
        if sec == "Enum":
            want = _murmur(want)
        if got != want:
            bad.append(f"GameDataList: {name} starts at {got!r}, planned {want!r}")
    f, entry, step, after = note["adult_clock"]
    for vname, fc in flow(f):
        if _name(fc, fc["entry_points"][entry]["main"]) != after:
            bad.append(f"{vname}: entry {entry} still sets the adult first-field flag ({step})")
    f, wait, menu = note["stone_menu"]
    for vname, fc in flow(f):
        if _name(fc, _ev(fc)[wait].get("next")) is not None:
            bad.append(f"{vname}: {wait} still opens the quest-menu presentation ({menu})")
    datas = {}
    for fl, off, new, old in note["binary"]:
        if fl not in datas:
            datas[fl] = fs.raw(fl)
        got = struct.unpack_from("<I", datas[fl], off)[0]
        if got != new:
            bad.append(f"{fl} @{off:#x}: {got:#x}, planned {new:#x}")
    for fl, d in datas.items():
        probs = ainb.Ainb(d).input_shape_problems()
        if probs:
            bad.append(f"{fl}: {probs[0]}")
    fl, reader, npc, exp = note["sheik"]
    a = ainb.Ainb(fs.raw(fl))
    names = {e["name"]: e for t in ainb.PTYPES for e in a.nodes[reader]["inputs"][t]}
    dele = next(e for e in a.nodes[npc]["inputs"]["bool"] if e["name"] == "Logic_Delete")
    if names["GameDataNameBoolExp"]["value"] != exp or (dele["node"], dele["plug"]) != (reader, 0) or \
            not a.nodes[reader]["outputs"]["bool"][0]["flag"] or a.input_shape_problems():
        bad.append(f"{fl}: Sheik's Logic_Delete doesn't read {exp} through node {reader}")
    if _exp_values(gd, exp) != _want(note["sheik_exp"]):
        bad.append(f"GameDataList: {exp} doesn't hold the planned expression")
    for name, steps in note["schedule_exps"].items():
        if _exp_values(gd, name) != _want(steps):
            bad.append(f"GameDataList: {name} doesn't hold the planned expression")
    f, after_thanks, npc, talks, flag, exp, call = note["link_goron"]
    if _murmur(flag) not in rows or rows[_murmur(flag)][1]["DefaultValue"] is not False:
        bad.append(f"GameDataList: no saved Bool {flag} (false on a new file)")
    for vname, fc in flow(f):
        s = [e for e in fc["events"] if e["name"].startswith(f"Rando_Story_{after_thanks}_") and e["type"] == "action"
             and _p(e, "GameDataName") == flag and _p(e, "Value") is True]
        pre = _ev(fc).get("Event314")
        if not s or _name(fc, pre.get("next")) != s[0]["name"] or _name(fc, s[0].get("next")) != after_thanks:
            bad.append(f"{vname}: {flag} isn't set right before {after_thanks} (after the tunic's thanks)")
    for vname, fc in flow(npc):
        for entry, talk in talks.items():
            first = _ev(fc).get(_name(fc, fc["entry_points"][entry]["main"]))
            a = first and _ev(fc).get(_cases(fc, first).get(1))
            c = a and _ev(fc).get(_cases(fc, a).get(0))
            if not first or _p(first, "GameDataName") != flag or _cases(fc, first).get(0) != talk or not a or _p(a, "GameDataName") != exp or not c or c["type"] != "subflow" or f"{c.get('flowchart')}:{c.get('entry_point')}" != call:
                bad.append(f"{vname}: his talk {entry} doesn't run {call} while {flag} is unset past TalkDaruniaJr")
    if note.get("cucco_text"):  # her lines naming chicken_count, read back from every language archive
        import msbt
        from romtools import sarc_files
        cache = {}
        for key, want in sorted(note["cucco_text"].items()):
            archive, label = key.split(":")
            if archive not in cache:
                rel = msbt.archives(fs.root)[archive]
                cache[archive] = msbt.Msbt(sarc_files(fs.read(rel))[CUCCO_FILE])
            got = cache[archive].markup(label)
            if got != want:
                bad.append(f"{archive} {CUCCO_FILE} {label}: doesn't hold the planned count line")
    if note.get("village_saria"):
        fl, node, inp, _, new = note["village_saria"]
        a = ainb.Ainb(fs.raw(fl))
        val = next((e["value"] for t in ainb.PTYPES for e in a.nodes[node]["inputs"][t] if e["name"] == inp), None)
        if val != new or a.input_shape_problems() or not _exp_values(gd, new):
            bad.append(f"{fl}: village Saria's node {node} reads {val}, planned {new}")
    if note.get("stone_count_gate"):
        f, ev, exp, steps = note["stone_count_gate"]
        if _exp_values(gd, exp) != _want(steps):
            bad.append(f"GameDataList: {exp} doesn't hold the planned expression")
        for vname, fc in flow(f):
            ep = _name(fc, fc["entry_points"]["DoorOfTime_CheckStoneNum"]["main"])
            g = [e for e in fc["events"] if e["name"].startswith(f"Rando_Story_{ev}_") and e["type"] == "switch"
                 and _p(e, "GameDataName") == exp]
            if not g or _cases(fc, g[0]).get(1) is not None or not _leads_to(fc, _cases(fc, g[0]).get(0), ev) or \
                    not _leads_to(fc, ep, g[0]["name"]):
                bad.append(f"{vname}: the stone check ({ev}) doesn't wait for {exp}")
        for vname, fc in flow("Goto_HyruleCastle"):
            if any(e["name"].startswith("Rando_Story_Event32_") and _p(e, "GameDataName") == "DoorOfTime_IsAfter_Ready_Exp"
                   for e in fc["events"]):
                bad.append(f"{vname}: Zelda's Step01 (Event32) is still skipped once a stone was counted")
    if note.get("owl"):
        o = note["owl"]
        f, ev, skipped, after = o["env"]
        for vname, fc in flow(f):
            if _name(fc, _ev(fc)[ev].get("next")) != after:
                bad.append(f"{vname}: Saria's bridge still sets HyruleField_ChangeENV ({ev} -> {skipped})")
        f, ev = o["lost_at"]
        for vname, fc in flow(f):
            q = [e for e in fc["events"] if e["name"].startswith(f"Rando_Story_{ev}_") and e["type"] == "switch"
                 and _p(e, "GameDataName") == o["played"]]
            sets, n = set(), (_cases(fc, q[0]).get(1) if q else None)
            while n and n.startswith(f"Rando_Story_{ev}_") and _ev(fc)[n]["type"] == "action":
                sets.add(_p(_ev(fc)[n], "GameDataName"))
                n = _name(fc, _ev(fc)[n].get("next"))
            if not q or sets != set(o["effects"]) or not _leads_to(fc, n, ev):
                bad.append(f"{vname}: Talon's wake-up ({ev}) doesn't set the owl's effects when the owl never played")
    if note.get("dmt_owl"):
        f, ev, _, to = note["dmt_owl"]
        for vname, fc in flow(f):
            if set(_cases(fc, _ev(fc)[ev]).values()) != {to}:
                bad.append(f"{vname}: the summit owl's Din's Fire test ({ev}) still refuses the flight")
    if note.get("scrub_note"):
        f, edits = note["scrub_note"]
        for vname, fc in flow(f):
            for ev, _, to in edits:
                if set(_cases(fc, _ev(fc)[ev]).values()) != {to}:
                    bad.append(f"{vname}: the HF scrub's note test ({ev}) still blocks the sale")
    if note.get("kf_ring"):  # each rock by its InstanceName; inputs constant (or b2db reading Adulthood alone)
        fl, keep, drop, (own, own_name, src, out) = note["kf_ring"]
        a = ainb.Ainb(fs.raw(fl))

        def inst(i):
            return next((x["value"] for x in a.nodes[i]["properties"]["string"] if x["name"] == "InstanceName"), None)

        def const(i, name, want):
            _, e = a._input(i, name)
            return e["node"] == -1 and e["value"] is want
        for k, v in keep.items():
            i = int(k)
            if inst(i) != f"Obj_LiftRock_A_01_{v}" or not const(i, "Logic_Create", True) or \
                    not const(i, "Logic_Delete", False):
                bad.append(f"{fl}: node {i} ({inst(i)}) isn't kept for every age")
        for k, v in drop.items():
            i = int(k)
            if inst(i) != f"Obj_LiftRock_A_01_{v}" or not const(i, "Logic_Create", False):
                bad.append(f"{fl}: node {i} ({inst(i)}) is still created")
        _, e = a._input(own, "Logic_Create")
        if inst(own) != f"Obj_LiftRock_A_01_{own_name}" or e["node"] != src or \
                a.nodes[src]["outputs"]["bool"][e["plug"]]["name"] != out or not const(own, "Logic_Delete", False):
            bad.append(f"{fl}: node {own} ({inst(own)}) isn't created for an adult always")
        fl2, (r19, r19_name), (fixed, fixed_name) = note["kf_centre"]
        c = ainb.Ainb(fs.raw(fl2))
        a = c
        if inst(r19) != r19_name or not const(r19, "Logic_Create", True) or not const(r19, "Logic_Delete", False) or \
                inst(fixed) != fixed_name or not const(fixed, "Logic_Create", False):
            bad.append(f"{fl2}: the centre isn't Rock 19 always ({inst(r19)}) and the fixed rock never ({inst(fixed)})")
        for f_ in (fl, fl2):
            probs = ainb.Ainb(fs.raw(f_)).input_shape_problems()
            if probs:
                bad.append(f"{f_}: {probs[0]}")
    if note.get("dmt_rocks"):  # one rock per Death Mountain spot: each node by its InstanceName
        fl, keep, drop = note["dmt_rocks"]
        a = ainb.Ainb(fs.raw(fl))
        for k, inst_name in list(keep.items()) + list(drop.items()):
            i = int(k)
            got = next((x["value"] for x in a.nodes[i]["properties"]["string"] if x["name"] == "InstanceName"), None)
            _, cr = a._input(i, "Logic_Create")
            _, de = a._input(i, "Logic_Delete")
            want_create = k in keep
            if got != inst_name or cr["node"] != -1 or cr["value"] is not want_create or (want_create and (de["node"] != -1 or de["value"] is not False)):
                bad.append(f"{fl}: node {i} ({got}) {'is not kept' if want_create else 'is still created'}")
        probs = a.input_shape_problems()
        if probs:
            bad.append(f"{fl}: {probs[0]}")
    if note.get("dc_lizalfos"):
        fl, node, inp, src, out = note["dc_lizalfos"]
        a = ainb.Ainb(fs.raw(fl))
        t, e = a._input(node, inp)
        base = -100 - e["node"]
        k = a._output_index(src, t, out)
        reads = [(m[0], m[1]) for m in a.multi[base:base + e["plug"]]] if e["node"] <= -100 else []
        if (src, k) not in reads or not a.nodes[src]["outputs"][t][k]["flag"] or a.input_shape_problems():
            bad.append(f"{fl}: node {node} {inp} doesn't read node {src} {out} ({reads})")
    if note.get("heart_piece_lift"):
        from romtools import sarc_files
        ap, ref, lp, own, src_pack, variants = note["heart_piece_lift"]
        files = sarc_files(fs.read(own))
        got = byml_load(files[ap])[0]["Components"].get("LiftableRef")
        ref_bytes = sarc_files(fs.read(src_pack)).get(lp)
        if got != ref or files.get(lp) is None or files.get(lp) != ref_bytes:
            bad.append(f"{own}: LiftableRef {got!r}, liftable file {'missing' if files.get(lp) is None else 'present'}")
        for vp in variants:  # the variants hold the same ActorParam (edited alike) and keep their own ""
            vf = sarc_files(fs.read(vp))
            name = vp.split("/")[-1].split(".")[0]
            own_ref = byml_load(vf[f"Actor/{name}.engine__actor__ActorParam.bgyml"])[0]["Components"].get("LiftableRef")
            if byml_load(vf[ap])[0]["Components"].get("LiftableRef") != ref or own_ref != "":
                bad.append(f"{vp}: the shared ActorParam or the variant's own LiftableRef ({own_ref!r}) changed")
    if "carpenters" not in note:  # plans made before this fix don't have it
        bad.append("story traps: the plan has no carpenters (made before this fix: regenerate it)")
    else:
        from romtools import sarc_files
        import packpaths
        for c, (ap, new, esc, old) in note["carpenters"]["schedules"].items():
            for file, want in ((ap, new), (esc, old)):  # every pack holding the file, edited alike
                for pack in packpaths.carriers(file, romfs):
                    got = byml_load(sarc_files(fs.read(pack))[file])[0].get("Components", {}).get("AIScheduleRef")
                    if got != want:
                        bad.append(f"{pack} {file}: AIScheduleRef {got!r}, not {want!r}")
        card = note["carpenters"]["card_played"]
        for fl, node, _ in note["carpenters"]["jail_gerudo"]:
            a = ainb.Ainb(fs.raw(fl))
            t, e = a._input(node, "BoolMulti")
            srcs = [m[0] for m in a.multi[-100 - e["node"]:-100 - e["node"] + e["plug"]]] if e["node"] <= -100 else []
            names = [x["value"] for s in srcs if a.nodes[s]["name"] == "HoldGameDataGetBoolSimple"
                     for x in a.nodes[s]["inputs"]["string"]]
            if card not in names or len(srcs) != 3 or a.input_shape_problems():
                bad.append(f"{fl}: node {node} reads {names} ({len(srcs)} sources), not also {card}")
    for key, what in (("lake_tree_wall", "the lake tree's hookshot wall"), ("gate_switch_wall", "the gate switch's wall")):
        if key not in note:  # gate_switch_wall: plans made before it don't have it
            bad.append(f"story traps: the plan has no {key} (made before this fix: regenerate it)")
            continue
        fl, h, pres = note[key]
        a = next((x for x in byml_load(fs.read(fl))[0].get("Actors") or [] if str(x.get("Hash")) == h), None)
        if a is None or a.get("Presence") != pres:
            bad.append(f"{fl} #{h}: {what} Presence is {a and a.get('Presence')}")
    if "owls_stay" not in note:
        bad.append("story traps: the plan has no owls_stay (made before this fix: regenerate it)")
    else:
        o = note["owls_stay"]
        for fl, h in o["placements"]:
            a = next((x for x in byml_load(fs.read(fl))[0].get("Actors") or [] if str(x.get("Hash")) == h), None)
            if a is None or a.get("Presence"):
                bad.append(f"{fl} #{h}: the owl {'is missing' if a is None else 'still has ' + str(a.get('Presence'))}")
        import ainb
        lf, node, name, want = o["logic"]
        e = ainb.Ainb(fs.raw(lf))._input(node, name)[1]
        if e.get("value") != want or e.get("node", -1) >= 0:
            bad.append(f"{lf}: node {node} reads {e.get('value')!r}, planned {want!r}")
    for path, old, new in note["schedules"]:
        flags = [s.get("ConditionFlag") for s in byml_load(fs.raw(path))[0].get("ConditionalSchedule", [])]
        if old in flags or new not in flags:
            bad.append(f"{path}: schedule flags {flags} (planned {old} -> {new})")
    bad += _verify_kf_boy(note, fs, gd)
    bad += _verify_owl_sunrise(note, flow)
    return bad


def _verify_owl_sunrise(note, flow):
    """OWL_SUNRISE read back. In every version of the owl's file, Event153 goes to the clock set (06:00), a 1-frame
    wait and the env rebuild, then the panorama step."""
    if "owl_sunrise" not in note:
        return ["story traps: the plan has no owl_sunrise (made before this fix: regenerate it)"]
    f, before, scene_step, _, _, hour, minute, graph = note["owl_sunrise"]
    bad = []
    for vname, fc in flow(f):
        by = _ev(fc)
        chain, n = [], _name(fc, (by.get(before) or {}).get("next"))
        while n and n.startswith(f"{graph}_") and len(chain) < 5:
            chain.append((_what(fc, by[n]), _p(by[n], "TimeHour"), _p(by[n], "TimeMin"), _p(by[n], "Frames")))
            n = _name(fc, by[n].get("next"))
        want = [("EventTrigger_SetTime", hour, minute, None), ("EventWait", None, None, 1),
                ("Event_RebuildConditionEnvTimePalette", None, None, None)]
        if chain != want or n != scene_step:
            bad.append(f"{vname}: {before} -> {chain} -> {n}, not the clock set to {hour:02d}:{minute:02d} before "
                       f"{scene_step}")
    return bad


def _verify_kf_boy(note, fs, gd):
    """KF_BOY read back. From a new file the ring Kokiri's schedule is AnchorAction2's, with its first ConditionFlag an
    always-true expression before the castle's, and his talk plays no rock step."""
    if "kf_boy" not in note:
        return ["story traps: the plan has no kf_boy (made before this fix: regenerate it)"]
    from romtools import byml_load
    from evfl_build import CASE_END_NAME
    bad = []
    (npc, old, new), steps, (ev, value, to) = note["kf_boy"]
    path = SCHEDULE.format(npc)
    sched = byml_load(fs.raw(path))[0]
    cond = sched.get("ConditionalSchedule") or []
    acts = [int((c.get("ActionSchedule") or [{}])[0].get("ActionType", 0)) for c in cond]
    if not cond or cond[0].get("ConditionFlag") != new or acts[0] != 3610578669 or \
            [c.get("ConditionFlag") for c in cond[1:]] != ["Rando_Kokiri_CastleAfterDeku_Exp"]:
        bad.append(f"{path}: schedules {[(c.get('ConditionFlag'), a) for c, a in zip(cond, acts)]}: not AnchorAction2 "
                   f"from a new file before the castle state")
    v = _exp_values(gd, new)
    if v != _want(KF_BOY_EXP) or len(v) != 4:
        bad.append(f"GameDataList: {new} isn't '(done) OR NOT (done)': {v}")
    fc = _boy_flow(fs)
    by = {e["name"]: e for e in fc["events"]}
    for e, k, want in steps:
        if e not in by or _p(by[e], k) != want:
            bad.append(f"{npc}: {e} {k} is {by.get(e) and _p(by[e], k)!r}, not {want!r}")
    c = next((c for c in (by.get(ev) or {}).get("cases", []) if c["value"] == value), None)
    t = c and _name(fc, c["next"])
    if t == f"{CASE_END_NAME}_w" and by[t].get("next") in (None, 0xFFFF):  # make_patch's do-nothing end step
        t = None
    if c is None or t != to:
        bad.append(f"{npc}: {ev}'s case {value} goes to {t}, not {to}")
    return bad
