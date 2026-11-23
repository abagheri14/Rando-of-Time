// Reads the remake's save files (GameData format, as Tears of the Kingdom): slot_NN/progress.sav.
//   0x00 u32 magic 0x01020304, 0x08 u32 offset of the value area, entries of 8 bytes (u32 key, u32 value) from 0x20
//   up to the value area. An entry with key 0 starts a type section (its value is the type index).
//   Bool(0) Int(2) UInt(20) Float(4) Enum(6) hold their value inline; arrays hold an offset into the value area
//   (u32 count, then the elements; a bool array's elements are bits packed into u32 words, lowest bit first).
//   Bool64bitKey(32): one entry whose value is the offset of a 0-ended list of the u64 keys that are TRUE. They're
//   placement hashes from the level files (a pot broken, a token taken...). An opened chest isn't one of them
//   (chests are AlwaysRespawn). It's the saved Bool IsTreasureBoxOpen.<placement hash>, a member of that GameData
//   struct.
// Keys are murmur3_32 of the GameData name.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace RandoOfTimeTracker
{
    public static class Murmur3
    {
        public static uint Hash(string s)
        {
            byte[] data = Encoding.UTF8.GetBytes(s);
            const uint c1 = 0xcc9e2d51, c2 = 0x1b873593;
            uint h = 0;
            int n = data.Length / 4;
            for (int i = 0; i < n; i++)
            {
                uint k = BitConverter.ToUInt32(data, i * 4);
                k *= c1;
                k = (k << 15) | (k >> 17);
                k *= c2;
                h ^= k;
                h = (h << 13) | (h >> 19);
                h = h * 5 + 0xe6546b64;
            }
            uint t = 0;
            int rem = data.Length & 3, b = n * 4;
            if (rem == 3) t ^= (uint)data[b + 2] << 16;
            if (rem >= 2) t ^= (uint)data[b + 1] << 8;
            if (rem >= 1)
            {
                t ^= data[b];
                t *= c1;
                t = (t << 15) | (t >> 17);
                t *= c2;
                h ^= t;
            }
            h ^= (uint)data.Length;
            h ^= h >> 16;
            h *= 0x85ebca6b;
            h ^= h >> 13;
            h *= 0xc2b2ae35;
            h ^= h >> 16;
            return h;
        }
    }

    public class SaveFile
    {
        public const uint Magic = 0x01020304;
        public readonly byte[] Data;
        public readonly Dictionary<int, Dictionary<uint, uint>> Sections = new Dictionary<int, Dictionary<uint, uint>>();
        public readonly HashSet<ulong> Bool64 = new HashSet<ulong>();
        public readonly string Path;
        public readonly DateTime Written;

        SaveFile(string path, byte[] data, DateTime written)
        {
            Path = path;
            Data = data;
            Written = written;
            if (data.Length < 0x28 || BitConverter.ToUInt32(data, 0) != Magic)
                throw new InvalidDataException("not a save (or caught mid-write)");
            int valueOff = (int)BitConverter.ToUInt32(data, 8);
            if (valueOff <= 0x20 || valueOff > data.Length) throw new InvalidDataException("bad value-area offset");
            Dictionary<uint, uint> cur = null;
            for (int p = 0x20; p + 8 <= valueOff; p += 8)
            {
                uint k = BitConverter.ToUInt32(data, p), v = BitConverter.ToUInt32(data, p + 4);
                if (k == 0)
                {
                    cur = new Dictionary<uint, uint>();
                    Sections[(int)v] = cur;
                }
                else if (cur != null) cur[k] = v;
            }
            Dictionary<uint, uint> b64;
            if (Sections.TryGetValue(32, out b64))
                foreach (uint off in b64.Values)
                    for (int p = (int)off; p + 8 <= data.Length; p += 8)
                    {
                        ulong key = BitConverter.ToUInt64(data, p);
                        if (key == 0) break;
                        Bool64.Add(key);
                    }
        }

        /// <summary>Reads a save, retrying briefly if the game is writing it.</summary>
        public static SaveFile Load(string path)
        {
            Exception last = null;
            for (int i = 0; i < 4; i++)
            {
                try
                {
                    DateTime t = File.GetLastWriteTime(path);
                    byte[] d;
                    using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                    {
                        d = new byte[fs.Length];
                        int got = 0;
                        while (got < d.Length)
                        {
                            int r = fs.Read(d, got, d.Length - got);
                            if (r <= 0) break;
                            got += r;
                        }
                    }
                    return new SaveFile(path, d, t);
                }
                catch (Exception e)
                {
                    last = e;
                    System.Threading.Thread.Sleep(150);
                }
            }
            throw new IOException(path + ": unreadable save", last);
        }

        uint? Inline(int type, string name)
        {
            Dictionary<uint, uint> sec;
            uint v;
            if (Sections.TryGetValue(type, out sec) && sec.TryGetValue(Murmur3.Hash(name), out v)) return v;
            return null;
        }

        public bool? Bool(string name) { var v = Inline(0, name); return v == null ? (bool?)null : v.Value != 0; }
        public int? Int(string name) { var v = Inline(2, name); return v == null ? (int?)null : unchecked((int)v.Value); }

        /// <summary>Element i of a saved bool array, or null when the array isn't in this save.</summary>
        public bool? BoolArray(string name, int i)
        {
            var off = Inline(1, name);
            if (off == null) return null;
            int o = (int)off.Value;
            if (o + 4 > Data.Length) return null;
            int n = (int)BitConverter.ToUInt32(Data, o);
            if (i < 0 || i >= n) return null;
            int w = o + 4 + 4 * (i / 32);
            if (w + 4 > Data.Length) return null;
            return ((BitConverter.ToUInt32(Data, w) >> (i % 32)) & 1) != 0;
        }

        public int PouchCount(string actor)
        {
            return Int("PouchData." + actor + ".StockNum") ?? 0;
        }
    }
}
