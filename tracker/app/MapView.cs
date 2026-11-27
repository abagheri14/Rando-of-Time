// The map panel. It shows the game's own map art at its native 2000x1440, with zoom (mouse wheel), pan (drag)
// and one pin per check at its true spot. A pin is a filled disc in the check kind's colour while it's open, and
// a dim disc with a tick once done. Hovering shows a parchment note with the check (and its item once the
// spoiler is open). A right-click marks a check by hand, for checks the save can't show.
// For speed we keep a few decoded maps (MapStore, 32bpp premultiplied, which is GDI+'s fastest) and keep the map
// scaled to the current zoom around the view, so panning only copies pixels. While the wheel turns the map is
// drawn quickly, and it's redrawn in high quality once it stops.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using RemakeUi;

namespace RandoOfTimeTracker
{
    public static class Theme
    {
        public static Color KindColour(string kind)
        {
            switch (kind)
            {
                case "chest": return Color.FromArgb(214, 92, 214);
                case "gs": return Color.FromArgb(250, 210, 40);
                case "pot": case "flying_pot": return Color.FromArgb(80, 150, 255);
                case "grass": case "grass_always_respawn": return Color.FromArgb(60, 200, 70);
                case "crate": case "small_crate": return Color.FromArgb(210, 140, 60);
                case "beehive": return Color.FromArgb(255, 170, 30);
                case "rock_liftable": case "rock_bombable": case "rock_silver": return Color.FromArgb(160, 150, 140);
                case "tree": return Color.FromArgb(40, 150, 90);
                case "bush": return Color.FromArgb(166, 226, 46);      // leafy lime (grass is a deeper green, trees bluer)
                case "icicle": case "icicle_falling": case "red_ice": return Color.FromArgb(150, 220, 255);
                case "fairy": return Color.FromArgb(248, 150, 206);    // soft pink (chests are the deeper magenta)
                case "freestanding": case "heart": case "boss_heart": return Color.FromArgb(255, 80, 80);
                case "npc": case "song": case "shop": case "scrub": return Color.FromArgb(255, 255, 255);
                default: return Color.FromArgb(230, 230, 230);
            }
        }

        public static string Pretty(string kind)
        {
            if (string.IsNullOrEmpty(kind)) return "Check";
            switch (kind)
            {
                case "gs": return "Gold Skulltula";
                case "npc": return "Gift or reward";
                case "rock_liftable": return "Rock";
                case "rock_bombable": return "Bombable rock";
                case "boss_heart": return "Heart Container";
                case "fairy": return "Fairy";
                case "bush": return "Bush";
            }
            kind = kind.Replace("_", " ");
            return char.ToUpper(kind[0]) + kind.Substring(1);
        }

        // what a hover note says about a check
        public static string Describe(Check c)
        {
            bool done = c.Done || c.Manual;
            string state = c.Manual ? "marked by hand" : done ? "done" : !LogicView.On ? "open" : c.Reach ? "in logic now" : "not in logic yet";
            string s = Pretty(c.Kind) + "  ·  " + state;
            if (LogicView.Locked(c)) s += "\nNeeds items you haven't found yet (by this seed's logic).";
            if (c.Item != null) s += "\nHolds: " + c.Item;
            s += c.Flags.Count == 0 ? "\nThe save can't show this one: right-click to mark it." : c.Manual ? "\nRight-click to unmark." : "";
            return s;
        }
    }

    // A map's decoded art, meaning the part of the image that holds the art. Origin is where it sits in the whole
    // image, Full is the whole image's size, and Art is the art's extent in Bmp's pixels.
    public class MapArt
    {
        public Bitmap Bmp;
        public Point Origin;
        public Size Full;
        public Rectangle Art;
    }

    // The decoded map art. It keeps at most Capacity maps (the least recently shown goes first) and each map's art
    // extent from data/maps/bounds.json, which tools/tracker/build_data.py writes. If that's missing we work it out
    // from the pixels.
    public class MapStore
    {
        public int Capacity = 6;
        readonly string dataDir;
        readonly LinkedList<KeyValuePair<string, MapArt>> lru = new LinkedList<KeyValuePair<string, MapArt>>();
        readonly Dictionary<string, Rectangle> bounds = new Dictionary<string, Rectangle>(StringComparer.OrdinalIgnoreCase);
        public int Loads;

