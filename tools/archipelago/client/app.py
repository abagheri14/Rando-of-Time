"""The Archipelago client window (Tk, standard library), in the randomizer's look (common/ui/Ui.cs): dark wood frame
with gold lettering, parchment pages, a dark log at the bottom.

Left: the seed, the server, the slot and password, the save folder, Connect; under them what is happening (connection,
checks, items, the game, the save, the goal). Right: the Items page (received and sent) and the Chat page.
"""
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk

from .protocol import ClientError
from .seed import Seed, SeedError
from .session import Session, default_save_root, settings_dir

# common/ui/Ui.cs Pal (the frame) and Paper (the pages)
BG, PANEL, RAISED, HOVER = '#2e2014', '#3e2c1c', '#4c3622', '#5a4129'
BORDER, BORDER_HI, DEEP = '#624a2e', '#967a3e', '#1e150d'
TEXT, TEXT_DIM, TEXT_FAINT = '#ecdeba', '#c6b48e', '#927c5a'
GOLD, GOLD_HI, GOLD_DIM, GOLD_INK = '#d6b25c', '#e8c878', '#967a3e', '#342416'
GREEN, RED = '#96c46e', '#e27860'
PAPER, CARD, PAPER_LINE, FIELD = '#ecdeba', '#f4ead0', '#dac89e', '#faf4e4'
INK, INK_DIM, INK_FAINT, PAPER_GOLD = '#342416', '#745e40', '#a69472', '#c49a3c'
# Archipelago's item colours, darkened to read on parchment
PROGRESSION, USEFUL, TRAP, FILLER = '#6a3fa0', '#2f5db8', '#b5452e', '#5e6b45'

SETTINGS = 'settings.json'


def _family(root, *names):
    have = {f.lower() for f in tkfont.families(root)}
    for name in names:
        if name.lower() in have:
            return name
    return names[-1]


def load_settings():
    try:
        with open(os.path.join(settings_dir(), SETTINGS), encoding='utf-8') as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    """The fields of the window, never the password."""
    try:
        os.makedirs(settings_dir(), exist_ok=True)
        path = os.path.join(settings_dir(), SETTINGS)
        with open(path + '.tmp', 'w', encoding='utf-8') as stream:
            json.dump({k: v for k, v in data.items() if k != 'password'}, stream, indent=1)
        os.replace(path + '.tmp', path)
    except OSError:
        pass


class Button(tk.Label):
    """A flat button drawn like the randomizer's (Label based: Tk's own Button ignores colours on macOS)."""

    def __init__(self, parent, text, command, primary=False, **kw):
        self.primary, self.command, self.enabled = primary, command, True
        super().__init__(parent, text=text, cursor='hand2', padx=14, pady=6, bd=1, relief='solid',
                         highlightthickness=0, **kw)
        self._paint(False)
        self.bind('<Enter>', lambda e: self._paint(True))
        self.bind('<Leave>', lambda e: self._paint(False))
        self.bind('<Button-1>', self._click)

    def _paint(self, hover):
        if not self.enabled:
            self.configure(bg=PANEL, fg=TEXT_FAINT, highlightbackground=BORDER)
        elif self.primary:
            self.configure(bg=GOLD_HI if hover else GOLD, fg=GOLD_INK)
        else:
            self.configure(bg=HOVER if hover else BG, fg=TEXT)

    def _click(self, _event):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor='hand2' if enabled else 'arrow')
        self._paint(False)


