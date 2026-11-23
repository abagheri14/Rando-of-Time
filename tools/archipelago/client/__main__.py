"""Command line of the Archipelago client (``python tools/archipelago/ap_client.py ...``).

  ap_client.py                                   the window
  ap_client.py OUT                               the window, with the seed folder OUT (from build_patch.py) chosen
  ap_client.py OUT --connect SERVER [--slot NAME] [--password P]
                                                 the window, connecting at once
  ap_client.py OUT --connect SERVER --nogui      no window: events are printed; a typed line is sent as chat
                                                 (or a !command); Ctrl+C stops
  ap_client.py --probe                           reads the running game once (never writes) and says what it found

  --save-root DIR   the folder holding slot_NN/progress.sav (default: the tracker's save folder)
  --save FILE       follow this progress.sav only
  --no-live         never read the running game (checks from the save only; nothing handed over)
  --no-marks        don't send the checks marked by hand in the tracker
The password can also come from the AP_PASSWORD environment variable (a command line is visible to other programs).
"""
import argparse
import os
import sys
import threading
import time


def _headless(args):
    from .protocol import ClientError
    from .seed import SeedError
    from .session import Session
    try:
        session = Session(args.seed, args.connect, args.slot or '', args.password, save_root=args.save_root or '',
                          save_path=args.save or '', live=not args.no_live, send_marks=not args.no_marks)
    except (SeedError, ClientError, ValueError) as error:
        print('error:', error, file=sys.stderr)
        return 2
    session.start()

    def chat():
        for line in sys.stdin:
            if line.strip():
                session.say(line.strip())

    threading.Thread(target=chat, daemon=True).start()
    last, shown = None, 0
    try:
        while True:
            for event in session.events():
                kind = event.get('kind')
                stamp = time.strftime('%H:%M:%S', time.localtime(event.get('time', time.time())))
                if kind == 'received':
                    if event.get('index', 0) < shown:
                        continue             # the whole list again after a reconnect, already printed
                    shown = event.get('index', 0) + 1
                print(f'{stamp} [{kind}] {event.get("text", "")}', flush=True)
            summary = session.summary()
            if summary['fatal']:
                return 1
            line = (summary['status'], summary['delivery'], summary['game'])
            if last is None or line != last.get('line'):
                print(f'          status: {summary["status"]} | game: {summary["game"]} | '
                      f'items: {summary["delivery"]}', flush=True)
            last = dict(summary, line=line)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        session.stop()


def _probe():
    from . import live_memory
    return live_memory.main()


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ap_client', description='Archipelago client of Rando of Time.',
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument('seed', nargs='?', default='', help='the seed folder (build_patch.py OUT, with ap.json)')
    parser.add_argument('--connect', metavar='SERVER', default='', help='server address, e.g. archipelago.gg:38281')
    parser.add_argument('--slot', default='', help='slot name (default: the one in ap.json)')
    parser.add_argument('--password', default=os.environ.get('AP_PASSWORD', ''))
    parser.add_argument('--save-root', default='')
    parser.add_argument('--save', default='')
    parser.add_argument('--no-live', action='store_true')
    parser.add_argument('--no-marks', action='store_true')
    parser.add_argument('--nogui', action='store_true')
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args(argv)
    if args.probe:
        return _probe()
    if args.nogui:
        if not args.seed or not args.connect:
            parser.error('--nogui needs the seed folder and --connect SERVER')
        return _headless(args)
    from .app import run
    run(args.seed, args.connect, args.slot, args.password, connect=bool(args.connect and args.seed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
