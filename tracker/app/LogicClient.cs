// tools/tracker/logic_server.py rebuilds the seed once, in the randomizer's Python process. Every time the save
// changes we send it the done checks and item counts, and OoTR's search answers with the reachable checks in a
// fraction of a second, using the seed's settings and tricks, Link's age and the time of day.
// Only one request is out at a time. If more saves come in while it runs, only the newest state waits in line.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RandoOfTimeTracker
{
    public class LogicClient : IDisposable
    {
        public enum Phase { Off, Starting, Ready, Working, Failed }

        public Phase State = Phase.Off;
        public string Why = "";                 // what Off or Failed means, for the status line
        public int Checks;                      // the checks the server's world holds
        public DateTime AnsweredAt, SentAt;
        public double LastMs, StartMs;
        public event Action<HashSet<string>> Answer;  // the not-done checks in logic now
        public event Action Changed;                   // State or Why changed

        readonly Control ui;
        Process proc;
        StreamWriter input;
        int nextId, outId = -1;                 // the question out (-1: none)
        string waiting;                          // the newest state while one is out
        string seedFolder;
        readonly LinkedList<string> errTail = new LinkedList<string>();
        readonly JavaScriptSerializer js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        readonly Stopwatch since = new Stopwatch();

        public static string ServerScript;      // for testing, another server (--logic-server FILE)

        public LogicClient(Control owner) { ui = owner; }

        /// <summary>The randomizer's folder (where tools/tracker/logic_server.py is). The tracker's exe sits in its
        /// tracker\dist, and a copy somewhere else looks a few folders up.</summary>
        public static string FindRoot()
        {
            string d = AppDomain.CurrentDomain.BaseDirectory;
            for (int i = 0; i < 5 && !string.IsNullOrEmpty(d); i++)
            {
                if (File.Exists(Path.Combine(d, "tools", "tracker", "logic_server.py"))) return d;
                d = Path.GetDirectoryName(d.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            }
            return null;
        }

        void Set(Phase p, string why)
        {
            if (State == p && Why == why) return;
            State = p;
            Why = why ?? "";
            if (Changed != null) Changed();
        }

        public bool Live { get { return State == Phase.Ready || State == Phase.Working; } }

        public void Start(string folder)
        {
            Stop();
            seedFolder = folder;
            if (ServerScript == null && !File.Exists(Path.Combine(folder, "settings_used.json")))
            {
                // a seed made before the randomizer saved the settings it used, so there's nothing to rebuild its
                // logic from
                Set(Phase.Off, "This seed was made before the tracker could follow a seed's logic. "
                               + "Make it again (same seed number and settings) to see what's in logic.");
                return;
            }
            string root = FindRoot();
            if (root == null && ServerScript == null)
            {
                Set(Phase.Off, "The randomizer's logic isn't next to this tracker (tools\\tracker\\logic_server.py).");
                return;
            }
            if (root == null) root = AppDomain.CurrentDomain.BaseDirectory;
            string py = Path.Combine(root, "python", "python.exe");
            if (!File.Exists(py)) py = "python";
            string script = ServerScript ?? Path.Combine(root, "tools", "tracker", "logic_server.py");
            var psi = new ProcessStartInfo(py, "-s " + Q(script) + " " + Q(folder))
            {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
            };
            // the randomizer's own Python, cut off from the player's PYTHON* settings like the randomizer runs it
            var env = psi.EnvironmentVariables;
            foreach (var k in env.Keys.Cast<string>().ToList())
                if (k.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase) || k.StartsWith("RANDO_", StringComparison.OrdinalIgnoreCase)) env.Remove(k);
            env["PYTHONHASHSEED"] = "0";
            env["PYTHONIOENCODING"] = "utf-8";
            env["PYTHONNOUSERSITE"] = "1";
            var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
            try { p.Start(); }
            catch (Exception e)
            {
                Set(Phase.Off, "Couldn't start the randomizer's Python (" + py + "): " + e.Message);
                return;
            }
            try { p.PriorityClass = ProcessPriorityClass.BelowNormal; } catch (Exception) { }  // the game comes first
            proc = p;
            input = new StreamWriter(p.StandardInput.BaseStream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
            outId = -1;
            waiting = null;
            AnsweredAt = DateTime.MinValue;
            lock (errTail) errTail.Clear();
            since.Restart();
            Set(Phase.Starting, "Reading the seed's logic...");
            var me = p;
            var t = new Thread(() => ReadLoop(me)) { IsBackground = true, Name = "logic" };
            t.Start();
            p.ErrorDataReceived += (s, e) =>
            {
                if (e.Data == null) return;
                lock (errTail) { errTail.AddLast(e.Data); while (errTail.Count > 12) errTail.RemoveFirst(); }
            };
            p.BeginErrorReadLine();
        }

        static string Q(string s) { return "\"" + s.TrimEnd('\\') + "\""; }

        void ReadLoop(Process p)
        {
            try
            {
                string line;
                while ((line = p.StandardOutput.ReadLine()) != null)
                {
                    Dictionary<string, object> d;
                    try { d = js.Deserialize<Dictionary<string, object>>(line); }
                    catch (Exception) { continue; }  // a stray print, not an answer
                    if (d == null) continue;
                    Post(() => Handle(p, d));
                }
            }
            catch (Exception) { }
            Post(() =>
            {
                if (p != proc) return;
                string tail;
                lock (errTail) tail = errTail.LastOrDefault(x => x.Trim().Length > 0);
                Set(Phase.Failed, "The logic stopped" + (tail != null ? ": " + tail.Trim() : "."));
                proc = null;
                input = null;
                outId = -1;
            });
        }

        void Post(Action a)
        {
            try { if (!ui.IsDisposed && ui.IsHandleCreated) ui.BeginInvoke(a); } catch (Exception) { }
        }

        void Handle(Process p, Dictionary<string, object> d)
        {
            if (p != proc) return;  // an answer from a seed closed since
            object v;
            if (d.TryGetValue("ready", out v))
            {
                if (true.Equals(v))
                {
                    if (d.TryGetValue("checks", out v) && v != null) Checks = Convert.ToInt32(v);
                    StartMs = since.Elapsed.TotalMilliseconds;
                    Set(Phase.Ready, "");
                    SendWaiting();
                }
                else
                {
                    string err = d.TryGetValue("error", out v) && v != null ? Convert.ToString(v) : "unknown";
                    // a seed made before the randomizer saved the settings it used is expected, so say it plainly and
                    // don't treat it as an error
                    if (err.Contains("settings_used.json")) Set(Phase.Off, "This seed was made before the tracker could follow a seed's logic. "
                                                               + "Make it again (same seed number and settings) to see what's in logic.");
                    else Set(Phase.Failed, err);
                }
                return;
            }
            if (!d.TryGetValue("id", out v) || v == null || Convert.ToInt32(v) != outId) return;
            outId = -1;
            var names = new HashSet<string>();
            if (d.TryGetValue("available", out v) && v is ArrayList)
                foreach (var x in (ArrayList)v) names.Add(Convert.ToString(x));
            if (d.TryGetValue("ms", out v) && v != null) LastMs = Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture);
            AnsweredAt = DateTime.Now;
            if (waiting == null) Set(Phase.Ready, "");
            if (Answer != null) Answer(names);
            SendWaiting();
        }

        /// <summary>Asks which checks are in logic with these done and these items (the tracker's names and counts).</summary>
        public void Ask(IEnumerable<string> done, Dictionary<string, int> inventory)
        {
            if (proc == null) return;
            waiting = js.Serialize(new Dictionary<string, object> { { "done", done.ToList() }, { "inventory", inventory }, { "buyable", true } });
            if (State == Phase.Ready || State == Phase.Working) SendWaiting();
        }

        void SendWaiting()
        {
            if (waiting == null || outId >= 0 || input == null) return;
            int id = ++nextId;
            string body = waiting;
            waiting = null;
            try
            {
                input.WriteLine("{\"id\": " + id + ", " + body.Substring(1));
                outId = id;
                SentAt = DateTime.Now;
                Set(Phase.Working, "");
            }
            catch (Exception e) { Set(Phase.Failed, "Couldn't reach the logic: " + e.Message); }
        }

        public void Stop()
        {
            var p = proc;
            proc = null;
            input = null;
            outId = -1;
            waiting = null;
            if (p == null) return;
            try { p.StandardInput.Close(); } catch (Exception) { }
            try { if (!p.WaitForExit(300)) p.Kill(); } catch (Exception) { }
            try { p.Dispose(); } catch (Exception) { }
            Set(Phase.Off, "");
        }

        /// <summary>Waits (pumping the window's messages) until an answer is in or the time is up. Used by the
        /// screenshot mode.</summary>
        public bool WaitIdle(int ms)
        {
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < ms)
            {
                Application.DoEvents();
                if (State == Phase.Ready && outId < 0 && waiting == null && AnsweredAt != DateTime.MinValue) return true;
                if (State == Phase.Failed || State == Phase.Off) return false;
                Thread.Sleep(15);
            }
            return false;
        }

        public void Dispose() { Stop(); }
    }
}