        public MapStore(string dataDir)
        {
            this.dataDir = dataDir;
            try
            {
                string p = Path.Combine(dataDir, "maps", "bounds.json");
                if (File.Exists(p))
                {
                    var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(p));
                    foreach (var kv in d)
                    {
                        var a = kv.Value as System.Collections.ArrayList;
                        if (a == null || a.Count < 6) continue;
                        int x0 = Convert.ToInt32(a[0]), y0 = Convert.ToInt32(a[1]), x1 = Convert.ToInt32(a[2]), y1 = Convert.ToInt32(a[3]);
                        int w = Convert.ToInt32(a[4]), h = Convert.ToInt32(a[5]);
                        // kept relative to the size it was measured at (scaled when the art is another size)
                        bounds[kv.Key] = new Rectangle(x0 * 10000 / Math.Max(1, w), y0 * 10000 / Math.Max(1, h),
                                                       (x1 - x0) * 10000 / Math.Max(1, w), (y1 - y0) * 10000 / Math.Max(1, h));
                    }
                }
            }
            catch (Exception) { }
        }

        public int Count { get { return lru.Count; } }

        /// <summary>A map's art, decoded and kept. Only the art's own extent, the frame around it is the panel's
        /// wood.</summary>
        public MapArt Get(string rel)
        {
            if (string.IsNullOrEmpty(rel)) return null;
            for (var n = lru.First; n != null; n = n.Next)
                if (n.Value.Key == rel)
                {
                    if (n != lru.First)
                    {
                        lru.Remove(n);
                        lru.AddFirst(n);
                    }
                    return n.Value.Value;
                }
            string p = Path.Combine(dataDir, rel);
            if (!File.Exists(p)) return null;
            MapArt art;
            try
            {
                using (var fs = new FileStream(p, FileMode.Open, FileAccess.Read, FileShare.Read))
                using (var img = Image.FromStream(fs, false, false))
                {
                    var full = new Rectangle(0, 0, img.Width, img.Height);
                    var ab = ArtBounds(rel, img);
                    var crop = Rectangle.Inflate(ab, 24, 24);  // the art's faint glow fades out inside this margin
                    crop.Intersect(full);
                    if (crop.Width < 8 || crop.Height < 8) crop = full;
                    var bmp = new Bitmap(crop.Width, crop.Height, PixelFormat.Format32bppPArgb);
                    using (var g = Graphics.FromImage(bmp))
                    {
                        g.CompositingMode = CompositingMode.SourceCopy;
                        g.InterpolationMode = InterpolationMode.NearestNeighbor;
                        g.DrawImage(img, new Rectangle(0, 0, crop.Width, crop.Height), crop.X, crop.Y, crop.Width, crop.Height, GraphicsUnit.Pixel);
                    }
                    art = new MapArt { Bmp = bmp, Origin = crop.Location, Full = full.Size, Art = new Rectangle(ab.X - crop.X, ab.Y - crop.Y, ab.Width, ab.Height) };
                }
            }
            catch (Exception) { return null; }
            Loads++;
            lru.AddFirst(new KeyValuePair<string, MapArt>(rel, art));
            while (lru.Count > Capacity)
            {
                var last = lru.Last;
                lru.RemoveLast();
                last.Value.Value.Bmp.Dispose();
            }
            return art;
        }

        public long Bytes { get { long n = 0; foreach (var kv in lru) n += 4L * kv.Value.Bmp.Width * kv.Value.Bmp.Height; return n; } }

