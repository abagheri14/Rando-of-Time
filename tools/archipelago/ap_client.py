"""Archipelago client of Rando of Time: ``python tools/archipelago/ap_client.py [OUT] [--connect SERVER]``.

The randomizer app's button runs ``pythonw tools/archipelago/ap_client.py "<seed folder>"`` (the window).
``--help`` lists the rest (no window, the read-only game probe). Code: tools/archipelago/client/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.__main__ import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
