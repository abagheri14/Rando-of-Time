// The seed file the randomizer writes next to its patch (tracker.json, spoiler-free). It has the maps, every check
// of the seed with its spot on the game's own map art and the save flags that say it's done, and the items to show.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;

namespace RandoOfTimeTracker
{
    public class MapInfo
    {
        public string Id, Title, Area, Image, Age, Floor;
        public bool Dungeon;
        public List<string> Levels = new List<string>();
        public Place Place;      // the place it is shown under (a dungeon's floors share one)
        public string Chip;      // its name among its place's maps ("Floor 1", "Basement 2"), when the place has several
        public int Done, All;    // its checks, counted once per save change
        public int Avail;        // its checks not done and in logic now (all open ones while the logic isn't known)
    }

    // A place in the list: one field map, or a dungeon with all its floors, or the checks without a map spot.
    public class Place
    {
        public string Name, Section;
        public readonly List<MapInfo> Maps = new List<MapInfo>();
        public readonly List<Check> Checks = new List<Check>();
        public int Done, All, Avail;

        public void Recount()
        {
            foreach (var m in Maps) m.Done = m.All = m.Avail = 0;
            int d = 0, a = 0;
            foreach (var c in Checks)
            {
                bool done = c.Done || c.Manual, av = !done && c.Reach;
                if (done) d++;
                if (av) a++;
                if (c.On != null)
                {
                    c.On.All++;
                    if (done) c.On.Done++;
                    if (av) c.On.Avail++;
                }
            }
            Done = d;
            All = Checks.Count;
            Avail = a;
        }

        public override string ToString() { return Name; }
    }

    public class Flag
    {
        public string Type;   // "b64" is a placement hash in the save's Bool64bitKey list, "bit" an element of a saved
        public ulong Hash;    // bool array, "bool" a named saved flag, "nbool" one that's done once it's false,
                              // "count" a number in saved flags (Bits, low bit first) that's done at Index or more
        public List<string> Bits;
        public string Name;
        public int Index;
    }

    public class Check
    {
        public int Id;
        public string Name, Kind, Map, Region, Area;
        public double X, Y;
        public bool HasSpot;
        public List<Flag> Flags = new List<Flag>();
        public bool Done, Manual;
        public bool Reach = true;  // in logic now with what the player has (true while the logic isn't known)
        public string Item;   // only once the spoiler is opened
        public MapInfo On;    // its map (null: no spot, listed under "Other checks")
        public Place Place;
    }

    public class ItemInfo
    {
        public string Name, Icon, Group, Pouch, Bool;
        public int Max = 1;
        public int Count;
    }

    public class SeedData
    {
        public string Path, Folder, Seed, Title, SpoilerPath;
        // the checks' map spots are in the game's 2000x1440 map pixels times this (0.5 for older seeds)
        public double MapScale = 0.5;
        public const int NativeW = 2000, NativeH = 1440;
        public const string OtherName = "Other checks";
        public List<Place> Places = new List<Place>();
        public Dictionary<string, MapInfo> MapById = new Dictionary<string, MapInfo>();
        public int Done, Avail;
        public bool LogicOn;  // the seed's logic answered, so Reach is known for every check
        public List<string> Settings = new List<string>();
        public List<MapInfo> Maps = new List<MapInfo>();
        public List<Check> Checks = new List<Check>();
        public List<ItemInfo> Items = new List<ItemInfo>();
        public Dictionary<string, string> LevelMap = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        static string S(Dictionary<string, object> d, string k)
        {
            object v;
            return d.TryGetValue(k, out v) && v != null ? Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture) : null;
        }

