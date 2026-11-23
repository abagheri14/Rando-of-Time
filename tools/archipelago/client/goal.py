"""The seed's goal, read from the save or the game. Per CONTRACT.md it's OoTR's goal for the settings, same as single
player.

The evidence comes from the game's own event flows and GameDataList, decoded from romfs, and the six Longshot saves.
- **Ganon.** ``Defeat_Ganon:InsideGanonCastle_Dungeon_BossDie_2`` Event37 runs EventExecuteProgressChallengeStep
  {ChallengeName 'Defeat_Ganon', StepName 'Complete'} right after Ganon's death, so the saved Enum
  ``Step_Defeat_Ganon`` becomes murmur3('Complete'). Every save so far reads 'Ready'. That only reaches the file at
  the game-clear save, after the credits (EndingProcess sets Sequence_ToTitleFromGameClear, and
  Sequence/EventToTitle.module.ainb nodes 17-19 run SeqExecuteAutoSaveMgrGameClearSave). So we read the running game
  too: the ending's ``HavePlayedEvent.Dm_Ending_0000`` (a saved Bool, set when the ending plays) and
  Sequence_ToTitleFromGameClear (not saved, set once the credits end).
- **Triforce Hunt.** The saved Int ``Rando_TriforcePieceNum`` (tools/rando make_patch, _gaps_triforce.py) counts the
  pieces, and the goal is in the seed's plan (``_gaps.triforce.goal``) or settings (``triforce_goal_per_world``).
  The goal piece asks for an autosave before the staff roll, so the save shows it.
"""
import json
import os

from .savefile import murmur3

GANON_STEP = 'Step_Defeat_Ganon'
COMPLETE = murmur3('Complete')
ENDING_PLAYED = 'HavePlayedEvent.Dm_Ending_0000'
TO_TITLE_FROM_CLEAR = 'Sequence_ToTitleFromGameClear'
TRIFORCE_COUNTER = 'Rando_TriforcePieceNum'


class GanonGoal:
    kind = 'ganon'
    text = 'Defeat Ganon'

    def reached(self, save, live=None):
        if save is not None and (save.enum(GANON_STEP) == COMPLETE or save.bool(ENDING_PLAYED) is True):
            return True
        bools = (live or {}).get('bool') or {}
        return bools.get(murmur3(ENDING_PLAYED)) is True or bools.get(murmur3(TO_TITLE_FROM_CLEAR)) is True


class TriforceGoal:
    kind = 'triforce'

    def __init__(self, goal, counter=TRIFORCE_COUNTER):
        self.goal, self.counter = int(goal), counter
        self.text = f'Collect {self.goal} Triforce pieces'

    def count(self, save):
        value = save.int(self.counter) if save is not None else None
        return value or 0

    def reached(self, save, live=None):
        return self.goal > 0 and self.count(save) >= self.goal


def _load(path):
    try:
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def seed_goal(folder, declared=None):
    """The goal of the seed in ``folder``: ap.json's "goal" ({"kind": "ganon"} or {"kind": "triforce_hunt",
    "count": N}) when given, else its plan.json, else its spoiler's or settings_used.json's settings."""
    if isinstance(declared, dict):
        kind = str(declared.get('kind') or '')
        if kind == 'ganon':
            return GanonGoal()
        if kind in ('triforce_hunt', 'triforce') and declared.get('count'):
            return TriforceGoal(declared['count'], declared.get('counter') or TRIFORCE_COUNTER)
    triforce = (_load(os.path.join(folder, 'plan.json')).get('_gaps') or {}).get('triforce')
    if isinstance(triforce, dict) and triforce.get('goal'):
        return TriforceGoal(triforce['goal'], triforce.get('counter') or TRIFORCE_COUNTER)
    for name in ('spoiler.json', 'settings_used.json'):
        settings = _load(os.path.join(folder, name)).get('settings') or {}
        if settings.get('triforce_hunt'):
            return TriforceGoal(settings.get('triforce_goal_per_world') or 20)
    return GanonGoal()
