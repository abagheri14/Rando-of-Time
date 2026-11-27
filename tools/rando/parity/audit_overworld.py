"""Parity plugin: the overworld requirements audit (every non-dungeon OoTR location in play, and the region exits
and events on the way to them).

OoTR's logic describes the 1998 game. Where the remake makes a check harder, OoTR's rule is too loose and a seed
could expect a check the player can't reach. This plugin owns no setting and patches nothing. It only carries the
stricter rules in data/rando/logic/audit_overworld.json, which world_settings.logic_overrides loads while the
plugin is enabled (enabled in config/plugins.json). Each rule there is OoTR's own rule with the remake's extra
condition added (or, for a grotto whose lid changed, the lid's real opener), with its evidence under "_why". The
full table (every location audited, the OoTR rule, the remake's requirement, sources, verdict) is in my notes.

What it tightens (details and confidence in the logic file and the research note):
- story gates: Bombchu Bowling only plays after the Goron Ruby stage, adult Zora's Domain keeps its shop behind a
  static red ice until the Water Temple, Epona needs the child's song lesson with Malon, and the Link's-house cow
  needs Talon back at the ranch
- money: the Colossus and outside-Ganon's-Castle Great Fairies take 300 and 500 rupee donations (Adult's Wallet)
- items: arrows don't stop the adult rolling Goron anymore, and the Gerudo desert gate stays shut from the desert
  side until the gatekeeper has opened it
- moved checks: Zora's River's tree skulltula lives in a bean soil. The bridge-ledge chest and the ReDead grotto
  chest are the chests plugin's locations, set up in data/rando/chests_locations.json by the grotto pass.
- grotto lids: each grotto entrance follows the lid the remake put on it (actor pack parent DisappearSrom = Song of
  Storms, BrokenBomb = bombs or hammer). HF Tektite and SFM Wolfos need the song, SFM Storms and ZD Storms need a
  bomb or the hammer instead, HF Open and LLR (child) get a bomb lid, and GF's grotto sits among crates. Zora's
  River's entrance rocks stand in both age layouts.
- skulltulas the guides and level files place out of OoTR's reach (Longshot, Hookshot or bean), and one Hyrule
  Field grotto skulltula that needs both ages.
"""
OWNS = {}