        static double D(Dictionary<string, object> d, string k)
        {
            object v;
            return d.TryGetValue(k, out v) && v != null ? Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture) : double.NaN;
        }

        static IEnumerable<Dictionary<string, object>> List(Dictionary<string, object> d, string k)
        {
            object v;
            if (d.TryGetValue(k, out v) && v is ArrayList)
                foreach (var x in (ArrayList)v)
                    if (x is Dictionary<string, object>) yield return (Dictionary<string, object>)x;
        }

        static List<string> Strings(Dictionary<string, object> d, string k)
        {
            object v;
            var out_ = new List<string>();
            if (d.TryGetValue(k, out v) && v is ArrayList)
                foreach (var x in (ArrayList)v)
                    if (x is string) out_.Add((string)x);
            return out_;
        }

        public static SeedData Load(string path)
        {
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var root = js.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            var s = new SeedData { Path = path, Folder = System.IO.Path.GetDirectoryName(path) };
            s.Seed = S(root, "seed") ?? "?";
            s.Title = S(root, "title") ?? ("Seed " + s.Seed);
            string sp = S(root, "spoiler");
            if (sp != null) s.SpoilerPath = System.IO.Path.Combine(s.Folder, sp);
            double ms = D(root, "map_scale");
            if (!double.IsNaN(ms) && ms > 0) s.MapScale = ms;
            object st;
            if (root.TryGetValue("settings", out st) && st is ArrayList)
                foreach (var x in (ArrayList)st) s.Settings.Add(Convert.ToString(x));
            foreach (var m in List(root, "maps"))
            {
                var mi = new MapInfo
                {
                    Id = S(m, "id"), Title = S(m, "title"), Area = S(m, "area") ?? S(m, "title"),
                    Image = S(m, "image"), Age = S(m, "age"), Floor = S(m, "floor"),
                    Dungeon = S(m, "kind") == "dungeon"
                };
                object lv;
                if (m.TryGetValue("levels", out lv) && lv is ArrayList)
                    foreach (var x in (ArrayList)lv)
                    {
                        mi.Levels.Add(Convert.ToString(x));
                        s.LevelMap[Convert.ToString(x)] = mi.Id;
                    }
                s.Maps.Add(mi);
            }
            int id = 0;
            foreach (var c in List(root, "checks"))
            {
                var ch = new Check
                {
                    Id = id++, Name = S(c, "name"), Kind = S(c, "kind") ?? "check", Map = S(c, "map"),
                    Region = S(c, "region"), Area = S(c, "area"), X = D(c, "x"), Y = D(c, "y")
                };
                ch.HasSpot = ch.Map != null && !double.IsNaN(ch.X) && !double.IsNaN(ch.Y);
                foreach (var f in List(c, "flags"))
                {
                    var fl = new Flag { Type = S(f, "t"), Name = S(f, "n") ?? S(f, "a") };
                    string h = S(f, "h");
                    if (h != null) fl.Hash = ulong.Parse(h);
                    string i = S(f, "i") ?? S(f, "min");
                    if (i != null) fl.Index = int.Parse(i);
                    var bits = Strings(f, "bits");
                    if (bits.Count > 0) fl.Bits = bits;
                    ch.Flags.Add(fl);
                }
                s.Checks.Add(ch);
            }
            foreach (var it in List(root, "items"))
            {
                var ii = new ItemInfo
                {
                    Name = S(it, "name"), Icon = S(it, "icon"), Group = S(it, "group") ?? "Items",
                    Pouch = S(it, "pouch"), Bool = S(it, "bool")
                };
                string mx = S(it, "max");
                if (mx != null) ii.Max = int.Parse(mx);
                s.Items.Add(ii);
            }
            s.BuildPlaces();
            s.Recount();
            return s;
        }

        // floors from the bottom up, as the game's dungeon maps name them
        static readonly string[] FloorOrder = { "B4", "B3", "B2", "B1", "1F", "2F", "3F", "4F", "5F", "6F" };

        static string PlaceName(MapInfo m)
        {
            string a = m.Area ?? m.Title ?? m.Id;
            if (m.Dungeon && !string.IsNullOrEmpty(m.Floor) && a.EndsWith(" " + m.Floor)) return a.Substring(0, a.Length - m.Floor.Length - 1);
            if (a.EndsWith(" (later)")) return a.Substring(0, a.Length - 8);
            return a;
        }

        static string ChipName(MapInfo m, string place)
        {
            string f = m.Floor;
            if (!string.IsNullOrEmpty(f))
            {
                if (f.Length == 2 && f[0] == 'B' && char.IsDigit(f[1])) return "Basement " + f[1];
                if (f.Length == 2 && f[1] == 'F' && char.IsDigit(f[0])) return "Floor " + f[0];
                return f;
            }
            string t = (m.Area ?? m.Title ?? "");
            if (t.StartsWith(place)) t = t.Substring(place.Length);
            t = t.Trim().Trim('(', ')').Trim();
            return t.Length == 0 ? "Main" : char.ToUpper(t[0]) + t.Substring(1);
        }

        static int FloorIndex(MapInfo m)
        {
            int i = m.Floor == null ? -1 : Array.IndexOf(FloorOrder, m.Floor);
            return i < 0 ? 100 : i;
        }

        // the places: each field map on its own, each dungeon with its floors, then the checks without a spot
        void BuildPlaces()
        {
            var byName = new Dictionary<string, Place>();
            foreach (var m in Maps)
            {
                if (m.Id != null) MapById[m.Id] = m;
                string n = PlaceName(m);
                Place p;
                if (!byName.TryGetValue(n, out p))
                {
                    p = new Place { Name = n, Section = m.Dungeon ? "Dungeons" : "Overworld" };
                    byName[n] = p;
                    Places.Add(p);
                }
                p.Maps.Add(m);
                m.Place = p;
            }
            foreach (var p in Places)
            {
                var sorted = p.Maps.Select((m, i) => new { m, i }).OrderBy(x => FloorIndex(x.m)).ThenBy(x => x.i).Select(x => x.m).ToList();
                p.Maps.Clear();
                p.Maps.AddRange(sorted);
                if (p.Maps.Count > 1)
                    foreach (var m in p.Maps)
                        m.Chip = ChipName(m, p.Name);
            }
            var other = new Place { Name = OtherName, Section = "Elsewhere" };
            foreach (var c in Checks)
            {
                MapInfo m;
                if (c.HasSpot && c.Map != null && MapById.TryGetValue(c.Map, out m))
                {
                    c.On = m;
                    c.Place = m.Place;
                    m.Place.Checks.Add(c);
                }
                else
                {
                    c.Place = other;
                    other.Checks.Add(c);
                }
            }
            var cmp = StringComparer.CurrentCultureIgnoreCase;
            var ordered = Places.Where(p => p.Section == "Overworld").OrderBy(p => p.Name, cmp)
                .Concat(Places.Where(p => p.Section == "Dungeons").OrderBy(p => p.Name, cmp)).ToList();
            Places.Clear();
            Places.AddRange(ordered);
            if (other.Checks.Count > 0) Places.Add(other);
        }

        /// <summary>Counts done / all for every place and map, and for the seed. Runs once per save change (or a
        /// mark by hand).</summary>
        public void Recount()
        {
            int d = 0, a = 0;
            foreach (var p in Places)
            {
                p.Recount();
                d += p.Done;
                a += p.Avail;
            }
            Done = d;
            Avail = a;
        }

        public Place FindPlace(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            foreach (var p in Places) if (string.Equals(p.Name, name, StringComparison.OrdinalIgnoreCase)) return p;
            foreach (var m in Maps)
                if (string.Equals(m.Area, name, StringComparison.OrdinalIgnoreCase) || string.Equals(m.Title, name, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(m.Id, name, StringComparison.OrdinalIgnoreCase)) return m.Place;
            return null;
        }

        public MapInfo FindMap(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            foreach (var m in Maps)
                if (string.Equals(m.Area, name, StringComparison.OrdinalIgnoreCase) || string.Equals(m.Title, name, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(m.Id, name, StringComparison.OrdinalIgnoreCase)) return m;
            return null;
        }

        /// <summary>The spoiler's item per check name (OoTR's spoiler: "locations": {name: item or {item: ...}}).</summary>
        public Dictionary<string, string> ReadSpoiler()
        {
            var outd = new Dictionary<string, string>();
            if (SpoilerPath == null || !File.Exists(SpoilerPath)) return outd;
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var root = js.Deserialize<Dictionary<string, object>>(File.ReadAllText(SpoilerPath));
            object locs;
            if (!root.TryGetValue("locations", out locs) || !(locs is Dictionary<string, object>)) return outd;
            foreach (var kv in (Dictionary<string, object>)locs)
            {
                var d = kv.Value as Dictionary<string, object>;
                outd[kv.Key] = d != null ? S(d, "item") : Convert.ToString(kv.Value);
            }
            return outd;
        }

        public IEnumerable<string> Areas()
        {
            return Maps.Select(m => m.Area).Distinct();
        }
    }
}