class ClientWindow:
    def __init__(self, root, seed_folder='', server='', slot='', password='', connect=False):
        self.root = root
        self.session = None
        self.settings = load_settings()
        root.title('Archipelago · Rando of Time')
        root.configure(bg=BG)
        try:
            self.scale = max(1.0, float(root.tk.call('tk', 'scaling')) / (96 / 72))
        except (tk.TclError, ValueError):
            self.scale = 1.0
        root.minsize(min(self.px(780), root.winfo_screenwidth()), min(self.px(540), root.winfo_screenheight()))
        self.serif = _family(root, 'Palatino Linotype', 'Book Antiqua', 'Palatino', 'DejaVu Serif', 'Times')
        self.ui = _family(root, 'Segoe UI', 'Noto Sans', 'DejaVu Sans', 'Helvetica')
        self.mono = _family(root, 'Consolas', 'DejaVu Sans Mono', 'Courier')
        self.f_title = tkfont.Font(root, family=self.serif, size=20, weight='bold')
        self.f_head = tkfont.Font(root, family=self.serif, size=14, weight='bold')
        self.f_text = tkfont.Font(root, family=self.ui, size=10)
        self.f_bold = tkfont.Font(root, family=self.ui, size=10, weight='bold')
        self.f_small = tkfont.Font(root, family=self.ui, size=9)
        self.f_mono = tkfont.Font(root, family=self.mono, size=9)
        self.f_tab = tkfont.Font(root, family=self.serif, size=12, weight='bold')
        self.vars = {name: tk.StringVar(root, value=value) for name, value in (
            ('seed', seed_folder or self.settings.get('seed', '')),
            ('server', server or self.settings.get('server', 'archipelago.gg:38281')),
            ('slot', slot or self.settings.get('slot', '')),
            ('password', password),
            ('saves', self.settings.get('saves') or default_save_root()))}
        self.marks = tk.BooleanVar(root, value=self.settings.get('marks', True))
        self._build()
        self._seed_changed()
        self.vars['seed'].trace_add('write', lambda *_: self._seed_changed())
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(200, self._poll)
        if connect:
            root.after(300, self.connect)

    # Layout
    def px(self, points):
        """Pixels for a length given at 96 DPI: the same physical size on every screen."""
        return int(round(points * self.scale))

    def _build(self):
        root = self.root
        self.left_width = self.px(350)
        style = ttk.Style(root)
        style.theme_use('clam')      # the theme whose scrollbars take colours (only ttk widgets use it)
        for name, trough, thumb, edge, arrow in (('Wood', DEEP, RAISED, BORDER, GOLD),
                                                 ('Paper', CARD, PAPER_LINE, PAPER_LINE, INK_DIM)):
            style.configure(f'{name}.Vertical.TScrollbar', troughcolor=trough, background=thumb,
                            bordercolor=edge, lightcolor=thumb, darkcolor=thumb, arrowcolor=arrow,
                            gripcount=0, arrowsize=self.px(12))
            style.map(f'{name}.Vertical.TScrollbar', background=[('active', HOVER if name == 'Wood' else
                                                                  PAPER_GOLD)])
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)
        root.rowconfigure(2, weight=0)
        header = tk.Frame(root, bg=BG)
        header.grid(row=0, column=0, columnspan=2, sticky='ew', padx=self.px(16), pady=(self.px(10), self.px(8)))
        header.columnconfigure(1, weight=1)
        self.logo = self._logo()
        if self.logo:
            tk.Label(header, image=self.logo, bg=BG).grid(row=0, column=0, rowspan=2, padx=(0, self.px(12)))
        tk.Label(header, text='Archipelago  ·  Multiworld', font=self.f_title, fg=GOLD, bg=BG,
                 anchor='w').grid(row=0, column=1, sticky='ew')
        subtitle = tk.Label(header, text='Your checks go to the server; other worlds\' items come to your game',
                            font=self.f_text, fg=TEXT_DIM, bg=BG, anchor='w', justify='left')
        subtitle.grid(row=1, column=1, sticky='ew')
        header.bind('<Configure>', lambda e: subtitle.configure(wraplength=max(self.px(200),
                                                                               e.width - self.px(90))))
        tk.Frame(root, bg=BORDER_HI, height=1).grid(row=0, column=0, columnspan=2, sticky='sew')

        # Let the left panel scroll when the window is too short to show every control.
        holder = tk.Frame(root, bg=BG)
        holder.grid(row=1, column=0, rowspan=2, sticky='nsew', padx=(self.px(16), self.px(12)), pady=self.px(8))
        holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, bd=0, width=self.left_width)
        canvas.grid(row=0, column=0, sticky='ns')
        bar = ttk.Scrollbar(holder, command=canvas.yview, style='Wood.Vertical.TScrollbar')
        canvas.configure(yscrollcommand=bar.set)
        left = tk.Frame(canvas, bg=BG)
        left.columnconfigure(0, weight=1)
        canvas.create_window((0, 0), window=left, anchor='nw', width=self.left_width)

        def fit(_event=None):
            canvas.configure(scrollregion=(0, 0, self.left_width, left.winfo_reqheight()))
            if left.winfo_reqheight() > canvas.winfo_height() > 1:
                bar.grid(row=0, column=1, sticky='ns', padx=(self.px(4), 0))
            else:
                bar.grid_remove()
                canvas.yview_moveto(0)
        left.bind('<Configure>', fit)
        canvas.bind('<Configure>', fit)

        def wheel(event):
            if bar.winfo_ismapped():
                canvas.yview_scroll(-1 if (event.delta > 0 or event.num == 4) else 1, 'units')
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            canvas.bind_all(sequence, lambda e: wheel(e) if str(e.widget).startswith(str(holder)) else None,
                            add='+')
        self._left(left)
        tk.Frame(root, bg=BORDER, width=1).grid(row=1, column=0, rowspan=2, sticky='nse')

        right = tk.Frame(root, bg=BG)
        right.grid(row=1, column=1, sticky='nsew', padx=(self.px(8), self.px(16)), pady=(self.px(8), self.px(4)))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self._pages(right)

        bottom = tk.Frame(root, bg=BG)
        bottom.grid(row=2, column=1, sticky='nsew', padx=(self.px(8), self.px(16)), pady=(0, self.px(12)))
        bottom.columnconfigure(0, weight=1)
        tk.Label(bottom, text='Log', font=self.f_head, fg=GOLD, bg=BG).grid(row=0, column=0, sticky='w')
        self.log = self._text(bottom, DEEP, TEXT, self.f_mono, height=6)
        self.log.master.grid(row=1, column=0, sticky='nsew')
        self.log.tag_configure('error', foreground=RED)
        self.log.tag_configure('good', foreground=GREEN)
        self.log.tag_configure('gold', foreground=GOLD)
        self.log.tag_configure('dim', foreground=TEXT_FAINT)

    def _logo(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for up in range(2, 6):
            base = here
            for _ in range(up):
                base = os.path.dirname(base)
            path = os.path.join(base, 'common', 'ui', 'randomizer_256.png')
            if os.path.isfile(path):
                try:
                    image = tk.PhotoImage(file=path)
                    scale = max(1, round(256 / (48 * float(self.root.tk.call('tk', 'scaling')) / 1.333)))
                    return image.subsample(scale)
                except tk.TclError:
                    return None
        return None

    def _label(self, parent, text, row, **kw):
        label = tk.Label(parent, text=text, font=self.f_text, fg=GOLD_DIM, bg=BG, anchor='w', justify='left', **kw)
        label.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(self.px(6), self.px(1)))
        return label

    def _entry(self, parent, var, row, show=None, browse=None):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=row, column=0, columnspan=2, sticky='ew')
        frame.columnconfigure(0, weight=1)
        entry = tk.Entry(frame, textvariable=var, font=self.f_text, bg=DEEP, fg=TEXT, insertbackground=GOLD,
                         relief='solid', bd=1, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=GOLD_DIM, show=show or '', width=1)
        entry.grid(row=0, column=0, sticky='ew', ipady=self.px(3))
        # Show the end of long paths so the seed folder name stays visible.
        var.trace_add('write', lambda *_: entry.after_idle(lambda: entry.xview_moveto(1.0)))
        entry.after_idle(lambda: entry.xview_moveto(1.0))
        if browse:
            Button(frame, 'Browse...', browse, font=self.f_text).grid(row=0, column=1, padx=(self.px(8), 0))
        return entry

    def _left(self, left):
        tk.Label(left, text='Connection', font=self.f_head, fg=GOLD, bg=BG, anchor='w').grid(
            row=0, column=0, sticky='ew')
        self._label(left, 'The seed (its folder, with ap.json)', 1)
        self._entry(left, self.vars['seed'], 2, browse=self._pick_seed)
        self._label(left, 'Server (address:port)', 3)
        server = self._entry(left, self.vars['server'], 4)
        self._label(left, 'Slot (your name in the multiworld)', 5)
        self._entry(left, self.vars['slot'], 6)
        self._label(left, 'Password (if the room has one)', 7)
        self._entry(left, self.vars['password'], 8, show='•')
        self._label(left, 'Save folder (slot_NN\\progress.sav)', 9)
        self._entry(left, self.vars['saves'], 10, browse=self._pick_saves)
        tk.Checkbutton(left, text='Also send checks marked by hand in the tracker', variable=self.marks,
                       font=self.f_small, fg=TEXT_DIM, bg=BG, activebackground=BG, activeforeground=TEXT,
                       selectcolor=DEEP, anchor='w', justify='left', wraplength=self.left_width - self.px(40)).grid(
            row=11, column=0, sticky='ew', pady=(self.px(6), 0))
        buttons = tk.Frame(left, bg=BG)
        buttons.grid(row=12, column=0, sticky='ew', pady=(self.px(10), self.px(2)))
        buttons.columnconfigure(0, weight=1)
        self.connect_button = Button(buttons, 'Connect', self.toggle, primary=True, font=self.f_head)
        self.connect_button.configure(pady=self.px(4))
        self.connect_button.grid(row=0, column=0, sticky='ew')
        server.bind('<Return>', lambda e: self.toggle())

        tk.Label(left, text='Status', font=self.f_head, fg=GOLD, bg=BG, anchor='w').grid(
            row=13, column=0, sticky='ew', pady=(self.px(10), self.px(2)))
        status = tk.Frame(left, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        status.grid(row=14, column=0, sticky='nsew', pady=(0, self.px(4)))
        status.columnconfigure(1, weight=1)
        self.status = {}
        for row, (key, title) in enumerate((('connection', 'Server'), ('checks', 'Checks'), ('items', 'Items'),
                                            ('game', 'Game'), ('save', 'Save'), ('goal', 'Goal'))):
            tk.Label(status, text=title, font=self.f_small, fg=TEXT_FAINT, bg=PANEL, anchor='nw').grid(
                row=row, column=0, sticky='nw', padx=(self.px(10), self.px(8)), pady=self.px(2))
            value = tk.Label(status, text='—', font=self.f_small, fg=TEXT, bg=PANEL, anchor='nw', justify='left',
                             wraplength=self.left_width - self.px(86))
            value.grid(row=row, column=1, sticky='new', padx=(0, self.px(10)), pady=self.px(2))
            self.status[key] = value

    def _text(self, parent, bg, fg, font, height):
        frame = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = tk.Text(frame, bg=bg, fg=fg, font=font, height=height, wrap='word', relief='flat', bd=0,
                       padx=10, pady=6, insertbackground=fg, highlightthickness=0, state='disabled', cursor='arrow')
        text.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(frame, command=text.yview,
                            style='Wood.Vertical.TScrollbar' if bg == DEEP else 'Paper.Vertical.TScrollbar')
        bar.grid(row=0, column=1, sticky='ns')
        text.configure(yscrollcommand=bar.set)
        return text

    def _pages(self, right):
        tabs = tk.Frame(right, bg=BG)
        tabs.grid(row=0, column=0, sticky='ew')
        book = tk.Frame(right, bg=PAPER, highlightthickness=1, highlightbackground=BORDER_HI)
        book.grid(row=1, column=0, sticky='nsew')
        book.columnconfigure(0, weight=1)
        book.rowconfigure(0, weight=1)
        self.pages, self.tab_labels = {}, {}

        items = tk.Frame(book, bg=PAPER)
        items.columnconfigure(0, weight=1)
        items.rowconfigure(1, weight=1)
        caption = tk.Label(items, text='← received from other worlds   → found here for another world   '
                                       '✓ handed over in the game', font=self.f_small, fg=INK_DIM, bg=PAPER,
                           anchor='w', justify='left')
        caption.grid(row=0, column=0, sticky='ew', padx=self.px(14), pady=(self.px(10), self.px(4)))
        items.bind('<Configure>', lambda e: caption.configure(wraplength=max(self.px(120), e.width - self.px(30))))
        self.items = self._text(items, CARD, INK, self.f_text, height=12)
        self.items.master.configure(highlightbackground=PAPER_LINE)
        self.items.master.grid(row=1, column=0, sticky='nsew', padx=14, pady=(0, 14))

        chat = tk.Frame(book, bg=PAPER)
        chat.columnconfigure(0, weight=1)
        chat.rowconfigure(0, weight=1)
        self.chat = self._text(chat, CARD, INK, self.f_text, height=12)
        self.chat.master.configure(highlightbackground=PAPER_LINE)
        self.chat.master.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=14, pady=(14, 8))
        self.say = tk.Entry(chat, font=self.f_text, bg=FIELD, fg=INK, insertbackground=INK, relief='solid', bd=1,
                            highlightthickness=1, highlightbackground=PAPER_LINE, highlightcolor=PAPER_GOLD)
        self.say.grid(row=1, column=0, sticky='ew', padx=(14, 8), pady=(0, 14), ipady=5)
        self.say.bind('<Return>', lambda e: self._say())
        send = tk.Label(chat, text='Send', font=self.f_bold, bg=PAPER_GOLD, fg=INK, padx=16, pady=5, cursor='hand2')
        send.grid(row=1, column=1, padx=(0, 14), pady=(0, 14))
        send.bind('<Button-1>', lambda e: self._say())
        hint = tk.Label(chat, text='Chat, or a server command: !hint <item>, !remaining, !release, !collect',
                        font=self.f_small, fg=INK_DIM, bg=PAPER, anchor='w', justify='left')
        hint.grid(row=2, column=0, columnspan=2, sticky='ew', padx=self.px(14), pady=(0, self.px(10)))
        chat.bind('<Configure>', lambda e: hint.configure(wraplength=max(self.px(120), e.width - self.px(30))), add='+')

        for widget in (self.items, self.chat):
            for tag, colour in (('progression', PROGRESSION), ('useful', USEFUL), ('trap', TRAP),
                                ('item', FILLER), ('player', INK), ('location', INK_DIM)):
                widget.tag_configure(tag, foreground=colour)
            widget.tag_configure('player', font=self.f_bold)
            widget.tag_configure('progression', font=self.f_bold)
            widget.tag_configure('time', foreground=INK_FAINT, font=self.f_small)
            widget.tag_configure('dim', foreground=INK_DIM)
            widget.tag_configure('in', foreground=INK)
            widget.tag_configure('good', foreground='#4d7a2a')

        for column, (key, title, page) in enumerate((('items', 'Items', items), ('chat', 'Chat', chat))):
            label = tk.Label(tabs, text=title, font=self.f_tab, padx=18, pady=7, cursor='hand2', bd=0)
            label.grid(row=0, column=column, padx=(0, 4), sticky='s')
            label.bind('<Button-1>', lambda e, k=key: self.show(k))
            self.pages[key], self.tab_labels[key] = page, label
        self.show('items')

    def show(self, key):
        for name, page in self.pages.items():
            if name == key:
                page.grid(row=0, column=0, sticky='nsew')
            else:
                page.grid_remove()
            self.tab_labels[name].configure(bg=GOLD if name == key else RAISED,
                                            fg=GOLD_INK if name == key else GOLD)
        self.current_page = key
        if key == 'chat':
            self.say.focus_set()

    # Actions
    def _pick_seed(self):
        folder = filedialog.askdirectory(parent=self.root, title='The seed folder (with ap.json and tracker.json)',
                                         initialdir=self.vars['seed'].get() or os.getcwd())
        if folder:
            self.vars['seed'].set(os.path.normpath(folder))

    def _pick_saves(self):
        folder = filedialog.askdirectory(parent=self.root, title='The folder holding slot_NN\\progress.sav',
                                         initialdir=self.vars['saves'].get() or os.getcwd())
        if folder:
            self.vars['saves'].set(os.path.normpath(folder))

    def _seed_changed(self):
        folder = self.vars['seed'].get().strip()
        if not folder or not os.path.isfile(os.path.join(folder, 'ap.json')):
            return
        try:
            seed = Seed(folder)
        except SeedError:
            return
        if seed.slot_name and (not self.vars['slot'].get().strip() or self._slot_from_seed):
            self.vars['slot'].set(seed.slot_name)
            self._slot_from_seed = True
        self.status['goal'].configure(text=seed.goal.text)
        self.status['checks'].configure(text=f'{len(seed.location_ids)} locations in this slot')

    _slot_from_seed = False
    received_shown = 0
    _shown_key = None

    def toggle(self):
        if self.session is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        values['password'] = self.vars['password'].get()
        if not values['seed']:
            self.write_log('Choose the seed folder first (the folder build_patch made, with ap.json).', 'error')
            return
        try:
            self.session = Session(values['seed'], values['server'], values['slot'], values['password'],
                                   save_root=values['saves'], send_marks=self.marks.get())
        except (SeedError, ClientError, ValueError) as error:
            self.write_log(str(error), 'error')
            self.session = None
            return
        save_settings(dict(seed=values['seed'], server=values['server'], slot=values['slot'],
                           saves=values['saves'], marks=self.marks.get()))
        key = (os.path.normcase(os.path.abspath(values['seed'])), self.session.client.slot_name)
        if key != self._shown_key:       # another seed or slot: its own item list
            self._shown_key, self.received_shown = key, 0
            for widget in (self.items, self.chat):
                widget.configure(state='normal')
                widget.delete('1.0', 'end')
                widget.configure(state='disabled')
        self.session.start()
        self.connect_button.configure(text='Disconnect')
        self.connect_button.primary = False
        self.connect_button._paint(False)

    def disconnect(self):
        session, self.session = self.session, None
        if session is not None:
            threading.Thread(target=session.stop, daemon=True).start()
        self.connect_button.configure(text='Connect')
        self.connect_button.primary = True
        self.connect_button._paint(False)
        self.status['connection'].configure(text='Disconnected', fg=TEXT_DIM)

    def _say(self):
        text = self.say.get().strip()
        if not text:
            return
        if self.session is None:
            self.write_log('Not connected: nothing sent.', 'error')
            return
        self.session.say(text)
        self.say.delete(0, 'end')

    def close(self):
        session, self.session = self.session, None
        if session is not None:
            done = threading.Event()
            threading.Thread(target=lambda: (session.stop(), done.set()), daemon=True).start()
            done.wait(2.0)
        self.root.destroy()

    # Updates
    def _append(self, widget, parts):
        follow = widget.yview()[1] >= 0.999
        widget.configure(state='normal')
        for text, tags in parts:
            widget.insert('end', text, tags)
        widget.insert('end', '\n')
        if int(widget.index('end-1c').split('.')[0]) > 3000:
            widget.delete('1.0', '500.0')
        widget.configure(state='disabled')
        if follow:                       # stays where the player scrolled to read
            widget.see('end')

    def write_log(self, text, tag=None):
        stamp = time.strftime('%H:%M:%S')
        self._append(self.log, [(stamp + '  ', 'dim'), (text, tag or ())])

    def _rich(self, event):
        """(text, tags) pieces of a PrintJSON event: its coloured parts."""
        text, tags = event.get('text', ''), event.get('tags') or []
        pieces, at = [], 0
        for start, end, tag in sorted(tags):
            if start > at:
                pieces.append((text[at:start], ()))
            pieces.append((text[start:end], (tag,)))
            at = end
        if at < len(text):
            pieces.append((text[at:], ()))
        return pieces

    def _event(self, event):
        kind = event.get('kind')
        stamp = time.strftime('%H:%M', time.localtime(event.get('time', time.time())))
        if kind == 'received':
            index = int(event.get('index') or 0)
            if index < self.received_shown:
                return  # Reconnects send the full item list again.
            self.received_shown = index + 1
            name, sender, where = self.session.client.describe_received(event.get('item') or {}) \
                if self.session else (event['text'], '', '')
            flags = int(event.get('flags') or 0)
            tag = 'trap' if flags & 4 else 'progression' if flags & 1 else 'useful' if flags & 2 else 'item'
            self._append(self.items, [(stamp + '  ', 'time'), ('←  ', 'dim'), (name, tag), ('  from ', 'dim'),
                                      (sender, 'player'), (f'  ({where})', 'location')])
        elif kind == 'sent':
            self._append(self.items, [(stamp + '  ', 'time'), ('→  ', 'dim')] + self._rich(event))
        elif kind == 'delivered':
            self._append(self.items, [(stamp + '  ', 'time'), ('✓  ' + event['text'], 'good')])
        elif kind in ('chat', 'own'):
            self._append(self.chat, [(stamp + '  ', 'time')] + self._rich(event))
        elif kind == 'error':
            self.write_log(event['text'], 'error')
        elif kind == 'goal':
            self.write_log(event['text'], 'good')
        elif kind == 'checks':
            self.write_log(event['text'], 'dim')
        else:
            self.write_log(event.get('text', ''), 'gold' if kind == 'status' else None)

    def _poll(self):
        session = self.session
        if session is not None:
            for event in session.events():
                self._event(event)
            s = session.summary()
            colour = GREEN if s['connected'] else RED if s['fatal'] else GOLD
            self.status['connection'].configure(text=('● ' + s['status']), fg=colour)
            self.status['checks'].configure(text=f"{s['checks']} of {s['total']} checked")
            items = f"{s['received']} received"
            if s['in_game'] is not None:
                items += f" · {s['in_game']} in the game"
            if s['to_hand_over']:
                items += f" · {s['to_hand_over']} to hand over"
            self.status['items'].configure(text=items + '\n' + s['delivery'])
            self.status['game'].configure(text=s['game'])
            self.status['save'].configure(text=s['save'] or '—')
            self.status['goal'].configure(text=s['goal'] + (' — reached, sent to the server' if s['goal_sent'] else
                                                            ' — reached' if s['goal_reached'] else ''),
                                          fg=GREEN if s['goal_reached'] else TEXT)
            if s['fatal']:
                self.session = None
                threading.Thread(target=session.stop, daemon=True).start()
                self.connect_button.configure(text='Connect')
                self.connect_button.primary = True
                self.connect_button._paint(False)
        self.root.after(200, self._poll)


def dpi_aware():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


def run(seed_folder='', server='', slot='', password='', connect=False):
    dpi_aware()
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', root.winfo_fpixels('1i') / 72.0)
    except tk.TclError:
        pass
    window = ClientWindow(root, seed_folder, server, slot, password, connect)
    width = min(window.px(1100), int(root.winfo_screenwidth() * 0.9))
    height = min(window.px(760), int(root.winfo_screenheight() * 0.85))
    root.geometry(f'{width}x{height}')
    root.mainloop()
    return window
