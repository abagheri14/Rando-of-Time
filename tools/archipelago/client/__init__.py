"""Archipelago client of Rando of Time (standard library only).

Reports the checks the player has done (from the save, and from the running game when it can be read), hands the
items received from other worlds to the running game (data/archipelago/MAILBOX.md), and reports the goal.
Parts ported from OotrR (github.com/Mozencaz/OotrR), MIT: see LICENSE-OotrR.txt.

  websocket.py    RFC 6455 client (ws://, wss:// verified, permessage-deflate)
  protocol.py     the Archipelago protocol (Connect, ReceivedItems, LocationChecks, StatusUpdate, PrintJSON, Say)
  savefile.py     slot_NN/progress.sav, read as the tracker reads it
  seed.py, goal.py  the seed's ap.json and tracker.json, its check flags and its goal
  live_memory.py  the running game's GameData (Longshot/Hookshot, yuzu-family emulators; Windows and Linux)
  delivery.py     the mailbox: one received item at a time, retries
  session.py      all of it for one seed;  app.py the window;  __main__.py the command line
"""
