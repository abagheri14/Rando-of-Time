// What the tracker watches. The save folder gives the newest progress.sav of any slot, read again whenever the
// game writes it. Longshot's log gives the level and age on every map change, and hearts and Gold Skulltulas
// from its status line. For other emulators you pick their save folder (the slot_NN/progress.sav layout is the
// game's own), and the log is optional.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace RandoOfTimeTracker
{
    public class SaveWatcher
    {
        public string Root;
        public string Slot;  // null = the newest slot
        string lastPath;
        DateTime lastTime;
        long lastLen;

        public string CurrentPath { get { return lastPath; } }

        // Newer Longshot builds keep their saves in %APPDATA%\Longshot\save\<account>\slot_NN after their save
        // import, and Hookshot, which Longshot came from, uses %APPDATA%\Hookshot\save. Older ones use
        // LongshotLauncher-data\user\save. For a Longshot save folder (or one holding no save) we look in all of
        // them and the newest save wins. Another game's folder (an emulator's) is read on its own, so a Longshot
        // save never stands in for it.
        IEnumerable<string> Roots()
        {
            var roots = new List<string>();
            if (!string.IsNullOrEmpty(Root)) roots.Add(Root);
            bool longshot = string.IsNullOrEmpty(Root) || Root.IndexOf("longshot", StringComparison.OrdinalIgnoreCase) >= 0
                            || Root.IndexOf("hookshot", StringComparison.OrdinalIgnoreCase) >= 0 || !HasSave(Root);
            if (longshot)
            {
                string app = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                foreach (var name in new[] { "Longshot", "Hookshot" }) roots.Add(Path.Combine(app, name, "save"));
            }
            return roots.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase);
        }

        static bool HasSave(string root)
        {
            try { return Directory.Exists(root) && Directory.EnumerateFiles(root, "progress.sav", SearchOption.AllDirectories).Any(); }
            catch (Exception) { return false; }
        }

        public string Newest()
        {
            try
            {
                var files = Roots().SelectMany(r => Directory.GetFiles(r, "progress.sav", SearchOption.AllDirectories));
                if (Slot != null) files = files.Where(f => string.Equals(Path.GetFileName(Path.GetDirectoryName(f)), Slot, StringComparison.OrdinalIgnoreCase));
                return files.OrderByDescending(File.GetLastWriteTimeUtc).FirstOrDefault();
            }
            catch (Exception) { return null; }
        }

        /// <summary>The newest save when it changed since the last call, else null.</summary>
        public SaveFile Poll(bool force = false)
        {
            string p = Newest();
            if (p == null) return null;
            var fi = new FileInfo(p);
            if (!force && p == lastPath && fi.LastWriteTimeUtc == lastTime && fi.Length == lastLen) return null;
            try
            {
                var s = SaveFile.Load(p);
                lastPath = p;
                lastTime = fi.LastWriteTimeUtc;
                lastLen = fi.Length;
                return s;
            }
            catch (Exception) { return null; }
        }
    }

    public class LogWatcher
    {
        public string PathName;
        long pos = -1;
        static readonly Regex MapRe = new Regex(@"\] map: (\S+) \((child|adult)\)");
        static readonly Regex StatusRe = new Regex(@"discord: the status: (.*?) / \S+ ([\d.]+)/(\d+) · \S+ (\d+) · \S+ (\d+)");
        public string Level, Age, AreaLabel;
        public double Hearts = double.NaN;
        public int MaxHearts, Skulltulas = -1;
        public bool GameRunning;

        /// <summary>Reads what the log gained; true if the level changed.</summary>
        public bool Poll()
        {
            if (string.IsNullOrEmpty(PathName) || !File.Exists(PathName)) return false;
            string oldLevel = Level;
            try
            {
                using (var fs = new FileStream(PathName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                {
                    if (pos < 0 || fs.Length < pos) pos = Math.Max(0, fs.Length - 4000000);  // first look, or a new log
                    if (fs.Length == pos) return false;
                    fs.Seek(pos, SeekOrigin.Begin);
                    var buf = new byte[fs.Length - pos];
                    int got = fs.Read(buf, 0, buf.Length);
                    pos += got;
                    foreach (var line in Encoding.UTF8.GetString(buf, 0, got).Split('\n'))
                    {
                        var m = MapRe.Match(line);
                        if (m.Success)
                        {
                            Level = m.Groups[1].Value;
                            Age = m.Groups[2].Value;
                        }
                        m = StatusRe.Match(line);
                        if (m.Success)
                        {
                            AreaLabel = m.Groups[1].Value;
                            Hearts = double.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
                            MaxHearts = int.Parse(m.Groups[3].Value);
                            Skulltulas = int.Parse(m.Groups[4].Value);
                        }
                    }
                }
                GameRunning = (DateTime.Now - File.GetLastWriteTime(PathName)).TotalSeconds < 30;
            }
            catch (Exception) { return false; }
            return Level != oldLevel;
        }
    }
}