        // where the art is in the whole image (the rest is the empty frame), in the image's pixels
        Rectangle ArtBounds(string rel, Image img)
        {
            string key = Path.GetFileNameWithoutExtension(rel ?? "");
            Rectangle r;
            if (!bounds.TryGetValue(key, out r))
            {
                var b = img as Bitmap;
                r = b != null ? Scan(b) : new Rectangle(0, 0, 10000, 10000);
                bounds[key] = r;
            }
            return new Rectangle((int)((long)r.X * img.Width / 10000), (int)((long)r.Y * img.Height / 10000),
                                 (int)((long)r.Width * img.Width / 10000), (int)((long)r.Height * img.Height / 10000));
        }
        // no bounds.json, so we sample a coarse grid for pixels outside the wood frame
        static Rectangle Scan(Bitmap img)
        {
            int w = img.Width, h = img.Height, step = Math.Max(1, Math.Min(w, h) / 180);
            int x0 = w, y0 = h, x1 = 0, y1 = 0;
            var data = img.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppPArgb);
            try
            {
                var row = new int[w];
                for (int y = 0; y < h; y += step)
                {
                    System.Runtime.InteropServices.Marshal.Copy(data.Scan0 + y * data.Stride, row, 0, w);
                    for (int x = 0; x < w; x += step)
                    {
                        int v = row[x], r = (v >> 16) & 255, gg = (v >> 8) & 255, b = v & 255;
                        if (Math.Abs(r - 46) + Math.Abs(gg - 32) + Math.Abs(b - 20) > 40)
                        {
                            if (x < x0) x0 = x;
                            if (x > x1) x1 = x;
                            if (y < y0) y0 = y;
                            if (y > y1) y1 = y;
                        }
                    }
                }
            }
            finally { img.UnlockBits(data); }
            if (x1 <= x0 || y1 <= y0) return new Rectangle(0, 0, 10000, 10000);
            return new Rectangle(x0 * 10000 / w, y0 * 10000 / h, (x1 - x0 + step) * 10000 / w, (y1 - y0 + step) * 10000 / h);
        }
    }

    public class MapView : UiControl
    {
        static readonly Color Back = Pal.Bg;   // the art's frame colour (46, 32, 20), so the map runs into the panel
        Bitmap image;
        MapInfo map;
        List<Check> checks = new List<Check>();
        double k = 1;                          // image pixels per check map unit
        Rectangle art;                         // the art's extent, image pixels
        PointF origin;                         // where the decoded part sits in the whole map image
        float zoom = 1f, fitZoom = 1f, offX, offY;
        bool userMoved;                        // zoomed or panned by hand, a resize keeps the view, else it fits again
        Point dragFrom, downAt;
        bool dragging, dragMoved;
        Check hover;
        public Check Highlight, ListHover;
        public event Action<Check> ManualToggle;
        public event Action<Check> PinClick;
        public PointF? Player;                 // image pixels, when known
        public string EmptyText = "No map";

        // the high-quality copy of the map at the current zoom, covering hqRect (scaled-map pixels) around the view
        Bitmap hq;
        Rectangle hqRect;
        float hqZoom = -1;
        Bitmap hqSource;
        bool interactive;                      // the wheel is turning or a drag or resize is on, so draw quickly
        readonly Timer hqTimer = new Timer { Interval = 180 };
        public double LastHqMs;

        public MapView()
        {
            BackColor = Back;
            hqTimer.Tick += (s, e) => { hqTimer.Stop(); interactive = false; Invalidate(); };
        }

        public MapInfo Map { get { return map; } }
        public Bitmap Picture { get { return image; } }

        public void Show(MapInfo m, MapArt a, List<Check> cs, double scale)
        {
            var img = a == null ? null : a.Bmp;
            bool same = map != null && m != null && map.Id == m.Id && img == image;
            map = m; image = img; checks = cs ?? new List<Check>(); k = scale;
            art = a == null ? Rectangle.Empty : a.Art;
            origin = a == null ? PointF.Empty : new PointF(a.Origin.X, a.Origin.Y);
            hover = null;
            if (!same)
            {
                userMoved = false;
                Fit();
                DropHq();
                interactive = false;
            }
            Invalidate();
        }

        public void SetPins(List<Check> cs) { checks = cs ?? new List<Check>(); Invalidate(); }

        void DropHq()
        {
            if (hq != null)
            {
                hq.Dispose();
                hq = null;
            }
            hqZoom = -1;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                DropHq();
                hqTimer.Dispose();
            }
            base.Dispose(disposing);
        }

        PointF Spot(Check c) { return new PointF((float)(c.X * k) - origin.X, (float)(c.Y * k) - origin.Y); }

        // Fits the map art and the pins near it. A stray pin, like a boss heart on another floor's frame, shouldn't
        // shrink the whole map. Selecting its row in the list brings it into view.
        RectangleF FitBounds()
        {
            RectangleF a = art.Width > 0 ? art : new RectangleF(0, 0, image.Width, image.Height);
            var near = a;
            float m = Math.Max(a.Width, a.Height) * 0.12f;
            near.Inflate(m, m);
            var r = a;
            foreach (var c in checks)
            {
                if (!c.HasSpot) continue;
                var p = Spot(c);
                if (near.Contains(p)) r = RectangleF.Union(r, new RectangleF(p.X - 1, p.Y - 1, 2, 2));
            }
            float pad = Math.Max(r.Width, r.Height) * 0.025f;
            r.Inflate(pad, pad);
            return r;
        }

        public void Fit()
        {
            if (image == null || Width < 10 || Height < 10) return;
            var r = FitBounds();
            zoom = fitZoom = Math.Min(Width / r.Width, Height / r.Height);
            offX = (Width - r.Width * zoom) / 2 - r.X * zoom;
            offY = (Height - r.Height * zoom) / 2 - r.Y * zoom;
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (image == null) return;
            if (!userMoved) Fit();
            interactive = true;
            hqTimer.Stop(); hqTimer.Start();
        }

        PointF ToScreen(PointF p) { return new PointF(offX + p.X * zoom, offY + p.Y * zoom); }

        float PinRadius()
        {
            float rel = (float)Math.Sqrt(Math.Max(0.01f, zoom / Math.Max(0.0001f, fitZoom)));
            return Px(6.5f) * Math.Max(0.9f, Math.Min(1.7f, rel));
        }

        /// <summary>Draws the map in high quality now (the screenshot mode and the timing runs).</summary>
        public void EnsureHighQuality()
        {
            hqTimer.Stop();
            interactive = false;
            Invalidate();
            Update();
        }

        Rectangle ViewRect()
        {
            int sw = (int)Math.Ceiling(image.Width * zoom), sh = (int)Math.Ceiling(image.Height * zoom);
            var v = new Rectangle((int)Math.Floor(-offX), (int)Math.Floor(-offY), Width + 2, Height + 2);
            v.Intersect(new Rectangle(0, 0, sw, sh));
            return v;
        }

        void RenderHq(Rectangle vis)
        {
            var t0 = System.Diagnostics.Stopwatch.StartNew();
            int sw = (int)Math.Ceiling(image.Width * zoom), sh = (int)Math.Ceiling(image.Height * zoom);
            int mx = (int)(Width * 0.35f), my = (int)(Height * 0.35f);
            var r = new Rectangle(vis.X - mx, vis.Y - my, vis.Width + 2 * mx, vis.Height + 2 * my);
            r.Intersect(new Rectangle(0, 0, sw, sh));
            if (r.Width <= 0 || r.Height <= 0) return;
            if (hq == null || hq.Width != r.Width || hq.Height != r.Height)
            {
                DropHq();
                hq = new Bitmap(r.Width, r.Height, PixelFormat.Format32bppPArgb);
            }
            using (var g = Graphics.FromImage(hq))
            using (var ia = new ImageAttributes())
            {
                ia.SetWrapMode(WrapMode.TileFlipXY);  // no dark seam at the edges
                g.Clear(Back);                         // a last part-pixel row beyond the art gets the frame's wood
                g.CompositingMode = CompositingMode.SourceOver;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.DrawImage(image, new Rectangle(0, 0, r.Width, r.Height), r.X / zoom, r.Y / zoom, r.Width / zoom, r.Height / zoom, GraphicsUnit.Pixel, ia);
            }
            hqRect = r; hqZoom = zoom; hqSource = image;
            LastHqMs = t0.Elapsed.TotalMilliseconds;
        }

        public double LastPaintMs;

        protected override void OnPaint(PaintEventArgs e)
        {
            var t0 = System.Diagnostics.Stopwatch.StartNew();
            DrawAll(e.Graphics);
            LastPaintMs = t0.Elapsed.TotalMilliseconds;
        }

        void DrawAll(Graphics g)
        {
            g.Clear(Back);
            if (image == null)
            {
                var f = F(10.5f, FontStyle.Regular, Fonts.Serif);
                var tr = new Rectangle(Px(24), 0, Width - Px(48), Height);
                var sz = TextRenderer.MeasureText(EmptyText, f, new Size(tr.Width, 2000), Gfx.Wrap | TextFormatFlags.HorizontalCenter);
                Gfx.Text(g, EmptyText, f, new Rectangle(tr.X, (Height - sz.Height) / 2, tr.Width, sz.Height + Px(4)), Pal.TextDim,
                         Gfx.Wrap | TextFormatFlags.HorizontalCenter);
                return;
            }
            var vis = ViewRect();
            if (vis.Width > 0 && vis.Height > 0)
            {
                bool valid = hq != null && hqZoom == zoom && hqSource == image && hqRect.Contains(vis);
                if (!valid && !interactive)
                {
                    RenderHq(vis);
                    valid = hq != null;
                }
                int ox = (int)Math.Round(offX), oy = (int)Math.Round(offY);
                if (valid)
                {
                    g.CompositingMode = CompositingMode.SourceCopy;
                    g.InterpolationMode = InterpolationMode.NearestNeighbor;
                    g.PixelOffsetMode = PixelOffsetMode.Half;
                    g.DrawImage(hq, new Rectangle(ox + hqRect.X, oy + hqRect.Y, hqRect.Width, hqRect.Height), 0, 0, hqRect.Width, hqRect.Height, GraphicsUnit.Pixel);
                    g.CompositingMode = CompositingMode.SourceOver;
                }
                else
                {
                    // quick: straight from the decoded art, only the part in view
                    g.CompositingMode = CompositingMode.SourceOver;
                    // bilinear upscaling costs ~20 ms a frame
                    g.InterpolationMode = zoom < 0.75f ? InterpolationMode.Bilinear : InterpolationMode.NearestNeighbor;
                    g.PixelOffsetMode = PixelOffsetMode.Half;
                    g.DrawImage(image, new Rectangle(ox + vis.X, oy + vis.Y, vis.Width, vis.Height), vis.X / zoom, vis.Y / zoom, vis.Width / zoom, vis.Height / zoom, GraphicsUnit.Pixel);
                    g.CompositingMode = CompositingMode.SourceOver;
                    if (!hqTimer.Enabled) hqTimer.Start();
                }
            }
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            DrawPins(g);
            if (Player.HasValue)
            {
                var p = ToScreen(new PointF(Player.Value.X - origin.X, Player.Value.Y - origin.Y));
                float s = Px(8);
                using (var b = new SolidBrush(Pal.Gold)) g.FillPolygon(b, new[] { new PointF(p.X, p.Y - s * 1.3f), new PointF(p.X + s, p.Y + s), new PointF(p.X - s, p.Y + s) });
            }
            if (hover != null && !dragging) DrawNote(g, hover);
        }

        void DrawPins(Graphics g)
        {
            float r = PinRadius(), line = Math.Max(1f, 1.2f * S);
            var clip = new RectangleF(-r * 3, -r * 3, Width + r * 6, Height + r * 6);
            using (var edge = new Pen(Color.FromArgb(210, 20, 14, 8), line))
            using (var tick = new Pen(Color.FromArgb(240, 250, 245, 230), Math.Max(1.5f, 1.7f * S)) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
            {
                // done checks first, then locked ones, and reachable checks on top
                for (int pass = 0; pass < 3; pass++)
                    foreach (var c in checks)
                    {
                        if (!c.HasSpot || LogicView.Hidden(c)) continue;
                        bool done = c.Done || c.Manual, locked = LogicView.Locked(c);
                        if ((done ? 0 : locked ? 1 : 2) != pass) continue;
                        var p = ToScreen(Spot(c));
                        if (!clip.Contains(p)) continue;
                        if (locked)
                        {
                            // not in logic yet: smaller, dark inside, a ring in its kind's colour
                            float rl = r * 0.8f, lw = Math.Max(1.6f, 2.1f * S);
                            using (var b = new SolidBrush(Color.FromArgb(205, 28, 20, 12))) g.FillEllipse(b, p.X - rl, p.Y - rl, 2 * rl, 2 * rl);
                            using (var ring = new Pen(Color.FromArgb(235, Theme.KindColour(c.Kind)), lw)) g.DrawEllipse(ring, p.X - rl + lw / 2, p.Y - rl + lw / 2, 2 * rl - lw, 2 * rl - lw);
                            continue;
                        }
                        var col = done ? Paper.Done : Theme.KindColour(c.Kind);
                        using (var b = new SolidBrush(Color.FromArgb(done ? 170 : 240, col)))
                            g.FillEllipse(b, p.X - r, p.Y - r, 2 * r, 2 * r);
                        g.DrawEllipse(edge, p.X - r, p.Y - r, 2 * r, 2 * r);
                        if (done)
                            g.DrawLines(tick, new[] { new PointF(p.X - r * 0.5f, p.Y + r * 0.02f), new PointF(p.X - r * 0.12f, p.Y + r * 0.42f), new PointF(p.X + r * 0.55f, p.Y - r * 0.42f) });
                    }
            }
            // a gold ring around the selected check and any check hovered here or in the list
            foreach (var c in new[] { Highlight, ListHover, hover })
            {
                if (c == null || !c.HasSpot || LogicView.Hidden(c) || !checks.Contains(c)) continue;
                var p = ToScreen(Spot(c));
                float rr = r + Px(3.5f);
                using (var halo = new Pen(Color.FromArgb(150, 20, 14, 8), Px(4.5f))) g.DrawEllipse(halo, p.X - rr, p.Y - rr, 2 * rr, 2 * rr);
                using (var ring = new Pen(Pal.GoldHi, Px(2.2f))) g.DrawEllipse(ring, p.X - rr, p.Y - rr, 2 * rr, 2 * rr);
            }
        }

        // the parchment note beside a pin: its name, its kind and state, its item once spoiled
        void DrawNote(Graphics g, Check c)
        {
            var tf = F(10f, FontStyle.Bold, Fonts.Serif);
            var bf = F(9f);
            string body = Theme.Describe(c);
            int pad = Px(10), maxW = Math.Min(Px(320), Width - Px(24));
            if (maxW < Px(80)) return;
            var ts = TextRenderer.MeasureText(g, c.Name, tf, new Size(maxW - 2 * pad, 2000), Gfx.Wrap);
            var bs = TextRenderer.MeasureText(g, body, bf, new Size(maxW - 2 * pad, 2000), Gfx.Wrap);
            int w = Math.Min(maxW, Math.Max(ts.Width, bs.Width) + 2 * pad + Px(2));
            int h = ts.Height + Px(3) + bs.Height + 2 * pad;
            var p = ToScreen(Spot(c));
            float r = PinRadius() + Px(8);
            int x = (int)(p.X + r), y = (int)(p.Y + r * 0.4f);
            if (x + w > Width - Px(6)) x = (int)(p.X - r - w);
            if (x < Px(6)) x = Px(6);
            if (y + h > Height - Px(6)) y = (int)(p.Y - r * 0.4f - h);
            if (y < Px(6)) y = Px(6);
            var box = new Rectangle(x, y, w, h);
            var shadow = box; shadow.Offset(Px(2), Px(3));
            Gfx.Fill(g, shadow, Px(5), Color.FromArgb(90, 0, 0, 0));
            Gfx.Fill(g, box, Px(5), Paper.Card);
            Gfx.Stroke(g, box, Px(5), Pal.GoldDim, Math.Max(1f, S));
            Gfx.Text(g, c.Name, tf, new Rectangle(x + pad, y + pad, w - 2 * pad, ts.Height + Px(2)), Paper.Ink, Gfx.Wrap);
            Gfx.Text(g, body, bf, new Rectangle(x + pad, y + pad + ts.Height + Px(3), w - 2 * pad, bs.Height + Px(2)), Paper.InkDim, Gfx.Wrap);
        }

        Check HitTest(Point pt)
        {
            float r = PinRadius() + Px(3);
            Check best = null;
            double bd = r * r;
            foreach (var c in checks)
            {
                if (!c.HasSpot || LogicView.Hidden(c)) continue;
                var p = ToScreen(Spot(c));
                double d = (p.X - pt.X) * (p.X - pt.X) + (p.Y - pt.Y) * (p.Y - pt.Y);
                if (d <= bd)
                {
                    bd = d;
                    best = c;
                }
            }
            return best;
        }

        /// <summary>Brings a check's pin into view (keeping the zoom) when it is outside it.</summary>
        public void Reveal(Check c)
        {
            if (image == null || c == null || !c.HasSpot) return;
            var p = ToScreen(Spot(c));
            int m = Px(40);
            if (p.X >= m && p.Y >= m && p.X <= Width - m && p.Y <= Height - m) return;
            offX += Width / 2f - p.X; offY += Height / 2f - p.Y;
            userMoved = true;
            Invalidate();
        }

        void ClampPan()
        {
            if (image == null) return;
            RectangleF a = art.Width > 0 ? art : new RectangleF(0, 0, image.Width, image.Height);
            foreach (var c in checks) if (c.HasSpot)
            {
                var p = Spot(c);
                a = RectangleF.Union(a, new RectangleF(p.X - 1, p.Y - 1, 2, 2));
            }
            float keep = Px(80);
            float left = offX + a.Left * zoom, right = offX + a.Right * zoom, top = offY + a.Top * zoom, bottom = offY + a.Bottom * zoom;
            if (right < keep) offX += keep - right;
            if (left > Width - keep) offX -= left - (Width - keep);
            if (bottom < keep) offY += keep - bottom;
            if (top > Height - keep) offY -= top - (Height - keep);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            Focus();
            if (e.Button == MouseButtons.Left)
            {
                dragging = true;
                dragMoved = false;
                dragFrom = downAt = e.Location;
            }
            if (e.Button == MouseButtons.Right)
            {
                var c = HitTest(e.Location);
                if (c != null && ManualToggle != null) ManualToggle(c);
            }
            base.OnMouseDown(e);
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (dragging && !dragMoved && e.Button == MouseButtons.Left)
            {
                var c = HitTest(e.Location);
                if (c != null)
                {
                    Highlight = c;
                    Invalidate();
                    if (PinClick != null) PinClick(c);
                }
            }
            if (dragging && dragMoved)
            {
                hqTimer.Stop();
                hqTimer.Start();
            }
            dragging = false;
            base.OnMouseUp(e);
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (dragging && image != null)
            {
                if (!dragMoved && Math.Abs(e.X - downAt.X) + Math.Abs(e.Y - downAt.Y) < Px(4)) return;
                dragMoved = true;
                Cursor = Cursors.SizeAll;
                offX += e.X - dragFrom.X;
                offY += e.Y - dragFrom.Y;
                dragFrom = e.Location;
                ClampPan();
                userMoved = true;
                interactive = true;
                Invalidate();
                return;
            }
            var c = HitTest(e.Location);
            Cursor = c != null ? Cursors.Hand : Cursors.Default;
            if (c != hover)
            {
                hover = c;
                Invalidate();
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            if (hover != null)
            {
                hover = null;
                Invalidate();
            }
            base.OnMouseLeave(e);
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            if (image == null) return;
            float old = zoom;
            float step = (float)Math.Pow(1.2, e.Delta / 120.0);
            zoom = Math.Max(fitZoom * 0.35f, Math.Min(Math.Max(fitZoom * 6f, 3f * S), zoom * step));
            offX = e.X - (e.X - offX) * zoom / old;
            offY = e.Y - (e.Y - offY) * zoom / old;
            ClampPan();
            userMoved = true;
            interactive = true;
            hqTimer.Stop(); hqTimer.Start();
            Invalidate();
        }

        protected override void OnDoubleClick(EventArgs e)
        {
            FitNow();
            base.OnDoubleClick(e);
        }

        public void TestHover(Check c) { hover = c; Invalidate(); }

        public void FitNow()
        {
            userMoved = false;
            Fit();
            interactive = false;
            Invalidate();
        }

        // for the timing run (--bench), a drag step and a wheel notch like the mouse would make them
        public void PanBy(int dx, int dy)
        {
            if (image == null) return;
            offX += dx; offY += dy;
            ClampPan();
            userMoved = true; interactive = true;
            Invalidate();
        }

        public void ZoomBy(int notches, Point at)
        {
            OnMouseWheel(new MouseEventArgs(MouseButtons.None, 0, at.X, at.Y, notches * 120));
        }
    }
}
