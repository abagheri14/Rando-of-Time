// Desktop front end for building seeds, installing them in Longshot, exporting LayeredFS mods for Rekarina,
// Switch emulators and Atmosphere, and opening the tracker.
// SettingsView reads the supported settings from data/settings_schema.json (tools/release/export_schema.py).
// Seed generation and patching run through tools/rando/generate.py and tools/make_patch.py using python\python.exe
// or Python on PATH. The shared controls live in common/ui/Ui.cs.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using RemakeUi;

[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8")]
[assembly: System.Reflection.AssemblyTitle("Rando of Time")]
[assembly: System.Reflection.AssemblyProduct("Rando of Time")]
[assembly: System.Reflection.AssemblyVersion("0.8.1.0")]
[assembly: System.Reflection.AssemblyFileVersion("0.8.1.0")]
[assembly: System.Reflection.AssemblyInformationalVersion("0.8.1")]

namespace RandoOfTime
{
    class AppConfig
    {
        public string Target = "longshot";   // longshot | rekarina | sdcard | emulator
        // Rekarina's game folder (with Rekarina.exe) the first time, found in the usual places (RekarinaHint). Never a
        // fixed path, since that would be one PC's own folder.
        static string rekarinaHint;
        public static string RekarinaHint()
        {
            if (rekarinaHint != null) return rekarinaHint;
            var roots = new List<string> { Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                           Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                                           Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles) };
            try
            {
                foreach (var dr in DriveInfo.GetDrives())
                    if (dr.DriveType == DriveType.Fixed && dr.IsReady)
                    {
                        roots.Add(dr.RootDirectory.FullName);
                        roots.Add(Path.Combine(dr.RootDirectory.FullName, "Games"));
                    }
            }
            catch (Exception) { }
            rekarinaHint = "";
            foreach (var r in roots.Where(r => !string.IsNullOrEmpty(r)))
                foreach (var sub in new[] { Path.Combine("Rekarina", "game"), "Rekarina" })
                {
                    string d = Path.Combine(r, sub);
                    try { if (File.Exists(Path.Combine(d, "Rekarina.exe"))) return rekarinaHint = d; }
                    catch (Exception) { }
                }
            return rekarinaHint;
        }
        public string LongshotDir = "";      // Longshot's launcher folder (builds.json) or one game folder (LongshotGame)
        public string RekarinaDir = "";
        public string ModOut = "";   // older app.json files keep the SD-card folder here, SD falls back to it
        public string SdOut = "";
        public string EmuOut = "";
        public string Romfs = "";
        public string LastSettings;
        // how many seconds each step of making a seed took last time on this PC, which RunProgress uses as the
        // progress bar's weights
        public Dictionary<string, double> StepSeconds = new Dictionary<string, double>();

        static string FilePath { get { return Path.Combine(DataFolder(), "app.json"); } }

        // %APPDATA%\RemakeRandomizer. It keeps the randomizer's first name on purpose: settings saved before the rename
        // stay where they are, and the Microsoft Store Python can't see a folder made in AppData after it was installed.
        public static string DataFolder()
        {
            string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "RemakeRandomizer");
            Directory.CreateDirectory(d);
            return d;
        }

        public static AppConfig Load()
        {
            try { return new JavaScriptSerializer().Deserialize<AppConfig>(File.ReadAllText(FilePath)) ?? new AppConfig(); }
            catch (Exception) { return new AppConfig(); }
        }

        public void Save() { try { File.WriteAllText(FilePath, new JavaScriptSerializer().Serialize(this)); } catch (Exception) { } }
    }

    // Where Longshot's game is. Longshot Launcher 1.2.0 keeps each build in its own folder (builds\stable\v3.1.0,
    // older launchers used builds\rc) and lists them in <its folder>\builds.json: {"home", "builds": [{"folder",
    // "version", "channel", "default"}]}. The player picks either that launcher folder, and we use the default build
    // so a new version gets picked up by itself, or one game folder (romfs and bin inside). The launcher can be
    // portable, so there's no fixed place.
    class LongshotGame
    {
        public string Folder = "";  // the game folder (romfs, bin), "" when none was found
        public string Home;         // the launcher's folder (builds.json) above it, when there is one
        public string Version;      // the build's version (builds.json), when known
        public bool Picked;         // the folder picked is the game folder itself (or its romfs)
        public bool Default;        // the launcher's default build (else its newest stable one)
        public string Romfs { get { return Folder == "" ? "" : Path.Combine(Folder, "romfs"); } }
        public const string ModName = "Rando of Time";  // tools/install.py MOD_NAME: <game>\mods\<this>
        public string ModDir { get { return Folder == "" ? "" : Path.Combine(Folder, "mods", ModName); } }
        // The randomizer's name before the rename (tools/install.py OLD_MOD_NAMES, OLD_MOD_RECORDS). A seed installed
        // under it is still found, and installing or removing a seed takes that folder out too.
        public const string OldModName = "OoT Remake Randomizer", Record = "rando-of-time.json", OldRecord = "remake-rando.json";
        // the folder holding the installed seed: ModDir, else the one under the old name when only that one is there
        public string InstalledModDir
        {
            get
            {
                if (Folder == "") return "";
                string old = Path.Combine(Folder, "mods", OldModName);
                return !Directory.Exists(ModDir) && Directory.Exists(old) ? old : ModDir;
            }
        }
        public static string RecordIn(string modDir)
        {
            string now = Path.Combine(modDir, Record), old = Path.Combine(modDir, OldRecord);
            return !File.Exists(now) && File.Exists(old) ? old : now;
        }

        public static bool IsGame(string dir)
        {
            try { return !string.IsNullOrEmpty(dir) && Directory.Exists(Path.Combine(dir, "romfs", "Pack")); }
            catch (Exception) { return false; }
        }

        static bool IsHome(string dir)
        {
            try { return !string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, "builds.json")); }
            catch (Exception) { return false; }
        }

        // the launcher folder at or above `path`. A game folder is builds\<channel>\<version> under it, even one
        // that's gone.
        public static string HomeOf(string path)
        {
            try
            {
                string d = string.IsNullOrEmpty(path) ? null : Path.GetFullPath(path);
                for (int up = 0; d != null && up < 4; up++, d = Path.GetDirectoryName(d))
                    if (IsHome(d)) return d.TrimEnd('\\');
            }
            catch (Exception) { }
            return null;
        }

        static string Str(Dictionary<string, object> d, string k) { object v; return d.TryGetValue(k, out v) ? v as string : null; }

        static System.Version Ver(string v)
        {
            System.Version r;
            v = (v ?? "").TrimStart('v', 'V');
            int cut = v.IndexOfAny(new[] { '-', '+', ' ' });
            return System.Version.TryParse(cut > 0 ? v.Substring(0, cut) : v, out r) ? r : new System.Version(0, 0);
        }

        // builds.json's default build, else its newest stable one, else its newest. If builds.json can't be read, a
        // build folder found under builds\ instead.
        static LongshotGame FromHome(string home)
        {
            var found = new List<Tuple<string, string, string, bool, string>>();  // folder, version, channel, default, updated
            try
            {
                var top = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(Path.Combine(home, "builds.json"))) as Dictionary<string, object>;
                object list;
                string was = top != null ? Str(top, "home") : null;
                if (top != null && top.TryGetValue("builds", out list) && list is IEnumerable)
                    foreach (var o in (IEnumerable)list)
                    {
                        var b = o as Dictionary<string, object>;
                        string folder = b != null ? Str(b, "folder") : null;
                        if (string.IsNullOrEmpty(folder)) continue;
                        if (!Path.IsPathRooted(folder)) folder = Path.Combine(home, folder);
                        // a portable launcher folder that was moved, its builds moved with it
                        else if (!IsGame(folder) && !string.IsNullOrEmpty(was) && folder.StartsWith(was.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                            folder = home + folder.Substring(was.TrimEnd('\\').Length);
                        object def;
                        found.Add(Tuple.Create(folder, Str(b, "version"), Str(b, "channel"), b.TryGetValue("default", out def) && def is bool && (bool)def,
                                               Str(b, "updated") ?? Str(b, "created") ?? ""));
                    }
            }
            catch (Exception) { }
            if (!found.Any(f => IsGame(f.Item1)))
            {
                try
                {
                    string builds = Path.Combine(home, "builds");
                    if (Directory.Exists(builds))
                        foreach (var d in Directory.GetDirectories(builds).Concat(Directory.GetDirectories(builds).SelectMany(Directory.GetDirectories)))
                            if (IsGame(d))
                            {
                                string parent = Path.GetFileName(Path.GetDirectoryName(d));
                                found.Add(Tuple.Create(d, Path.GetFileName(d), parent == "builds" ? "" : parent, false, ""));
                            }
                }
                catch (Exception) { }
            }
            var pick = found.Where(f => IsGame(f.Item1))
                            .OrderByDescending(f => f.Item4)
                            .ThenByDescending(f => string.Equals(f.Item3, "stable", StringComparison.OrdinalIgnoreCase))
                            .ThenByDescending(f => Ver(f.Item2))
                            .ThenByDescending(f => f.Item5, StringComparer.Ordinal).FirstOrDefault();
            var g = new LongshotGame { Home = home };
            if (pick != null)
            {
                g.Folder = Path.GetFullPath(pick.Item1).TrimEnd('\\');
                g.Version = pick.Item2;
                g.Default = pick.Item4;
            }
            return g;
        }

        // the game for what the player picked. A game folder (or its romfs) is used as it is. A launcher folder, or a
        // game folder that's gone from under one (builds\rc after Launcher 1.2.0), goes through builds.json.
        public static LongshotGame Find(string picked)
        {
            string p = (picked ?? "").Trim().Trim('"').TrimEnd('\\', '/');
            if (p == "") return new LongshotGame();
            try { p = Path.GetFullPath(p.Length == 2 && p[1] == ':' ? p + "\\" : p).TrimEnd('\\'); }
            catch (Exception) { return new LongshotGame(); }
            if (string.Equals(Path.GetFileName(p), "romfs", StringComparison.OrdinalIgnoreCase) && IsGame(Path.GetDirectoryName(p)))
                p = Path.GetDirectoryName(p);
            if (IsGame(p)) return new LongshotGame { Folder = p, Picked = true, Home = HomeOf(p) };
            string home = HomeOf(p);  // the launcher folder itself, or one below it (builds, builds\stable, a gone build)
            return home != null ? FromHome(home) : new LongshotGame();
        }

        // For a saved folder that isn't a game any more (Launcher 1.2.0 moved builds\rc away) under a launcher folder
        // that has a game, this returns that launcher folder, used from then on. null means nothing to change.
        public static string Migrated(string saved)
        {
            string p = (saved ?? "").Trim().Trim('"').TrimEnd('\\', '/');
            try
            {
                if (p == "" || IsGame(p) || IsGame(Path.GetDirectoryName(p) ?? "") || IsHome(p)) return null;
                string home = HomeOf(p);
                return home != null && FromHome(home).Folder != "" ? home : null;
            }
            catch (Exception) { return null; }
        }

        // On the first run, a launcher folder in a usual place (its installed folder, or a portable one at a drive's
        // root or in your user folder), or "" and the box asks for one.
        static string hint;
        public static string Hint()
        {
            if (hint != null) return hint;
            var places = new List<string> { Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "LongshotLauncher"),
                                            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "LongshotLauncher-data") };
            try
            {
                foreach (var dr in DriveInfo.GetDrives())
                    if (dr.DriveType == DriveType.Fixed && dr.IsReady) places.Add(Path.Combine(dr.RootDirectory.FullName, "LongshotLauncher-data"));
            }
            catch (Exception) { }
            hint = places.FirstOrDefault(h => IsHome(h) && FromHome(h).Folder != "") ?? "";
            return hint;
        }

        // Longshot's Mods tab keeps its switches in mods.json ({"mods": [{"id": folder, "enabled": ...}]}). It's
        // <launcher folder>\user\mods.json for the builds the launcher starts, and <game folder>\mods.json when the
        // game is started by itself. Returns the list that has the randomizer's mod switched off, or null.
        public string SwitchedOff()
        {
            var lists = new List<string>();
            if (Home != null) lists.Add(Path.Combine(Home, "user", "mods.json"));
            if (Folder != "") lists.Add(Path.Combine(Folder, "mods.json"));
            foreach (var f in lists)
            {
                try
                {
                    if (!File.Exists(f)) continue;
                    var top = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(f)) as Dictionary<string, object>;
                    object mods;
                    if (top == null || !top.TryGetValue("mods", out mods) || !(mods is IEnumerable)) continue;
                    foreach (var o in (IEnumerable)mods)
                    {
                        var m = o as Dictionary<string, object>;
                        object on;
                        if (m != null && Str(m, "id") == ModName && m.TryGetValue("enabled", out on) && on is bool && !(bool)on) return f;
                    }
                }
                catch (Exception) { }
            }
            return null;
        }

        // the game folder the way the player reads it, relative to the launcher folder when it's under it
        // (builds\stable\v3.1.0)
        public string Short()
        {
            return Home != null && Folder.StartsWith(Home + "\\", StringComparison.OrdinalIgnoreCase) ? Folder.Substring(Home.Length + 1) : Folder;
        }
    }

    // Parts
    class HeaderBar : UiControl
    {
        public Image Logo;
        public string Title = "Rando of Time", Sub = "The Ocarina of Time remake randomizer. Every setting here is one the remake can make.";

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Bg);
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
            int s = Px(36), x = Px(16);
            if (Logo != null) g.DrawImage(Logo, new Rectangle(x, (Height - s) / 2, s, s));
            int tx = x + s + Px(12);
            var tf = F(17f, FontStyle.Bold, Fonts.Serif);
            var tr = new Rectangle(tx, 0, Width - tx, Height);
            Gfx.Text(g, Title, tf, tr, Pal.Gold, Gfx.Left);
            int tw = TextRenderer.MeasureText(g, Title, tf, tr.Size, Gfx.Left).Width;
            if (tx + tw + Px(24) < Width - Px(20))
                Gfx.Text(g, Sub, F(9.5f), new Rectangle(tx + tw + Px(18), Px(3), Width - tx - tw - Px(36), Height), Pal.TextDim, Gfx.Left);
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, 0, Height - 1, Width, Height - 1);
        }
    }

    // where the seed goes: four radio rows on the wood column
    class TargetList : UiControl
    {
        public static readonly string[][] Targets =
        {
            new[] { "longshot", "Longshot", "installs as a mod" },
            new[] { "rekarina", "Rekarina", "its mods folder" },
            new[] { "sdcard", "Switch console", "its SD card, Atmosphere" },
            new[] { "emulator", "Switch emulator", "the game's mod folder" },
        };
        public string Value = "longshot";
        public event Action Changed;
        int hover = -1;

        public TargetList() { Cursor = Cursors.Hand; TabStop = true; BackColor = Pal.Panel; }

        Rectangle Row(int i) { int h = Height / 4; return new Rectangle(0, i * h, Width, h); }

        int At(Point p) { for (int i = 0; i < 4; i++) if (Row(i).Contains(p)) return i; return -1; }

        protected override void OnMouseMove(MouseEventArgs e) { int h = At(e.Location); if (h != hover) { hover = h; Invalidate(); } base.OnMouseMove(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = -1; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            Focus();
            int i = At(e.Location);
            if (i >= 0) Pick(Targets[i][0]);
            base.OnMouseDown(e);
        }

        public void Pick(string v)
        {
            if (v == Value) return;
            Value = v;
            Invalidate();
            if (Changed != null) Changed();
        }

        protected override bool IsInputKey(Keys k) { return k == Keys.Up || k == Keys.Down || base.IsInputKey(k); }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            int i = Array.FindIndex(Targets, t => t[0] == Value);
            if (e.KeyCode == Keys.Down)
            {
                Pick(Targets[(i + 1) % 4][0]);
                e.Handled = true;
            }
            if (e.KeyCode == Keys.Up)
            {
                Pick(Targets[(i + 3) % 4][0]);
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            Gfx.Smooth(g);
            for (int i = 0; i < 4; i++)
            {
                var r = Row(i);
                bool sel = Targets[i][0] == Value;
                if (i == hover) Gfx.Fill(g, new Rectangle(r.X, r.Y + Px(1), r.Width, r.Height - Px(2)), Px(4), Pal.Hover);
                var dot = new RectangleF(r.X + Px(8), r.Y + (r.Height - Px(16)) / 2f, Px(16), Px(16));
                Gfx.Fill(g, dot, Px(8), Pal.Deep);
                Gfx.Stroke(g, dot, Px(8), sel ? Pal.Gold : Pal.GoldDim, Math.Max(1.5f, 1.6f * S));
                if (sel) Gfx.Fill(g, new RectangleF(dot.X + Px(4), dot.Y + Px(4), Px(8), Px(8)), Px(4), Pal.Gold);
                var tf = F(10f, sel ? FontStyle.Bold : FontStyle.Regular);
                var tr = new Rectangle(r.X + Px(32), r.Y, r.Width - Px(36), r.Height);
                Gfx.Text(g, Targets[i][1], tf, tr, sel ? Pal.GoldHi : Pal.Text, Gfx.Left);
                int tw = TextRenderer.MeasureText(g, Targets[i][1], tf, tr.Size, Gfx.Left).Width;
                Gfx.Text(g, "(" + Targets[i][2] + ")", F(9f), new Rectangle(tr.X + tw + Px(4), r.Y, tr.Right - tr.X - tw - Px(4), r.Height), Pal.TextDim, Gfx.Left);
                if (sel && Focused) Gfx.Stroke(g, new Rectangle(r.X, r.Y + Px(1), r.Width, r.Height - Px(2)), Px(4), Pal.GoldDim, 1f);
            }
        }
    }

    // The settings tabs across the top, like the old window had them (gold for the open one), each with its count
    // of changed settings. A name is never cut. The strip tries slightly smaller type and padding first, and if the
    // window is too narrow for one row it wraps the tabs onto a second row, like Windows' classic tab rows do.
    class TabStrip : UiControl
    {
        public readonly List<Page> Pages = new List<Page>();
        public int Selected;
        public Func<Page, int> Changed = p => 0;
        public event Action<int> Picked;
        int hover = -1;
        readonly List<Rectangle> tabs = new List<Rectangle>();
        float fontPt = 10.5f;

        static readonly float[][] Fits = { new[] { 10.5f, 26f }, new[] { 10f, 20f }, new[] { 9.5f, 16f }, new[] { 9f, 12f } };
        const int Gap = 3, RowH = 38;

        public TabStrip() { BackColor = Pal.Bg; Cursor = Cursors.Hand; }

        int TabWidth(Page p, float pt, float pad)
        {
            int w = TextRenderer.MeasureText(p.Title, F(pt, FontStyle.Bold, Fonts.Serif), new Size(4000, 200),
                                             TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix).Width + Px(pad);
            int n = Changed(p);
            if (n > 0) w += TextRenderer.MeasureText(n.ToString(), F(8.5f, FontStyle.Bold)).Width + Px(16);
            return w;
        }

        // lays the tabs out for `width` and returns how many rows it needs
        int Arrange(int width, List<Rectangle> into)
        {
            into.Clear();
            int gap = Px(Gap), rowH = Px(RowH);
            foreach (var fit in Fits)
            {
                var ws = Pages.Select(p => TabWidth(p, fit[0], fit[1])).ToList();
                if (ws.Sum() + gap * Math.Max(0, ws.Count - 1) <= width)
                {
                    fontPt = fit[0];
                    int x = 0;
                    foreach (int w in ws)
                    {
                        into.Add(new Rectangle(x, 0, w, rowH));
                        x += w + gap;
                    }
                    return 1;
                }
            }
            fontPt = Fits[1][0];
            int rows = 1, xx = 0;
            foreach (var p in Pages)
            {
                int w = Math.Min(width, TabWidth(p, Fits[1][0], Fits[1][1]));
                if (xx > 0 && xx + w > width)
                {
                    rows++;
                    xx = 0;
                }
                into.Add(new Rectangle(xx, (rows - 1) * (rowH + gap), w, rowH));
                xx += w + gap;
            }
            return rows;
        }

        public int HeightFor(int width)
        {
            int rows = Arrange(width, new List<Rectangle>());
            return rows * Px(RowH) + (rows - 1) * Px(Gap) + Px(2);
        }

        int At(Point p) { for (int i = 0; i < tabs.Count; i++) if (tabs[i].Contains(p)) return i; return -1; }

        protected override void OnMouseMove(MouseEventArgs e) { int h = At(e.Location); if (h != hover) { hover = h; Invalidate(); } base.OnMouseMove(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = -1; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            int i = At(e.Location);
            if (i >= 0 && Picked != null) Picked(i);
            base.OnMouseDown(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Bg);
            Gfx.Smooth(g);
            int rows = Arrange(Width, tabs);
            var f = F(fontPt, FontStyle.Bold, Fonts.Serif);
            int lastRowY = tabs.Count > 0 ? tabs.Max(t => t.Y) : 0;
            for (int i = 0; i < tabs.Count; i++)
            {
                var r = tabs[i];
                bool sel = i == Selected;
                bool bottomRow = r.Y == lastRowY;
                // the bottom row's tabs run into the page (square bottoms), upper rows are whole
                var shape = new RectangleF(r.X, r.Y, r.Width, bottomRow ? r.Height + Px(6) : r.Height);
                Gfx.Fill(g, shape, Px(5), sel ? Pal.Gold : i == hover ? Pal.Hover : Pal.Panel);
                if (!sel) Gfx.Stroke(g, shape, Px(5), Pal.Border, 1f);
                int n = Changed(Pages[i]);
                int right = r.Right - Px(8);
                if (n > 0)
                {
                    var bf = F(8.5f, FontStyle.Bold);
                    string t = n.ToString();
                    int bw = Math.Max(Px(18), TextRenderer.MeasureText(g, t, bf).Width + Px(6));
                    var br = new Rectangle(right - bw, r.Y + (r.Height - Px(18)) / 2, bw, Px(18));
                    Gfx.Fill(g, br, Px(9), sel ? Pal.GoldInk : Pal.GoldDim);
                    Gfx.Text(g, t, bf, br, sel ? Pal.Gold : Pal.GoldInk, Gfx.Center);
                    right = br.Left - Px(4);
                }
                var tr = new Rectangle(r.X, r.Y, right - r.X + (n > 0 ? 0 : Px(8)), r.Height);
                if (n > 0) tr = new Rectangle(r.X + Px(4), r.Y, right - r.X - Px(4), r.Height);
                Gfx.Text(g, Pages[i].Title, f, tr, sel ? Pal.GoldInk : Pal.Text, n > 0 ? Gfx.Center : Gfx.Center);
            }
            using (var b = new SolidBrush(Pal.Gold)) g.FillRectangle(b, 0, Height - Px(2), Width, Px(2));
        }
    }

    // the left column: where the seed goes, the game files, the seed, settings files, and the two big buttons
    class LeftPanel : UiControl
    {
        public readonly TargetList Targets = new TargetList();
        public readonly TextField PathBox = new TextField { Cue = "Pick a folder", FontPt = 9.5f };
        public readonly TextField RomfsBox = new TextField { Cue = "Empty: Longshot's copy", FontPt = 9.5f };
        public readonly FlatButton Browse = new FlatButton { Text = "Browse...", FontPt = 9.5f };
        public readonly FlatButton Browse2 = new FlatButton { Text = "Browse...", FontPt = 9.5f };
        // undoes the seed where it went, so Longshot's original files come back or the seed's mod files go
        // (MainWindow.Restore)
        public readonly FlatButton Restore = new FlatButton { Text = "Restore the original game", FontPt = 9.5f };
        public readonly TextField Seed = new TextField { FontPt = 12f, Cue = "Seed", FontFamily = Fonts.Serif, FontStyle = FontStyle.Bold };
        public readonly FlatButton Dice = new FlatButton { Text = "New", FontPt = 9.5f };
        public readonly FlatButton Load = new FlatButton { Text = "Load settings", FontPt = 9.5f };
        public readonly FlatButton Save = new FlatButton { Text = "Save settings", FontPt = 9.5f };
        public readonly FlatButton Reset = new FlatButton { Text = "Defaults", FontPt = 9.5f };
        public readonly FlatButton Tracker = new FlatButton { Text = "Open the tracker" };
        public readonly ProgressButton Make = new ProgressButton { Text = "Make the seed", Kind = ButtonKind.Primary, FontPt = 12f };
        public string PathTitle = "", RomfsTitle = "";
        public bool ShowRomfs = true;  // Longshot has its own game files, so there's no box to fill
        public const string Note = "Point at a setting for its explanation; right-click it to set it back. Begin a NEW file for each seed.";
        int yHead1, yPathLabel, yRomfsLabel, yHead2, yNote, noteBottom;
        // The two big buttons sit on their own footer. When a short window can't hold everything above them (a long
        // folder path wraps over several lines), that part scrolls under the footer instead of running into the
        // buttons. You scroll with the mouse wheel or by tabbing to a field, and a thin bar at the right shows where
        // you are.
        readonly UiControl footer = new UiControl { BackColor = Pal.Panel };
        int scroll, maxScroll;

        public LeftPanel()
        {
            BackColor = Pal.Panel;
            var above = new Control[] { Targets, PathBox, Browse, RomfsBox, Browse2, Restore, Seed, Dice, Load, Save, Reset };
            foreach (Control c in above)
            {
                Controls.Add(c);
                c.Enter += (s, e) => Reveal((Control)s);
            }
            footer.Controls.Add(Tracker);
            footer.Controls.Add(Make);
            Controls.Add(footer);
            footer.BringToFront();
            footer.Paint += (s, e) =>  // a hairline on the footer's edge while something is scrolled under it
            {
                if (scroll < maxScroll)
                    using (var pen = new Pen(Pal.GoldDim)) e.Graphics.DrawLine(pen, Px(14), 0, footer.Width - Px(14), 0);
            };
            foreach (var t in new[] { PathBox, RomfsBox, Seed }) t.BackColor = Pal.Panel;
            foreach (var t in new[] { PathBox, RomfsBox })
            {
                t.WrapLines = true;  // a long folder path wraps, never cut
                t.Box.TextChanged += (s, e) => PerformLayout();
            }
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            ScrollBy(-e.Delta * Px(48) / 120);
            base.OnMouseWheel(e);
        }

        public void ScrollBy(int px)  // also used by the --scroll left:N test option
        {
            if (maxScroll == 0) return;
            scroll = Math.Max(0, Math.Min(maxScroll, scroll + px));
            PerformLayout();
            Invalidate();
            footer.Invalidate();
        }

        void Reveal(Control c)  // a field reached with Tab is scrolled into sight
        {
            if (maxScroll == 0) return;
            if (c.Bottom > footer.Top) scroll = Math.Min(maxScroll, scroll + c.Bottom - footer.Top + Px(8));
            else if (c.Top < 0) scroll = Math.Max(0, scroll + c.Top - Px(8));
            else return;
            PerformLayout();
            Invalidate();
            footer.Invalidate();
        }

        protected override void OnLayout(LayoutEventArgs e)
        {
            int pad = Px(14), w = Width - 2 * pad, x = pad, gap = Px(6);
            bool tight = Height < Px(560);  // a short window (a small laptop screen)
            // the footer has the buttons at the bottom like before, and its top is where the space above them ended
            int footTop = tight ? Height - pad - Px(44) - Px(8) : Height - pad - Px(46) - Px(8) - Px(34) - Px(8);
            footer.SetBounds(0, footTop, Math.Max(0, Width - 1), Math.Max(0, Height - footTop));
            int fb = footer.Height - pad;
            if (tight)
            {
                int tw = (w - gap) * 2 / 5;
                Tracker.SetBounds(x, fb - Px(44), tw, Px(44));
                Make.SetBounds(x + tw + gap, fb - Px(44), w - tw - gap, Px(44));
            }
            else
            {
                Make.SetBounds(x, fb - Px(46), w, Px(46));
                Tracker.SetBounds(x, Make.Top - Px(8) - Px(34), w, Px(34));
            }
            noteBottom = footTop;
            // everything above, scrolled. However much doesn't fit is how far it can scroll
            maxScroll = Math.Max(0, PlaceAbove(0) - footTop);
            scroll = Math.Min(scroll, maxScroll);
            PlaceAbove(scroll);
            footer.Invalidate();
            base.OnLayout(e);
        }

        // lays out everything above the footer, scrolled up by `off`, and returns where it ends unscrolled
        int PlaceAbove(int off)
        {
            int pad = Px(14), w = Width - 2 * pad, x = pad, y = Px(10) - off;
            int bw = Px(82), fh = Px(30), gap = Px(6);
            bool tight = Height < Px(560);
            yHead1 = y; y += Px(28);
            Targets.SetBounds(x - Px(4), y, w + Px(8), Px(4 * (tight ? 26 : 30))); y = Targets.Bottom + Px(tight ? 6 : 10);
            yPathLabel = y; y += LabelHeight(PathTitle, w);
            int ph = PathBox.HeightFor(w - bw - gap, fh);
            PathBox.SetBounds(x, y, w - bw - gap, ph); Browse.SetBounds(x + w - bw, y, bw, fh); y += ph + Px(10);
            yRomfsLabel = y; y += LabelHeight(RomfsTitle, w);
            RomfsBox.Visible = Browse2.Visible = ShowRomfs;
            if (ShowRomfs)
            {
                int rh = RomfsBox.HeightFor(w - bw - gap, fh);
                RomfsBox.SetBounds(x, y, w - bw - gap, rh); Browse2.SetBounds(x + w - bw, y, bw, fh); y += rh + Px(8);
            }
            else y += Px(2);
            Restore.SetBounds(x, y, w, fh); y += fh + Px(14);
            yHead2 = y; y += Px(28);
            Seed.SetBounds(x, y, w - Px(64) - gap, Px(34)); Dice.SetBounds(x + w - Px(64), y, Px(64), Px(34)); y += Px(34) + gap;
            int third = (w - 2 * gap) / 3;
            Load.SetBounds(x, y, third, fh); Save.SetBounds(x + third + gap, y, third, fh); Reset.SetBounds(x + 2 * (third + gap), y, w - 2 * (third + gap), fh);
            y += fh + Px(10);
            yNote = y;
            return y + off;
        }

        int LabelHeight(string t, int w)
        {
            return TextRenderer.MeasureText(t ?? "", F(9f), new Size(w, 1000), Gfx.Wrap).Height + Px(5);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            int pad = Px(14), w = Width - 2 * pad;
            var hf = F(12.5f, FontStyle.Bold, Fonts.Serif);
            Gfx.Text(g, "Where the seed goes", hf, new Rectangle(pad, yHead1, w, Px(28)), Pal.Gold, Gfx.Left);
            Gfx.Text(g, PathTitle, F(9f), new Rectangle(pad, yPathLabel, w, LabelHeight(PathTitle, w)), Pal.Gold, Gfx.Wrap);
            Gfx.Text(g, RomfsTitle, F(9f), new Rectangle(pad, yRomfsLabel, w, LabelHeight(RomfsTitle, w)), Pal.Gold, Gfx.Wrap);
            Gfx.Text(g, "Seed", hf, new Rectangle(pad, yHead2, w, Px(28)), Pal.Gold, Gfx.Left);
            if (noteBottom - yNote > Px(40))
                Gfx.Text(g, Note, F(9f), new Rectangle(pad, yNote, w, noteBottom - yNote), Pal.TextDim, Gfx.Wrap);
            if (maxScroll > 0)  // a thin bar along the right, above the footer, shows where the scrolled part is
            {
                int track = noteBottom, thumb = Math.Max(Px(24), track * track / (track + maxScroll));
                int ty = (track - thumb) * scroll / maxScroll;
                using (var b = new SolidBrush(Pal.GoldDim)) g.FillRectangle(b, Width - Px(6), ty, Px(3), thumb);
            }
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, Width - 1, 0, Width - 1, Height);
        }
    }

    // the log at the bottom, as a terminal, with the current step and a progress line while a seed is made
    class LogPanel : UiControl
    {
        public readonly TextBox Box = new TextBox
        {
            ReadOnly = true, Multiline = true, ScrollBars = ScrollBars.Vertical, BorderStyle = BorderStyle.None, WordWrap = true,
            BackColor = Pal.Deep, ForeColor = Pal.Text
        };
        public string Status = "Ready";
        public Color StatusColour = Pal.TextDim;
        public bool Busy;
        public double Progress = -1;  // share done while a seed is made (bar under the header), < 0 is a sliding light
        public string Elapsed = "";   // the time since the run began, at the header's right
        int phase;
        readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer { Interval = 33 };

        public LogPanel()
        {
            BackColor = Pal.Bg;
            Controls.Add(Box);
            anim.Tick += (s, e) => { phase = (phase + 1) % 100000; Invalidate(new Rectangle(0, Px(26), Width, Px(4))); };
        }

        protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); Native.DarkControl(Box); }

        public void SetBusy(bool b)
        {
            Busy = b;
            if (b) anim.Start(); else anim.Stop();
            Invalidate();
        }

        protected override void OnLayout(LayoutEventArgs e)
        {
            Box.Font = Fonts.Get(Dpi, 9.5f, FontStyle.Regular, Fonts.Mono);
            Box.SetBounds(Px(14), Px(36), Width - Px(20), Height - Px(44));
            base.OnLayout(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Deep);
            using (var b = new SolidBrush(Pal.Bg)) g.FillRectangle(b, 0, 0, Width, Px(28));
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, 0, Px(28), Width, Px(28));
            var hf = F(10.5f, FontStyle.Bold, Fonts.Serif);
            Gfx.Text(g, "Log", hf, new Rectangle(Px(14), 0, Px(60), Px(28)), Pal.Gold, Gfx.Left);
            int ew = 0;
            if (Busy && Elapsed != "")
            {
                var ef = F(9f);
                ew = TextRenderer.MeasureText(Elapsed, ef).Width + Px(4);
                Gfx.Text(g, Elapsed, ef, new Rectangle(Width - Px(14) - ew, 0, ew, Px(28)), Pal.TextFaint, Gfx.Right);
                ew += Px(12);
            }
            Gfx.Text(g, Status, F(9f), new Rectangle(Px(60), 0, Width - Px(74) - ew, Px(28)), StatusColour, Gfx.Left);
            if (Busy && Progress >= 0)  // the share done, with a light running along it
            {
                int fw = (int)(Width * Math.Min(1.0, Progress));
                using (var b = new SolidBrush(Pal.GoldDim)) g.FillRectangle(b, 0, Px(27), Width, Px(3));
                using (var b = new SolidBrush(Pal.Gold)) g.FillRectangle(b, 0, Px(27), fw, Px(3));
                int lw = Math.Max(Px(40), Width / 8);
                int lx = (int)((phase * Px(6)) % (fw + lw)) - lw;
                if (fw > Px(6))
                    using (var b = new SolidBrush(Pal.GoldHi))
                        g.FillRectangle(b, Math.Max(0, lx), Px(27), Math.Min(fw, lx + lw) - Math.Max(0, lx), Px(3));
            }
            else if (Busy)
            {
                int bw = Math.Max(Px(80), Width / 5);
                int x = (int)((phase * Px(8)) % (Width + bw)) - bw;
                using (var b = new SolidBrush(Pal.Gold)) g.FillRectangle(b, Math.Max(0, x), Px(27), Math.Min(Width, x + bw) - Math.Max(0, x), Px(3));
            }
        }
    }

    // The Make button doubles as the progress bar while a seed is made. Gold fills it from the left, a soft light runs
    // along the gold so it never looks stuck, and the label says how far (ink on the gold, light on the wood).
    // Label holds the forms to try, longest first, one per line. The first one that fits is shown, so it's never cut.
    class ProgressButton : FlatButton
    {
        public double Progress = -1;   // 0..1 while a seed is made, < 0 is the plain button
        public bool Indeterminate;     // a step with no share to show (the first run's preparation), a light sweeps it
        public string Label = "";
        int frame;

        public void Show(double progress, bool indeterminate, string label, int animFrame)
        {
            Progress = progress; Indeterminate = indeterminate; Label = label ?? ""; frame = animFrame;
            Cursor = progress >= 0 ? Cursors.Default : Cursors.Hand;
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            if (Progress < 0)
            {
                base.OnPaint(e);
                return;
            }
            var g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : Pal.Bg);
            Gfx.Smooth(g);
            var r = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
            float rad = Px(4);
            Gfx.Fill(g, r, rad, Pal.Deep);
            var fill = Indeterminate ? RectangleF.Empty : new RectangleF(0, 0, (float)(Width * Math.Min(1.0, Progress)), Height);
            var keep = g.Clip;
            using (var path = Gfx.Round(r, rad))
            {
                g.SetClip(path, CombineMode.Intersect);
                if (fill.Width > 0)
                    using (var b = new SolidBrush(Pal.Gold)) g.FillRectangle(b, fill);
                float span = Indeterminate ? Width : fill.Width, band = Math.Max(Px(40), Width / 5f);
                if (span > Px(6))  // the light makes one pass every 3 s (90 frames)
                {
                    float x = -band + (span + band) * (frame % 90) / 90f;
                    var lr = new RectangleF(x, 0, band, Height);
                    using (var lb = new LinearGradientBrush(lr, Color.Transparent, Color.Transparent, LinearGradientMode.Horizontal))
                    {
                        var glow = Color.FromArgb(Indeterminate ? 120 : 90, 255, 244, 210);
                        lb.InterpolationColors = new ColorBlend
                        {
                            Colors = new[] { Color.FromArgb(0, glow), glow, Color.FromArgb(0, glow) },
                            Positions = new[] { 0f, 0.5f, 1f }
                        };
                        g.SetClip(Indeterminate ? r : fill, CombineMode.Intersect);
                        g.FillRectangle(lb, lr);
                    }
                }
            }
            g.Clip = keep;
            Gfx.Stroke(g, r, rad, Pal.Gold, Math.Max(1f, S));
            var font = F(FontPt + 1f, FontStyle.Bold, Fonts.Serif);
            string[] forms = Label.Split('\n');
            string text = forms.FirstOrDefault(t => TextRenderer.MeasureText(t, font).Width <= Width - Px(16)) ?? forms.Last();
            Gfx.Text(g, text, font, ClientRectangle, Pal.Text, Gfx.Center);
            if (fill.Width > 0)  // the same label in ink where the gold is under it
            {
                g.SetClip(fill);
                Gfx.Text(g, text, font, ClientRectangle, Pal.GoldInk, Gfx.Center);
                g.Clip = keep;
            }
        }
    }

    // Each step is weighted by how long it took last time on this PC (AppConfig.StepSeconds), or by typical timings on
    // the first run. The tool's "@progress F" lines (tools/progress.py) move it, and it eases forward between updates.
    // Before the first report it goes by the clock against the step's usual time up to 80%, then slows down toward 95%
    // until the step ends. Progress never goes backward. Unplanned steps like first-run setup show an indeterminate
    // bar. The worker reports progress and the window reads it on a timer.
    class RunProgress
    {
        static readonly Dictionary<string, double> Typical = new Dictionary<string, double>
        {
            { "generate", 7 }, { "patch", 17 }, { "cosmetics_check", 0.5 }, { "check", 11 },
            { "install", 4 }, { "rekarina", 4 }, { "export", 2 }
        };

        public static string[] Plan(string target)
        {
            var steps = new List<string> { "generate", "patch", "cosmetics_check", "check" };
            if (target == "longshot") steps.Add("install");
            else
            {
                if (target == "rekarina") steps.Add("rekarina");
                steps.Add("export");
            }
            return steps.ToArray();
        }

        readonly object gate = new object();
        readonly List<string> keys;
        readonly Dictionary<string, double> weight = new Dictionary<string, double>();
        readonly double total;
        int cur = -1;
        string curKey;
        DateTime curStart, reportedAt;
        double reported = -1, curShare, best;
        public readonly DateTime Started = DateTime.Now;
        public readonly Dictionary<string, double> Took = new Dictionary<string, double>();  // seconds, steps that worked
        public bool Indeterminate { get { lock (gate) return cur < 0 && curKey != null; } }

        public RunProgress(string[] plan, Dictionary<string, double> learned)
        {
            keys = plan.ToList();
            foreach (var k in keys)
            {
                double s;
                weight[k] = learned != null && learned.TryGetValue(k, out s) && s > 0.1 ? s : Typical[k];
            }
            total = keys.Sum(k => weight[k]);
        }

        public void Start(string key)
        {
            lock (gate)
            {
                curKey = key; curStart = DateTime.Now; reported = -1; curShare = 0;
                cur = keys.IndexOf(key);
            }
        }

        public void Report(double share)
        {
            lock (gate) { reported = Math.Max(reported, Math.Min(1.0, share)); reportedAt = DateTime.Now; }
        }

        public void End(string key, bool ok)
        {
            lock (gate)
            {
                if (ok) Took[key] = (DateTime.Now - curStart).TotalSeconds;
                if (cur >= 0 && ok) curShare = 1;
                if (cur < 0) curKey = null;
            }
        }

        public double Overall()
        {
            lock (gate)
            {
                if (cur < 0) return best;
                double w = weight[keys[cur]], f = reported;
                if (f >= 0)  // between reports it creeps on with the clock (12% of the step at most, below 98%)
                    f = Math.Min(0.98, f + 0.12 * (1 - Math.Exp(-(DateTime.Now - reportedAt).TotalSeconds / 3)));
                else
                {
                    double x = (DateTime.Now - curStart).TotalSeconds / w;
                    f = x < 0.8 ? x : 0.8 + 0.15 * (1 - Math.Exp(-(x - 0.8) * 3));
                }
                curShare = Math.Max(curShare, Math.Min(1.0, f));
                double before = keys.Take(cur).Sum(k => weight[k]);
                best = Math.Max(best, Math.Min(1.0, (before + w * curShare) / total));
                return best;
            }
        }
    }

    // Window
    class MainWindow : DpiForm
    {
        readonly string root;   // the randomizer's folder (tools\rando\generate.py inside)
        readonly string pyRoot; // the same folder the way Python gets it, its short (8.3) form when it has one
        public int ForceDpi;    // --dpi N for testing, lays it out as at that scaling
        readonly AppConfig cfg = AppConfig.Load();
        readonly List<Setting> settings = new List<Setting>();
        readonly List<Page> pages = new List<Page>();
        readonly Dictionary<string, object> baseValues = new Dictionary<string, object>();
        readonly Dictionary<string, Setting> byName = new Dictionary<string, Setting>();
        readonly HeaderBar header = new HeaderBar();
        readonly LeftPanel left = new LeftPanel();
        readonly TabStrip tabs = new TabStrip();
        readonly TextField search = new TextField { Cue = "Search all settings", FontPt = 9.5f, BackColor = Paper.Bg, OnPaper = true };
        readonly SettingsView view = new SettingsView();
        readonly LogPanel logPanel = new LogPanel();
        string shownTarget;
        string longshotNote;  // the saved Longshot folder was moved to the launcher folder (MigrateSavedLongshot)
        bool testing;
        string lastOut;
        Thread worker;
        RunProgress runProgress;   // the seed being made (null between runs), for the Make button's bar and the log's
        double shownProgress;      // what the bars show, eases toward runProgress.Overall() and never goes back
        int progressFrame, doneFrames;
        bool runFinished, runOk;
        readonly System.Windows.Forms.Timer progressTimer = new System.Windows.Forms.Timer { Interval = 33 };

        public MainWindow()
        {
            root = FindRoot();
            pyRoot = root == null ? null : ShortPath(root);
            Text = "Rando of Time";
            Icon = AppIcon();
            header.Logo = Logo("RemakeUi.logo.png");
            SetLogicalSize(1300, 860, 900, 600);
            StartPosition = FormStartPosition.CenterScreen;
            Controls.Add(header); Controls.Add(left); Controls.Add(tabs); Controls.Add(view); Controls.Add(logPanel);
            view.Controls.Add(search);
            Wire();
            if (root == null)
            {
                Log("Can't find the randomizer's tools next to this program (tools\\rando\\generate.py).");
                left.Make.Enabled = false;
                return;
            }
            LoadBase();
            LoadSchema();
            tabs.Pages.AddRange(pages);
            if (File.Exists(LastSettingsPath)) LoadSettingsFile(LastSettingsPath, false);
            else if (cfg.LastSettings != null && File.Exists(cfg.LastSettings)) LoadSettingsFile(cfg.LastSettings, false);
            left.Seed.Text = NewSeed();
            Log("Ready. Randomizer folder: " + root);
            if (longshotNote != null) Log(longshotNote);
            int deepest = PythonTooDeep();
            if (deepest > 0)
                Log("Note: the randomizer's folder is too deep for Python. Its files would sit " + deepest + " characters deep, and Windows can't load "
                    + "them past 250, even through the folder's short name. Move the randomizer's folder somewhere shorter, such as C:\\Games, "
                    + "and start it from there.");
            SetStatus(deepest > 0 ? "Move the randomizer's folder somewhere shorter (see the log)." : "Ready", deepest > 0 ? Pal.Red : Pal.TextDim);
            ShowTab(0);
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            if (ForceDpi > 0 && ForceDpi != Dpi)
            {
                Dpi = ForceDpi;
                Font = Fonts.Get(Dpi, 10f);
                PerformLayout();
                Invalidate(true);
            }
        }

        static string FindRoot()
        {
            string d = AppDomain.CurrentDomain.BaseDirectory;
            for (int i = 0; i < 5 && d != null; i++, d = Path.GetDirectoryName(d.TrimEnd('\\')))
                if (File.Exists(Path.Combine(d, "tools", "rando", "generate.py"))) return d;
            return null;
        }

        // Layout
        // Same arrangement as the old window, with the seed's setup on the left, the settings tabs on top and the log
        // at the bottom
        protected override void OnLayout(LayoutEventArgs e)
        {
            if (header == null)
            {
                base.OnLayout(e);
                return;
            }
            var c = ClientRectangle;
            int hh = Px(56), lw = Px(336), gap = Px(8), lh = Math.Max(Px(110), Math.Min(Px(176), (c.Height - hh) / 4));
            header.SetBounds(0, 0, c.Width, hh);
            left.SetBounds(0, hh, lw, c.Height - hh);
            int x = lw + gap, w = c.Width - x - gap;
            tabs.SetBounds(x, hh + gap, w, tabs.HeightFor(w));  // every tab name whole, in one row or more
            logPanel.SetBounds(x, c.Height - gap - lh, w, lh);
            int sw = Math.Min(Px(240), Math.Max(Px(160), w / 4));
            view.HeaderReserveRight = sw + Px(20);
            view.SetBounds(x, tabs.Bottom, w, logPanel.Top - gap - tabs.Bottom);
            int colW = Math.Min(w - Px(44), Px(1040)), colX = Math.Max(Px(20), (w - colW) / 2);
            search.SetBounds(colX + colW - sw, Px(14), sw, Px(32));
            base.OnLayout(e);
        }

        void Wire()
        {
            view.IsChanged = st => !st.Off && !Same(Value(st), st.Default);
            view.Shown = ShownValue;
            view.Changed += st => { ApplyDisables(); tabs.Invalidate(); PerformLayout(); };
            view.ResetOne += st => { SetValue(st, st.Default); ApplyDisables(); view.Invalidate(); tabs.Invalidate(); };
            tabs.Changed = p => p.All.Count(st => !st.Off && !Same(Value(st), st.Default));
            tabs.Picked += i => { if (search.Text != "") search.Text = ""; ShowTab(i); };
            search.Box.TextChanged += (s, e) =>
            {
                string q = search.Text.Trim();
                if (q.Length >= 2)
                {
                    view.ShowSearch(q, pages);
                    tabs.Selected = -1;
                    tabs.Invalidate();
                }
                else if (q.Length == 0 && view.Searching) ShowTab(0);
            };
            search.Box.KeyDown += (s, e) => { if (e.KeyCode == Keys.Escape) { search.Text = ""; e.SuppressKeyPress = true; } };
            left.Targets.Changed += TargetChanged;
            left.Browse.Click += (s, e) => PickFolder(left.PathBox);
            left.Browse2.Click += (s, e) => PickFolder(left.RomfsBox);
            left.Dice.Click += (s, e) => left.Seed.Text = NewSeed();
            left.Load.Click += (s, e) => { using (var d = new OpenFileDialog { Filter = "Settings|*.json" }) if (d.ShowDialog(this) == DialogResult.OK) LoadSettingsFile(d.FileName, true); };
            left.Save.Click += (s, e) =>
            {
                using (var d = new SaveFileDialog { Filter = "Settings|*.json", FileName = "my_settings.json" })
                    if (d.ShowDialog(this) == DialogResult.OK)
                    {
                        File.WriteAllText(d.FileName, SettingsJson());
                        cfg.LastSettings = d.FileName;
                        Log("Saved " + d.FileName);
                        SetStatus("Settings saved to " + d.FileName, Pal.TextDim);
                    }
            };
            left.Reset.Click += (s, e) => { ResetSettings(); cfg.LastSettings = null; Log("Settings back to the defaults."); SetStatus("Settings back to the defaults", Pal.TextDim); };
            left.Make.Click += (s, e) => Run();
            progressTimer.Tick += (s, e) => ProgressTick();
            left.Tracker.Click += (s, e) => OpenTracker();
            left.Restore.Click += (s, e) => Restore();
            left.RomfsBox.Text = cfg.Romfs;
            left.PathBox.Box.TextChanged += (s, e) => ShowLongshotGame();
            longshotNote = MigrateSavedLongshot();
            left.Targets.Value = cfg.Target == "rekarina" ? "rekarina" : cfg.Target == "sdcard" || cfg.Target == "layeredfs" ? "sdcard"
                               : cfg.Target == "emulator" ? "emulator" : "longshot";
            TargetChanged();
            FormClosing += (s, e) =>
            {
                StopStep();  // a step still running stops with the window
                if (testing) return;
                SaveTarget(); cfg.Save(); SaveLastSettings();
            };
        }

        void PickFolder(TextField box)
        {
            using (var d = new FolderBrowserDialog { SelectedPath = box.Text }) if (d.ShowDialog(this) == DialogResult.OK) box.Text = d.SelectedPath;
        }

        void ShowTab(int i)
        {
            if (i < 0 || i >= pages.Count) return;
            tabs.Selected = i;
            tabs.Invalidate();
            view.ShowPage(pages[i]);
        }

        void FocusSetup() { left.PathBox.Box.Focus(); }

        void SetStatus(string text, Color c)
        {
            logPanel.Status = text; logPanel.StatusColour = c; logPanel.Invalidate();
        }

        // Target
        string CurrentTarget() { return left.Targets.Value; }


        void TargetChanged()
        {
            SaveTarget();
            string t = CurrentTarget();
            shownTarget = t;
            cfg.Target = t;
            if (t == "longshot")
            {
                left.PathTitle = "Longshot's launcher folder (with builds.json) or a game folder";
                left.PathBox.Text = cfg.LongshotDir != "" ? cfg.LongshotDir : LongshotGame.Hint();
                left.RomfsBox.Enabled = false;
                left.RomfsBox.Text = cfg.Romfs;
                ShowLongshotGame();
            }
            else if (t == "rekarina")
            {
                left.PathTitle = "Rekarina's game folder (with Rekarina.exe)";
                left.RomfsTitle = "Game files: a dumped romfs folder (empty = Longshot's copy)";
                left.PathBox.Text = cfg.RekarinaDir != "" ? cfg.RekarinaDir : AppConfig.RekarinaHint();
                left.RomfsBox.Enabled = true;
                left.RomfsBox.Text = cfg.Romfs;
            }
            else if (t == "sdcard")
            {
                left.PathTitle = "The SD card's root (the mod goes to atmosphere\\contents\\0400486024DEC000)";
                left.RomfsTitle = "Game files: a dumped romfs folder (empty = Longshot's copy)";
                left.PathBox.Text = cfg.SdOut != "" ? cfg.SdOut : cfg.ModOut;
                left.RomfsBox.Enabled = true;
                left.RomfsBox.Text = cfg.Romfs;
            }
            else
            {
                left.PathTitle = "The emulator's mod folder for this game (Ryujinx: mods\\contents\\0400486024DEC000)";
                left.RomfsTitle = "Game files: a dumped romfs folder (empty = Longshot's copy)";
                left.PathBox.Text = cfg.EmuOut;
                left.RomfsBox.Enabled = true;
                left.RomfsBox.Text = cfg.Romfs;
            }
            left.Browse2.Enabled = left.RomfsBox.Enabled;
            left.ShowRomfs = left.RomfsBox.Enabled;
            left.PerformLayout();
            left.Invalidate();
        }

        // Under the Longshot box we show the game the seed goes to (the launcher's default build, or the folder
        // picked), so a launcher folder never hides which build that is.
        void ShowLongshotGame()
        {
            if (CurrentTarget() != "longshot") return;
            string p = Clean(left.PathBox.Text);
            var g = LongshotGame.Find(p);
            string text;
            if (g.Folder == "")
                text = p == "" ? "Pick Longshot's launcher folder: the seed goes in its game as a mod."
                     : "No Longshot game there: pick the launcher's folder (the one with builds.json) or a game folder (with romfs and bin).";
            else if (g.Picked)
                text = "The seed goes in this game's mods folder, as a mod. Longshot's own game files aren't changed.";
            else
                text = "Game: " + g.Short() + (g.Version != null ? " (" + g.Version + ", " : " (") + (g.Default ? "the launcher's default build" : "the launcher's newest build")
                     + "). The seed goes in its mods folder, as a mod.";
            if (text == left.RomfsTitle) return;
            left.RomfsTitle = text;
            left.PerformLayout();
            left.Invalidate();
        }

        // Longshot Launcher 1.2.0 moved the game out of the folder we saved before (builds\rc). So we save the
        // launcher folder above it instead and use its default build. The note goes in the log once the window is
        // ready.
        string MigrateSavedLongshot()
        {
            string saved = Clean(cfg.LongshotDir), home = LongshotGame.Migrated(saved);
            if (home == null) return null;
            cfg.LongshotDir = home;
            return LongshotMovedNote(saved, home);
        }

        static string LongshotMovedNote(string saved, string home)
        {
            var g = LongshotGame.Find(home);
            return "Longshot's game is no longer in " + saved + ": Longshot Launcher 1.2.0 keeps each version in a folder of its own. "
                 + "The randomizer now uses the launcher's folder, " + home + ", and its " + (g.Default ? "default" : "newest") + " build, "
                 + g.Short() + (g.Version != null ? " (" + g.Version + ")" : "") + ".";
        }

        void SaveTarget()
        {
            string p = left.PathBox.Text.Trim();
            if (shownTarget == "longshot") cfg.LongshotDir = p;
            else if (shownTarget == "rekarina") cfg.RekarinaDir = p;
            else if (shownTarget == "sdcard") cfg.SdOut = p;
            else if (shownTarget == "emulator") cfg.EmuOut = p;
            if (left.RomfsBox.Enabled) cfg.Romfs = left.RomfsBox.Text.Trim();
        }

        // Settings
        void LoadBase()
        {
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var d = js.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(root, "config", "rando_settings.json")));
            object s;
            if (d.TryGetValue("settings", out s) && s is Dictionary<string, object>)
                foreach (var kv in (Dictionary<string, object>)s) baseValues[kv.Key] = kv.Value;
        }

        void LoadSchema()
        {
            string p = Path.Combine(root, "release", "data", "settings_schema.json");
            if (!File.Exists(p)) p = Path.Combine(root, "data", "settings_schema.json");
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var d = js.Deserialize<Dictionary<string, object>>(File.ReadAllText(p));
            foreach (Dictionary<string, object> t in (ArrayList)d["tabs"])
            {
                var page = new Page { Title = (string)t["text"], Blurb = TabBlurb((string)t["text"]) };
                foreach (Dictionary<string, object> sec in (ArrayList)t["sections"])
                {
                    var list = new List<Setting>();
                    foreach (Dictionary<string, object> e in (ArrayList)sec["settings"])
                    {
                        var st = MakeSetting(e);
                        if (st == null) continue;
                        st.Tab = page.Title; st.Section = (string)sec["text"];
                        list.Add(st);
                        settings.Add(st);
                        byName[st.Name] = st;
                    }
                    page.Sections.Add(new KeyValuePair<string, List<Setting>>((string)sec["text"], list));
                }
                pages.Add(page);
            }
            ApplyDisables();
        }

        static string TabBlurb(string tab)
        {
            switch (tab)
            {
                case "Main Rules": return "How the world opens up, what is shuffled and where dungeon items can be.";
                case "Detailed Logic": return "Locations to leave out and the tricks the logic may expect.";
                case "Starting Inventory": return "What Link starts the game with.";
                case "Other": return "Timesavers, hints, gameplay changes and the item pool.";
                case "Cosmetics": return "Colours and looks (no effect on the seed's items).";
                case "SFX": return "Music and sound effects (no effect on the seed's items).";
                default: return "";
            }
        }

        // a setting's one-line summary: the first sentence of its explanation
        static readonly string[] Abbrev = { "e.g", "i.e", "etc", "vs", "approx", "incl", "no", "St", "Mr", "Dr" };

        // A tooltip's first sentence, shown under the setting's name (the whole tooltip shows on hover). It ends at a
        // ". " that isn't part of an abbreviation ("e.g. ", "i.e. "). A long first sentence is shown whole, never cut.
        static string Summary(string tip)
        {
            if (string.IsNullOrEmpty(tip)) return "";
            string t = System.Text.RegularExpressions.Regex.Replace(tip.Replace("\r", " ").Replace("\n", " "), @"\s+", " ").Trim();
            int from = 0;
            while (true)
            {
                int i = t.IndexOf(". ", from, StringComparison.Ordinal);
                if (i <= 0) return t;
                int w = i;
                while (w > 0 && (char.IsLetter(t[w - 1]) || t[w - 1] == '.')) w--;
                string word = t.Substring(w, i - w);
                if (Abbrev.Any(a => string.Equals(a, word, StringComparison.OrdinalIgnoreCase)))
                {
                    from = i + 2;
                    continue;
                }
                return t.Substring(0, i + 1);
            }
        }

        // a free-form value as the player types it: words as they are, tables and lists as JSON
        static string AsText(object v)
        {
            if (v == null) return "";
            if (v is string) return (string)v;
            return new JavaScriptSerializer().Serialize(v);
        }

        string ShownValue(Setting st)
        {
            switch (st.Type)
            {
                case "choice": return st.C >= 0 && st.C < st.Choices.Count ? st.Choices[st.C][1] : "";
                case "list":
                    if (st.On.Count == 0) return "";
                    var names = st.Choices.Where(c => st.On.Contains(c[0])).Select(c => c[1]).ToList();
                    return names.Count <= 2 ? string.Join(", ", names) : names.Count + " chosen: " + string.Join(", ", names.Take(2)) + ", ...";
                default: return st.T;
            }
        }

        static string Key(object v)
        {
            if (v is bool) return (bool)v ? "True" : "False";
            return Convert.ToString(v);
        }

        // OoTR's rules for greying a setting out while another one has some value ("!v" means any value but v).
        // Greyed-out settings aren't written, and the generator gives them their "disabled" value like OoTR's GUI
        // does.
        void ApplyDisables()
        {
            var off = new HashSet<string>();
            for (int round = 0; round < 3; round++)
            {
                var now = new HashSet<string>();
                foreach (var st in settings)
                {
                    if (off.Contains(st.Name) || st.Disable.Count == 0) continue;
                    string v = Key(Value(st));
                    foreach (var rule in st.Disable)
                    {
                        bool neg = rule.Key.StartsWith("!");
                        string want = neg ? rule.Key.Substring(1) : rule.Key;
                        if ((v == want) != neg) foreach (var n in rule.Value) now.Add(n);
                    }
                }
                if (now.SetEquals(off)) break;
                off = now;
            }
            bool changed = false;
            foreach (var st in settings)
            {
                bool o = off.Contains(st.Name);
                if (st.Off != o)
                {
                    st.Off = o;
                    changed = true;
                }
            }
            if (changed) view.Rebuild(); else view.Invalidate();
            tabs.Invalidate();
        }

        Setting MakeSetting(Dictionary<string, object> e)
        {
            var st = new Setting { Name = (string)e["name"], Label = (string)e["label"], Type = (string)e["type"] };
            object v;
            st.Tooltip = e.TryGetValue("tooltip", out v) ? Convert.ToString(v) : "";
            st.Summary = Summary(st.Tooltip);
            st.Default = baseValues.TryGetValue(st.Name, out v) ? v : (e.TryGetValue("default", out v) ? v : null);
            if (e.TryGetValue("choices", out v) && v is ArrayList)
                foreach (ArrayList c in (ArrayList)v) st.Choices.Add(new[] { Convert.ToString(c[0]), Convert.ToString(c[1]) });
            if (e.TryGetValue("disable", out v) && v is ArrayList)
                foreach (Dictionary<string, object> r in (ArrayList)v)
                    st.Disable.Add(new KeyValuePair<string, List<string>>(Convert.ToString(r["when"]), ((ArrayList)r["settings"]).Cast<object>().Select(Convert.ToString).ToList()));
            if (st.Type == "int")
            {
                st.Min = e.TryGetValue("min", out v) ? Convert.ToInt32(v) : 0;
                st.Max = e.TryGetValue("max", out v) ? Convert.ToInt32(v) : 1000;
                st.Step = e.TryGetValue("step", out v) ? Math.Max(1, Convert.ToInt32(v)) : 1;
            }
            if (!SetValue(st, st.Default))
            {
                if (st.Type == "choice" && st.Choices.Count > 0) st.C = 0;
                if (st.Type == "int") st.I = st.Min;
            }
            return st;
        }

        object Value(Setting s)
        {
            switch (s.Type)
            {
                case "bool": return s.B;
                case "int": return s.Min + (s.I - s.Min) / s.Step * s.Step;  // on its step
                case "choice": return s.C >= 0 && s.C < s.Choices.Count ? s.Choices[s.C][0] : s.Default;
                case "list":
                    var on = s.Choices.Where(c => s.On.Contains(c[0])).Select(c => c[0]).ToList();
                    // the loaded order first (the same file makes the same seed), then new ones in the list's order
                    return s.ListOrder.Where(on.Contains).Concat(on.Where(k => !s.ListOrder.Contains(k))).ToList();
                default:
                    string t = (s.T ?? "").Trim();
                    if (t == "") return null;
                    // a table or list as JSON, a plain word or number as itself ("vanilla", 12)
                    try { return new JavaScriptSerializer().DeserializeObject(t); } catch (Exception) { return t; }
            }
        }

        static bool Same(object a, object b)
        {
            var js = new JavaScriptSerializer();
            return js.Serialize(a) == js.Serialize(b);
        }

        string SettingsJson()
        {
            view.Commit();
            var changed = new Dictionary<string, object>();
            foreach (var s in settings)
            {
                if (s.Off) continue;
                var v = Value(s);
                if (v == null) continue;
                // Only what differs from its default (the base file's value, else the generator's default). That way a
                // setting left alone behaves exactly like it would without the app (some follow another one's value).
                if (!Same(v, s.Default)) changed[s.Name] = v;
            }
            var d = new Dictionary<string, object> { { "_about", "Made by the randomizer app" }, { "base", "config/rando_settings.json" }, { "settings", changed } };
            return new JavaScriptSerializer().Serialize(d);
        }

        // Shows v, or returns false when it isn't a value the app offers (a choice it doesn't have, a number out of
        // its range).
        bool SetValue(Setting st, object v)
        {
            switch (st.Type)
            {
                case "bool": st.B = v is bool && (bool)v; return v is bool;
                case "int":
                    decimal x;
                    try { x = Convert.ToDecimal(v); } catch (Exception) { return false; }
                    if (x < st.Min || x > st.Max || (x - st.Min) % st.Step != 0) return false;
                    st.I = (int)x;
                    return true;
                case "choice":
                    int i = st.Choices.FindIndex(c => c[0] == Key(v));
                    if (i < 0) return false;
                    st.C = i;
                    return true;
                case "list":
                    st.ListOrder = (v as ArrayList ?? new ArrayList()).Cast<object>().Select(Convert.ToString).ToList();
                    st.On = new HashSet<string>(st.ListOrder.Where(k => st.Choices.Any(c => c[0] == k)));
                    return st.ListOrder.All(k => st.Choices.Any(c => c[0] == k));
                default: st.T = AsText(v); return true;
            }
        }

        void ResetSettings()
        {
            foreach (var st in settings) SetValue(st, st.Default);
            ApplyDisables();
        }

        // Loads a settings file the way the generator reads it, with its "base" chain and familiar names such as
        // shuffle_trees (tools/release/resolve_settings.py). Settings it doesn't name keep their default.
        void LoadSettingsFile(string path, bool tell)
        {
            try
            {
                path = Path.GetFullPath(path);  // Python runs in the randomizer's folder
                var psi = new ProcessStartInfo(Python(), "-s tools/release/resolve_settings.py " + Q(PyPath(path)))
                {
                    WorkingDirectory = pyRoot, UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8
                };
                Isolate(psi);
                string text;
                using (var p = Process.Start(psi))
                {
                    text = p.StandardOutput.ReadToEnd();
                    p.WaitForExit();
                }
                var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
                var d = js.Deserialize<Dictionary<string, object>>(text);
                if (d == null)
                {
                    Log("Couldn't load " + path + ": the randomizer's Python gave no answer.");
                    return;
                }
                if (d.ContainsKey("error"))
                {
                    Log("Couldn't load " + path + ": " + d["error"]);
                    return;
                }
                var s = (Dictionary<string, object>)d["settings"];
                var notOffered = new List<string>();
                foreach (var st in settings)
                {
                    object v = s.ContainsKey(st.Name) ? s[st.Name] : st.Default;
                    if (!SetValue(st, v))
                    {
                        SetValue(st, st.Default);
                        if (s.ContainsKey(st.Name)) notOffered.Add(st.Label + " = " + AsText(v));
                    }
                }
                // settings the app doesn't show: only those that would change something are worth a word
                var dropped = s.Keys.Where(k => !byName.ContainsKey(k) && !(baseValues.ContainsKey(k) && Same(baseValues[k], s[k])))
                                    .ToList();
                ApplyDisables();
                cfg.LastSettings = path;
                if (notOffered.Count > 0)
                    Log("Not something the remake can make, so left at the default: " + string.Join("; ", notOffered));
                if (dropped.Count > 0)
                    Log("Settings this app doesn't have, so left out: " + string.Join(", ", dropped));
                if (tell)
                {
                    Log("Loaded " + path);
                    SetStatus("Loaded " + Path.GetFileName(path), Pal.TextDim);
                }
            }
            catch (Exception e) { Log("Couldn't load " + path + ": " + e.Message); }
        }

        // The settings in use, kept between runs (%APPDATA%\RemakeRandomizer\last_settings.json).
        static string LastSettingsPath
        {
            get { return Path.Combine(AppConfig.DataFolder(), "last_settings.json"); }
        }

        void SaveLastSettings()
        {
            if (testing || settings.Count == 0) return;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(LastSettingsPath));
                File.WriteAllText(LastSettingsPath, SettingsJson());
            }
            catch (Exception) { }
        }

        // Run
        readonly StringBuilder logText = new StringBuilder();

        string LogText() { lock (logText) return logText.ToString(); }

        void Log(string text)
        {
            lock (logText) logText.AppendLine(text);
            if (IsDisposed) return;
            if (InvokeRequired) { try { BeginInvoke(new Action<string>(LogUi), text); } catch (Exception) { } return; }
            LogUi(text);
        }

        void LogUi(string text)
        {
            if (logPanel.Box.IsDisposed) return;
            logPanel.Box.AppendText(text + Environment.NewLine);
            if (logPanel.Busy && !text.StartsWith(" ")) SetStatus(text.StartsWith("== ") ? text.Substring(3) + "..." : text, Pal.TextDim);
        }

        void SafeInvoke(Action a)
        {
            if (IsDisposed) return;
            try { BeginInvoke(a); } catch (Exception) { }
        }

        // The bundled Python runs on its own. None of the player's PYTHON* settings (PYTHONPATH, PYTHONOPTIMIZE, which
        // would drop the format checks, ...) or RANDO_* switches get through, and no user packages (-s).
        string stepRomfs;     // the game files this run's steps read (the tools' REMAKE_ROMFS)
        string stepOriginal;  // where this game copy's originals and install record live (REMAKE_ORIGINAL)
        Process current;      // the step running now (stopped if the window closes)
        string lastStepLine;  // last line the running (or last) step wrote, which says why it stopped if it did

        void Isolate(ProcessStartInfo psi)
        {
            var env = psi.EnvironmentVariables;
            foreach (var k in env.Keys.Cast<string>().ToList())
                if (k.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase) || k.StartsWith("RANDO_", StringComparison.OrdinalIgnoreCase))
                    env.Remove(k);
            env["PYTHONHASHSEED"] = "0";
            env["PYTHONIOENCODING"] = "utf-8";
            env["PYTHONNOUSERSITE"] = "1";
            if (!string.IsNullOrEmpty(stepRomfs)) env["REMAKE_ROMFS"] = PyPath(stepRomfs).Replace(Path.DirectorySeparatorChar, '/');
            if (!string.IsNullOrEmpty(stepOriginal)) env["REMAKE_ORIGINAL"] = PyPath(stepOriginal);
            env.Remove("REMAKE_IGNORE_RUNNING");  // only a test on a scratch copy of a game folder (IgnoreRunning) sets it
            if (IgnoreRunning) env["REMAKE_IGNORE_RUNNING"] = "1";
        }

        // The bundled Python (python\python.exe), else the one on PATH. Windows only loads a DLL from a path of at
        // most 250 characters, whether long paths are on or not. I measured it: python\DLLs\unicodedata.pyd loads
        // at 250 and fails at 251 with "The filename or extension is too long", and a player's 224-character folder
        // made it 252. So Python is started through the folder's short (8.3) path, its working folder is that too,
        // and paths under the folder reach it the same way.
        string Python()
        {
            string bundled = Path.Combine(root, "python", "python.exe");
            return File.Exists(bundled) ? Path.Combine(pyRoot, "python", "python.exe") : "python";
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern uint GetShortPathNameW(string longPath, StringBuilder shortPath, uint size);

        // the short (8.3) form of an existing path, or the path itself when the volume keeps no short names
        static string ShortPath(string p)
        {
            try
            {
                string q = p.Length >= 240 && !p.StartsWith(@"\\") ? @"\\?\" + p : p;
                var sb = new StringBuilder(1024);
                uint n = GetShortPathNameW(q, sb, (uint)sb.Capacity);
                if (n >= sb.Capacity)
                {
                    sb = new StringBuilder((int)n + 1);
                    n = GetShortPathNameW(q, sb, (uint)sb.Capacity);
                }
                if (n == 0 || n >= sb.Capacity) return p;
                string sp = sb.ToString();
                if (sp.StartsWith(@"\\?\") && !p.StartsWith(@"\\?\")) sp = sp.Substring(4);
                return sp.Length > 0 && sp.Length <= p.Length ? sp : p;
            }
            catch (Exception) { return p; }
        }

        // a path the way Python gets it, through the short path when it's under the randomizer's folder
        string PyPath(string p)
        {
            if (string.IsNullOrEmpty(p) || pyRoot == root) return p;
            if (string.Equals(p, root, StringComparison.OrdinalIgnoreCase)) return pyRoot;
            return p.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase) ? pyRoot + p.Substring(root.Length) : p;
        }

        // A step's arguments, with the paths under the randomizer's folder going through the short path too.
        string PyArgs(string args) { return pyRoot == root ? args : args.Replace(root + "\\", pyRoot + "\\"); }

        // > 0 when the bundled Python can't run from here even through the short path. It's the length its deepest
        // DLL would have (python\...\*.pyd, *.dll, numpy's are the deepest at about 100 characters). 0 when it can,
        // or when Python isn't bundled.
        int PythonTooDeep()
        {
            string py = Path.Combine(root, "python");
            if (!File.Exists(Path.Combine(py, "python.exe")) || pyRoot.Length + 130 <= 250) return 0;
            int most = 0;
            try
            {
                string lp = Long(py);
                foreach (var pat in new[] { "*.pyd", "*.dll" })
                    foreach (var f in Directory.EnumerateFiles(lp, pat, SearchOption.AllDirectories))
                        most = Math.Max(most, f.Length - lp.Length);
            }
            catch (Exception) { }
            int deepest = pyRoot.Length + "\\python".Length + most;
            return deepest > 250 ? deepest : 0;
        }

        // key is the step's name for the progress bar (RunProgress.Plan). Its tool's "@progress F" lines move the bar
        // and stay out of the log (tools/progress.py only prints them with REMAKE_PROGRESS=1, which we set here).
        int Step(string what, string args, string key = null)
        {
            Log("== " + what);
            lastStepLine = "";
            var psi = new ProcessStartInfo(Python(), "-s " + PyArgs(args))
            {
                WorkingDirectory = pyRoot, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true,
                CreateNoWindow = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
            };
            Isolate(psi);
            psi.EnvironmentVariables["REMAKE_PROGRESS"] = "1";
            var prog = key != null ? runProgress : null;
            if (prog != null) prog.Start(key);
            using (var p = new Process { StartInfo = psi })
            {
                p.OutputDataReceived += (s, e) =>
                {
                    if (e.Data == null) return;
                    if (e.Data.StartsWith("@progress "))
                    {
                        double f;
                        string[] parts = e.Data.Split(' ');
                        if (prog != null && double.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out f))
                            prog.Report(f);
                        return;
                    }
                    if (!e.Data.StartsWith("  note")) Log(e.Data);
                    if (e.Data.Trim() != "") lastStepLine = e.Data.Trim();
                };
                p.ErrorDataReceived += (s, e) => { if (e.Data != null) { Log(e.Data); if (e.Data.Trim() != "") lastStepLine = e.Data.Trim(); } };
                try { p.Start(); }
                catch (Exception e)
                {
                    Log("Couldn't start Python (" + Python() + "): " + e.Message);
                    if (prog != null) prog.End(key, false);
                    return -1;
                }
                current = p;
                p.BeginOutputReadLine(); p.BeginErrorReadLine(); p.WaitForExit();
                current = null;
                if (prog != null) prog.End(key, p.ExitCode == 0);
                return p.ExitCode;
            }
        }

        // The bars while a seed is made, 30 frames a second. They ease toward RunProgress.Overall(). After a seed that
        // worked the button fills, says "Done" for a second and then goes back to being the Make button. After a
        // failure it goes back at once.
        void ProgressTick()
        {
            var rp = runProgress;
            if (rp == null)
            {
                progressTimer.Stop();
                return;
            }
            progressFrame++;
            double target = runFinished && runOk ? 1.0 : rp.Overall();
            if (target > shownProgress)
                shownProgress = Math.Min(target, shownProgress + Math.Max((target - shownProgress) * 0.12, 0.002));
            int pct = (int)Math.Floor(shownProgress * 100 + 1e-9);
            bool indeterminate = rp.Indeterminate && !runFinished;
            string label = runFinished ? "Done"
                         : indeterminate ? "Preparing (only this once)\nPreparing"
                         : "Making the seed \u00b7 " + pct + "%\nMaking \u00b7 " + pct + "%\n" + pct + "%";
            if (runFinished && (!runOk || (shownProgress >= 1.0 && ++doneFrames > 30)))
            {
                progressTimer.Stop();
                runProgress = null;
                left.Make.Show(-1, false, null, 0);
                logPanel.Progress = -1;
                logPanel.Elapsed = "";
                logPanel.Invalidate();
                return;
            }
            left.Make.Show(shownProgress, indeterminate, label, progressFrame);
            logPanel.Progress = indeterminate ? -1 : shownProgress;
            var el = DateTime.Now - rp.Started;
            string elapsed = string.Format("{0}:{1:00}", (int)el.TotalMinutes, el.Seconds);
            if (elapsed != logPanel.Elapsed)
            {
                logPanel.Elapsed = elapsed;
                logPanel.Invalidate();
            }
        }

        void StopStep()
        {
            try { var p = current; if (p != null && !p.HasExited) p.Kill(); } catch (Exception) { }
        }


        // A new seed the way OoTR makes them, 10 letters and digits. That's about 3.7 quadrillion for each choice of
        // settings (the generator mixes the seed with every setting and hashes it). Any seed text OoTR keeps (letters,
        // digits, - and _) can be typed in instead, numbers included.
        static readonly System.Security.Cryptography.RandomNumberGenerator seedRng = System.Security.Cryptography.RandomNumberGenerator.Create();

        static string NewSeed()
        {
            const string abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
            var sb = new StringBuilder();
            var b = new byte[1];
            while (sb.Length < 10)
            {
                seedRng.GetBytes(b);
                if (b[0] < 252) sb.Append(abc[b[0] % 36]);  // 252 = 7 x 36: every character equally likely
            }
            return sb.ToString();
        }

        // OoTR's rule (Settings.sanitize_seed keeps letters, digits, - and _), and it's safe in a folder name too
        static bool SeedOk(string seed)
        {
            return seed.Length > 0 && seed.Length <= 32 && seed.All(ch => (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_');
        }

        static string Q(string s)  // for CommandLineToArgvW, escape quotes and double the backslashes before them
        {
            var sb = new StringBuilder("\"");
            int bs = 0;
            foreach (char c in s ?? "")
            {
                if (c == '\\')
                {
                    bs++;
                    continue;
                }
                if (c == '"')
                {
                    sb.Append('\\', bs * 2 + 1);
                    sb.Append('"');
                }
                else
                {
                    sb.Append('\\', bs);
                    sb.Append(c);
                }
                bs = 0;
            }
            sb.Append('\\', bs * 2);
            sb.Append('"');
            return sb.ToString();
        }

        public void ExportSettings(string input, string output_)
        {
            testing = true;
            LoadSettingsFile(input, false);
            File.WriteAllText(output_, SettingsJson());
        }

        public void NoMemory() { testing = true; }  // a screenshot run leaves app.json and the last settings alone

        // for testing, scrolls the settings page (logical pixels, or "end") before the screenshot
        public void TestScroll(string v)
        {
            if (v.StartsWith("left:"))
            {
                left.ScrollBy(v == "left:end" ? int.MaxValue / 2 : Px(int.Parse(v.Substring(5))));
                return;
            }
            view.Scroll.Offset = v == "end" ? int.MaxValue / 2 : Px(int.Parse(v));
            view.Scroll.Clamp();
            view.Invalidate();
        }

        public void SelectTab(string tab)
        {
            int i;
            if (tab.StartsWith("search:")) search.Text = tab.Substring(7);
            else if (int.TryParse(tab, out i)) ShowTab(i);
        }

        public void SelfTest(string dir, string seed, string settingsFile)
        {
            testing = true;  // nothing of the test is remembered (app.json, last_settings.json)
            if (settingsFile != null) LoadSettingsFile(settingsFile, true);
            left.Targets.Pick("sdcard");
            left.Seed.Text = seed;
            left.PathBox.Text = dir;
            Run(null, ok =>
            {
                try { File.WriteAllText(Path.Combine(dir, "selftest.log"), (ok ? "OK" : "FAILED") + Environment.NewLine + LogText()); } catch (Exception) { }
                Close();
            });
        }

        // Self-test of the Longshot mod path (--selftest DIR SEED --longshot ROMFS) on a scratch launcher folder,
        // never the real game folder. DIR\LongshotHome\builds.json names builds\stable\v3.1.0 as its default build,
        // and that build's romfs is a junction to ROMFS (only read) next to an empty bin.
        // First it tests finding the game (pure checks, including a second fake launcher folder). Then, with a gone
        // builds\rc in the box and the mod switched off in the launcher's user\mods.json, it runs "Make the seed"
        // (the box moves to the launcher folder, the seed goes in as a mod, the switch is noticed),
        // tools/install.py mod-status, and "Restore the original game" (mod-remove). ROMFS must be the same
        // throughout.
        // DIR\selftest.log gets OK or FAILED, each check, then the app's log. The junction is removed at the end.
        public void SelfTestLongshot(string dir, string seed, string settingsFile, string romfsSrc)
        {
            testing = true;        // nothing of the test is remembered (app.json, last_settings.json)
            IgnoreRunning = true;  // a scratch game folder, the real game may be running meanwhile
            dir = Path.GetFullPath(dir);
            string home = Path.Combine(dir, "LongshotHome"), game = Path.Combine(home, "builds", "stable", "v3.1.0");
            string junction = Path.Combine(game, "romfs"), stale = Path.Combine(home, "builds", "rc");
            string textsLink = Path.Combine(game, "texts"), textsSrc = null;  // Longshot's text copies, the PC wording
            string mod = Path.Combine(game, "mods", LongshotGame.ModName);
            var lines = new List<string>();
            bool good = true;
            Action<bool, string> check = (ok, what) => { lines.Add((ok ? "ok      " : "FAILED  ") + what); if (!ok) good = false; };
            Func<string, bool> isLink = p => Directory.Exists(p) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0;
            Action end = () =>
            {
                foreach (var made in new[] { junction, textsLink })
                {
                    try { if (isLink(made)) Directory.Delete(made); }  // only the link, never what it points to
                    catch (Exception e) { check(false, "removing the junction " + made + ": " + e.Message); }
                }
                check(!Directory.Exists(junction) && !Directory.Exists(textsLink), "the junctions are removed");
                try { File.WriteAllText(Path.Combine(dir, "selftest.log"), (good ? "OK" : "FAILED") + Environment.NewLine + string.Join(Environment.NewLine, lines) + Environment.NewLine + Environment.NewLine + LogText()); }
                catch (Exception) { }
                Close();
            };
            Func<string> romfsState = () =>  // the game files' count, size and newest change, so any write would show
            {
                long n = 0, bytes = 0, newest = 0;
                foreach (var src in new[] { romfsSrc, textsSrc })
                    if (src != null)
                        foreach (var f in new DirectoryInfo(src).EnumerateFiles("*", SearchOption.AllDirectories))
                        {
                            n++;
                            bytes += f.Length;
                            newest = Math.Max(newest, f.LastWriteTimeUtc.Ticks);
                        }
                return n + " files, " + bytes + " bytes, newest " + new DateTime(newest, DateTimeKind.Utc).ToString("u");
            };
            Func<string, string, bool> link = (at, to) =>
            {
                using (var mk = Process.Start(new ProcessStartInfo("cmd.exe", "/c mklink /J " + Q(at) + " " + Q(to)) { UseShellExecute = false, CreateNoWindow = true }))
                    mk.WaitForExit();
                return isLink(at);
            };
            try
            {
                if (settingsFile != null) LoadSettingsFile(settingsFile, true);
                romfsSrc = Path.GetFullPath(romfsSrc).TrimEnd('\\');
                if (!Directory.Exists(Path.Combine(romfsSrc, "Pack")))
                {
                    check(false, "no game files in " + romfsSrc);
                    end();
                    return;
                }
                if (Directory.Exists(home))
                {
                    check(false, home + " is there already: the test starts from a folder without it");
                    end();
                    return;
                }
                Directory.CreateDirectory(Path.Combine(game, "bin"));
                check(link(junction, romfsSrc) && Directory.Exists(Path.Combine(junction, "Pack")), "the scratch game's romfs is a junction to " + romfsSrc);
                string texts = Path.Combine(Path.GetDirectoryName(romfsSrc), "texts");
                if (Directory.Exists(texts) && link(textsLink, texts)) textsSrc = texts;
                check(textsSrc != null, "its texts (Longshot's own text copies) is a junction to " + texts);
                var js = new JavaScriptSerializer();
                Func<string, string, string, bool, Dictionary<string, object>> build = (folder, version, channel, def) => new Dictionary<string, object>
                    { { "id", version }, { "name", version }, { "folder", folder }, { "version", version }, { "channel", channel }, { "default", def } };
                File.WriteAllText(Path.Combine(home, "builds.json"), js.Serialize(new Dictionary<string, object> { { "format", 1 }, { "home", home }, { "builds", new List<object> {
                    build(Path.Combine(home, "builds", "stable", "v3.0.0"), "v3.0.0", "stable", false), build(game, "v3.1.0", "stable", true) } } }));
                string before = romfsState();

                // finding the game
                check(LongshotGame.Migrated(stale) == home, "a gone game folder (builds\\rc) under a launcher folder moves to the launcher folder");
                check(LongshotGame.Migrated(game) == null && LongshotGame.Migrated(home) == null, "a game folder or a launcher folder stays as it is");
                var g = LongshotGame.Find(home);
                check(g.Folder == game && g.Default && g.Version == "v3.1.0" && g.Home == home, "the launcher folder: its default build, " + g.Folder + " (" + g.Version + ")");
                g = LongshotGame.Find(game);
                check(g.Folder == game && g.Picked && g.Home == home, "a game folder: itself, with the launcher folder above it");
                check(LongshotGame.Find(junction).Folder == game, "a game's romfs folder: its game folder");
                check(LongshotGame.Find(stale).Folder == game, "a gone game folder: the launcher's default build");
                check(LongshotGame.Find(dir).Folder == "", "a folder with no game and no launcher folder above: none");
                // A second launcher folder of tiny fakes (empty romfs\Pack). With no default we get the newest stable
                // build, and a moved portable launcher folder (builds.json's paths point elsewhere) finds its builds
                // where it is now.
                string home2 = Path.Combine(dir, "LongshotHome2");
                foreach (var v in new[] { @"stable\v1.0.0", @"stable\v1.10.0", @"stable\v1.9.0", @"beta\v2.0.0" })
                    Directory.CreateDirectory(Path.Combine(home2, "builds", v, "romfs", "Pack"));
                string elsewhere = @"Z:\Moved\LongshotLauncher-data";
                File.WriteAllText(Path.Combine(home2, "builds.json"), js.Serialize(new Dictionary<string, object> { { "home", elsewhere }, { "builds", new List<object> {
                    build(elsewhere + @"\builds\stable\v1.0.0", "v1.0.0", "stable", false), build(elsewhere + @"\builds\stable\v1.10.0", "v1.10.0", "stable", false),
                    build(elsewhere + @"\builds\stable\v1.9.0", "v1.9.0", "stable", false), build(elsewhere + @"\builds\beta\v2.0.0", "v2.0.0", "beta", false) } } }));
                g = LongshotGame.Find(home2);
                check(g.Folder == Path.Combine(home2, "builds", "stable", "v1.10.0") && !g.Default, "no default build: the newest stable one (v1.10.0 over v1.9.0 and beta v2.0.0), in the moved launcher folder: " + g.Folder);
                File.WriteAllText(Path.Combine(home2, "builds.json"), "not json");
                g = LongshotGame.Find(home2);
                check(g.Folder == Path.Combine(home2, "builds", "stable", "v1.10.0"), "an unreadable builds.json: the newest stable build folder under builds: " + g.Folder);
                Directory.Delete(home2, true);  // only tiny fakes, no junction in it

                // the seed, as a mod
                Directory.CreateDirectory(Path.Combine(home, "user"));
                File.WriteAllText(Path.Combine(home, "user", "mods.json"), "{\n  \"mods\": [\n    { \"id\": \"" + LongshotGame.ModName + "\", \"enabled\": false }\n  ]\n}\n");
                left.Targets.Pick("longshot");
                left.PathBox.Text = stale;
                check(left.RomfsTitle.Contains(@"builds\stable\v3.1.0") && left.RomfsTitle.Contains("default"), "the note under the box names the build: " + left.RomfsTitle);
                left.Seed.Text = seed;
                Run(null, ok =>
                {
                    check(ok, "Make the seed: made, and installed as a Longshot mod");
                    check(Clean(left.PathBox.Text) == home, "the gone builds\\rc in the box became the launcher folder: " + left.PathBox.Text);
                    check(LogText().Contains("Longshot Launcher 1.2.0 keeps each version"), "the log says why the folder changed");
                    check(LogText().Contains("switched off (" + Path.Combine(home, "user", "mods.json")), "the log notices the mod switched off on Longshot's Mods tab");
                    string list = Path.Combine(mod, "randomizer_files.txt"), record = Path.Combine(mod, "rando-of-time.json");
                    check(File.Exists(record) && File.Exists(list) && File.Exists(Path.Combine(mod, "seed.txt")), "the mod folder has its record, file list and seed.txt: " + mod);
                    var rels = File.Exists(list) ? File.ReadAllLines(list).Where(r => r.Trim() != "").ToList() : new List<string>();
                    int present = rels.Count(r => File.Exists(Long(Path.Combine(mod, "romfs", r))));
                    check(rels.Count > 0 && present == rels.Count, present + " of the " + rels.Count + " listed files are in the mod's romfs");
                    check(InstalledSeed(record) == seed, "the mod's record names seed " + seed);
                    // The release ships no game text (no data\longshot_pc_text.json), so the PC wording is
                    // worked out from the game. The mod's text then differs from the patch's where Longshot
                    // rewords things (the microphone help line).
                    string usen = Path.Combine("Mals", "USen.Product.110.sarc.zs"), patchText = Path.Combine(root, "out", "seed_" + seed, "patch", usen);
                    bool shipsPc = File.Exists(Path.Combine(root, "data", "longshot_pc_text.json"));
                    check(File.Exists(patchText) && File.Exists(Path.Combine(mod, "romfs", usen))
                          && !File.ReadAllBytes(patchText).SequenceEqual(File.ReadAllBytes(Path.Combine(mod, "romfs", usen))),
                          "the mod's English text carries Longshot's PC wording (" + (shipsPc ? "from data\\longshot_pc_text.json" : "worked out from the game") + ")");
                    check(!File.Exists(Path.Combine(game, "rando-of-time", "installed.json")), "no install into the game files (installed.json)");
                    check(romfsState() == before, "the game files (romfs) are unchanged: " + before);
                    var status = new Thread(() =>
                    {
                        Step("Test: the mod's status", "tools/install.py mod-status " + Q(junction));
                        string said = lastStepLine ?? "";
                        SafeInvoke(() =>
                        {
                            check(said.StartsWith("installed as a mod:") && said.Contains(" files, complete") && !said.Contains("CHANGED"), "mod-status: " + said);
                            var plan = PlanRestore("longshot", home);
                            check(plan.HasMod && !plan.OldInstall && plan.Message.Contains(mod) && plan.Message.Contains(seed), "the restore question names the seed and its mod folder");
                            Restore(false, ok2 =>
                            {
                                check(ok2, "Restore the original game: done");
                                check(!Directory.Exists(mod), "the mod folder is gone");
                                check(romfsState() == before, "the game files (romfs) are still unchanged");
                                var after = PlanRestore("longshot", home);
                                check(after.Nothing != null, "afterwards there's nothing to restore");
                                end();
                            });
                        });
                    }) { IsBackground = true };
                    status.Start();
                });
            }
            catch (Exception e)
            {
                check(false, "error: " + e.Message);
                end();
            }
        }

        static string Clean(string p)
        {
            p = (p ?? "").Trim().Trim('"');
            string t = p.TrimEnd('\\', '/');
            return t.Length == 2 && t[1] == ':' ? t + "\\" : t;  // a drive root ("F:\", an SD card) keeps its backslash
        }

        // The game files the patch is built from. Longshot keeps them extracted (<game folder>\romfs, LongshotGame).
        // Rekarina reads the dump in place, so it uses the romfs box or Longshot's copy, and so do consoles and
        // emulators.
        string FindRomfs(string target, string dest)
        {
            string box = Clean(left.RomfsBox.Text);
            if (target == "longshot") return LongshotGame.Find(dest).Romfs;
            if (box != "") return box;
            string ls = LongshotGame.Find(Clean(cfg.LongshotDir) != "" ? Clean(cfg.LongshotDir) : LongshotGame.Hint()).Romfs;
            return ls != "" && Directory.Exists(ls) ? ls : "";
        }

        static string NoLongshotGame(string dest)
        {
            return (dest == "" ? "Longshot's game isn't set" : "There's no Longshot game in " + dest)
                 + ": under \"Where the seed goes\", pick Longshot's launcher folder (the one with builds.json) or a game folder (the one with romfs and bin).";
        }

        // Where a game copy's original files and the install record live. For Longshot that's next to the game, so a
        // new copy of the randomizer finds what an older one installed. Otherwise it's per game copy. An older setup
        // that installed from the randomizer's own folder (original\ + installed.json there) keeps using it.
        // Longshot's store from before the rename (remake-rando next to the game) is used as it is when there's no
        // new one yet.
        string OriginalStore(string target, string romfs)
        {
            if (File.Exists(Path.Combine(root, "installed.json")) && Directory.Exists(Path.Combine(root, "original"))) return null;
            string full = Path.GetFullPath(romfs);
            if (target == "longshot")
            {
                string game = Path.GetDirectoryName(full.TrimEnd('\\'));
                return NewOrOld(Path.Combine(game, "rando-of-time", "original"), Path.Combine(game, "remake-rando", "original"));
            }
            uint h = 2166136261;  // FNV-1a of the folder's path, one store per game copy
            foreach (char c in full.ToLowerInvariant())
            {
                h ^= c;
                h *= 16777619;
            }
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RemakeRandomizer",
                                "originals", h.ToString("x8"), "original");
        }

        static string NewOrOld(string now, string old) { return !Directory.Exists(now) && Directory.Exists(old) ? old : now; }

        // The files the release doesn't ship (the game's text, the tracker's check list) are built from the player's game
        // the first time (tools/release/first_run.py).
        bool FirstRunReady(string romfs)
        {
            var need = new[] { @"data\rando\hints_messages.json", @"data\rando\hints_extra.json", @"data\rando\extras_hints.json",
                               @"tracker\research\checks_proto.json" };
            if (need.All(n => File.Exists(Path.Combine(root, n))) && !ProtoStale()) return true;
            if (Step("Preparing the randomizer from your game's files (only this once)", "tools/release/first_run.py " + Q(romfs), "first_run") == 0) return true;
            Log("The randomizer couldn't read what it needs from your game files (see above).");
            return false;
        }

        // the check list is older than what it's made from (an updated randomizer folder), so first_run.py
        // rebuilds it
        bool ProtoStale()
        {
            try
            {
                var proto = new FileInfo(Path.Combine(root, "tracker", "research", "checks_proto.json"));
                if (!proto.Exists) return true;
                foreach (var rel in new[] { new[] { "tracker", "research", "build_checks.py" }, new[] { "tracker", "research", "mapinfo.py" },
                                            new[] { "data", "rando", "drop_map.json" } })
                {
                    var f = new FileInfo(Path.Combine(root, Path.Combine(rel)));
                    if (f.Exists && f.LastWriteTimeUtc > proto.LastWriteTimeUtc) return true;
                }
            }
            catch (Exception) { }
            return false;
        }

        void Fail(string why, Action<bool> finish)
        {
            Log(why);
            SetStatus(why, Pal.Red);
            finish(false);
        }

        void Run() { Run(null, null); }

        void Run(string forceTarget, Action<bool> done)
        {
            if (worker != null && worker.IsAlive) return;
            view.Commit();
            SaveTarget();
            if (!testing)
            {
                cfg.Save();
                SaveLastSettings();
            }
            Action<bool> finish = ok => { if (done != null) done(ok); };
            string seed = left.Seed.Text.Trim();
            if (!SeedOk(seed))
            {
                Fail("A seed is up to 32 letters, digits, - or _ (the dice makes a new one).", finish);
                return;
            }
            string target = forceTarget ?? cfg.Target, dest = Clean(left.PathBox.Text);
            string moved = target == "longshot" ? LongshotGame.Migrated(dest) : null;
            if (moved != null)  // a Longshot folder typed or kept from before the launcher moved its game
            {
                Log(LongshotMovedNote(dest, moved));
                left.PathBox.Text = moved;
                dest = moved;
                SaveTarget();
                if (!testing) cfg.Save();
            }
            string romfs = FindRomfs(target, dest);
            if (romfs == "" || !Directory.Exists(romfs) || !Directory.Exists(Path.Combine(romfs, "Pack")))
            {
                Fail(target == "longshot" ? NoLongshotGame(dest)
                     : "No game files" + (romfs != "" ? " at '" + romfs + "'" : "") + ": under \"Game files\", pick a dumped romfs folder (the one with Pack, Event, System ... inside).", finish);
                FocusSetup();
                return;
            }
            if (dest == "")
            {
                Fail("Pick the folder the seed goes to (Game & output).", finish);
                FocusSetup();
                return;
            }
            if (target == "rekarina" && !File.Exists(Path.Combine(dest, "Rekarina.exe")))
            {
                Fail("There's no Rekarina.exe in " + dest + ": pick Rekarina's game folder (the one with Rekarina.exe).", finish);
                FocusSetup();
                return;
            }
            stepRomfs = romfs;
            stepOriginal = OriginalStore(target, romfs);
            string final = Path.Combine(root, "out", "seed_" + seed), outDir = final + ".new";
            string settingsPath = Path.Combine(root, "out", "seed_" + seed + "_settings.json");
            try
            {
                Directory.CreateDirectory(Path.Combine(root, "out"));
                File.WriteAllText(settingsPath, SettingsJson());
            }
            catch (Exception e)
            {
                Fail("Can't write in " + Path.Combine(root, "out") + " (" + e.Message + "). Move the randomizer's folder somewhere you can write, such as Documents.", finish);
                return;
            }
            logPanel.SetBusy(true);
            SetStatus("Making seed " + seed + "...", Pal.TextDim);
            runProgress = new RunProgress(RunProgress.Plan(target), cfg.StepSeconds);
            shownProgress = 0; progressFrame = 0; doneFrames = 0; runFinished = runOk = false;
            progressTimer.Start();
            worker = new Thread(() =>
            {
                bool ok = false;
                string patch = Path.Combine(outDir, "patch"), plan = Path.Combine(outDir, "plan.json");
                string result = null, status = null;  // status has the status line's shorter words when it worked
                try
                {
                    if (Directory.Exists(Long(outDir))) Directory.Delete(Long(outDir), true);  // deep patch paths
                    if (!FirstRunReady(romfs))
                    {
                        result = "The randomizer couldn't read your game files (see the log).";
                        return;
                    }
                    if (Step("Making seed " + seed, "tools/rando/generate.py " + Q(outDir) + " --seed " + Q(seed) + " --settings " + Q(settingsPath), "generate") != 0)
                    {
                        result = "The seed couldn't be made (see the log).";
                        Log(result);
                        return;
                    }
                    if (Step("Building the patch", "tools/make_patch.py " + Q(romfs) + " " + Q(patch) + " " + Q(plan), "patch") != 0)
                    {
                        result = "The patch couldn't be built (see the log).";
                        Log(result);
                        return;
                    }
                    // make_patch already writes the cosmetics (same _cosmetics_apply.build, same bytes), so we
                    // don't write them a second time here. The check reads them back from the patch.
                    if (Step("Checking the cosmetics", "tools/rando/parity/_cosmetics_apply.py " + Q(romfs) + " " + Q(patch) + " " + Q(plan) + " --check", "cosmetics_check") != 0)
                    {
                        result = "The cosmetics check failed (see the log).";
                        Log(result);
                        return;
                    }
                    if (Step("Checking the patch", "tools/rando/in_game_check.py " + Q(outDir) + " " + Q(romfs), "check") != 0)
                    {
                        result = "The check found problems: this seed isn't safe to play. Try another seed, and report it.";
                        Log(result);
                        return;
                    }
                    if (!File.Exists(Path.Combine(outDir, "tracker.json")))
                        Log("Note: this seed's tracker file wasn't written (see above), so the tracker can't show its checks.");
                    // only now does the new seed replace an older one of the same number (its spoiler, its tracker file)
                    if (Directory.Exists(Long(final))) Directory.Delete(Long(final), true);
                    Directory.Move(Long(outDir), Long(final));
                    outDir = final;
                    patch = Path.Combine(final, "patch");
                    lastOut = final;
                    if (target == "longshot")
                    {
                        // Longshot 3.1.0 loads mods from <game folder>\mods\<name>\romfs, so the seed goes there
                        // and the game's own files stay untouched (tools/install.py mod-install). A seed put in them
                        // the old way comes out first.
                        if (Running(target))
                        { result = "Longshot is running: close the game, then press \"Make the seed\" again."; Log(result); return; }
                        var game = LongshotGame.Find(dest);
                        if (Step("Installing the seed as a Longshot mod", "tools/install.py mod-install " + Q(romfs) + " " + Q(patch), "install") != 0)
                        { result = "The seed couldn't be installed: " + (string.IsNullOrEmpty(lastStepLine) ? "see the log." : lastStepLine); Log(result); return; }
                        try { File.WriteAllText(Path.Combine(game.ModDir, "seed.txt"), "Seed " + seed + Environment.NewLine + "Made " + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + Environment.NewLine + "Files: " + final + Environment.NewLine); }
                        catch (Exception) { }
                        result = "Done: seed " + seed + " is installed as a Longshot mod, in " + game.ModDir + ". Longshot's own game files are untouched. "
                               + "Start the game from Longshot and begin a NEW file. Longshot's Mods tab (F1 in game) lists the seed; "
                               + "\"Restore the original game\" takes it out.";
                        Log(result);
                        status = "Done: seed " + seed + " is a Longshot mod. Begin a NEW file.";
                        if (CodePatches(final).Count > 0)
                        {
                            // Longshot compiles the game's code ahead of time, so a code patch only gets in when
                            // the game is built again (its Builder applies the mod's exefs patches then)
                            Log("This seed also changes the game's code (its exefs folder): build the game again in the Longshot launcher before you play, "
                                + "or that part isn't in the game. Longshot's Mods tab (F1 in game) says whether it is.");
                            status = "Done: seed " + seed + " is a Longshot mod. Build the game again in Longshot, then begin a NEW file.";
                        }
                        string off = game.SwitchedOff();
                        if (off != null)
                        {
                            Log("Note: Longshot's Mods tab has the randomizer's mod switched off (" + off + "). Switch it on there (F1 in game), or the game starts without the seed.");
                            status = "Done, but Longshot has the seed's mod switched off: switch it on in its Mods tab (F1).";
                        }
                    }
                    else
                    {
                        if (target == "rekarina" && Process.GetProcessesByName("Rekarina").Length > 0)
                        { result = "Rekarina is running: close it, then press \"Make the seed\" again."; Log(result); return; }
                        string modRoot;
                        if (target == "rekarina")
                        {
                            // Rekarina's fast text (rekarina.ini fast_text) is an overlay of the message archives,
                            // and a mod's archives win over it, so we take the same pauses out of the seed's
                            // (rekarina_text.py).
                            if (Step("Matching Rekarina's text speed", "tools/release/rekarina_text.py " + Q(patch) + " " + Q(dest), "rekarina") != 0)
                            { result = "Couldn't match Rekarina's fast text (see the log)."; Log(result); return; }
                            if (runProgress != null) runProgress.Start("export");
                            modRoot = ModRoot(target, dest, AppId);
                            ReplaceMod(modRoot, Files(patch, false)[AppId], false);
                        }
                        else
                        {
                            if (runProgress != null) runProgress.Start("export");
                            modRoot = ExportLayered(target, dest, patch);
                        }
                        File.WriteAllText(Path.Combine(modRoot, "seed.txt"), "Seed " + seed + Environment.NewLine + "Made " + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + Environment.NewLine + "Files: " + final + Environment.NewLine);
                        int code = PlaceCodePatches(target, dest, modRoot, final);
                        if (runProgress != null) runProgress.End("export", true);
                        result = "Done: the mod is in " + modRoot + " (it replaces the previous seed). Begin a NEW file.";
                        if (code > 0)
                            result += target == "rekarina" ? " It also changes the game's code: Rekarina rebuilds the game by itself at its next start."
                                    : " It also changes the game's code, in " + CodePatchDir(target, dest, modRoot) + ".";
                        Log(result);
                        // the status line is one line, so it names the place in short and the full path is in the log
                        status = "Done: seed " + seed + (target == "sdcard" ? " is on the SD card" : target == "rekarina" ? " is in Rekarina's mods folder"
                                 : " is in the emulator's mod folder") + ". Begin a NEW file.";
                    }
                    ok = true;
                }
                catch (Exception e)
                {
                    result = "Error: " + e.Message;
                    Log(result);
                }
                finally
                {
                    try
                    {
                        string where = Directory.Exists(Long(outDir)) ? outDir : final;
                        if (Directory.Exists(Long(where))) File.WriteAllText(Path.Combine(where, "app.log"), LogText());
                    }
                    catch (Exception) { }
                    string r = ok && status != null ? status : result;
                    bool k = ok;
                    SafeInvoke(() =>
                    {
                        logPanel.SetBusy(false);
                        SetStatus(r ?? (k ? "Done" : "Stopped"), k ? Pal.Green : Pal.Red);
                        if (k && runProgress != null)  // each step's time, next run's weights (half old, half new)
                        {
                            foreach (var kv in runProgress.Took)
                            {
                                double old;
                                cfg.StepSeconds[kv.Key] = cfg.StepSeconds.TryGetValue(kv.Key, out old) && old > 0 ? (old + kv.Value) / 2 : kv.Value;
                            }
                            if (!testing) cfg.Save();
                        }
                        runFinished = true; runOk = k;
                        
                        finish(k);
                    });
                }
            }) { IsBackground = true };
            worker.Start();
        }

        // Paths past Windows' old 260-character limit (a deep mod folder) work with the \\?\ form.
        static string Long(string p)
        {
            p = Path.GetFullPath(p);
            return p.StartsWith(@"\\?\") ? p : (p.StartsWith(@"\\") ? @"\\?\UNC\" + p.Substring(2) : @"\\?\" + p);
        }

        // LayeredFS (a Switch console's SD card, an emulator's mod folders). Longshot's romfs holds the game and its
        // add-on content (the Master Quest DLC) together, with the DLC's files under AoC1/ (add-on content index 1).
        // On a Switch they belong to the DLC's own title, which is the application id + 0x1000 + the index
        // (0400486024DEC000 -> 0400486024DED001, see tools/release/layeredfs.py). Every other file is the game's.
        const string AppId = "0400486024DEC000", ModName = "Rando of Time";
        static readonly string[] NotGameFiles = { "patch_report.json", "rekarina_fast_text.txt" };

        static string AocTitle(int index)
        {
            ulong app = Convert.ToUInt64(AppId, 16);
            return ((app & ~0xFFFUL) + 0x1000UL + (ulong)index).ToString("X16");
        }

        // {title: [(source file, path inside that title's romfs)]}. With `split` false, AoC1/ stays a folder of the
        // game's romfs, since Rekarina reads the dump the way Longshot extracts it.
        static Dictionary<string, List<KeyValuePair<string, string>>> Files(string patch, bool split)
        {
            var by = new Dictionary<string, List<KeyValuePair<string, string>>> { { AppId, new List<KeyValuePair<string, string>>() } };
            string root = Long(Path.GetFullPath(patch));
            foreach (var f in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
            {
                string rel = f.Substring(root.Length).TrimStart(Path.DirectorySeparatorChar);
                if (NotGameFiles.Contains(rel)) continue;
                string title = AppId, inner = rel;
                int cut = rel.IndexOf(Path.DirectorySeparatorChar);
                int n;
                if (split && cut > 3 && rel.StartsWith("AoC") && int.TryParse(rel.Substring(3, cut - 3), out n))
                {
                    title = AocTitle(n);
                    inner = rel.Substring(cut + 1);
                }
                if (!by.ContainsKey(title)) by[title] = new List<KeyValuePair<string, string>>();
                by[title].Add(new KeyValuePair<string, string>(f, inner));
            }
            return by;
        }

        // Exports the seed as a LayeredFS mod, the game's files in its title's folder and the DLC's in the DLC
        // title's, and returns the game's mod folder. A title with no files this time still loses the previous
        // seed's (its manifest).
        string ExportLayered(string target, string dest, string patch)
        {
            var by = Files(patch, true);
            if (!by.ContainsKey(AocTitle(1))) by[AocTitle(1)] = new List<KeyValuePair<string, string>>();
            string gameRoot = null;
            foreach (var kv in by)
            {
                string modRoot = ModRoot(target, dest, kv.Key);
                if (kv.Key == AppId) gameRoot = modRoot;
                if (kv.Value.Count == 0 && !File.Exists(Path.Combine(modRoot, "randomizer_files.txt"))) continue;
                ReplaceMod(modRoot, kv.Value, target == "sdcard");
                if (kv.Key != AppId && kv.Value.Count > 0) Log(kv.Value.Count + " Master Quest (DLC) files went to " + modRoot + ".");
            }
            return gameRoot;
        }

        // Where a target keeps the seed's files for a title (the game's, AppId, or the Master Quest DLC's). That's
        // Rekarina's mods folder (just one, with AoC1\ inside), the SD card's atmosphere\contents\<title>, or an
        // emulator's mod folder for the game with the DLC's next to it (<mods>\<DLC title>\Rando of Time).
        static string ModRoot(string target, string dest, string title)
        {
            if (target == "rekarina") return Path.Combine(dest, "mods", ModName);
            if (target == "sdcard") return Path.Combine(dest, "atmosphere", "contents", title);
            return title == AppId ? Path.Combine(dest, ModName)
                 : Path.Combine(Path.GetDirectoryName(dest.TrimEnd(Path.DirectorySeparatorChar)) ?? dest, title, ModName);
        }

        // A seed's code patches: make_patch writes them to <seed>\exefs beside the patch (romfs) folder, IPSwitch
        // .pchtxt files for the game's code (tools/rando/parity/_extras_wheel.py). Longshot gets them through
        // tools/install.py mod-install and applies them when the game is built again. Rekarina and the emulators read
        // a mod's exefs folder as it is. Atmosphere only reads IPS files, one per build id, in
        // atmosphere\exefs_patches\<name>, so for the SD card each one is turned into that.
        static List<string> CodePatches(string seedDir)
        {
            string d = Path.Combine(seedDir, "exefs");
            if (!Directory.Exists(d)) return new List<string>();
            return Directory.GetFiles(d, "rando_of_time*.pchtxt").OrderBy(f => f, StringComparer.OrdinalIgnoreCase).ToList();
        }

        static string CodePatchDir(string target, string dest, string modRoot)
        {
            return target == "sdcard" ? Path.Combine(dest, "atmosphere", "exefs_patches", ModName) : Path.Combine(modRoot, "exefs");
        }

        // Takes out the code patches a previous seed put there (ours only, by name), so a seed without one doesn't
        // keep the old one.
        static void RemoveCodePatches(string dir, bool ips)
        {
            if (!Directory.Exists(dir)) return;
            foreach (var f in Directory.GetFiles(dir, ips ? "*.ips" : "rando_of_time*.pchtxt")) File.Delete(f);
            RemoveIfEmpty(dir);
        }

        // (build id, IPS32 bytes) of a .pchtxt: its lines "OFFSET BYTES" between @enabled and @stop, offsets shifted
        // by "@flag offset_shift" (an IPS offset counts the NSO header, as Atmosphere and Longshot read them).
        static KeyValuePair<string, byte[]> PchtxtToIps(string text)
        {
            string bid = null;
            int shift = 0;
            bool on = false;
            var ips = new List<byte>(Encoding.ASCII.GetBytes("IPS32"));
            foreach (var raw in text.Split('\n'))
            {
                string line = raw.Split(new[] { "//" }, StringSplitOptions.None)[0].Trim();
                if (line == "") continue;
                if (line.StartsWith("@stop")) break;
                if (line.StartsWith("@nsobid-")) { bid = line.Substring(8).Trim(); continue; }
                if (line.StartsWith("@enabled")) { on = true; continue; }
                if (line.StartsWith("@disabled")) { on = false; continue; }
                if (line.StartsWith("@flag"))
                {
                    var f = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                    if (f.Length >= 3 && f[1] == "offset_shift")
                        shift = f[2].StartsWith("0x") ? Convert.ToInt32(f[2].Substring(2), 16) : int.Parse(f[2]);
                    continue;
                }
                if (line.StartsWith("@") || !on) continue;
                var parts = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length != 2 || parts[1].Length % 2 != 0) throw new InvalidDataException("not a patch line: " + line);
                uint off = Convert.ToUInt32(parts[0], 16) + (uint)shift;
                var body = new byte[parts[1].Length / 2];
                for (int i = 0; i < body.Length; i++) body[i] = Convert.ToByte(parts[1].Substring(2 * i, 2), 16);
                for (int at = 0; at < body.Length; at += 0xFFFF)
                {
                    int n = Math.Min(0xFFFF, body.Length - at);
                    uint o = off + (uint)at;
                    ips.AddRange(new[] { (byte)(o >> 24), (byte)(o >> 16), (byte)(o >> 8), (byte)o, (byte)(n >> 8), (byte)n });
                    ips.AddRange(body.Skip(at).Take(n));
                }
            }
            if (bid == null) throw new InvalidDataException("no @nsobid line");
            ips.AddRange(Encoding.ASCII.GetBytes("EEOF"));
            return new KeyValuePair<string, byte[]>(bid.ToUpperInvariant().PadRight(64, '0'), ips.ToArray());
        }

        // Puts the seed's code patches where the target reads them (none: the previous seed's are taken out).
        int PlaceCodePatches(string target, string dest, string modRoot, string seedDir)
        {
            string dir = CodePatchDir(target, dest, modRoot);
            RemoveCodePatches(dir, target == "sdcard");
            var patches = CodePatches(seedDir);
            if (patches.Count == 0) return 0;
            Directory.CreateDirectory(dir);
            foreach (var p in patches)
            {
                if (target == "sdcard")
                {
                    var ips = PchtxtToIps(File.ReadAllText(p));
                    File.WriteAllBytes(Path.Combine(dir, ips.Key + ".ips"), ips.Value);
                }
                else File.Copy(p, Path.Combine(dir, Path.GetFileName(p)), true);
            }
            Log(patches.Count + " code patch(es) went to " + dir + ".");
            return patches.Count;
        }

        // Puts this seed in a mod folder, removing the previous seed's files (randomizer_files.txt) first. A Switch
        // SD card's romfs folder is shared by every LayeredFS mod for the game, so other mods' files there stay.
        void ReplaceMod(string modRoot, List<KeyValuePair<string, string>> files, bool shared)
        {
            string romfsOut = Path.Combine(modRoot, "romfs"), list = Path.Combine(modRoot, "randomizer_files.txt");
            if (File.Exists(list))
            {
                foreach (var rel in File.ReadAllLines(list))
                {
                    string f = Long(Path.Combine(romfsOut, rel));
                    if (rel.Trim() != "" && File.Exists(f)) File.Delete(f);
                }
            }
            else if (!shared && Directory.Exists(Long(romfsOut))) Directory.Delete(Long(romfsOut), true);  // our own folder
            var written = new List<string>();
            foreach (var kv in files)
            {
                string dst = Long(Path.Combine(romfsOut, kv.Value));
                Directory.CreateDirectory(Path.GetDirectoryName(dst));
                File.Copy(kv.Key, dst, true);
                written.Add(kv.Value);
            }
            Directory.CreateDirectory(Long(modRoot));
            File.WriteAllLines(list, written);
            if (shared && Directory.Exists(Long(romfsOut)))
            {
                int others = Directory.GetFiles(Long(romfsOut), "*", SearchOption.AllDirectories).Length - written.Count;
                if (others > 0) Log(others + " files of other mods are in " + romfsOut + " too: a mod that changes the same game files can clash with the seed.");
            }
        }

        // The tracker's map art and icons come from the player's own game, since nothing of the game ships with
        // the randomizer. They're built once, the first time the tracker opens (tools/tracker/build_data.py assets).
        void OpenTracker()
        {
            string exe = Path.Combine(root ?? "", "tracker", "dist", "RandoOfTimeTracker.exe");
            if (!File.Exists(exe)) exe = Path.Combine(root ?? "", "RandoOfTimeTracker.exe");
            if (!File.Exists(exe))
            {
                Log("The tracker (RandoOfTimeTracker.exe) isn't next to the randomizer.");
                SetStatus("The tracker isn't next to the randomizer.", Pal.Red);
                return;
            }
            string maps = Path.Combine(Path.GetDirectoryName(exe), "data", "maps");
            if (!Directory.Exists(maps) || Directory.GetFiles(maps).Length < 20 || !File.Exists(Path.Combine(maps, "full.txt")))
            {
                if (worker != null && worker.IsAlive) return;
                SaveTarget();
                string romfs = FindRomfs(cfg.Target, Clean(left.PathBox.Text));
                if (romfs == "" || !Directory.Exists(Path.Combine(romfs, "Pack")))
                {
                    Log("The tracker builds its maps from your game files once: set where the seed goes (Longshot) or the game files (romfs) first.");
                    SetStatus("Set the game files first (Game & output): the tracker builds its maps from them once.", Pal.Red);
                    FocusSetup();
                    return;
                }
                left.Tracker.Enabled = false;
                logPanel.SetBusy(true);
                stepRomfs = romfs;
                worker = new Thread(() =>
                {
                    bool ok = false;
                    try
                    {
                        ok = Step("Building the tracker's maps from your game (a few minutes, only this once)",
                                  "tools/tracker/build_data.py assets " + Q(romfs)) == 0;
                        // seeds made before the maps existed get their pins placed again on the drawn art
                        var seeds = SeedFolders();
                        if (ok && seeds.Count > 0)
                            Step("Placing the made seeds' checks on the new maps", "tools/tracker/build_data.py seed " + string.Join(" ", seeds.Select(Q).ToArray()));
                    }
                    catch (Exception e) { Log("Error: " + e.Message); }
                    SafeInvoke(() =>
                    {
                        left.Tracker.Enabled = true;
                        logPanel.SetBusy(false);
                        if (ok)
                        {
                            SetStatus("Tracker maps ready", Pal.Green);
                            OpenTrackerNow(exe);
                        }
                        else
                        {
                            Log("The tracker's maps couldn't be built (see above).");
                            SetStatus("The tracker's maps couldn't be built (see the log).", Pal.Red);
                        }
                    });
                }) { IsBackground = true };
                worker.Start();
                return;
            }
            OpenTrackerNow(exe);
        }

        // every made seed (out\seed_*) with what its tracker file is made from
        List<string> SeedFolders()
        {
            var list = new List<string>();
            try
            {
                string outDir = Path.Combine(root, "out");
                if (Directory.Exists(outDir))
                    foreach (var d in Directory.GetDirectories(outDir, "seed_*"))
                        if (!d.EndsWith(".new") && File.Exists(Path.Combine(d, "spoiler.json")) && File.Exists(Path.Combine(d, "plan.json")))
                            list.Add(d);
            }
            catch (Exception) { }
            return list;
        }

        void OpenTrackerNow(string exe)
        {
            string seedFile = lastOut != null ? Path.Combine(lastOut, "tracker.json") : NewestTrackerFile();
            var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe) };
            var args = new List<string>();
            if (seedFile != null && File.Exists(seedFile)) args.Add(Q(seedFile));
            else Log("No tracker file for the last seed: the tracker opens without one.");
            // Where the chosen game keeps its saves (slot_NN\progress.sav below) and, for Longshot, its log (the live
            // map follows it). For a console or an emulator the player picks the save folder in the tracker.
            SaveTarget();
            string dest = Clean(left.PathBox.Text);
            var game = cfg.Target == "longshot" ? LongshotGame.Find(dest) : null;
            if (game != null && game.Folder != "")
            {
                // the saves are in the launcher folder (user\save) for every build, the log is in the game folder
                string data = game.Home ?? Path.GetDirectoryName(Path.GetDirectoryName(game.Folder));
                string save = data != null ? Path.Combine(data, "user", "save") : "";
                if (!Directory.Exists(save)) save = Path.Combine(game.Folder, "user", "save");  // older Longshot builds
                args.Add("--save " + Q(save));
                args.Add("--log " + Q(Path.Combine(game.Folder, "logs", "longshot_log.txt")));
            }
            else if (cfg.Target == "rekarina" && dest != "")
            {
                args.Add("--save " + Q(Path.Combine(dest, "profile", "save")));
                args.Add("--log \"\"");
            }
            else
            {
                args.Add("--save \"\"");
                args.Add("--log \"\"");
            }
            psi.Arguments = string.Join(" ", args);
            try { Process.Start(psi); }
            catch (Exception e)
            {
                Log("Couldn't open the tracker: " + e.Message);
                SetStatus("Couldn't open the tracker: " + e.Message, Pal.Red);
                return;
            }
            Log("Tracker opened" + (seedFile != null ? " for " + seedFile : "") + ".");
            SetStatus("Tracker opened", Pal.TextDim);
        }

        // Restore
        // "Restore the original game" takes the seed out of where it went.
        // - Longshot 3.1.0 and later: the seed is a mod, <game folder>\mods\Rando of Time, and tools/install.py
        //   mod-remove deletes it (only a folder holding its record). A seed installed the old way, into the game
        //   files (installed.json next to the originals kept by the game, OriginalStore), is put back first with
        //   tools/install.py restore, like mod-install does.
        // - Rekarina, a console's SD card, an emulator: we delete the files the randomizer wrote there, as each mod
        //   folder's randomizer_files.txt lists them (ReplaceMod), so other mods' files stay.
        // It's refused while the game is running, same as installs. We ask first and say plainly what happened after.
        class RestorePlan
        {
            public string Error, Nothing;                          // can't / there's no seed to take out
            public string Heading, Message, OkText, DoneMessage;
            public string Romfs, Store, ModDir;                    // Longshot
            public bool OldInstall, HasMod;                        // Longshot: a seed in the game files / its mod folder
            public readonly List<string> Mods = new List<string>(); // the others: mod folders with a file list
            public int Files;
        }

        static string Where(string target)
        {
            return target == "longshot" ? "Longshot" : target == "rekarina" ? "Rekarina" : target == "sdcard" ? "the Switch" : "the emulator";
        }

        // the seed an install record names (its patch: out\seed_<seed>\patch), or null
        static string InstalledSeed(string record)
        {
            try
            {
                var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(record));
                object patch;
                if (d == null || !d.TryGetValue("patch", out patch) || !(patch is string)) return null;
                string dir = Path.GetFileName(Path.GetDirectoryName(((string)patch).TrimEnd('\\', '/')));
                return dir != null && dir.StartsWith("seed_") ? dir.Substring(5) : null;
            }
            catch (Exception) { return null; }
        }

        RestorePlan PlanRestore(string target, string dest)
        {
            var plan = new RestorePlan();
            if (target == "longshot")
            {
                var game = LongshotGame.Find(dest);
                plan.Romfs = game.Romfs;
                if (game.Folder == "")
                {
                    plan.Error = NoLongshotGame(dest);
                    return plan;
                }
                plan.Store = OriginalStore(target, plan.Romfs);
                string store = plan.Store ?? Path.Combine(root, "original");
                string record = Path.Combine(Path.GetDirectoryName(store), "installed.json");
                plan.ModDir = game.InstalledModDir;
                plan.HasMod = File.Exists(LongshotGame.RecordIn(plan.ModDir)) || File.Exists(Path.Combine(plan.ModDir, "randomizer_files.txt"));
                plan.OldInstall = File.Exists(record) && File.Exists(Path.Combine(store, "SHA256SUMS.txt"));
                if (!plan.HasMod && !plan.OldInstall)
                {
                    plan.Nothing = "There's no seed of this randomizer in Longshot's game, " + game.Folder + ": no " + LongshotGame.ModName
                                 + " mod in its mods folder, and its own game files are as they came. Longshot already plays the vanilla game.";
                    return plan;
                }
                string seed = plan.HasMod ? InstalledSeed(LongshotGame.RecordIn(plan.ModDir)) : InstalledSeed(record);
                string old = plan.OldInstall ? InstalledSeed(record) : null;
                plan.Heading = "Remove the seed from Longshot?";
                plan.OkText = "Remove the seed";
                var msg = new StringBuilder();
                if (plan.HasMod)
                {
                    msg.Append((seed != null ? "Seed " + seed + " is" : "The seed is") + " a Longshot mod: its folder, " + plan.ModDir
                               + ", is deleted. The seed never changed Longshot's own game files, so they stay as they are, and so do other mods.");
                    if (plan.OldInstall)
                        msg.Append("\n\nAn older seed" + (old != null && old != seed ? " (" + old + ")" : "") + " that this randomizer put into the game files "
                                   + "themselves comes out first: Longshot's original files go back in " + plan.Romfs + ".");
                }
                else
                    msg.Append((seed != null ? "Seed " + seed + " was" : "A seed was") + " put into Longshot's game files themselves, as the randomizer did "
                               + "before Longshot had mods: Longshot's original files go back in " + plan.Romfs + ", from the copies kept next to the game.");
                msg.Append("\n\nYour saves stay as they are. Afterwards Longshot plays the vanilla game, with no seed, until you make a new one.");
                if (plan.HasMod) msg.Append(" To play without the seed only for a while, switch it off on Longshot's Mods tab (F1 in game) instead.");
                plan.Message = msg.ToString();
                plan.DoneMessage = (plan.HasMod ? "The seed's mod folder is gone from " + game.Folder + "\\mods" + (plan.OldInstall ? ", and " : ". ") : "")
                                 + (plan.OldInstall ? "Longshot's original game files are back in " + plan.Romfs + (plan.HasMod ? " (an older seed had changed them). " : ". ")
                                                    : "Longshot's own game files were left untouched. ")
                                 + "Other mods are as they were: Longshot plays the vanilla game until you make a new seed.";
                return plan;
            }
            if (dest == "")
            {
                plan.Error = "Pick the folder the seed went to under \"Where the seed goes\" first.";
                return plan;
            }
            var titles = target == "rekarina" ? new[] { AppId } : new[] { AppId, AocTitle(1) };
            foreach (var title in titles)
            {
                string mod = ModRoot(target, dest, title), list = Path.Combine(mod, "randomizer_files.txt");
                if (!File.Exists(list)) continue;
                plan.Mods.Add(mod);
                string romfsOut = Path.Combine(mod, "romfs");
                plan.Files += File.ReadAllLines(list).Count(rel => rel.Trim() != "" && File.Exists(Long(Path.Combine(romfsOut, rel))));
            }
            string where = Where(target);
            if (plan.Mods.Count == 0)
            {
                plan.Nothing = "There's no seed of this randomizer in " + ModRoot(target, dest, AppId) + " (no randomizer_files.txt there): "
                             + where.Substring(0, 1).ToUpperInvariant() + where.Substring(1) + " already plays the game without it.";
                return plan;
            }
            // the folders under where the seed went, named from there since the paths are long (the place
            // is said once)
            string under = dest.TrimEnd('\\') + "\\";
            string folders = plan.Mods.All(m => m.StartsWith(under, StringComparison.OrdinalIgnoreCase))
                           ? dest + " (" + string.Join(" and ", plan.Mods.Select(m => m.Substring(under.Length))) + ")"
                           : string.Join(" and ", plan.Mods);
            plan.Heading = "Remove the seed from " + (target == "sdcard" ? "the SD card" : where) + "?";
            plan.Message = "The " + plan.Files + " files this randomizer put in " + folders + " are deleted, as the list it keeps there "
                         + "(randomizer_files.txt) names them. Other mods' files stay as they are.\n\nYour saves stay as they are. "
                         + "Afterwards " + where + " plays the vanilla game, with no seed, until you make a new one.";
            plan.OkText = "Remove the seed";
            plan.DoneMessage = "The seed's files are gone from " + folders + ". " + where.Substring(0, 1).ToUpperInvariant() + where.Substring(1)
                             + (target == "sdcard" ? " plays the vanilla game with this SD card" : " plays the vanilla game") + "; other mods are as they were.";
            return plan;
        }

        public bool IgnoreRunning;  // --ignore-running, to test on a scratch game folder copy while the real game runs

        bool Running(string target)
        {
            if (IgnoreRunning) return false;
            if (target == "longshot") return Process.GetProcessesByName("longshot").Length > 0;
            if (target == "rekarina") return Process.GetProcessesByName("Rekarina").Length > 0;
            return false;
        }

        static string RunningNote(string target)
        {
            return Where(target) + " is running: close " + (target == "longshot" ? "the game" : "it") + ", then press \"Restore the original game\" again.";
        }

        void Restore() { Restore(true, null); }

        // ask shows the questions and the closing message as dialogs (false when testing with --restore-test)
        void Restore(bool ask, Action<bool> done)
        {
            if (worker != null && worker.IsAlive) return;
            view.Commit();
            SaveTarget();
            if (!testing) cfg.Save();
            Action<bool> finish = ok => { if (done != null) done(ok); };
            string target = cfg.Target;
            var plan = PlanRestore(target, Clean(left.PathBox.Text));
            if (plan.Error != null)
            {
                Fail(plan.Error, finish);
                FocusSetup();
                return;
            }
            if (Running(target))
            {
                Fail(RunningNote(target), finish);
                return;
            }
            if (plan.Nothing != null)
            {
                Log(plan.Nothing);
                SetStatus("Nothing to restore: no seed of this randomizer is there.", Pal.TextDim);
                if (ask) AskDialog.Tell(this, "Nothing to restore", plan.Nothing, ForceDpi);
                finish(true);
                return;
            }
            if (ask && !AskDialog.Confirm(this, plan.Heading, plan.Message, plan.OkText, ForceDpi))
            {
                SetStatus("Nothing changed.", Pal.TextDim);
                return;
            }
            left.Restore.Enabled = false;
            logPanel.SetBusy(true);
            SetStatus("Removing the seed...", Pal.TextDim);
            worker = new Thread(() =>
            {
                bool ok = false;
                string result = null;
                try
                {
                    if (Running(target))
                    {
                        result = RunningNote(target);
                        Log(result);
                        return;
                    }  // started while asking
                    if (target == "longshot")
                    {
                        stepRomfs = plan.Romfs;
                        stepOriginal = plan.Store;
                        if (plan.OldInstall && Step("Putting back Longshot's original game files (a seed installed the old way)", "tools/install.py restore " + Q(plan.Romfs)) != 0)
                        { result = "The original game files couldn't be put back: " + (string.IsNullOrEmpty(lastStepLine) ? "see the log." : lastStepLine); Log(result); return; }
                        if (plan.HasMod && Step("Removing the seed's Longshot mod", "tools/install.py mod-remove " + Q(plan.Romfs)) != 0)
                        { result = "The seed's mod couldn't be removed: " + (string.IsNullOrEmpty(lastStepLine) ? "see the log." : lastStepLine); Log(result); return; }
                    }
                    else
                    {
                        Log("== Removing the seed from " + Where(target));
                        foreach (var mod in plan.Mods) RemoveMod(mod);
                    }
                    ok = true;
                    result = "Done: the game is back to vanilla. " + plan.DoneMessage;
                    Log(result);
                }
                catch (Exception e)
                {
                    result = "Error: " + e.Message;
                    Log(result);
                }
                finally
                {
                    string r = result;
                    bool k = ok;
                    SafeInvoke(() =>
                    {
                        left.Restore.Enabled = true;
                        logPanel.SetBusy(false);
                        SetStatus(k ? "The game is back to vanilla." : r ?? "Stopped", k ? Pal.Green : Pal.Red);
                        if (ask)
                        {
                            if (k) AskDialog.Tell(this, "The game is back to vanilla", plan.DoneMessage, ForceDpi);
                            else AskDialog.Tell(this, "Couldn't restore the original game", (r ?? "It stopped.") + "\n\nThe log has the details.", ForceDpi);
                        }
                        finish(k);
                    });
                }
            }) { IsBackground = true };
            worker.Start();
        }

        // Deletes the files a mod folder's randomizer_files.txt lists (only under its romfs folder), then the
        // folders that held only them, the list and seed.txt. The mod folder itself only goes if nothing else is
        // left in it.
        void RemoveMod(string modRoot)
        {
            string romfsOut = Path.GetFullPath(Path.Combine(modRoot, "romfs")), list = Path.Combine(modRoot, "randomizer_files.txt");
            var dirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int n = 0;
            foreach (var rel in File.ReadAllLines(list))
            {
                if (rel.Trim() == "") continue;
                string f = Path.GetFullPath(Path.Combine(romfsOut, rel));
                // a list only names files inside it
                if (!f.StartsWith(romfsOut + "\\", StringComparison.OrdinalIgnoreCase)) continue;
                if (File.Exists(Long(f)))
                {
                    File.Delete(Long(f));
                    n++;
                }
                for (string d = Path.GetDirectoryName(f); d != null && d.Length > romfsOut.Length; d = Path.GetDirectoryName(d)) dirs.Add(d);
            }
            foreach (var d in dirs.OrderByDescending(x => x.Length)) RemoveIfEmpty(d);
            RemoveIfEmpty(romfsOut);
            foreach (var f in new[] { list, Path.Combine(modRoot, "seed.txt") }) if (File.Exists(f)) File.Delete(f);
            // the seed's code patches: in the mod's exefs folder, or for the SD card Atmosphere's exefs_patches
            RemoveCodePatches(Path.Combine(modRoot, "exefs"), false);
            string contents = Path.GetDirectoryName(Path.GetFullPath(modRoot).TrimEnd('\\'));
            if (contents != null && string.Equals(Path.GetFileName(contents), "contents", StringComparison.OrdinalIgnoreCase)
                && string.Equals(Path.GetFileName(modRoot.TrimEnd('\\')), AppId, StringComparison.OrdinalIgnoreCase))
                RemoveCodePatches(Path.Combine(Path.GetDirectoryName(contents), "exefs_patches", ModName), true);
            RemoveIfEmpty(modRoot);
            Log("  removed   " + n + " files from " + romfsOut);
        }

        static void RemoveIfEmpty(string d)
        {
            try { if (Directory.Exists(Long(d)) && !Directory.EnumerateFileSystemEntries(Long(d)).Any()) Directory.Delete(Long(d)); }
            catch (Exception) { }
        }

        // For testing: where the seed goes (--target T [--path P]), the restore without its dialogs
        // (--restore-test LOG), and a dialog as it would open (--dialog restore|restored|nothing).
        public void TestTarget(string target, string path)
        {
            if (target != null) left.Targets.Pick(target);
            if (path != null) left.PathBox.Text = path;
        }

        public void RestoreTest(string logFile)
        {
            testing = true;
            Restore(false, ok =>
            {
                try { File.WriteAllText(logFile, (ok ? "OK" : "FAILED") + Environment.NewLine + LogText()); } catch (Exception) { }
                Close();
            });
        }

        public AskDialog TestDialog(string kind)
        {
            SaveTarget();
            var plan = PlanRestore(cfg.Target, Clean(left.PathBox.Text));
            AskDialog d;
            if (plan.Error != null) d = new AskDialog("Restore the original game", plan.Error, "OK", null, ButtonKind.Primary);
            else if (plan.Nothing != null || kind == "nothing") d = new AskDialog("Nothing to restore", plan.Nothing ?? "", "OK", null, ButtonKind.Primary);
            else if (kind == "restored") d = new AskDialog("The game is back to vanilla", plan.DoneMessage, "OK", null, ButtonKind.Primary);
            else d = new AskDialog(plan.Heading, plan.Message, plan.OkText, "Cancel", ButtonKind.Primary);
            d.ForceDpi = ForceDpi;
            return d;
        }

        // The seed made last (out\seed_*\tracker.json), so the tracker opens on it after a restart too.
        string NewestTrackerFile()
        {
            string outDir = Path.Combine(root, "out");
            if (!Directory.Exists(outDir)) return null;
            return Directory.GetDirectories(outDir, "seed_*").Where(d => !d.EndsWith(".new"))
                .Select(d => Path.Combine(d, "tracker.json")).Where(File.Exists)
                .OrderByDescending(File.GetLastWriteTimeUtc).FirstOrDefault();
        }
    }

    static class Program
    {
        // --screenshot FILE [PAGE] [--scroll PX|end] [--dialog restore|restored|nothing]: render the window to a PNG
        //   and exit. PAGE is a settings page's number, setup, log, or search:WORDS. --scroll scrolls the page that
        //   far first. --dialog shows the restore question, its closing message or its "nothing to restore" over the
        //   window.
        // --dpi N: laid out as at that scaling (96 = 100%, 144 = 150%, 192 = 200%). --size W H is then at 96 DPI.
        // --target longshot|rekarina|sdcard|emulator [--path DIR]: where the seed goes, for the test (not remembered).
        // --restore-test LOG: "Restore the original game" for that target without its dialogs. LOG gets OK or FAILED
        //   and the log. [--ignore-running] runs it on a scratch copy of a game folder while the real game runs.
        // --selftest DIR SEED [--load FILE]: make SEED as a LayeredFS mod in DIR and write DIR\selftest.log.
        //   [--longshot ROMFS] does the Longshot mod path instead, on a scratch launcher folder in DIR whose game's
        //   romfs is a junction to ROMFS: finding the game, a gone builds\rc moved, install, mod-status, restore
        //   (SelfTestLongshot). [--frames FRAMEDIR] shows the window and saves it every 1.5 s while it works, and
        //   --scroll left:N|left:end scrolls the left column after 6 frames, like --scroll does for a settings page.
        // --export-settings IN OUT: what the app would hand the generator for a settings file.
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var form = new MainWindow();
            int di = Array.IndexOf(args, "--dpi");  // N lays it out as on a screen at that scaling (144 = 150%)
            if (di >= 0 && di + 1 < args.Length) form.ForceDpi = int.Parse(args[di + 1]);
            int zi = Array.IndexOf(args, "--size");  // W H (at 96 DPI), to try the window at a laptop's size
            if (zi >= 0 && zi + 2 < args.Length)
            {
                int zw = int.Parse(args[zi + 1]), zh = int.Parse(args[zi + 2]);
                if (form.ForceDpi > 0)
                {
                    form.MinimumSize = new Size(1, 1);
                    form.Size = new Size(zw * form.ForceDpi / 96, zh * form.ForceDpi / 96);
                }
                else form.SetLogicalSize(zw, zh, Math.Min(zw, 900), Math.Min(zh, 600));
            }
            int gi = Array.IndexOf(args, "--target"), pi = Array.IndexOf(args, "--path");
            string testTarget = gi >= 0 && gi + 1 < args.Length ? args[gi + 1] : null;
            string testPath = pi >= 0 && pi + 1 < args.Length ? args[pi + 1] : null;
            form.IgnoreRunning = Array.IndexOf(args, "--ignore-running") >= 0 && Array.IndexOf(args, "--restore-test") >= 0;
            int ri = Array.IndexOf(args, "--restore-test");
            if (ri >= 0 && ri + 1 < args.Length)
            {
                string log = args[ri + 1];
                form.NoMemory();
                form.WindowState = FormWindowState.Minimized; form.ShowInTaskbar = false;
                form.Shown += (s, e) => { form.TestTarget(testTarget, testPath); form.RestoreTest(log); };
                Application.Run(form);
                return;
            }
            int si = Array.IndexOf(args, "--screenshot"), ti = Array.IndexOf(args, "--selftest");
            int ei = Array.IndexOf(args, "--export-settings");
            if (ei >= 0 && ei + 2 < args.Length)
            {
                form.ExportSettings(args[ei + 1], args[ei + 2]);
                return;
            }
            if (si >= 0 && si + 1 < args.Length)
            {
                string file = args[si + 1];
                string tab = si + 2 < args.Length && !args[si + 2].StartsWith("--") ? args[si + 2] : "0";
                int sci = Array.IndexOf(args, "--scroll");
                string scroll = sci >= 0 && sci + 1 < args.Length ? args[sci + 1] : null;
                int dli = Array.IndexOf(args, "--dialog");
                string dialogKind = dli >= 0 && dli + 1 < args.Length ? args[dli + 1] : null;
                form.NoMemory();
                form.Shown += (s, e) =>
                {
                    if (testTarget != null || testPath != null) form.TestTarget(testTarget, testPath);
                    form.SelectTab(tab);
                    if (scroll != null) form.TestScroll(scroll);
                    var t = new System.Windows.Forms.Timer { Interval = 1200 };
                    t.Tick += (s2, e2) =>
                    {
                        t.Stop();
                        using (var bmp = new Bitmap(form.Width, form.Height))
                        {
                            form.DrawToBitmap(bmp, new Rectangle(0, 0, form.Width, form.Height));
                            if (dialogKind != null)  // the dialog over the window, where it would open
                            {
                                var dialog = form.TestDialog(dialogKind);
                                dialog.StartPosition = FormStartPosition.Manual;
                                dialog.Show(form);
                                dialog.Location = new Point(form.Left + (form.Width - dialog.Width) / 2, form.Top + (form.Height - dialog.Height) / 2);
                                Application.DoEvents();
                                using (var ob = new Bitmap(dialog.Width, dialog.Height))
                                using (var g = Graphics.FromImage(bmp))
                                {
                                    dialog.DrawToBitmap(ob, new Rectangle(0, 0, dialog.Width, dialog.Height));
                                    using (var shade = new SolidBrush(Color.FromArgb(70, 0, 0, 0))) g.FillRectangle(shade, 0, 0, bmp.Width, bmp.Height);
                                    g.DrawImage(ob, dialog.Left - form.Left, dialog.Top - form.Top, dialog.Width, dialog.Height);
                                }
                                dialog.Close();
                            }
                            bmp.Save(file, System.Drawing.Imaging.ImageFormat.Png);
                        }
                        form.Close();
                    };
                    t.Start();
                };
            }
            else if (ti >= 0 && ti + 2 < args.Length)
            {
                string dir = args[ti + 1], seed = args[ti + 2];
                int li = Array.IndexOf(args, "--load"), fi = Array.IndexOf(args, "--frames");
                string load = li >= 0 && li + 1 < args.Length ? args[li + 1] : null;
                string frames = fi >= 0 && fi + 1 < args.Length ? args[fi + 1] : null;
                if (frames == null)
                {
                    form.WindowState = FormWindowState.Minimized;
                    form.ShowInTaskbar = false;
                }
                else  // --frames DIR keeps the window up, on top, and saves its pixels on screen to DIR\frame_NNN.png
                {     // every 1.5 s (DrawToBitmap would stack overlapping child controls the wrong way round)
                    Directory.CreateDirectory(frames);
                    form.TopMost = true;
                    int n = 0;
                    var ft = new System.Windows.Forms.Timer { Interval = 1500 };
                    ft.Tick += (s2, e2) =>
                    {
                        var r = form.Bounds;
                        using (var bmp = new Bitmap(r.Width, r.Height))
                        {
                            using (var g = Graphics.FromImage(bmp)) g.CopyFromScreen(r.Location, Point.Empty, r.Size);
                            bmp.Save(Path.Combine(frames, string.Format("frame_{0:000}.png", n++)), System.Drawing.Imaging.ImageFormat.Png);
                        }
                    };
                    int sci2 = Array.IndexOf(args, "--scroll");
                    string scroll2 = sci2 >= 0 && sci2 + 1 < args.Length ? args[sci2 + 1] : null;
                    if (scroll2 != null) ft.Tick += (s3, e3) => { if (n == 6) form.TestScroll(scroll2); };
                    form.Shown += (s2, e2) => ft.Start();
                }
                int lsi = Array.IndexOf(args, "--longshot");
                string lsRomfs = lsi >= 0 && lsi + 1 < args.Length ? args[lsi + 1] : null;
                form.Shown += (s, e) => { if (lsRomfs != null) form.SelfTestLongshot(dir, seed, load, lsRomfs); else form.SelfTest(dir, seed, load); };
            }
            Application.Run(form);
        }
    }
}
