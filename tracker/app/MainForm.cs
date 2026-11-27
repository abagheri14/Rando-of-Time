// The tracker window, built from the shared controls in common/ui/Ui.cs. The header has the seed's progress and
// the Seed, View and Spoiler menus. Each place lists its done and total checks, and a dungeon's count covers all
// its floors. The map and its floor buttons sit above the activity log, the items are on the right, and the save
// and game status run along the bottom. A narrow window puts the map on top, the two lists side by side under it
// and the items below them.
// The save and Longshot's log feed the activity. You mark a check the save can't report by hand, with a
// right-click. LogicClient takes the items found so far and counts the reachable open checks per place, floor and
// seed, in green. The checks panel shows either only reachable checks, or all of them with out-of-logic ones as
// hollow rings. The activity log lists done checks, items found and places entered as they happen.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using RemakeUi;

[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8")]
[assembly: System.Reflection.AssemblyTitle("Rando of Time Tracker")]
[assembly: System.Reflection.AssemblyProduct("Rando of Time Tracker")]
[assembly: System.Reflection.AssemblyVersion("0.9.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("0.9.0.0")]
[assembly: System.Reflection.AssemblyInformationalVersion("0.9")]

namespace RandoOfTimeTracker
{
    // Where Longshot keeps its saves and log. That's the launcher's folder (the one with builds.json), found in the
    // places the randomizer looks (%LOCALAPPDATA%\LongshotLauncher, %USERPROFILE%\LongshotLauncher-data,
    // \LongshotLauncher-data on a fixed drive), and its default build (else the first listed) for the log.
    public static class LongshotHome
    {
        public static string Home()
        {
            var cands = new List<string> {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "LongshotLauncher"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "LongshotLauncher-data") };
            try
            {
                foreach (var d in DriveInfo.GetDrives())
                    if (d.DriveType == DriveType.Fixed && d.IsReady) cands.Add(Path.Combine(d.RootDirectory.FullName, "LongshotLauncher-data"));
            }
            catch (Exception) { }
            foreach (var c in cands)
                if (File.Exists(Path.Combine(c, "builds.json"))) return c;
            return null;
        }

        public static string Build(string home)
        {
            try
            {
                var j = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(home, "builds.json")));
                object b;
                if (j == null || !j.TryGetValue("builds", out b) || !(b is System.Collections.ArrayList)) return null;
                string first = null;
                foreach (var o in (System.Collections.ArrayList)b)
                {
                    var e = o as Dictionary<string, object>;
                    if (e == null || !(e.ContainsKey("folder") && e["folder"] is string)) continue;
                    string f = (string)e["folder"];
                    if (!Directory.Exists(f)) continue;
                    if (e.ContainsKey("default") && e["default"] is bool && (bool)e["default"]) return f;
                    if (first == null) first = f;
                }
                return first;
            }
            catch (Exception) { return null; }
        }

        public static string SaveRoot()
        {
            string h = Home();
            return h == null ? "" : Path.Combine(h, "user", "save");
        }

        public static string LogPath()
        {
            string h = Home(), b = h == null ? null : Build(h);
            return b == null ? "" : Path.Combine(b, "logs", "longshot_log.txt");
        }
    }

    public class AppSettings
    {
        // Longshot Launcher 1.2.0 keeps each version in its own folder (builds\stable\<version>), listed in its
        // builds.json. The defaults follow its default build (LongshotHome), and they're empty when no launcher
        // folder is found.
        public string SaveRoot = LongshotHome.SaveRoot();
        public string LogPath = LongshotHome.LogPath();
        public string LastSeed;
        public string Slot;
        public bool FollowPlayer = true;
        public bool ShowAll;                                        // if false, lists and map only show what's in logic
        public List<string> Tainted = new List<string>();          // seed|save paths whose spoiler was opened
        public Dictionary<string, List<string>> Manual = new Dictionary<string, List<string>>();  // seed -> check names
        // seed|save -> the highest count seen of each item ("#done" is the checks the save showed done then). The
        // logic keeps an item once it's found, so using the last bomb doesn't take the Bomb Bag out of logic.
        public Dictionary<string, Dictionary<string, int>> MaxSeen = new Dictionary<string, Dictionary<string, int>>();
        // the panels' sizes as the player left them, at 96 DPI (0 means the default)
        public int LeftW, RightW, EventsH;
        public double PlacesFrac;
        internal bool Frozen;  // a screenshot or timing run, so the player's settings are left alone

        static string FilePath
        {
            get
            {
                // keeps the tracker's first name, as the app's %APPDATA%\RemakeRandomizer does (Randomizer.cs DataFolder)
                string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "RemakeRandoTracker");
                Directory.CreateDirectory(d);
                return Path.Combine(d, "settings.json");
            }
        }

        public static AppSettings Load()
        {
            try { return new JavaScriptSerializer().Deserialize<AppSettings>(File.ReadAllText(FilePath)) ?? new AppSettings(); }
            catch (Exception) { return new AppSettings(); }
        }

        public void Save()
        {
            if (Frozen) return;
            try { File.WriteAllText(FilePath, new JavaScriptSerializer().Serialize(this)); } catch (Exception) { }
        }
    }

    class Note
    {
        public string Time, Text;
        public Color Dot;
        public int H = -1, ForW, ForDpi;  // its row height, measured for that width and DPI
    }


    public class MainForm : DpiForm
    {
        readonly AppSettings cfg = AppSettings.Load();
        SeedData seed;
        readonly SaveWatcher saves = new SaveWatcher();
        readonly LogWatcher log = new LogWatcher();
        readonly HeaderBar header = new HeaderBar();
        readonly Banner taint = new Banner();
        readonly StatusBar status = new StatusBar();
        readonly VirtualList places = new VirtualList { Back = Paper.Bg, RowHeight = 28 };
        readonly VirtualList checkList = new VirtualList { Back = Paper.Bg, RowHeight = 24 };
        readonly VirtualList events = new VirtualList { Back = Paper.Bg, RowHeight = 21 };
        readonly MapView mapView = new MapView();
        readonly CheckBoard board = new CheckBoard();
        readonly ChipStrip chips = new ChipStrip();
        readonly ItemGrid itemGrid = new ItemGrid();
        readonly PanelBox placesBox, checksBox, mapBox, eventsBox, itemsBox;
        readonly Timer timer = new Timer { Interval = 1000 };
        readonly MapStore store;
        readonly string dataDir;
        readonly MenuButton seedButton = new MenuButton { Text = "Seed" }, viewButton = new MenuButton { Text = "View" }, spoilerButton = new MenuButton { Text = "Spoiler" };
        ToolStripMenuItem followItem, slotItem, onlyLogicItem;
        readonly Segmented showWhich = new Segmented();
        readonly LogicClient logic;
        bool syncingShow;
        Place currentPlace;
        MapInfo currentMap;
        bool spoilerOpen;
        HashSet<string> haveItems = new HashSet<string>();
        string lastSavePath;
        public int ForceDpi;  // --dpi N for testing, lays out as if the screen had that scaling

        // the gaps between panels can be dragged (left column, right column, places/checks, map/events)
        Rectangle body, splitLeft, splitRight, splitPlaces, splitEvents;
        int dragSplit = -1, hoverSplit = -1;

        public MainForm(string seedPath, bool frozen)
        {
            cfg.Frozen = frozen;
            Text = "Rando of Time Tracker";
            Icon = AppIcon();
            dataDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "data");
            store = new MapStore(dataDir);
            header.Logo = Logo("RemakeUi.logo.png");
            placesBox = new PanelBox("Places", places);
            checksBox = new PanelBox("Checks here", checkList) { Sub = "Right-click a check to mark it by hand" };
            mapBox = new PanelBox("Map", mapView) { BodyOnPaper = false };
            mapBox.SetExtra(chips);
            eventsBox = new PanelBox("What happened", events);
            itemsBox = new PanelBox("Items", itemGrid);
            itemGrid.DataDir = dataDir;
            logic = new LogicClient(this);
            logic.Answer += LogicAnswered;
            logic.Changed += LogicChanged;
            LogicView.OnlyInLogic = !cfg.ShowAll;
            SetLogicalSize(1500, 900, 1000, 640);
            StartPosition = FormStartPosition.CenterScreen;
            BuildUi();
            saves.Root = cfg.SaveRoot; saves.Slot = cfg.Slot;
            log.PathName = cfg.LogPath;
            timer.Tick += (s, e) => Tick(false);
            string path = seedPath ?? cfg.LastSeed;
            if (path != null && File.Exists(path)) OpenSeed(path);
            else
            {
                ShowNoSeed();
                if (!frozen) Shown += (s, e) => ChooseSeed();
            }
            timer.Start();
        }

        // Parts
        void BuildUi()
        {
            var seedMenu = Menus.New();
            seedMenu.Items.Add("Open seed (tracker.json)...", null, (s, e) => ChooseSeed());
            seedMenu.Items.Add(new ToolStripSeparator());
            seedMenu.Items.Add("Save folder...", null, (s, e) => ChooseSaveRoot());
            seedMenu.Items.Add("Longshot log file...", null, (s, e) => ChooseLog());
            slotItem = new ToolStripMenuItem("Use only one slot...", null, (s, e) => ChooseSlot());
            seedMenu.Items.Add(slotItem);
            seedMenu.Items.Add(new ToolStripSeparator());
            seedMenu.Items.Add("Exit", null, (s, e) => Close());
            seedMenu.Opening += (s, e) => { slotItem.ShortcutKeyDisplayString = cfg.Slot ?? "newest save"; };
            seedButton.Menu = seedMenu;

            var viewMenu = Menus.New();
            followItem = new ToolStripMenuItem("Follow the player's map") { Checked = cfg.FollowPlayer, CheckOnClick = true };
            followItem.CheckedChanged += (s, e) => { cfg.FollowPlayer = followItem.Checked; cfg.Save(); };
            viewMenu.Items.Add(followItem);
            onlyLogicItem = new ToolStripMenuItem("Only the checks in logic") { Checked = !cfg.ShowAll, CheckOnClick = true };
            onlyLogicItem.CheckedChanged += (s, e) => { if (!syncingShow) SetShowAll(!onlyLogicItem.Checked); };
            viewMenu.Items.Add(onlyLogicItem);
            viewMenu.Items.Add("Re-read the save now", null, (s, e) => Tick(true));
            viewMenu.Items.Add(new ToolStripSeparator());
            viewMenu.Items.Add("Fit the map to its panel", null, (s, e) => mapView.FitNow());
            viewMenu.Items.Add("Panels back to their sizes", null, (s, e) => { cfg.LeftW = cfg.RightW = cfg.EventsH = 0; cfg.PlacesFrac = 0; cfg.Save(); PerformLayout(); });
            viewButton.Menu = viewMenu;

            var spoilerMenu = Menus.New();
            spoilerMenu.Items.Add("Show items (marks this run as spoiled)...", null, (s, e) => OpenSpoiler());
            spoilerButton.Menu = spoilerMenu;
            header.AddButton(seedButton); header.AddButton(viewButton); header.AddButton(spoilerButton);

            places.RowHeightOf = PlaceRowHeight;
            places.Selectable = i => places.Items[i] is Place;
            places.DrawRow = DrawPlace;
            places.SelectedIndexChanged += i => { var p = places.SelectedItem as Place; if (p != null) ShowPlace(p, false, null); };
            places.RowHover += (i, pt) =>
            {
                var pl = i >= 0 ? places.Items[i] as Place : null;
                if (pl == null)
                {
                    Tips.Hide();
                    return;
                }
                Tips.Show(PlaceTip(pl), places.PointToScreen(new Point(pt.X + Px(16), pt.Y + Px(18))), Dpi);
            };
            places.Scroll.OnPaper = true;
            // a resize (the spoiler line, a dragged divider) keeps the chosen place in view
            places.Resize += (s, e) =>
            {
                if (places.Selected < 0) return;
                var r = places.RowRect(places.Selected);
                if (r.Top < 0 || r.Bottom > places.Height)
                {
                    places.Scroll.ScrollTo(r.Top + places.Scroll.Offset, r.Bottom + places.Scroll.Offset);
                    places.Invalidate();
                }
            };

            // A check's name (and its item once the spoiler is open) wraps onto more lines instead of being cut.
            // "Water Temple Middle Water Level Pot 1..4" has to stay four different names on a narrow window.
            checkList.RowHeightOf = i =>
            {
                var o = checkList.Items[i];
                if (o is Head) return 26;
                if (o is MoreRow) return CheckRows.MoreHeight((MoreRow)o, checkList.Width - Px(4), Dpi);
                return CheckRowHeight((Check)o);
            };
            checkList.Selectable = i => checkList.Items[i] is Check;
            checkList.DrawRow = DrawCheck;
            checkList.Scroll.OnPaper = true;
            checkList.RowClick += (i, e) =>
            {
                if (checkList.Items[i] is MoreRow && e.Button == MouseButtons.Left)
                {
                    SetShowAll(true);
                    return;
                }
                var c = checkList.Items[i] as Check;
                if (c == null) return;
                if (e.Button == MouseButtons.Right) ToggleManual(c);
                else if (e.Button == MouseButtons.Left) FocusCheck(c);
            };
            checkList.RowHover += (i, p) =>
            {
                var c = i >= 0 ? checkList.Items[i] as Check : null;
                checkList.Cursor = i >= 0 && checkList.Items[i] is MoreRow ? Cursors.Hand : Cursors.Default;
                if (mapView.ListHover != c)
                {
                    mapView.ListHover = c;
                    mapView.Invalidate();
                }
                if (c == null)
                {
                    Tips.Hide();
                    return;
                }
                Tips.Show(CheckRows.Tip(c), checkList.PointToScreen(new Point(p.X + Px(16), p.Y + Px(18))), Dpi);
            };
            checkList.MouseLeave += (s, e) => { Tips.Hide(); if (mapView.ListHover != null) { mapView.ListHover = null; mapView.Invalidate(); } };
            checkList.MouseWheel += (s, e) => Tips.Hide();

            events.Selectable = i => false;
            events.DrawRow = DrawNote;
            events.Scroll.OnPaper = true;
            events.RowHeightOf = i => events.Items[i] is Note ? NoteRowHeight((Note)events.Items[i]) : 21;
            events.RowHover += (i, p) =>
            {
                var n = i >= 0 ? events.Items[i] as Note : null;
                if (n == null || NoteFits(n))
                {
                    Tips.Hide();
                    return;
                }
                Tips.Show(n.Time + "   " + n.Text, events.PointToScreen(new Point(p.X + Px(16), p.Y + Px(18))), Dpi);
            };
            events.MouseLeave += (s, e) => Tips.Hide();
            places.MouseLeave += (s, e) => Tips.Hide();

            chips.Picked += i =>
            {
                if (currentPlace == null || i >= currentPlace.Maps.Count) return;
                var m = currentPlace.Maps[i];
                ShowMap(m);
                // the list shows that floor's checks at its top
                int row = checkList.Items.FindIndex(o => o is Head && ((Head)o).Map == m);
                if (row >= 0)
                {
                    checkList.Scroll.Offset = checkList.RowRect(row).Top + checkList.Scroll.Offset;
                    checkList.Scroll.Clamp();
                    checkList.Invalidate();
                }
            };
            showWhich.Labels = new[] { "In logic", "All" };
            showWhich.TipsText = new[] { "Only the checks you can get now with the items you have (by this seed's logic)",
                                         "Every check here: those not in logic yet as hollow rings, the done ones ticked" };
            showWhich.Selected = cfg.ShowAll ? 1 : 0;
            showWhich.Visible = false;  // once the logic is known
            showWhich.Picked += i => SetShowAll(i == 1);
            checksBox.SetExtra(showWhich);
            board.MoreClick += m => SetShowAll(true);
            mapView.ManualToggle += ToggleManual;
            mapView.PinClick += c => SelectCheckRow(c);
            board.CheckClick += (c, b) =>
            {
                if (b == MouseButtons.Right) ToggleManual(c);
                else if (b == MouseButtons.Left) SelectCheckRow(c);
            };

            Controls.Add(header); Controls.Add(taint); Controls.Add(status);
            foreach (var b in new[] { placesBox, checksBox, mapBox, eventsBox, itemsBox }) Controls.Add(b);
            taint.Visible = false;
            FormClosing += (s, e) => { timer.Stop(); Tips.Hide(); logic.Changed -= LogicChanged; logic.Stop(); };
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            if (ForceDpi > 0 && ForceDpi != Dpi)
            {
                Dpi = ForceDpi;
                Font = Fonts.Get(Dpi, 10f);
                OnDpiApplied();
                PerformLayout();
                Invalidate(true);
            }
        }

        protected override void OnDpiApplied()
        {
            places.Measure(); checkList.Measure(); events.Measure();
            Tips.Hide();
        }

        // Layout
        protected override void OnLayout(LayoutEventArgs e)
        {
            if (placesBox == null || header == null)
            {
                base.OnLayout(e);
                return;
            }
            var c = ClientRectangle;
            if (c.Width < 50 || c.Height < 50)
            {
                base.OnLayout(e);
                return;
            }
            int W = c.Width, H = c.Height, gap = Px(6);
            int hh = header.HeightFor(W);
            header.SetBounds(0, 0, W, hh);
            int y = hh;
            int th = taint.Visible ? taint.HeightFor(W) : 0;
            taint.SetBounds(0, y, W, th);
            y += th;
            int sh = status.HeightFor(W);
            status.SetBounds(0, H - sh, W, sh);
            body = new Rectangle(gap, y + gap, W - 2 * gap, Math.Max(Px(200), H - sh - y - 2 * gap));
            splitLeft = splitRight = splitPlaces = splitEvents = Rectangle.Empty;
            if (body.Width >= Px(880)) LayoutWide(gap); else LayoutStacked(gap);
            base.OnLayout(e);
        }

        static int Clamp(int v, int lo, int hi) { return Math.Max(lo, Math.Min(Math.Max(lo, hi), v)); }

        void LayoutWide(int gap)
        {
            int minL = Px(230), minR = Px(210);
            int lw = Clamp(cfg.LeftW > 0 ? Px(cfg.LeftW) : Math.Max(Px(280), body.Width / 5), minL, Px(560));
            int rw = Clamp(cfg.RightW > 0 ? Px(cfg.RightW) : Math.Max(Px(270), body.Width * 19 / 100), minR, Px(560));
            int minC = Math.Max(Px(380), body.Width * 2 / 5);
            int over = lw + rw + 2 * gap + minC - body.Width;
            if (over > 0)
            {
                int canL = lw - minL, canR = rw - minR;
                int takeL = Math.Min(canL, over * canL / Math.Max(1, canL + canR));
                lw -= takeL; over -= takeL;
                int takeR = Math.Min(canR, over);
                rw -= takeR;
            }
            int cx = body.X + lw + gap, cw = body.Width - lw - rw - 2 * gap;
            double pf = cfg.PlacesFrac > 0.1 && cfg.PlacesFrac < 0.9 ? cfg.PlacesFrac : 0.47;
            int ph = Clamp((int)((body.Height - gap) * pf), Px(150), body.Height - gap - Px(150));
            placesBox.SetBounds(body.X, body.Y, lw, ph);
            checksBox.SetBounds(body.X, body.Y + ph + gap, lw, body.Height - ph - gap);
            int eh = Clamp(cfg.EventsH > 0 ? Px(cfg.EventsH) : Math.Max(Px(150), body.Height / 5), Px(100), body.Height / 2);
            mapBox.SetBounds(cx, body.Y, cw, body.Height - eh - gap);
            eventsBox.SetBounds(cx, body.Bottom - eh, cw, eh);
            itemGrid.PreferCell = 0;
            itemsBox.SetBounds(cx + cw + gap, body.Y, rw, body.Height);
            splitLeft = new Rectangle(body.X + lw, body.Y, gap, body.Height);
            splitRight = new Rectangle(cx + cw, body.Y, gap, body.Height);
            splitPlaces = new Rectangle(body.X, body.Y + ph, lw, gap);
            splitEvents = new Rectangle(cx, body.Bottom - eh - gap, cw, gap);
        }

        // a narrow window (a portrait screen) gets the map across the top, then the two lists side by side, the
        // items and the feed
        void LayoutStacked(int gap)
        {
            int W = body.Width, avail = body.Height - 3 * gap;
            int mapH = (int)(W * 0.74) + Px(84);
            int itemsH = itemGrid.HeightFor(W - Px(14), 44) + Px(50);
            int listsH = Math.Max(Px(260), avail * 30 / 100);
            int evH = Px(150);
            int[] want = { mapH, listsH, itemsH, evH };
            int[] min = { Px(220), Px(150), Px(120), Px(90) };
            int total = want.Sum();
            if (total > avail)
            {
                // everything gives up the same share of what it has above its minimum
                int extra = want.Select((v, i) => v - min[i]).Sum();
                double keep = extra > 0 ? Math.Max(0, (double)(avail - min.Sum()) / extra) : 0;
                for (int i = 0; i < 4; i++) want[i] = min[i] + (int)((want[i] - min[i]) * keep);
            }
            else
            {
                // room to spare goes to the lists and the feed
                int spare = avail - total;
                want[1] += spare * 6 / 10;
                want[3] += spare - spare * 6 / 10;
            }
            int y = body.Y;
            mapBox.SetBounds(body.X, y, W, want[0]); y += want[0] + gap;
            int half = (W - gap) / 2;
            placesBox.SetBounds(body.X, y, half, want[1]);
            checksBox.SetBounds(body.X + half + gap, y, W - half - gap, want[1]); y += want[1] + gap;
            itemGrid.PreferCell = 0;
            itemsBox.SetBounds(body.X, y, W, want[2]); y += want[2] + gap;
            eventsBox.SetBounds(body.X, y, W, Math.Max(Px(60), body.Bottom - y));
        }

        int SplitAt(Point p)
        {
            var all = new[] { splitLeft, splitRight, splitPlaces, splitEvents };
            for (int i = 0; i < all.Length; i++)
                if (!all[i].IsEmpty && Rectangle.Inflate(all[i], Px(2), Px(2)).Contains(p)) return i;
            return -1;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (dragSplit >= 0)
            {
                int gap = Px(6);
                float k = 96f / Dpi;
                if (dragSplit == 0) cfg.LeftW = (int)((e.X - body.X - gap / 2) * k);
                else if (dragSplit == 1) cfg.RightW = (int)((body.Right - e.X - gap / 2) * k);
                else if (dragSplit == 2) cfg.PlacesFrac = Math.Max(0.12, Math.Min(0.88, (e.Y - body.Y - gap / 2) / (double)Math.Max(1, body.Height - gap)));
                else cfg.EventsH = (int)((body.Bottom - e.Y - gap / 2) * k);
                PerformLayout();
                Update();
                return;
            }
            int h = SplitAt(e.Location);
            Cursor = h == 0 || h == 1 ? Cursors.VSplit : h >= 2 ? Cursors.HSplit : Cursors.Default;
            if (h != hoverSplit)
            {
                hoverSplit = h;
                Invalidate();
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            int h = SplitAt(e.Location);
            if (h >= 0 && e.Button == MouseButtons.Left)
            {
                dragSplit = h;
                Capture = true;
            }
            base.OnMouseDown(e);
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (dragSplit >= 0)
            {
                dragSplit = -1; Capture = false;
                // keep what the layout allowed (a drag past a limit stays at the limit)
                float k = 96f / Dpi;
                if (!splitLeft.IsEmpty) cfg.LeftW = (int)(placesBox.Width * k);
                if (!splitRight.IsEmpty) cfg.RightW = (int)(itemsBox.Width * k);
                if (!splitEvents.IsEmpty) cfg.EventsH = (int)(eventsBox.Height * k);
                cfg.Save();
            }
            base.OnMouseUp(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            if (hoverSplit >= 0 && dragSplit < 0)
            {
                hoverSplit = -1;
                Invalidate();
            }
            base.OnMouseLeave(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            int h = dragSplit >= 0 ? dragSplit : hoverSplit;
            var all = new[] { splitLeft, splitRight, splitPlaces, splitEvents };
            if (h >= 0 && h < all.Length && !all[h].IsEmpty)
            {
                var r = all[h];
                using (var b = new SolidBrush(Pal.GoldDim))
                {
                    if (h <= 1) e.Graphics.FillRectangle(b, r.X + r.Width / 2 - Px(1), r.Y + Px(8), Math.Max(2, Px(2)), r.Height - Px(16));
                    else e.Graphics.FillRectangle(b, r.X + Px(8), r.Y + r.Height / 2 - Px(1), r.Width - Px(16), Math.Max(2, Px(2)));
                }
            }
        }

        // Rows
        // one font for a place's name whether it's chosen or not (the gold row shows which), so the row's height
        // never changes on a click
        Font PlaceFont { get { return Fonts.Get(Dpi, 10.5f, FontStyle.Regular, Fonts.Serif); } }
        Font CountFont { get { return Fonts.Get(Dpi, 9f); } }
        Font SectionFont { get { return Fonts.Get(Dpi, 9.5f, FontStyle.Bold, Fonts.Serif); } }

        string PlaceCount(Place p) { return p.Done + "/" + p.All; }

        // A place's row, right to left: room for the scroll bar, the count (right-aligned in one column as wide as the
        // widest count), the badge column, then the name, which wraps instead of being cut. Every badge is as wide as
        // the biggest number's, and a done place's tick sits in that column too. Columns are measured once per change
        // (Measure()).
        int placeCountW, placeBadgeW;

        void PlaceColumns()
        {
            var cf = CountFont;
            placeCountW = 0;
            int most = 0;
            if (seed != null)
                foreach (var p in seed.Places)
                {
                    placeCountW = Math.Max(placeCountW, Measure.Text(PlaceCount(p), cf).Width);
                    most = Math.Max(most, p.Avail);
                }
            placeBadgeW = LogicView.On ? LogicView.BadgeWidth(most, Dpi) : 0;
        }

        int PlaceColW { get { return Math.Max(placeBadgeW, Px(16)); } }

        // where the badge column starts in a row of width rowW (the name ends a gap before it)
        int PlaceColX(int rowW) { return rowW - Px(16) - placeCountW - Px(10) - PlaceColW; }

        int PlaceNameWidth(int rowW) { return PlaceColX(rowW) - Px(12) - Px(10); }

        string PlaceTip(Place p)
        {
            string s = p.Name + "\n";
            if (LogicView.On) s += p.Avail + " in logic now  ·  ";
            s += p.Done + " / " + p.All + " done";
            int locked = LogicView.On ? p.Checks.Count(LogicView.Locked) : 0;
            if (locked > 0) s += "\n" + locked + (locked == 1 ? " needs" : " need") + " items you haven't found yet";
            return s;
        }

        int PlaceRowHeight(int i)
        {
            if (i == 0) PlaceColumns();  // Measure() asks for every row from the first, so the columns are fresh
            var o = places.Items[i];
            if (!(o is Place)) return 30;
            var p = (Place)o;
            int w = PlaceNameWidth(places.Width);
            if (Measure.Text(p.Name, PlaceFont).Width <= w) return 30;
            // a name too long for its row wraps onto a second line (never cut)
            var ws = Measure.Wrapped(p.Name, PlaceFont, Math.Max(Px(40), w));
            return (int)Math.Ceiling(ws.Height * 96.0 / Dpi) + 12;
        }

        void DrawPlace(Graphics g, Rectangle r, int i, ItemState st)
        {
            var o = places.Items[i];
            if (o is string)
            {
                using (var b = new SolidBrush(Paper.Bg)) g.FillRectangle(b, r);
                var sf = SectionFont;
                var ts = Measure.Text((string)o, sf);
                var tr = new Rectangle(r.X + Px(10), r.Y + Px(4), ts.Width + Px(2), r.Height - Px(4));
                Gfx.Text(g, (string)o, sf, tr, Paper.Gold, Gfx.Left & ~TextFormatFlags.EndEllipsis);
                using (var pen = new Pen(Paper.Line, Math.Max(1f, Dpi / 96f)))
                    g.DrawLine(pen, tr.Right + Px(6), tr.Y + tr.Height / 2, r.Right - Px(14), tr.Y + tr.Height / 2);
                return;
            }
            var p = (Place)o;
            bool sel = st.Selected, all = p.All > 0 && p.Done == p.All;
            Color bg = sel ? Pal.Gold : st.Hover ? Paper.Hover : all ? Paper.Line : Paper.Bg;
            using (var b = new SolidBrush(bg)) g.FillRectangle(b, r);
            // the count, right-aligned in its column
            var cr = new Rectangle(r.Right - Px(16) - placeCountW, r.Y, placeCountW, r.Height);
            Gfx.Text(g, PlaceCount(p), CountFont, cr, sel ? Pal.GoldInk : Paper.InkDim, Gfx.Right & ~TextFormatFlags.EndEllipsis);
            // the badge column: the checks in logic now, or the tick of a place that's all done
            int colX = r.X + PlaceColX(r.Width), colW = PlaceColW;
            Gfx.Smooth(g);
            if (all)
            {
                int t = Px(14);
                Gfx.Tick(g, new RectangleF(colX + (colW - t) / 2f, r.Y + (r.Height - t) / 2f, t, t), sel ? Pal.GoldInk : Paper.Gold, Math.Max(1.5f, 1.8f * Dpi / 96f));
            }
            else if (LogicView.On && p.Avail > 0)
            {
                int bh = LogicView.BadgeHeight(Dpi);
                LogicView.DrawBadge(g, new Rectangle(colX + (colW - placeBadgeW) / 2, r.Y + (r.Height - bh) / 2, placeBadgeW, bh), p.Avail, Dpi);
            }
            // the name, centred on the row whether it takes one line or two, and fainter when nothing there is in
            // logic yet
            int w = PlaceNameWidth(r.Width);
            var f = PlaceFont;
            bool wrap = Measure.Text(p.Name, f).Width > w;
            int nh = wrap ? Measure.Wrapped(p.Name, f, Math.Max(Px(40), w)).Height : r.Height;
            var nr = new Rectangle(r.X + Px(12), r.Y + (r.Height - nh) / 2, w + Px(2), nh);
            bool idle = LogicView.On && p.Avail == 0;
            Gfx.Text(g, p.Name, f, nr, sel ? Pal.GoldInk : all || idle ? Paper.InkDim : Paper.Ink, wrap ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
            if (!all && p.Done > 0 && p.All > 0)
            {
                // how far along, as a thin gold line on a faint track along the row's foot
                int x0 = r.X + Px(12), w0 = cr.Right - x0, bh = Math.Max(2, Px(2)), by = r.Bottom - Px(4);
                int bw = Math.Max(bh * 2, (int)(w0 * (p.Done / (double)p.All)));
                using (var b = new SolidBrush(sel ? Pal.GoldDim : Paper.Line)) g.FillRectangle(b, x0, by, w0, bh);
                using (var b = new SolidBrush(sel ? Pal.GoldInk : Paper.Gold)) g.FillRectangle(b, x0, by, bw, bh);
            }
        }

        void DrawCheck(Graphics g, Rectangle r, int i, ItemState st)
        {
            var o = checkList.Items[i];
            var hd = o as Head;
            if (hd != null) CheckRows.DrawHead(g, r, hd, Dpi);
            else if (o is MoreRow) CheckRows.DrawMore(g, new Rectangle(r.X, r.Y, r.Width - Px(4), r.Height), (MoreRow)o, st.Hover, Dpi);
            else CheckRows.DrawCheck(g, new Rectangle(r.X, r.Y, r.Width - Px(4), r.Height), (Check)o, st.Selected, st.Hover, Dpi);
        }

        int CheckRowHeight(Check c)
        {
            int w = Math.Max(Px(40), checkList.Width - Px(4) - Px(28) - Px(10));
            var s = Measure.Wrapped(CheckRows.Text(c), Fonts.Get(Dpi, 9.5f), w);
            return Math.Max(24, (int)Math.Ceiling(s.Height * 96.0 / Dpi) + 8);
        }

        int NoteRowHeight(Note n)
        {
            if (n.H >= 0 && n.ForW == events.Width && n.ForDpi == Dpi) return n.H;
            n.ForW = events.Width; n.ForDpi = Dpi;
            int tw = Measure.Text(n.Time, Fonts.Get(Dpi, 8.5f)).Width;
            int w = Math.Max(Px(40), events.Width - Px(10) - tw - Px(22) - Px(12));
            var s = Measure.Wrapped(n.Text, Fonts.Get(Dpi, 9.5f), w);
            return n.H = Math.Max(21, (int)Math.Ceiling(s.Height * 96.0 / Dpi) + 6);
        }

        bool NoteFits(Note n)
        {
            int tw = Measure.Text(n.Time, Fonts.Get(Dpi, 8.5f)).Width;
            return Measure.Text(n.Text, Fonts.Get(Dpi, 9.5f)).Width <= events.Width - Px(10) - tw - Px(22) - Px(12);
        }

        void DrawNote(Graphics g, Rectangle r, int i, ItemState st)
        {
            var n = (Note)events.Items[i];
            using (var b = new SolidBrush(st.Hover ? Paper.Hover : Paper.Bg)) g.FillRectangle(b, r);
            var tf = Fonts.Get(Dpi, 8.5f);
            var ts = Measure.Text(n.Time, tf);
            Gfx.Text(g, n.Time, tf, new Rectangle(r.X + Px(10), r.Y, ts.Width + Px(2), r.Height), Paper.InkFaint, Gfx.Left & ~TextFormatFlags.EndEllipsis);
            Gfx.Smooth(g);
            float d = Px(7);
            int x = r.X + Px(10) + ts.Width + Px(8);
            using (var b = new SolidBrush(n.Dot)) g.FillEllipse(b, x, r.Y + (r.Height - d) / 2f, d, d);
            var nf = Fonts.Get(Dpi, 9.5f);
            int nw = r.Right - x - Px(14) - Px(12);
            int nh = Measure.Wrapped(n.Text, nf, Math.Max(Px(40), nw)).Height;
            Gfx.Text(g, n.Text, nf, new Rectangle(x + Px(14), r.Y + (r.Height - nh) / 2, nw, nh), Paper.Ink, Gfx.Wrap);
        }

        // Seed
        void ChooseSeed()
        {
            using (var d = new OpenFileDialog { Title = "Open the seed's tracker.json (next to its patch)", Filter = "Tracker seed (tracker.json)|tracker.json;*.json" })
                if (d.ShowDialog(this) == DialogResult.OK) OpenSeed(d.FileName);
        }

        void ChooseSaveRoot()
        {
            using (var d = new FolderBrowserDialog { Description = "The folder holding slot_NN\\progress.sav (Longshot: LongshotLauncher-data\\user\\save; emulators: the game's save folder)", SelectedPath = cfg.SaveRoot })
                if (d.ShowDialog(this) == DialogResult.OK)
                {
                    cfg.SaveRoot = saves.Root = d.SelectedPath;
                    cfg.Save();
                    Tick(true);
                }
        }

        void ChooseLog()
        {
            // Longshot Launcher 1.2.0 keeps each version in its own folder (builds\stable\<version>), so start in the
            // log's folder (the one saved, else the launcher's default build's, LongshotHome).
            string dir = null;
            foreach (var p in new[] { cfg.LogPath, LongshotHome.LogPath() })
                if (!string.IsNullOrEmpty(p) && Directory.Exists(Path.GetDirectoryName(p)))
                {
                    dir = Path.GetDirectoryName(p);
                    break;
                }
            using (var d = new OpenFileDialog { Title = "Longshot's log (logs\\longshot_log.txt in the game's build folder): optional, for the live map",
                                                Filter = "Log|*.txt|All|*.*", InitialDirectory = dir ?? "" })
                if (d.ShowDialog(this) == DialogResult.OK)
                {
                    cfg.LogPath = log.PathName = d.FileName;
                    cfg.Save();
                }
        }

        void ChooseSlot()
        {
            var found = new List<string> { "" };
            try
            {
                if (!string.IsNullOrEmpty(cfg.SaveRoot) && Directory.Exists(cfg.SaveRoot))
                    found.AddRange(Directory.GetFiles(cfg.SaveRoot, "progress.sav", SearchOption.AllDirectories)
                        .Select(f => Path.GetFileName(Path.GetDirectoryName(f))).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(x => x).Take(12));
            }
            catch (Exception) { }
            string ans = AskDialog.AskText(this, "Save slot", "Track one save slot only (e.g. slot_03), or leave it empty for the newest save of any slot.",
                                           cfg.Slot ?? "", "Empty: the newest save", found);
            if (ans == null) return;
            cfg.Slot = saves.Slot = string.IsNullOrWhiteSpace(ans) ? null : ans.Trim();
            cfg.Save();
            Tick(true);
        }

        void ShowNoSeed()
        {
            header.SetText("No seed open", "", 0);
            mapView.EmptyText = "Open a seed's tracker.json (Seed, then Open seed): the randomizer writes it next to the seed's patch.";
            mapView.Show(null, null, null, 1);
            UpdateStatus();
        }

        void OpenSeed(string path)
        {
            SeedData s;
            try { s = SeedData.Load(path); }
            catch (Exception e)
            {
                AskDialog.Tell(this, "Couldn't open the seed", "Couldn't read " + path + ":\n" + e.Message);
                return;
            }
            seed = s;
            cfg.LastSeed = path; cfg.Save();
            List<string> man;
            if (cfg.Manual.TryGetValue(seed.Seed, out man))
                foreach (var c in seed.Checks) c.Manual = man.Contains(c.Name);
            spoilerOpen = false;
            foreach (var c in seed.Checks)
            {
                c.Item = null;
                c.Reach = true;
            }
            LogicView.On = false;
            seed.Recount();
            logic.Start(seed.Folder);
            currentPlace = null; currentMap = null;
            var rows = new List<object>();
            string section = null;
            foreach (var p in seed.Places)
            {
                if (p.Section != section)
                {
                    section = p.Section;
                    rows.Add(section);
                }
                rows.Add(p);
            }
            places.SetItems(rows);
            itemGrid.SetItems(seed.Items);
            haveItems = new HashSet<string>();
            events.Items.Clear(); events.Measure(); events.Invalidate();
            Note("Opened " + seed.Title + " (" + seed.Checks.Count + " checks)", Pal.GoldDim);
            UpdateTaint();
            var first = seed.Places.FirstOrDefault();
            if (first != null) ShowPlace(first, true, null);
            Tick(true);
            AskLogic();
            UpdateHeadings();
        }

        // Logic
        // Sends the save's done checks and items to the logic server, then applies what it says is reachable.
        void AskLogic()
        {
            if (seed == null || logic.State == LogicClient.Phase.Off || logic.State == LogicClient.Phase.Failed) return;
            var inv = new Dictionary<string, int>();
            var seen = SeenCounts(false);
            foreach (var it in seed.Items)
            {
                if (it.Name == null) continue;
                int m;
                int n = Math.Max(it.Count, seen != null && seen.TryGetValue(it.Name, out m) ? m : 0);
                if (n > 0) inv[it.Name] = n;
            }
            logic.Ask(seed.Checks.Where(LogicView.IsDone).Select(c => c.Name), inv);
        }

        Dictionary<string, int> SeenCounts(bool make)
        {
            if (seed == null) return null;
            Dictionary<string, int> seen;
            if (!cfg.MaxSeen.TryGetValue(TaintKey(), out seen) && make) cfg.MaxSeen[TaintKey()] = seen = new Dictionary<string, int>();
            return seen;
        }

        // the highest count of each item this save has shown. A save with fewer checks done than before is a new
        // file.
        void RememberCounts()
        {
            var seen = SeenCounts(true);
            int done = seed.Checks.Count(c => c.Done), last;
            bool changed = false;
            if (seen.TryGetValue("#done", out last) && done < last)
            {
                seen.Clear();
                changed = true;
            }
            if (!seen.TryGetValue("#done", out last) || last != done)
            {
                seen["#done"] = done;
                changed = true;
            }
            foreach (var it in seed.Items)
            {
                int m;
                if (it.Name != null && it.Count > (seen.TryGetValue(it.Name, out m) ? m : 0))
                {
                    seen[it.Name] = it.Count;
                    changed = true;
                }
            }
            if (changed) cfg.Save();
        }

        void LogicAnswered(HashSet<string> inLogic)
        {
            if (seed == null || IsDisposed) return;
            bool first = !seed.LogicOn;
            var newly = new List<Check>();
            foreach (var c in seed.Checks)
            {
                bool r = LogicView.IsDone(c) || inLogic.Contains(c.Name);
                if (!first && r && !c.Reach) newly.Add(c);
                c.Reach = r;
            }
            seed.LogicOn = true;
            LogicView.On = true;
            seed.Recount();
            if (first) Note("Logic ready: " + seed.Avail + " checks in logic now", LogicView.Green);
            else if (newly.Count > 0)
            {
                var ps = newly.Select(c => c.Place.Name).Distinct().ToList();
                Note("Now in logic: " + newly.Count + " more check" + (newly.Count == 1 ? "" : "s") + ", in " + string.Join(", ", ps.Take(3).ToArray())
                     + (ps.Count > 3 ? " and " + (ps.Count - 3) + " more place" + (ps.Count - 3 == 1 ? "" : "s") : ""), LogicView.Green);
            }
            places.Measure();  // a place's pill takes room from its name
            Refreshed(true);
            UpdateStatus();
        }

        void LogicChanged()
        {
            if (IsDisposed) return;
            if ((logic.State == LogicClient.Phase.Failed || logic.State == LogicClient.Phase.Off) && seed != null && seed.LogicOn)
            {
                // no logic any more, so every open check shows as open again (a stale answer would mislead)
                seed.LogicOn = false;
                LogicView.On = false;
                foreach (var c in seed.Checks) c.Reach = true;
                seed.Recount();
                places.Measure();
                Note("Logic stopped: every open check shows as open", Pal.Red);
                Refreshed(true);
            }
            UpdateStatus();
            UpdateHeadings();
        }

        void SetShowAll(bool all)
        {
            syncingShow = true;
            try
            {
                cfg.ShowAll = all;
                cfg.Save();
                LogicView.OnlyInLogic = !all;
                if (showWhich.Selected != (all ? 1 : 0))
                {
                    showWhich.Selected = all ? 1 : 0;
                    showWhich.Invalidate();
                }
                if (onlyLogicItem.Checked == all) onlyLogicItem.Checked = !all;
            }
            finally { syncingShow = false; }
            FillChecks(false);
            mapView.Invalidate();
            UpdateHeadings();
        }

        // the checks panel's choice (in logic now / all here) and its counts, once the logic is known
        void UpdateShowWhich()
        {
            bool on = seed != null && seed.LogicOn && currentPlace != null && currentPlace.All > 0;
            bool relayout = showWhich.Visible != on;
            showWhich.Visible = on;
            if (currentPlace != null)
                relayout |= showWhich.SetLabels("In logic (" + currentPlace.Avail + ")", "All (" + currentPlace.All + ")");
            if (relayout) checksBox.PerformLayout();
        }

        // State
        void Tick(bool force)
        {
            if (seed == null)
            {
                UpdateStatus();
                return;
            }
            bool moved = log.Poll();
            var save = saves.Poll(force);
            if (save != null) ApplySave(save);
            if (saves.CurrentPath != lastSavePath)
            {
                lastSavePath = saves.CurrentPath;
                UpdateTaint();
            }
            if (moved && log.Level != null)
            {
                string mapId;
                MapInfo m = null;
                if (seed.LevelMap.TryGetValue(log.Level, out mapId)) seed.MapById.TryGetValue(mapId, out m);
                Note("Entered " + (m != null ? m.Area : log.Level) + " as " + (log.Age ?? "?"), Color.FromArgb(80, 130, 200));
                if (cfg.FollowPlayer && m != null) ShowPlace(m.Place, true, m);
            }
            UpdateHeadings();
            UpdateStatus();
        }

        void UpdateStatus()
        {
            var parts = new List<StatusBar.Part>();
            if (seed == null)
            {
                // nothing read yet (the save is read once a seed is open)
                parts.Add(new StatusBar.Part { Text = "No seed open", Colour = Pal.Text });
                parts.Add(new StatusBar.Part { Text = "Saves from " + cfg.SaveRoot, Colour = Pal.TextDim });
                status.SetParts(parts);
                return;
            }
            if (saves.CurrentPath != null)
            {
                string slot = Path.GetFileName(Path.GetDirectoryName(saves.CurrentPath));
                string when = "";
                try { when = File.GetLastWriteTime(saves.CurrentPath).ToString("HH:mm:ss"); } catch (Exception) { }
                parts.Add(new StatusBar.Part { Text = "Save: " + slot + (when != "" ? "  (written " + when + ")" : ""), Tip = saves.CurrentPath, Colour = Pal.Text });
            }
            else parts.Add(new StatusBar.Part { Text = "No save found in " + cfg.SaveRoot, Colour = Pal.TextDim, Tip = "Seed, then Save folder: where the game keeps slot_NN\\progress.sav" });
            if (cfg.Slot != null) parts.Add(new StatusBar.Part { Text = "Only " + cfg.Slot, Colour = Pal.TextDim });
            if (log.GameRunning) parts.Add(new StatusBar.Part { Text = "Game running", Colour = Pal.Green });
            if (!double.IsNaN(log.Hearts)) parts.Add(new StatusBar.Part { Text = "Hearts " + log.Hearts + "/" + log.MaxHearts, Colour = Pal.Text });
            if (log.Skulltulas >= 0) parts.Add(new StatusBar.Part { Text = "Skulltulas " + log.Skulltulas, Colour = Pal.Text });
            switch (logic.State)
            {
                case LogicClient.Phase.Starting:
                    parts.Add(new StatusBar.Part { Text = "Logic: reading the seed...", Colour = Pal.TextDim, Tip = "The randomizer is loading this seed's rules (once, a few seconds)." });
                    break;
                case LogicClient.Phase.Ready:
                case LogicClient.Phase.Working:
                    bool slow = logic.State == LogicClient.Phase.Working && (DateTime.Now - logic.SentAt).TotalMilliseconds > 700;
                    parts.Add(new StatusBar.Part
                    {
                        Text = slow || !seed.LogicOn ? "Logic: updating..." : "Logic up to date", Colour = slow || !seed.LogicOn ? Pal.TextDim : Pal.Green,
                        Tip = "In logic: the checks you can reach with the items you have, by this seed's settings and tricks (the randomizer's own rules)."
                              + (logic.AnsweredAt > DateTime.MinValue ? "\nUpdated " + logic.AnsweredAt.ToString("HH:mm:ss") + " (" + Math.Round(logic.LastMs) + " ms)." : "")
                    });
                    break;
                case LogicClient.Phase.Failed:
                    parts.Add(new StatusBar.Part { Text = "Logic off", Colour = Pal.Red, Tip = logic.Why + "\nEvery open check shows as open." });
                    break;
                default:
                    if (logic.Why.Length > 0) parts.Add(new StatusBar.Part { Text = "Logic off", Colour = Pal.TextDim, Tip = logic.Why + "\nEvery open check shows as open." });
                    break;
            }
            if (spoilerOpen) parts.Add(new StatusBar.Part { Text = "Spoiler open", Colour = Pal.Red });
            status.SetParts(parts);
        }

        void UpdateHeadings()
        {
            if (seed == null) return;
            int all = seed.Checks.Count;
            float fd = all == 0 ? 0 : seed.Done / (float)all, fa = all == 0 ? 0 : (seed.Done + seed.Avail) / (float)all;
            if (seed.LogicOn) header.SetText(seed.Title, seed.Done + " / " + all + " done  \u00B7  " + seed.Avail + " in logic", fd, fa);
            else header.SetText(seed.Title, seed.Done + " / " + all + " checks", fd);
            int placesDone = seed.Places.Count(p => p.All > 0 && p.Done == p.All);
            placesBox.SetHeading("Places", placesDone + " / " + seed.Places.Count + " done", "");
            if (currentPlace != null)
            {
                string hint = !seed.LogicOn ? "Right-click a check to mark it by hand"
                            : LogicView.OnlyInLogic ? "What you can get now with your items. Right-click marks a check by hand."
                            : "Hollow rings need items you haven't found yet. Right-click marks a check by hand.";
                checksBox.SetHeading("Checks here", currentPlace.Done + " / " + currentPlace.All + " done", hint);
                mapBox.SetHeading(currentPlace.Name, (seed.LogicOn ? currentPlace.Avail + " in logic  \u00B7  " : "") + currentPlace.Done + " / " + currentPlace.All + " done",
                                  currentMap != null ? "Wheel: zoom  \u00B7  drag: move  \u00B7  double-click: fit  \u00B7  right-click: mark by hand"
                                  : currentPlace.Maps.Count == 0 ? "No spot on a map: gifts, songs, shops, scrubs, rooms without art. Right-click a check to mark it by hand." : "");
            }
            itemsBox.SetHeading("Items", itemGrid.Found + " / " + itemGrid.Total + " found", "");
            UpdateShowWhich();
        }

        void ApplySave(SaveFile save)
        {
            var newly = new List<Check>();
            foreach (var c in seed.Checks)
            {
                bool was = c.Done;
                c.Done = c.Flags.Count > 0 && c.Flags.Any(f => FlagSet(save, f));
                if (c.Done && !was) newly.Add(c);
            }
            foreach (var c in newly.Take(30)) Note("Checked: " + c.Name, Color.FromArgb(70, 150, 70));
            if (newly.Count > 30) Note("... and " + (newly.Count - 30) + " more checks", Color.FromArgb(70, 150, 70));
            var now = new HashSet<string>();
            foreach (var it in seed.Items)
            {
                int n = 0;
                if (it.Pouch != null) n = save.PouchCount(it.Pouch);
                if (n == 0 && it.Bool != null && save.Bool(it.Bool) == true) n = 1;
                it.Count = n;
                if (n > 0) now.Add(it.Name);
            }
            if (haveItems.Count > 0)
                foreach (var name in now.Where(x => !haveItems.Contains(x))) Note("Found: " + name, Paper.Gold);
            haveItems = now;
            RememberCounts();
            seed.Recount();
            Refreshed(newly.Count > 0);
            AskLogic();
        }

        // after the save or a mark changed. The counts were already made once (SeedData.Recount), the rows only
        // repaint.
        void Refreshed(bool reorder)
        {
            places.Measure();
            places.Invalidate();
            chips.Invalidate();
            itemGrid.Invalidate();
            mapView.Invalidate();
            if (reorder) FillChecks(false); else
            {
                checkList.Invalidate();
                board.Invalidate();
            }
            if (chips.Visible) mapBox.PerformLayout();
            UpdateHeadings();
        }

        static bool FlagSet(SaveFile s, Flag f)
        {
            switch (f.Type)
            {
                case "b64": return s.Bool64.Contains(f.Hash);
                case "bit": return s.BoolArray(f.Name, f.Index) == true;
                case "bool": return s.Bool(f.Name) == true;
                case "nbool": return s.Bool(f.Name) == false;  // done once it's false (a special deal's stock flag)
                case "count":  // a counter in saved flags, done once it's at least Index (the Mask Shop's slots)
                    {
                        if (f.Bits == null) return false;
                        int n = 0;
                        for (int k = 0; k < f.Bits.Count; k++) if (s.Bool(f.Bits[k]) == true) n |= 1 << k;
                        return n >= f.Index;
                    }
                default: return false;
            }
        }

        void ToggleManual(Check c)
        {
            if (seed == null) return;
            c.Manual = !c.Manual;
            List<string> man;
            if (!cfg.Manual.TryGetValue(seed.Seed, out man)) cfg.Manual[seed.Seed] = man = new List<string>();
            if (c.Manual) { if (!man.Contains(c.Name)) man.Add(c.Name); } else man.Remove(c.Name);
            cfg.Save();
            Note((c.Manual ? "Marked by hand: " : "Unmarked: ") + c.Name, Pal.GoldDim);
            seed.Recount();
            Refreshed(true);
            AskLogic();
        }

        public void SelectArea(string area)
        {
            if (seed == null) return;
            var p = seed.FindPlace(area);
            if (p != null) ShowPlace(p, true, seed.FindMap(area));
        }

        void ShowPlace(Place p, bool fromCode, MapInfo map)
        {
            if (p == null) return;
            bool changed = p != currentPlace;
            currentPlace = p;
            if (fromCode)
            {
                int i = places.Items.IndexOf(p);
                if (i >= 0 && places.Selected != i)
                {
                    places.Select(i, false);
                    // shown from the game or a menu, so the row goes in the middle of the list with its neighbours
                    // around it
                    var r = places.RowRect(i);
                    places.Scroll.Offset += r.Top - (places.Height - r.Height) / 2;
                    places.Scroll.Clamp();
                    int top = places.IndexAt(new Point(0, 0));  // a whole row at the top, not a sliver
                    if (top >= 0 && places.Scroll.Offset < places.Scroll.Max)
                    {
                        places.Scroll.Offset += places.RowRect(top).Top;
                        places.Scroll.Clamp();
                    }
                    places.Invalidate();
                }
            }
            chips.Maps.Clear();
            if (p.Maps.Count > 1) chips.Maps.AddRange(p.Maps);
            chips.Visible = p.Maps.Count > 1;
            var m = map != null && p.Maps.Contains(map) ? map : currentMap != null && p.Maps.Contains(currentMap) ? currentMap : p.Maps.FirstOrDefault();
            ShowMap(m);
            FillChecks(changed);
            UpdateHeadings();
            mapBox.PerformLayout();
        }

        void ShowMap(MapInfo m)
        {
            currentMap = m;
            chips.Selected = m == null || currentPlace == null ? -1 : currentPlace.Maps.IndexOf(m);
            chips.Invalidate();
            if (mapView.Highlight != null && mapView.Highlight.On != m) mapView.Highlight = null;
            if (m == null && currentPlace != null && currentPlace.Checks.Count > 0)
            {
                // no map, the place's checks fill the panel instead (gifts, songs, shops, scrubs, rooms without art)
                mapBox.SetBody(board, true);
                mapView.Show(null, null, null, 1);
                UpdateHeadings();
                return;
            }
            mapBox.SetBody(mapView, false);
            if (m == null)
            {
                mapView.EmptyText = "This place has no map art: its checks are listed on the left.";
                mapView.Show(null, null, null, 1);
                UpdateHeadings();
                return;
            }
            var art = store.Get(m.Image);
            if (art == null)
            {
                mapView.EmptyText = "This map's art isn't built yet. Open the tracker once from the randomizer: it builds the maps from your game files.";
                mapView.Show(null, null, null, 1);
                UpdateHeadings();
                return;
            }
            double k = art.Full.Width / (SeedData.NativeW * seed.MapScale);
            var pins = currentPlace.Checks.Where(c => c.On == m).ToList();
            mapView.Show(m, art, pins, k);
            UpdateHeadings();
        }

        // The place's checks: in logic first, then the ones not in logic yet, then the done ones. They go by floor
        // when a dungeon has several, and by kind for those without a spot. "In logic now" only lists the first
        // group, and a last row says what else is there and shows it all.
        void FillChecks(bool top)
        {
            var rows = new List<object>();
            if (currentPlace != null)
            {
                Func<Check, bool> isDone = LogicView.IsDone;
                Func<Check, int> rank = c => isDone(c) ? 2 : LogicView.Locked(c) ? 1 : 0;
                Func<Check, bool> shown = c => !LogicView.On || !LogicView.OnlyInLogic || rank(c) == 0;
                var byName = StringComparer.CurrentCultureIgnoreCase;
                if (currentPlace.Maps.Count > 1)
                {
                    foreach (var m in currentPlace.Maps)
                    {
                        var cs = currentPlace.Checks.Where(c => c.On == m && shown(c)).OrderBy(rank).ThenBy(c => c.Name, byName).ToList();
                        if (cs.Count == 0) continue;
                        rows.Add(new Head { Text = m.Chip ?? m.Title, Count = m.Done + "/" + m.All, Avail = m.Avail, Map = m });
                        rows.AddRange(cs);
                    }
                }
                else if (currentPlace.Maps.Count == 0)
                {
                    foreach (var g in currentPlace.Checks.GroupBy(c => Theme.Pretty(c.Kind)).OrderBy(g => g.Key))
                    {
                        var cs = g.Where(shown).OrderBy(rank).ThenBy(c => c.Name, byName).ToList();
                        if (cs.Count == 0) continue;
                        rows.Add(new Head { Text = g.Key, Count = g.Count(isDone) + "/" + g.Count(), Avail = g.Count(c => rank(c) == 0) });
                        rows.AddRange(cs);
                    }
                }
                else rows.AddRange(currentPlace.Checks.Where(shown).OrderBy(rank).ThenBy(c => c.Name, byName));
                var heads = rows.OfType<Head>().ToList();
                if (heads.Count > 0)
                {
                    int most = heads.Max(h => h.Avail);
                    string widest = heads.Select(h => h.Count ?? "").OrderByDescending(c => Measure.Text(c, Fonts.Get(Dpi, 9f)).Width).First();
                    foreach (var h in heads)
                    {
                        h.MaxAvail = most;
                        h.WidestCount = widest;
                    }
                }
                var more = MoreFor(currentPlace);
                if (more != null) rows.Add(more);
            }
            checkList.SetItems(rows, !top);
            if (currentPlace != null && currentPlace.Maps.Count == 0) board.SetRows(rows, !top);
        }

        // the rows "In logic now" hides, counted, and the click that shows them
        MoreRow MoreFor(Place p)
        {
            if (!LogicView.On || !LogicView.OnlyInLogic || p.All == 0) return null;
            int locked = p.Checks.Count(LogicView.Locked), done = p.Done;
            if (locked + done == 0) return null;
            string all = "Show all " + p.All + " check" + (p.All == 1 ? "" : "s") + " here";
            if (p.Avail == 0 && locked == 0) return new MoreRow { Text = "Every check here is done.", Action = all };
            string need = locked + (locked == 1 ? " check needs" : " checks need") + " items you haven't found yet";
            if (p.Avail == 0)
                return new MoreRow { Text = "Nothing here is in logic yet: " + need + "." + (done > 0 ? " " + done + " done." : ""), Action = all };
            var bits = new List<string>();
            if (locked > 0) bits.Add(locked + " not in logic yet");
            if (done > 0) bits.Add(done + " done");
            return new MoreRow { Text = "Also here: " + string.Join("  \u00B7  ", bits.ToArray()), Action = all };
        }

        void FocusCheck(Check c)
        {
            if (c.On != null && c.On != currentMap) ShowMap(c.On);
            mapView.Highlight = c;
            mapView.Reveal(c);
            mapView.Invalidate();
        }

        void SelectCheckRow(Check c)
        {
            int i = checkList.Items.IndexOf(c);
            if (i >= 0) checkList.Select(i, false);
        }

        void Note(string text, Color dot)
        {
            events.Items.Insert(0, new Note { Time = DateTime.Now.ToString("HH:mm:ss"), Text = text, Dot = dot });
            while (events.Items.Count > 500) events.Items.RemoveAt(events.Items.Count - 1);
            events.Measure();
            events.Invalidate();
        }

        // Spoiler
        string TaintKey() { return seed.Seed + "|" + (saves.CurrentPath ?? "no save"); }

        void UpdateTaint()
        {
            bool t = seed != null && cfg.Tainted.Contains(TaintKey());
            string text = t ? "Spoiler opened for this seed and save: this run is spoiled" : "";
            if (taint.Visible == t && taint.Text == text) return;
            taint.Text = text;
            taint.Visible = t;
            PerformLayout();
        }

        void OpenSpoiler()
        {
            if (seed == null) return;
            if (seed.SpoilerPath == null || !File.Exists(seed.SpoilerPath))
            {
                AskDialog.Tell(this, "No spoiler", "This seed has no spoiler file next to it.");
                return;
            }
            if (!spoilerOpen && !AskDialog.Confirm(this, "Open the spoiler", "Show every check's item?\n\nThis marks this seed and save as spoiled, for good.",
                                                   "Show the items", "Cancel", true)) return;
            ApplySpoiler();
        }

        public void ApplySpoiler()
        {
            if (seed == null) return;
            var items = seed.ReadSpoiler();
            foreach (var c in seed.Checks)
            {
                string it;
                c.Item = items.TryGetValue(c.Name, out it) ? it : null;
            }
            spoilerOpen = true;
            if (!cfg.Tainted.Contains(TaintKey()))
            {
                cfg.Tainted.Add(TaintKey());
                cfg.Save();
            }
            Note("Spoiler opened: this run is spoiled", Pal.Red);
            UpdateTaint();
            UpdateStatus();
            FillChecks(false);  // the rows now say each item (the board's columns follow)
            mapView.Invalidate();
        }

        // Tests
        /// <summary>For the screenshot mode. Shows a place (and floor) and draws the map in high quality right
        /// away.</summary>
        public void PrepareShot(string area)
        {
            if (logic.State != LogicClient.Phase.Off && logic.State != LogicClient.Phase.Failed) logic.WaitIdle(90000);
            if (area != null) SelectArea(area);
            PerformLayout();
            mapView.EnsureHighQuality();
            Update();
        }

        // screenshot mode extras (--hover CHECK, --menu NAME) that show what the mouse would
        public void TestHover(string check)
        {
            var c = seed == null ? null : seed.Checks.FirstOrDefault(x => string.Equals(x.Name, check, StringComparison.OrdinalIgnoreCase));
            if (c == null) return;
            if (c.Place != currentPlace) ShowPlace(c.Place, true, c.On);
            if (c.On != null && c.On != currentMap) ShowMap(c.On);
            SelectCheckRow(c);
            mapView.TestHover(c);
            Update();
        }

        public void TestShowAll(bool all) { cfg.Frozen = true; SetShowAll(all); }

        public ContextMenuStrip TestMenu(string name)
        {
            var b = name == "view" ? viewButton : name == "spoiler" ? spoilerButton : seedButton;
            b.Open();
            return b.Menu;
        }

        /// <summary>--bench FILE times the switch between places (cold with the map decoded, warm from the cache),
        /// panning and zooming, and the memory once ~20 maps were shown.</summary>
        public void Bench(string file)
        {
            var lines = new List<string>();
            var proc = Process.GetCurrentProcess();
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            proc.Refresh();
            lines.Add(string.Format("window {0}x{1} px, dpi {2}, map panel {3}x{4} px", Width, Height, Dpi, mapView.Width, mapView.Height));
            lines.Add(string.Format("start: working set {0:F1} MB, private {1:F1} MB, managed {2:F1} MB", proc.WorkingSet64 / 1048576.0, proc.PrivateMemorySize64 / 1048576.0, GC.GetTotalMemory(false) / 1048576.0));
            var maps = seed.Places.SelectMany(p => p.Maps).Take(20).ToList();
            var cold = new List<double>();
            var sw = new Stopwatch();
            foreach (var m in maps)
            {
                sw.Restart();
                ShowPlace(m.Place, true, m);
                mapView.EnsureHighQuality();
                checkList.Update(); places.Update();
                cold.Add(sw.Elapsed.TotalMilliseconds);
            }
            var warm = new List<double>();
            foreach (var m in maps.Skip(maps.Count - 5).Concat(maps.Skip(maps.Count - 5)))
            {
                sw.Restart();
                ShowPlace(m.Place, true, m);
                mapView.EnsureHighQuality();
                checkList.Update(); places.Update();
                warm.Add(sw.Elapsed.TotalMilliseconds);
            }
            lines.Add(string.Format("switch place, map decoded (cold), {0} maps: avg {1:F0} ms, max {2:F0} ms (high-quality render of the view: {3:F0} ms)", cold.Count, cold.Average(), cold.Max(), mapView.LastHqMs));
            lines.Add(string.Format("switch place, map cached (warm), {0} switches: avg {1:F0} ms, max {2:F0} ms", warm.Count, warm.Average(), warm.Max()));
            var pan = new List<double>();
            for (int i = 0; i < 20; i++)
            {
                mapView.PanBy(i % 2 == 0 ? Px(12) : -Px(12), Px(4) * (i % 3 - 1));
                mapView.Update();
                pan.Add(mapView.LastPaintMs);
            }
            lines.Add(string.Format("pan frame (fit zoom): avg {0:F1} ms, max {1:F1} ms", pan.Average(), pan.Max()));
            var wheel = new List<double>();
            for (int i = 0; i < 6; i++)
            {
                mapView.ZoomBy(1, new Point(mapView.Width / 2, mapView.Height / 2));
                mapView.Update();
                wheel.Add(mapView.LastPaintMs);
            }
            lines.Add(string.Format("wheel frame (quick draw while zooming in): avg {0:F1} ms, max {1:F1} ms", wheel.Average(), wheel.Max()));
            sw.Restart(); mapView.EnsureHighQuality();
            lines.Add(string.Format("high-quality redraw after the wheel stops (zoomed in): {0:F0} ms", sw.Elapsed.TotalMilliseconds));
            var pan2 = new List<double>();
            for (int i = 0; i < 20; i++)
            {
                mapView.PanBy(i % 2 == 0 ? Px(12) : -Px(12), 0);
                mapView.Update();
                pan2.Add(mapView.LastPaintMs);
            }
            lines.Add(string.Format("pan frame (zoomed in): avg {0:F1} ms, max {1:F1} ms", pan2.Average(), pan2.Max()));
            var tick = new List<double>();
            for (int i = 0; i < 5; i++)
            {
                sw.Restart();
                Tick(false);
                tick.Add(sw.Elapsed.TotalMilliseconds);
            }
            lines.Add(string.Format("1-second tick, save unchanged: avg {0:F1} ms", tick.Average()));
            sw.Restart(); Tick(true); Update();
            lines.Add(string.Format("re-read the save and repaint: {0:F0} ms", sw.Elapsed.TotalMilliseconds));
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            proc.Refresh();
            lines.Add(string.Format("after {0} maps shown ({1} decoded, {2} kept, {3:F1} MB of map pixels): working set {4:F1} MB, private {5:F1} MB, managed {6:F1} MB",
                maps.Count, store.Loads, store.Count, store.Bytes / 1048576.0, proc.WorkingSet64 / 1048576.0, proc.PrivateMemorySize64 / 1048576.0, GC.GetTotalMemory(false) / 1048576.0));
            File.WriteAllLines(file, lines);
        }
    }

    static class Program
    {
        // RandoOfTimeTracker.exe [tracker.json] [--save DIR] [--log FILE] [--screenshot FILE [AREA]]
        //   --screenshot: render the whole window to a PNG once the seed and its map are shown, and exit. AREA is a
        //   place, a map's title such as "Deku Tree B1", or a map id. Hidden test options: --size WxH (the window at
        //   96 DPI), --dpi N (lay out as at that scaling), --bench FILE (timings and memory). With --screenshot also
        //   --hover CHECK (the map's note on a check), --menu seed|view|spoiler, --dialog slot|spoiler, --spoiler
        //   (items shown, and the settings file is left alone in these runs), and --in-logic / --all (the checks
        //   panel's choice, the shot waits for the logic's first answer). --logic-server FILE: another logic server
        //   with the same protocol, a test stand-in.
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            int si = Array.IndexOf(args, "--screenshot");
            string shot = si >= 0 && si + 1 < args.Length ? args[si + 1] : null;
            string area = si >= 0 && si + 2 < args.Length && !args[si + 2].StartsWith("--") ? args[si + 2] : null;
            int bi = Array.IndexOf(args, "--bench");
            string bench = bi >= 0 && bi + 1 < args.Length ? args[bi + 1] : null;
            string seedArg = args.Length > 0 && !args[0].StartsWith("--") ? args[0] : null;
            // --save DIR / --log FILE (the randomizer app passes the chosen game's) are remembered for next time
            int sv = Array.IndexOf(args, "--save"), lg = Array.IndexOf(args, "--log");
            if ((sv >= 0 && sv + 1 < args.Length) || (lg >= 0 && lg + 1 < args.Length))
            {
                var s = AppSettings.Load();
                if (sv >= 0 && sv + 1 < args.Length) s.SaveRoot = args[sv + 1];
                if (lg >= 0 && lg + 1 < args.Length) s.LogPath = args[lg + 1];
                s.Save();
            }
            int ls = Array.IndexOf(args, "--logic-server");
            if (ls >= 0 && ls + 1 < args.Length) LogicClient.ServerScript = Path.GetFullPath(args[ls + 1]);
            bool test = shot != null || bench != null;
            var form = new MainForm(seedArg, test);
            int di = Array.IndexOf(args, "--dpi");
            if (di >= 0 && di + 1 < args.Length) form.ForceDpi = int.Parse(args[di + 1]);
            int zi = Array.IndexOf(args, "--size");
            if (zi >= 0 && zi + 1 < args.Length)
            {
                var wh = args[zi + 1].ToLowerInvariant().Split('x');
                int zw = int.Parse(wh[0]), zh = int.Parse(wh[1]);
                if (form.ForceDpi > 0)
                {
                    form.MinimumSize = new Size(1, 1);
                    form.Size = new Size(zw * form.ForceDpi / 96, zh * form.ForceDpi / 96);
                }
                else form.SetLogicalSize(zw, zh, Math.Min(zw, 1000), Math.Min(zh, 640));
            }
            if (shot != null || bench != null)
            {
                form.Shown += (s, e) =>
                {
                    var t = new Timer { Interval = 500 };
                    t.Tick += (s2, e2) =>
                    {
                        t.Stop();
                        if (bench != null) form.Bench(bench);
                        if (shot != null)
                        {
                            form.PrepareShot(area);
                            if (Array.IndexOf(args, "--all") >= 0) form.TestShowAll(true);
                            else if (Array.IndexOf(args, "--in-logic") >= 0) form.TestShowAll(false);
                            if (Array.IndexOf(args, "--spoiler") >= 0) form.ApplySpoiler();
                            int hi = Array.IndexOf(args, "--hover");
                            if (hi >= 0 && hi + 1 < args.Length) form.TestHover(args[hi + 1]);
                            Application.DoEvents();
                            using (var bmp = new Bitmap(form.Width, form.Height))
                            {
                                form.DrawToBitmap(bmp, new Rectangle(0, 0, form.Width, form.Height));
                                // a menu or a dialog over the window, where it would open
                                int mi = Array.IndexOf(args, "--menu"), dl = Array.IndexOf(args, "--dialog");
                                Control over = null;
                                Form dialog = null;
                                if (mi >= 0 && mi + 1 < args.Length) over = form.TestMenu(args[mi + 1]);
                                if (dl >= 0 && dl + 1 < args.Length)
                                {
                                    dialog = AskDialog.ForTest(args[dl + 1]);
                                    dialog.StartPosition = FormStartPosition.Manual;
                                    dialog.Show(form);
                                    dialog.Location = new Point(form.Left + (form.Width - dialog.Width) / 2, form.Top + (form.Height - dialog.Height) / 2);
                                    over = dialog;
                                }
                                if (over != null)
                                {
                                    Application.DoEvents();
                                    using (var ob = new Bitmap(over.Width, over.Height))
                                    using (var g = Graphics.FromImage(bmp))
                                    {
                                        over.DrawToBitmap(ob, new Rectangle(0, 0, over.Width, over.Height));
                                        var at = over.PointToScreen(Point.Empty);
                                        if (dialog != null) at = dialog.Location;
                                        g.DrawImage(ob, at.X - form.Left, at.Y - form.Top, over.Width, over.Height);
                                    }
                                    if (dialog != null) dialog.Close(); else ((ToolStripDropDown)over).Close();
                                }
                                bmp.Save(shot, System.Drawing.Imaging.ImageFormat.Png);
                            }
                        }
                        form.Close();
                    };
                    t.Start();
                };
            }
            Application.Run(form);
        }
    }
}
