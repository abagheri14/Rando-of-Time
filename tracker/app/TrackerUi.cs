// The tracker's own parts, in the look both apps share (common/ui/Ui.cs):
// - the wood header with the logo, the seed and its count, and the menu buttons
// - the panels, a gold heading on the wood over a parchment page
// - the floor chips over the map, the item grid, the status line and the spoiler banner
// - the parchment menus, a small dialog and the hover notes
// Every piece measures its text and grows (wraps) instead of cutting a heading short.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using RemakeUi;

namespace RandoOfTimeTracker
{
    // a part whose height follows from its width (its text wraps)
    public interface IFlow
    {
        int HeightFor(int width);
    }

    static class Measure
    {
        public const TextFormatFlags Line = TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix;

        public static Size Text(string s, Font f) { return TextRenderer.MeasureText(s ?? "", f, new Size(int.MaxValue, int.MaxValue), Line); }

        public static Size Wrapped(string s, Font f, int width)
        {
            return TextRenderer.MeasureText(string.IsNullOrEmpty(s) ? " " : s, f, new Size(Math.Max(1, width), int.MaxValue), Gfx.Wrap);
        }
    }

    // Hover notes
    // One parchment note for the lists (the map draws its own). It shows after a short pause and hides when the
    // mouse leaves.
    public static class Tips
    {
        static TipWindow tip;
        static readonly Timer timer = new Timer { Interval = 450 };
        static string pending, shown;
        static Point at;
        static int dpi = 96;

        static Tips()
        {
            timer.Tick += (s, e) =>
            {
                timer.Stop();
                if (pending == null) return;
                if (tip == null) tip = new TipWindow();
                tip.ShowAt(pending, at, dpi);
                shown = pending;
            };
        }

        public static void Show(string text, Point screen, int forDpi)
        {
            if (text == shown && text != null) return;
            Hide();
            pending = text; at = screen; dpi = forDpi;
            if (text != null) timer.Start();
        }

        public static void Hide()
        {
            timer.Stop();
            pending = null;
            if (shown != null && tip != null && tip.IsHandleCreated)
            {
                tip.HideTip();
                Native.SetWindowPos(tip.Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0080 | 0x0001 | 0x0002 | 0x0010 | 0x0004);
            }
            shown = null;
        }
    }

    // Header
    // A wood button with a gold rim that opens its parchment menu under itself (Seed, View, Spoiler).
    public class MenuButton : UiControl
    {
        public ContextMenuStrip Menu;
        bool hover, open;
        DateTime closedAt;

        public MenuButton() { Cursor = Cursors.Hand; TabStop = true; }

        public int PreferredWidth() { return Measure.Text(Text, F(10f)).Width + Px(34); }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left) Open();
            base.OnMouseDown(e);
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter || e.KeyCode == Keys.Down)
            {
                Open();
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        public void Open()
        {
            if (Menu == null || (DateTime.Now - closedAt).TotalMilliseconds < 200) return;  // a click that closed it
            Menus.Prepare(Menu, Dpi);
            open = true; Invalidate();
            ToolStripDropDownClosedEventHandler h = null;
            h = (s, e) => { Menu.Closed -= h; open = false; closedAt = DateTime.Now; Invalidate(); };
            Menu.Closed += h;
            Menu.Show(this, new Point(0, Height + Px(3)));
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : Pal.Bg);
            Gfx.Smooth(g);
            var r = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
            Gfx.Fill(g, r, Px(4), open ? Pal.Deep : hover ? Pal.Raised : Pal.Bg);
            Gfx.Stroke(g, r, Px(4), open || hover || (Focused && ShowFocusCues) ? Pal.GoldHi : Pal.Gold, Math.Max(1f, S));
            var tr = new Rectangle(Px(12), 0, Width - Px(30), Height);
            Gfx.Text(g, Text, F(10f), tr, Pal.Text, Gfx.Left);
            Gfx.Chevron(g, new RectangleF(Width - Px(24), (Height - Px(14)) / 2f, Px(14), Px(14)), Pal.Gold, Math.Max(1.4f, 1.5f * S), open);
        }
    }

    // The wood header with the logo, the seed in gold, its count with a gold bar, and the menu buttons on the
    // right. A narrow window first puts the count under the seed, then sets the seed smaller, then wraps it, so
    // nothing is cut.
    public class HeaderBar : UiControl
    {
        public Image Logo;
        public string Title = "", Count = "";
        public float Progress, Progress2;  // done, and done + in logic now (the bar's green part follows the gold)
        public readonly List<MenuButton> Buttons = new List<MenuButton>();
        float titlePt = 17f;
        Rectangle titleR, countR, barR;
        bool wrapTitle;

        public HeaderBar() { BackColor = Pal.Bg; }

        public void AddButton(MenuButton b) { Buttons.Add(b); Controls.Add(b); b.BackColor = Pal.Bg; }

        public int HeightFor(int width) { return Plan(width, false); }

        protected override void OnLayout(LayoutEventArgs e) { Plan(Width, true); base.OnLayout(e); }

        public void SetText(string title, string count, float progress) { SetText(title, count, progress, progress); }

        public void SetText(string title, string count, float progress, float progress2)
        {
            if (title == Title && count == Count && Math.Abs(progress - Progress) < 0.0001f && Math.Abs(progress2 - Progress2) < 0.0001f) return;
            Progress2 = progress2;
            bool relayout = Measure.Text(title, F(titlePt, FontStyle.Bold, Fonts.Serif)).Width != Measure.Text(Title, F(titlePt, FontStyle.Bold, Fonts.Serif)).Width
                            || Measure.Text(count, CountFont).Width != Measure.Text(Count, CountFont).Width;
            Title = title; Count = count; Progress = progress;
            if (relayout)
            {
                // The parent handles height changes from wrapping. We redo the header's rectangles even when its
                // size stays the same, since no layout event comes to update the count's width.
                if (Parent != null) Parent.PerformLayout();
                Plan(Width, true);
            }
            Invalidate();
        }

        Font CountFont { get { return F(12.5f, FontStyle.Regular, Fonts.Serif); } }

        int Plan(int width, bool apply)
        {
            int pad = Px(16), logo = Logo != null ? Px(36) : 0, gap = Px(12), bgap = Px(6), bh = Px(32);
            int bw = 0;
            foreach (var b in Buttons) bw += b.PreferredWidth() + bgap;
            int tx = pad + logo + (logo > 0 ? gap : 0);
            int right = width - pad - bw;
            int avail = Math.Max(Px(80), right - Px(10) - tx);
            var cf = CountFont;
            var cs = Measure.Text(Count, cf);
            int barH = Px(3), cgap = Px(22);
            float[] sizes = { 17f, 15.5f, 14f, 13f, 12f };
            int h = Px(56);
            bool done = false;
            // one line: the seed, then the count
            foreach (float pt in sizes)
            {
                var ts = Measure.Text(Title, F(pt, FontStyle.Bold, Fonts.Serif));
                if (ts.Width + cgap + cs.Width <= avail)
                {
                    if (apply)
                    {
                        titlePt = pt; wrapTitle = false;
                        titleR = new Rectangle(tx, 0, ts.Width + Px(2), h);
                        int cy = (h - cs.Height - barH - Px(3)) / 2;
                        countR = new Rectangle(titleR.Right + cgap, cy, cs.Width + Px(2), cs.Height);
                        barR = new Rectangle(countR.X + Px(5), countR.Bottom + Px(1), Math.Max(Px(40), cs.Width - Px(10)), barH);
                    }
                    done = true;
                    break;
                }
            }
            if (!done)
            {
                // two lines, the seed over the count, with the seed set smaller and then wrapped until it fits
                float pt = sizes[sizes.Length - 1];
                bool wrap = true;
                Size ts = Size.Empty;
                foreach (float p in sizes)
                {
                    ts = Measure.Text(Title, F(p, FontStyle.Bold, Fonts.Serif));
                    if (ts.Width <= avail)
                    {
                        pt = p;
                        wrap = false;
                        break;
                    }
                }
                if (wrap) ts = Measure.Wrapped(Title, F(pt, FontStyle.Bold, Fonts.Serif), avail);
                int top = Px(8);
                int countW = Math.Min(avail, cs.Width);
                var csw = cs.Width > avail ? Measure.Wrapped(Count, cf, avail) : cs;
                h = Math.Max(Px(56), top + ts.Height + Px(2) + csw.Height + Px(4) + barH + Px(8));
                if (apply)
                {
                    titlePt = pt; wrapTitle = wrap;
                    titleR = new Rectangle(tx, top, Math.Min(avail, ts.Width + Px(2)), ts.Height);
                    countR = new Rectangle(tx, titleR.Bottom + Px(2), Math.Min(avail, csw.Width + Px(2)), csw.Height);
                    barR = new Rectangle(tx + Px(5), countR.Bottom + Px(2), Math.Max(Px(40), Math.Min(avail, countW) - Px(10)), barH);
                }
            }
            if (apply)
            {
                int x = width - pad;
                for (int i = Buttons.Count - 1; i >= 0; i--)
                {
                    int w = Buttons[i].PreferredWidth();
                    x -= w;
                    Buttons[i].SetBounds(x, (h - bh) / 2, w, bh);
                    x -= bgap;
                }
            }
            return h;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Bg);
            int pad = Px(16);
            if (Logo != null)
            {
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                int s = Px(36);
                g.DrawImage(Logo, new Rectangle(pad, Math.Min((Height - s) / 2, Px(10)), s, s));
            }
            var tf = F(titlePt, FontStyle.Bold, Fonts.Serif);
            Gfx.Text(g, Title, tf, titleR, Pal.Gold, wrapTitle ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
            Gfx.Text(g, Count, CountFont, countR, Pal.Text, countR.Width < Measure.Text(Count, CountFont).Width ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
            if (Count.Length > 0)
            {
                Gfx.Smooth(g);
                Gfx.Fill(g, barR, barR.Height / 2f, Pal.Deep);
                if (Progress2 > Progress)
                {
                    var ar = new RectangleF(barR.X, barR.Y, Math.Max(barR.Height, barR.Width * Math.Max(0f, Math.Min(1f, Progress2))), barR.Height);
                    Gfx.Fill(g, ar, barR.Height / 2f, LogicView.GreenOnWood);
                }
                var fr = new RectangleF(barR.X, barR.Y, Math.Max(barR.Height, barR.Width * Math.Max(0f, Math.Min(1f, Progress))), barR.Height);
                if (Progress > 0) Gfx.Fill(g, fr, barR.Height / 2f, Pal.Gold);
            }
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, 0, Height - 1, Width, Height - 1);
        }
    }

    // Panels
    // A panel of the window, a gold heading on the wood (a count on its right, a hint under it) with its page below.
    public class PanelBox : UiControl
    {
        public string Title = "", RightText = "", Sub = "";
        public Control Body;
        public UiControl Extra;          // a part between the heading and the page (the floor chips), an IFlow
        public bool BodyOnPaper = true;
        Rectangle titleR, rightR, subR, frameR;
        bool titleWrap, rightWrap;

        public PanelBox(string title, Control body)
        {
            Title = title; Body = body;
            BackColor = Pal.Panel;
            if (body != null) Controls.Add(body);
        }

        public void SetExtra(UiControl c) { Extra = c; Controls.Add(c); c.BackColor = Pal.Panel; }

        // the page shown (the map, or the board of checks without a spot), the other one gets hidden
        public void SetBody(Control c, bool onPaper)
        {
            if (Body == c) return;
            if (Body != null) Body.Visible = false;
            Body = c;
            BodyOnPaper = onPaper;
            if (!Controls.Contains(c)) Controls.Add(c);
            c.Visible = true;
            PerformLayout();
            Invalidate();
        }

        public void SetHeading(string title, string right, string sub)
        {
            title = title ?? ""; right = right ?? ""; sub = sub ?? "";
            if (title == Title && right == RightText && sub == Sub) return;
            bool relayout = HeadHeight(Width, title, right, sub) != HeadHeight(Width, Title, RightText, Sub)
                            || Measure.Text(right, RightFont).Width != Measure.Text(RightText, RightFont).Width;
            Title = title; RightText = right; Sub = sub;
            if (relayout) PerformLayout();
            Invalidate();
        }

        Font TitleFont { get { return F(12f, FontStyle.Bold, Fonts.Serif); } }
        Font RightFont { get { return F(9.5f); } }
        Font SubFont { get { return F(8.5f); } }

        int HeadHeight(int width, string title, string right, string sub)
        {
            Rectangle a, b, c; bool w1, w2;
            return PlanHead(width, title, right, sub, out a, out b, out c, out w1, out w2);
        }

        int PlanHead(int width, string title, string right, string sub, out Rectangle tR, out Rectangle rR, out Rectangle sR, out bool tWrap, out bool rWrap)
        {
            int padX = Px(10), top = Px(6), inner = Math.Max(Px(40), width - 2 * padX);
            var tf = TitleFont; var rf = RightFont;
            var ts = Measure.Text(title, tf);
            var rs = right.Length > 0 ? Measure.Text(right, rf) : Size.Empty;
            int y = top;
            tWrap = rWrap = false;
            rR = Rectangle.Empty;
            if (rs.Width == 0 || ts.Width + Px(12) + rs.Width <= inner)
            {
                if (ts.Width > inner)
                {
                    ts = Measure.Wrapped(title, tf, inner);
                    tWrap = true;
                }
                int lh = Math.Max(ts.Height, tWrap ? 0 : tf.Height + Px(4));
                tR = new Rectangle(padX, y, Math.Min(inner, ts.Width + Px(2)), lh);
                if (rs.Width > 0) rR = new Rectangle(padX + inner - rs.Width - Px(2), y, rs.Width + Px(2), lh);
                y += lh;
            }
            else
            {
                if (ts.Width > inner)
                {
                    ts = Measure.Wrapped(title, tf, inner);
                    tWrap = true;
                }
                tR = new Rectangle(padX, y, Math.Min(inner, ts.Width + Px(2)), Math.Max(ts.Height, tf.Height + Px(2)));
                y = tR.Bottom;
                if (rs.Width > inner)
                {
                    rs = Measure.Wrapped(right, rf, inner);
                    rWrap = true;
                }
                rR = new Rectangle(padX, y, Math.Min(inner, rs.Width + Px(2)), rs.Height + Px(2));
                y = rR.Bottom;
            }
            sR = Rectangle.Empty;
            if (sub.Length > 0)
            {
                var ss = Measure.Wrapped(sub, SubFont, inner);
                sR = new Rectangle(padX, y - Px(2), inner, ss.Height + Px(1));
                y = sR.Bottom;
            }
            return y + Px(6);
        }

        protected override void OnLayout(LayoutEventArgs e)
        {
            int y = PlanHead(Width, Title, RightText, Sub, out titleR, out rightR, out subR, out titleWrap, out rightWrap);
            int pad = Px(6);
            if (Extra != null && Extra.Visible)
            {
                int eh = ((IFlow)Extra).HeightFor(Width - 2 * pad);
                Extra.SetBounds(pad, y, Width - 2 * pad, eh);
                y += eh + Px(6);
            }
            frameR = new Rectangle(pad, y, Width - 2 * pad, Math.Max(0, Height - y - pad));
            if (Body != null) Body.SetBounds(frameR.X + 1, frameR.Y + 1, Math.Max(0, frameR.Width - 2), Math.Max(0, frameR.Height - 2));
            base.OnLayout(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            using (var pen = new Pen(Pal.Border)) g.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
            Gfx.Text(g, Title, TitleFont, titleR, Pal.Gold, titleWrap ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
            if (RightText.Length > 0)
                Gfx.Text(g, RightText, RightFont, rightR, Pal.TextDim, rightWrap ? Gfx.Wrap : ((rightR.X > titleR.Right ? Gfx.Right : Gfx.Left) & ~TextFormatFlags.EndEllipsis));
            if (Sub.Length > 0) Gfx.Text(g, Sub, SubFont, subR, Pal.TextFaint, Gfx.Wrap);
            using (var pen = new Pen(BodyOnPaper ? Paper.BorderHi : Pal.GoldDim))
                g.DrawRectangle(pen, frameR.X, frameR.Y, frameR.Width - 1, frameR.Height - 1);
        }
    }

    // The maps of a place (a dungeon's floors) as chips over the map, each with its count and the shown one in gold.
    public class ChipStrip : UiControl, IFlow
    {
        public readonly List<MapInfo> Maps = new List<MapInfo>();
        public int Selected = -1;
        public event Action<int> Picked;
        readonly List<Rectangle> rects = new List<Rectangle>();
        readonly List<bool> wraps = new List<bool>();
        int hover = -1;

        public ChipStrip() { Cursor = Cursors.Hand; BackColor = Pal.Panel; }

        Font LabelFont { get { return F(10f, FontStyle.Bold, Fonts.Serif); } }
        Font CountFont { get { return F(8.5f); } }

        static string CountOf(MapInfo m) { return m.Done + "/" + m.All; }

        // the green pill of a floor's checks in logic, and the gap after it (none while the logic isn't known)
        int BadgeRoom(MapInfo m) { return LogicView.On && m.Avail > 0 ? StripBadgeWidth() + Px(7) : 0; }

        int StripBadgeWidth() { return LogicView.BadgeWidth(Maps.Count == 0 ? 0 : Maps.Max(x => x.Avail), Dpi); }

        public int HeightFor(int width) { return Flow(width, null, null); }

        int Flow(int width, List<Rectangle> outR, List<bool> outW)
        {
            if (Maps.Count == 0) return 0;
            int x = 0, y = 0, lineH = 0, gap = Px(6), padX = Px(11), h0 = Px(28);
            foreach (var m in Maps)
            {
                var ls = Measure.Text(m.Chip ?? m.Title, LabelFont);
                var cs = Measure.Text(CountOf(m), CountFont);
                int bw = BadgeRoom(m);
                int w = padX + ls.Width + Px(6) + bw + cs.Width + padX, h = h0;
                bool wrap = false;
                if (w > width)
                {
                    // a chip wider than the strip wraps its name inside it
                    w = width;
                    var wl = Measure.Wrapped(m.Chip ?? m.Title, LabelFont, Math.Max(Px(30), width - 2 * padX - cs.Width - bw - Px(6)));
                    h = Math.Max(h0, wl.Height + Px(8));
                    wrap = true;
                }
                if (x > 0 && x + w > width)
                {
                    x = 0;
                    y += lineH + gap;
                    lineH = 0;
                }
                if (outR != null)
                {
                    outR.Add(new Rectangle(x, y, w, h));
                    outW.Add(wrap);
                }
                x += w + gap;
                lineH = Math.Max(lineH, h);
            }
            return y + lineH;
        }

        protected override void OnLayout(LayoutEventArgs e) { rects.Clear(); wraps.Clear(); Flow(Width, rects, wraps); base.OnLayout(e); }

        int At(Point p) { for (int i = 0; i < rects.Count; i++) if (rects[i].Contains(p)) return i; return -1; }

        protected override void OnMouseMove(MouseEventArgs e) { int h = At(e.Location); if (h != hover) { hover = h; Invalidate(); } base.OnMouseMove(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = -1; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            int i = At(e.Location);
            if (i >= 0 && e.Button == MouseButtons.Left && Picked != null) Picked(i);
            base.OnMouseDown(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            Gfx.Smooth(g);
            rects.Clear(); wraps.Clear(); Flow(Width, rects, wraps);  // the counts change as checks are done
            for (int i = 0; i < Maps.Count && i < rects.Count; i++)
            {
                var r = rects[i];
                var m = Maps[i];
                bool sel = i == Selected, all = m.All > 0 && m.Done == m.All;
                var rf = new RectangleF(r.X + 0.5f, r.Y + 0.5f, r.Width - 1, r.Height - 1);
                Gfx.Fill(g, rf, Px(5), sel ? Pal.Gold : i == hover ? Pal.Hover : Pal.Raised);
                Gfx.Stroke(g, rf, Px(5), sel ? Pal.GoldHi : i == hover ? Pal.GoldDim : Pal.Border, Math.Max(1f, S));
                string cnt = CountOf(m);
                var cs = Measure.Text(cnt, CountFont);
                int padX = Px(11);
                var cr = new Rectangle(r.Right - padX - cs.Width, r.Y, cs.Width + Px(2), r.Height);
                Gfx.Text(g, cnt, CountFont, cr, sel ? Pal.GoldInk : all ? Pal.Green : Pal.TextDim, Gfx.Left & ~TextFormatFlags.EndEllipsis);
                int bw = BadgeRoom(m);
                if (bw > 0)
                {
                    int bh = LogicView.BadgeHeight(Dpi);
                    LogicView.DrawBadge(g, new Rectangle(cr.X - bw, r.Y + (r.Height - bh) / 2, StripBadgeWidth(), bh), m.Avail, Dpi);
                }
                var lr = new Rectangle(r.X + padX, r.Y, cr.X - bw - Px(6) - r.X - padX + Px(2), r.Height);
                if (wraps[i])
                {
                    lr.Y += Px(4);
                    lr.Height -= Px(8);
                }
                Gfx.Text(g, m.Chip ?? m.Title, LabelFont, lr, sel ? Pal.GoldInk : Pal.Text, wraps[i] ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
            }
        }
    }

    // Two choices side by side on the wood, the chosen one in gold. The checks panel uses it for "In logic now" or
    // "All here". A panel too narrow for both on one line puts one under the other, and a label wraps instead of
    // being cut.
    public class Segmented : UiControl, IFlow
    {
        public string[] Labels = new string[0];
        public string[] TipsText = new string[0];
        public int Selected;
        public event Action<int> Picked;
        readonly List<Rectangle> rects = new List<Rectangle>();
        int hover = -1;

        public Segmented() { Cursor = Cursors.Hand; BackColor = Pal.Panel; }

        Font LabelFont { get { return F(9.5f, FontStyle.Bold); } }

        /// <summary>Sets new labels and returns true when the height they need changed (the panel lays out
        /// again).</summary>
        public bool SetLabels(params string[] labels)
        {
            if (labels.SequenceEqual(Labels)) return false;
            int before = HeightFor(Width);
            Labels = labels;
            rects.Clear();
            Invalidate();
            return HeightFor(Width) != before;
        }

        public int HeightFor(int width) { return Flow(width, null); }

        int Flow(int width, List<Rectangle> outR)
        {
            int n = Labels.Length;
            if (n == 0 || width <= 0) return 0;
            int h0 = Px(30), padX = Px(12), inset = Px(3);
            int need = Labels.Max(l => Measure.Text(l, LabelFont).Width) + 2 * padX + 2 * inset;
            if (need * n <= width)
            {
                int x = 0;
                for (int i = 0; i < n; i++)
                {
                    int w = i == n - 1 ? width - x : width / n;
                    if (outR != null) outR.Add(new Rectangle(x, 0, w, h0));
                    x += w;
                }
                return h0;
            }
            int y = 0;
            for (int i = 0; i < n; i++)
            {
                var s = Measure.Wrapped(Labels[i], LabelFont, Math.Max(Px(30), width - 2 * padX - 2 * inset));
                int h = Math.Max(h0, s.Height + Px(12));
                if (outR != null) outR.Add(new Rectangle(0, y, width, h));
                y += h;
            }
            return y;
        }

        protected override void OnLayout(LayoutEventArgs e) { rects.Clear(); base.OnLayout(e); }
        protected override void OnResize(EventArgs e) { rects.Clear(); Invalidate(); base.OnResize(e); }

        int At(Point p) { for (int i = 0; i < rects.Count; i++) if (rects[i].Contains(p)) return i; return -1; }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            int h = At(e.Location);
            if (h != hover)
            {
                hover = h;
                Invalidate();
                if (h >= 0 && h < TipsText.Length && TipsText[h] != null) Tips.Show(TipsText[h], PointToScreen(new Point(e.X + Px(14), e.Y + Px(20))), Dpi);
                else Tips.Hide();
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e) { hover = -1; Tips.Hide(); Invalidate(); base.OnMouseLeave(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            int i = At(e.Location);
            if (i >= 0 && e.Button == MouseButtons.Left)
            {
                Tips.Hide();
                if (i != Selected)
                {
                    Selected = i;
                    Invalidate();
                    if (Picked != null) Picked(i);
                }
            }
            base.OnMouseDown(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            if (rects.Count != Labels.Length)
            {
                rects.Clear();
                Flow(Width, rects);
            }
            if (rects.Count == 0) return;
            Gfx.Smooth(g);
            var all = new RectangleF(0.5f, 0.5f, Width - 1, rects[rects.Count - 1].Bottom - 1);
            Gfx.Fill(g, all, Px(6), Pal.Deep);
            Gfx.Stroke(g, all, Px(6), Pal.Border, Math.Max(1f, S));
            int inset = Px(3), padX = Px(12);
            for (int i = 0; i < rects.Count; i++)
            {
                var r = rects[i];
                var seg = new RectangleF(r.X + inset, r.Y + inset, r.Width - 2 * inset, r.Height - 2 * inset);
                bool sel = i == Selected;
                if (sel) Gfx.Fill(g, seg, Px(4), Pal.Gold);
                else if (i == hover) Gfx.Fill(g, seg, Px(4), Pal.Hover);
                var tr = Rectangle.Round(seg);
                tr.Inflate(-padX, 0);
                bool wrap = Measure.Text(Labels[i], LabelFont).Width > tr.Width;
                if (wrap)
                {
                    var s = Measure.Wrapped(Labels[i], LabelFont, tr.Width);
                    tr = new Rectangle(tr.X, tr.Y + (tr.Height - s.Height) / 2, tr.Width, s.Height + Px(2));
                }
                Gfx.Text(g, Labels[i], LabelFont, tr, sel ? Pal.GoldInk : Pal.Text,
                         wrap ? (Gfx.Wrap | TextFormatFlags.HorizontalCenter) : (Gfx.Center & ~TextFormatFlags.EndEllipsis));
            }
        }
    }

    // Items
    // Every item to show, in groups (Items, Upgrades, Songs, Equipment, Quest), drawn as one control. The icons are
    // scaled once for the cell size, found ones in colour with a gold ring and the rest grey and faint. Hovering
    // names them.
    public class ItemGrid : UiControl
    {
        public static readonly string[] GroupOrder = { "Items", "Upgrades", "Songs", "Equipment", "Quest" };
        readonly List<KeyValuePair<string, List<ItemInfo>>> groups = new List<KeyValuePair<string, List<ItemInfo>>>();
        readonly Dictionary<string, Image> originals = new Dictionary<string, Image>();
        readonly Dictionary<string, Bitmap> lit = new Dictionary<string, Bitmap>(), dim = new Dictionary<string, Bitmap>();
        // in content coordinates
        readonly List<KeyValuePair<Rectangle, ItemInfo>> cells = new List<KeyValuePair<Rectangle, ItemInfo>>();
        readonly List<KeyValuePair<Rectangle, string>> heads = new List<KeyValuePair<Rectangle, string>>();
        public readonly ScrollCore Scroll;
        public string DataDir;
        public int PreferCell = 0;        // fixed cell size (96 DPI) for the stacked layout, 0 means fit the panel
        int scaledFor = -1, planW = -1, planH = -1, planDpi = -1, iconPx;
        ItemInfo hover;

        static readonly ImageAttributes Greyed = MakeGreyed();

        static ImageAttributes MakeGreyed()
        {
            var m = new ColorMatrix(new[]
            {
                new[] { .3f, .3f, .3f, 0f, 0f }, new[] { .59f, .59f, .59f, 0f, 0f }, new[] { .11f, .11f, .11f, 0f, 0f },
                new[] { 0f, 0f, 0f, .38f, 0f }, new[] { 0f, 0f, 0f, 0f, 1f }
            });
            var a = new ImageAttributes();
            a.SetColorMatrix(m);
            return a;
        }

        public ItemGrid()
        {
            Scroll = new ScrollCore(this) { OnPaper = true };
            BackColor = Paper.Bg;
        }

        public void SetItems(List<ItemInfo> items)
        {
            groups.Clear();
            var order = GroupOrder.ToList();
            foreach (var g in items.Select(i => i.Group ?? "Items").Distinct()) if (!order.Contains(g)) order.Add(g);
            foreach (var g in order)
            {
                var list = items.Where(i => (i.Group ?? "Items") == g).ToList();
                if (list.Count > 0) groups.Add(new KeyValuePair<string, List<ItemInfo>>(g, list));
            }
            planW = -1;
            Invalidate();
        }

        public int Found { get { return groups.Sum(g => g.Value.Count(i => i.Count > 0)); } }
        public int Total { get { return groups.Sum(g => g.Value.Count); } }

        Font HeadFont { get { return F(10f, FontStyle.Bold, Fonts.Serif); } }
        int HeadH { get { return Px(24); } }

        // the grid's height at a width for a cell size (all at the current DPI)
        int ContentHeight(int width, int cell, out int cols, out int cellW)
        {
            int pad = Px(8);
            int inner = Math.Max(cell, width - 2 * pad);
            cols = Math.Max(1, inner / cell);
            cellW = inner / cols;
            int h = Px(4);
            foreach (var g in groups) h += HeadH + (g.Value.Count + cols - 1) / cols * cellW + Px(6);
            return h;
        }

        /// <summary>The height the grid needs at a width with its preferred cell (the stacked layout).</summary>
        public int HeightFor(int width, int cellLogical)
        {
            int cols, cw;
            return ContentHeight(width, Px(cellLogical), out cols, out cw);
        }

        void Plan()
        {
            if (planW == Width && planH == Height && planDpi == Dpi) return;
            planW = Width; planH = Height; planDpi = Dpi;
            int cols = 1, cw = Px(40);
            if (PreferCell > 0) ContentHeight(Width, Px(PreferCell), out cols, out cw);
            else
            {
                bool fit = false;
                // the largest cells that fit without scrolling, with icons capped at 96 pixels, else the small
                // scrollable layout
                int most = Math.Min(Px(84), 96 + Px(12));
                for (int c = most; c >= Px(34); c -= Math.Max(1, Px(2)))
                {
                    if (ContentHeight(Width, c, out cols, out cw) <= Height && cw <= most)
                    {
                        fit = true;
                        break;
                    }
                }
                if (!fit) ContentHeight(Width - Px(10), Px(36), out cols, out cw);
            }
            cells.Clear(); heads.Clear();
            int pad = Px(8), y = Px(4);
            foreach (var g in groups)
            {
                heads.Add(new KeyValuePair<Rectangle, string>(new Rectangle(pad, y, Width - 2 * pad, HeadH), g.Key));
                y += HeadH;
                for (int i = 0; i < g.Value.Count; i++)
                    cells.Add(new KeyValuePair<Rectangle, ItemInfo>(new Rectangle(pad + i % cols * cw, y + i / cols * cw, cw, cw), g.Value[i]));
                y += (g.Value.Count + cols - 1) / cols * cw + Px(6);
            }
            Scroll.Content = y;
            Scroll.Line = 40;
            Scroll.Clamp();
            int icon = Math.Max(Px(16), cw - Px(12));
            if (icon != scaledFor) ScaleIcons(icon);
        }

        Image Original(string rel)
        {
            if (string.IsNullOrEmpty(rel) || DataDir == null) return null;
            Image img;
            if (originals.TryGetValue(rel, out img)) return img;
            string p = Path.Combine(DataDir, rel);
            try
            {
                if (File.Exists(p))
                    using (var fs = new FileStream(p, FileMode.Open, FileAccess.Read, FileShare.Read))
                    using (var src = Image.FromStream(fs))
                        img = new Bitmap(src);
            }
            catch (Exception) { img = null; }
            originals[rel] = img;
            return img;
        }

        // the icons at the cell's size, lit and greyed, made once instead of on every paint
        void ScaleIcons(int size)
        {
            foreach (var b in lit.Values) b.Dispose();
            foreach (var b in dim.Values) b.Dispose();
            lit.Clear(); dim.Clear();
            scaledFor = iconPx = size;
            foreach (var g in groups)
                foreach (var it in g.Value)
                {
                    var o = Original(it.Icon);
                    if (o == null || lit.ContainsKey(it.Icon)) continue;
                    var a = new Bitmap(size, size, PixelFormat.Format32bppPArgb);
                    var b = new Bitmap(size, size, PixelFormat.Format32bppPArgb);
                    using (var ga = Graphics.FromImage(a))
                    using (var gb = Graphics.FromImage(b))
                    {
                        foreach (var gg in new[] { ga, gb })
                        {
                            gg.InterpolationMode = InterpolationMode.HighQualityBicubic;
                            gg.PixelOffsetMode = PixelOffsetMode.HighQuality;
                        }
                        ga.DrawImage(o, new Rectangle(0, 0, size, size));
                        gb.DrawImage(o, new Rectangle(0, 0, size, size), 0, 0, o.Width, o.Height, GraphicsUnit.Pixel, Greyed);
                    }
                    lit[it.Icon] = a; dim[it.Icon] = b;
                }
        }

        protected override void OnResize(EventArgs e) { planW = -1; Invalidate(); base.OnResize(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Paper.Bg);
            Plan();
            int off = Scroll.Offset;
            Gfx.Smooth(g);
            foreach (var h in heads)
            {
                var r = h.Key; r.Offset(0, -off);
                if (r.Bottom < 0 || r.Top > Height) continue;
                var list = groups.First(x => x.Key == h.Value).Value;
                string cnt = list.Count(i => i.Count > 0) + "/" + list.Count;
                var hf = HeadFont;
                var ts = Measure.Text(h.Value, hf);
                Gfx.Text(g, h.Value, hf, new Rectangle(r.X + Px(2), r.Y, ts.Width + Px(2), r.Height), Paper.InkDim, Gfx.Left & ~TextFormatFlags.EndEllipsis);
                var cf = F(8.5f);
                var cs = Measure.Text(cnt, cf);
                Gfx.Text(g, cnt, cf, new Rectangle(r.Right - cs.Width - Px(2), r.Y, cs.Width + Px(2), r.Height), Paper.InkFaint, Gfx.Left & ~TextFormatFlags.EndEllipsis);
                int lx0 = r.X + Px(2) + ts.Width + Px(8), lx1 = r.Right - cs.Width - Px(8);
                if (lx1 > lx0) using (var pen = new Pen(Paper.Line, Math.Max(1f, S))) g.DrawLine(pen, lx0, r.Y + r.Height / 2 + Px(1), lx1, r.Y + r.Height / 2 + Px(1));
            }
            var nf = F(7f);
            foreach (var c in cells)
            {
                var r = c.Key; r.Offset(0, -off);
                if (r.Bottom < 0 || r.Top > Height) continue;
                var it = c.Value;
                bool have = it.Count > 0;
                var box = new RectangleF(r.X + Px(2), r.Y + Px(2), r.Width - Px(4), r.Height - Px(4));
                if (have)
                {
                    Gfx.Fill(g, box, Px(5), Paper.Card);
                    Gfx.Stroke(g, box, Px(5), Paper.Gold, Math.Max(1.5f, 1.6f * S));
                }
                else if (it == hover) Gfx.Fill(g, box, Px(5), Paper.Hover);
                if (it == hover) Gfx.Stroke(g, box, Px(5), Paper.BorderHi, Math.Max(1f, S));
                Bitmap bmp;
                if (it.Icon != null && (have ? lit : dim).TryGetValue(it.Icon, out bmp))
                {
                    g.InterpolationMode = InterpolationMode.NearestNeighbor;
                    g.DrawImage(bmp, new Rectangle(r.X + (r.Width - iconPx) / 2, r.Y + (r.Height - iconPx) / 2, iconPx, iconPx), 0, 0, iconPx, iconPx, GraphicsUnit.Pixel);
                }
                else
                    Gfx.Text(g, it.Name, nf, Rectangle.Inflate(r, -Px(3), -Px(3)), have ? Paper.Ink : Paper.InkFaint,
                             TextFormatFlags.WordBreak | TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPrefix);
                if (it.Count > 1 || (it.Count > 0 && IsCounter(it)))
                {
                    string t = it.Count.ToString();
                    var bf = F(8f, FontStyle.Bold);
                    var bs = Measure.Text(t, bf);
                    int bw = Math.Max(Px(16), bs.Width + Px(2)), bh = Px(15);
                    var br = new Rectangle(r.Right - bw - Px(2), r.Bottom - bh - Px(2), bw, bh);
                    Gfx.Fill(g, br, bh / 2f, Pal.GoldInk);
                    Gfx.Text(g, t, bf, br, Pal.GoldHi, Gfx.Center & ~TextFormatFlags.EndEllipsis);
                }
            }
            Scroll.Draw(g);
        }

        // Gold Skulltula Tokens show a count even at one. Bags and wallets show their upgrade tier.
        static bool IsCounter(ItemInfo it) { return it.Name == "Gold Skulltula Tokens"; }

        ItemInfo At(Point p)
        {
            var q = new Point(p.X, p.Y + Scroll.Offset);
            foreach (var c in cells) if (c.Key.Contains(q)) return c.Value;
            return null;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (Scroll.MouseMove(e) && Capture) return;
            var it = Scroll.InBar(e.Location) ? null : At(e.Location);
            if (it != hover)
            {
                hover = it;
                Invalidate();
                if (it == null) Tips.Hide();
                else
                {
                    string t = it.Name + (it.Count > 1 || (it.Count > 0 && IsCounter(it)) ? "  ×" + it.Count : "") + (it.Count > 0 ? "\nFound" : "\nNot found yet");
                    Tips.Show(t, PointToScreen(new Point(e.X + Px(14), e.Y + Px(18))), Dpi);
                }
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e) { Scroll.Leave(); hover = null; Tips.Hide(); Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { Focus(); Scroll.MouseDown(e); base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { Scroll.MouseUp(); base.OnMouseUp(e); }
        protected override void OnMouseWheel(MouseEventArgs e) { Tips.Hide(); Scroll.Wheel(e.Delta); }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                foreach (var b in lit.Values) b.Dispose();
                foreach (var b in dim.Values) b.Dispose();
                foreach (var b in originals.Values) if (b != null) b.Dispose();
            }
            base.Dispose(disposing);
        }
    }

    // Checks
    // a heading row in the checks lists (a dungeon's floor, a kind of the checks without a spot)
    public class Head
    {
        public string Text, Count;
        public int Avail;     // its checks in logic now (a green badge, once the logic is known)
        public int MaxAvail;  // the biggest Avail among the list's headings, so one badge width fits all of them
        public string WidestCount;  // the widest count among them, so they all share one count column
        public MapInfo Map;
    }

    // The last row of a list that only shows the checks in logic. It says what's left out and a click shows it all.
    public class MoreRow
    {
        public string Text, Action;
    }

    // Logic
    // What the views show of the seed's logic: whether it's known (the logic answered for this save) and whether the
    // player chose to see only what's in logic. It's one green throughout. A number in a green pill means "in logic
    // now", and a check not in logic yet is a hollow ring in its kind's colour, with fainter ink.
    public static class LogicView
    {
        public static bool On;            // Check.Reach is known
        public static bool OnlyInLogic;   // the lists and the map leave out what isn't in logic yet
        public static readonly Color Green = Color.FromArgb(62, 120, 50);         // the pill (parchment and wood)
        public static readonly Color GreenInk = Color.FromArgb(250, 246, 232);
        public static readonly Color GreenOnWood = Color.FromArgb(118, 168, 84);  // the header bar's part in logic
        public static readonly Color LinkInk = Color.FromArgb(136, 96, 28);       // a click on the parchment ("Show all")

        public static bool IsDone(Check c) { return c.Done || c.Manual; }
        public static bool Locked(Check c) { return On && !IsDone(c) && !c.Reach; }
        public static bool Hidden(Check c) { return OnlyInLogic && Locked(c); }

        static int P(int dpi, float v) { return (int)Math.Round(v * dpi / 96f); }

        public static int BadgeHeight(int dpi) { return P(dpi, 18); }

        static readonly Dictionary<long, int> widths = new Dictionary<long, int>();

        /// <summary>The badge width for a list whose biggest number is maxN. Every badge in a list gets this width, so
        /// they stand in one straight column however many digits they have.</summary>
        public static int BadgeWidth(int maxN, int dpi)
        {
            int digits = Math.Max(1, Math.Max(0, maxN).ToString().Length);
            long key = digits * 100000L + dpi;
            int w;
            if (widths.TryGetValue(key, out w)) return w;
            using (var path = NumberPath(new string('8', digits), dpi))
                w = Math.Max(BadgeHeight(dpi) + P(dpi, 4), (int)Math.Ceiling(path.GetBounds().Width) + P(dpi, 14));
            return widths[key] = w;
        }

        static GraphicsPath NumberPath(string s, int dpi)
        {
            var p = new GraphicsPath();
            var f = Fonts.Get(dpi, 8.5f, FontStyle.Bold);
            p.AddString(s, f.FontFamily, (int)FontStyle.Bold, 8.5f * dpi / 72f, PointF.Empty, StringFormat.GenericTypographic);
            return p;
        }

        /// <summary>The green badge filling r, its number centred on the digits' own shapes (not on the font's line box,
        /// which would leave more room on one side).</summary>
        public static void DrawBadge(Graphics g, Rectangle r, int n, int dpi)
        {
            Gfx.Smooth(g);
            Gfx.Fill(g, new RectangleF(r.X, r.Y, r.Width, r.Height), r.Height / 2f, Green);
            using (var path = NumberPath(n.ToString(), dpi))
            {
                var b = path.GetBounds();
                using (var m = new Matrix())
                {
                    m.Translate(r.X + (r.Width - b.Width) / 2f - b.X, r.Y + (r.Height - b.Height) / 2f - b.Y);
                    path.Transform(m);
                }
                using (var br = new SolidBrush(GreenInk)) g.FillPath(br, path);
            }
        }
    }

    // How a check's row looks in the list on the left and on the board. It's a dot in its kind's colour (grey with a
    // tick once done), its name, and its item once spoiled. A long name ends in "..." and shows whole on hover.
    public static class CheckRows
    {
        static int P(int dpi, float v) { return (int)Math.Round(v * dpi / 96f); }

        public static void DrawHead(Graphics g, Rectangle r, Head hd, int dpi)
        {
            using (var b = new SolidBrush(Paper.Bg)) g.FillRectangle(b, r);
            var sf = Fonts.Get(dpi, 9.5f, FontStyle.Bold, Fonts.Serif);
            var cf = Fonts.Get(dpi, 9f);
            var ts = Measure.Text(hd.Text, sf);
            int cw = Math.Max(Measure.Text(hd.Count ?? "", cf).Width, Measure.Text(hd.WidestCount ?? "", cf).Width);
            int bwide = LogicView.BadgeWidth(Math.Max(hd.MaxAvail, hd.Avail), dpi);
            int bw = LogicView.On && hd.Avail > 0 ? bwide + P(dpi, 8) : 0;
            var tr = new Rectangle(r.X + P(dpi, 10), r.Y + P(dpi, 3), Math.Min(ts.Width + P(dpi, 2), r.Width - P(dpi, 20) - cw - bw), r.Height - P(dpi, 3));
            Gfx.Text(g, hd.Text, sf, tr, Paper.Gold, Gfx.Left);
            var cr = new Rectangle(r.Right - P(dpi, 16) - cw, tr.Y, cw, tr.Height);
            Gfx.Text(g, hd.Count ?? "", cf, cr, Paper.InkFaint, Gfx.Right & ~TextFormatFlags.EndEllipsis);
            if (bw > 0)
            {
                int bh = LogicView.BadgeHeight(dpi);
                LogicView.DrawBadge(g, new Rectangle(cr.X - bw, tr.Y + (tr.Height - bh) / 2, bwide, bh), hd.Avail, dpi);
            }
            int lineEnd = cr.X - bw - P(dpi, 8);
            if (lineEnd > tr.Right + P(dpi, 6))
                using (var pen = new Pen(Paper.Line, Math.Max(1f, dpi / 96f)))
                    g.DrawLine(pen, tr.Right + P(dpi, 6), tr.Y + tr.Height / 2, lineEnd, tr.Y + tr.Height / 2);
        }

        public static string Text(Check c)
        {
            return c.Name + (c.Item != null ? "  —  " + c.Item : "") + (c.Manual ? "  ·  by hand" : "");
        }

        public static void DrawCheck(Graphics g, Rectangle r, Check c, bool sel, bool hover, int dpi)
        {
            bool done = c.Done || c.Manual, locked = LogicView.Locked(c);
            using (var b = new SolidBrush(sel ? Pal.Gold : hover ? Paper.Hover : Paper.Bg)) g.FillRectangle(b, r);
            Gfx.Smooth(g);
            float d = P(dpi, 10);
            var dot = new RectangleF(r.X + P(dpi, 10), r.Y + (r.Height - d) / 2f, d, d);
            if (locked)
            {
                // not in logic yet, so a hollow ring in its kind's colour (darkened enough to read on the parchment)
                var ring = Gfx.Mix(Theme.KindColour(c.Kind), Paper.Ink, 0.35f);
                float w = Math.Max(1.6f, 2f * dpi / 96f);
                using (var pen = new Pen(ring, w)) g.DrawEllipse(pen, RectangleF.Inflate(dot, -w / 2f, -w / 2f));
            }
            else
            {
                using (var b = new SolidBrush(done ? Paper.Done : Theme.KindColour(c.Kind))) g.FillEllipse(b, dot);
                using (var pen = new Pen(Color.FromArgb(170, 52, 36, 22), Math.Max(1f, dpi / 96f))) g.DrawEllipse(pen, dot);
                if (done) Gfx.Tick(g, RectangleF.Inflate(dot, -P(dpi, 1), -P(dpi, 1)), Paper.Card, Math.Max(1.3f, 1.4f * dpi / 96f));
            }
            var f = Fonts.Get(dpi, 9.5f);
            int tw = r.Width - P(dpi, 28) - P(dpi, 10);
            int th = Measure.Wrapped(Text(c), f, Math.Max(1, tw)).Height;  // wrapped, never cut, the row is as tall
            var tr = new Rectangle(r.X + P(dpi, 28), r.Y + (r.Height - th) / 2, tw, th);
            Gfx.Text(g, Text(c), f, tr, sel ? Pal.GoldInk : done ? Paper.InkFaint : locked ? Paper.InkDim : Paper.Ink, Gfx.Wrap);
        }

        static Font MoreFont(int dpi) { return Fonts.Get(dpi, 9f); }
        static Font MoreActionFont(int dpi) { return Fonts.Get(dpi, 9.5f, FontStyle.Bold); }

        /// <summary>The "more" row's height at 96 DPI for a row width in pixels (its lines wrap).</summary>
        public static int MoreHeight(MoreRow m, int width, int dpi)
        {
            int w = Math.Max(P(dpi, 40), width - P(dpi, 24));
            int h = Measure.Wrapped(m.Text, MoreFont(dpi), w).Height;
            if (!string.IsNullOrEmpty(m.Action)) h += P(dpi, 3) + Measure.Wrapped(m.Action, MoreActionFont(dpi), w).Height;
            return (int)Math.Ceiling(h * 96.0 / dpi) + 18;
        }

        public static void DrawMore(Graphics g, Rectangle r, MoreRow m, bool hover, int dpi)
        {
            using (var b = new SolidBrush(hover && !string.IsNullOrEmpty(m.Action) ? Paper.Hover : Paper.Bg)) g.FillRectangle(b, r);
            using (var pen = new Pen(Paper.Line, Math.Max(1f, dpi / 96f))) g.DrawLine(pen, r.X + P(dpi, 10), r.Y + P(dpi, 3), r.Right - P(dpi, 14), r.Y + P(dpi, 3));
            int x = r.X + P(dpi, 12), w = Math.Max(P(dpi, 40), r.Width - P(dpi, 24));
            var ts = Measure.Wrapped(m.Text, MoreFont(dpi), w);
            var acts = string.IsNullOrEmpty(m.Action) ? Size.Empty : Measure.Wrapped(m.Action, MoreActionFont(dpi), w);
            int total = ts.Height + (acts.Height > 0 ? P(dpi, 3) + acts.Height : 0);
            int y = r.Y + P(dpi, 3) + (r.Height - P(dpi, 3) - total) / 2;
            Gfx.Text(g, m.Text, MoreFont(dpi), new Rectangle(x, y, w, ts.Height), Paper.InkDim, Gfx.Wrap);
            if (acts.Height > 0)
                Gfx.Text(g, m.Action, MoreActionFont(dpi), new Rectangle(x, y + ts.Height + P(dpi, 3), w, acts.Height), LogicView.LinkInk, Gfx.Wrap);
        }

        public static string Tip(Check c)
        {
            string where = c.On != null && c.On.Chip != null ? "\nOn " + c.On.Chip : "";
            return c.Name + where + "\n" + Theme.Describe(c);
        }
    }

    // The checks without a spot on a map, shown where the map would be in columns by kind. Right-click marks one by
    // hand.
    public class CheckBoard : UiControl
    {
        readonly List<object> rows = new List<object>();
        // in content coordinates
        readonly List<KeyValuePair<Rectangle, object>> cells = new List<KeyValuePair<Rectangle, object>>();
        public readonly ScrollCore Scroll;
        public event Action<Check, MouseButtons> CheckClick;
        public event Action<MoreRow> MoreClick;
        public Check Selected;
        Check hover;
        int planW = -1, planDpi = -1;

        public CheckBoard()
        {
            Scroll = new ScrollCore(this) { OnPaper = true };
            BackColor = Paper.Bg;
            TabStop = true;
        }

        public void SetRows(IEnumerable<object> r, bool keepScroll)
        {
            rows.Clear(); rows.AddRange(r);
            planW = -1;
            if (!keepScroll) Scroll.Offset = 0;
            Invalidate();
        }

        void Plan()
        {
            if (planW == Width && planDpi == Dpi) return;
            planW = Width; planDpi = Dpi;
            cells.Clear();
            int pad = Px(6), inner = Math.Max(Px(100), Width - 2 * pad - Px(12));
            // columns as wide as nine names in ten need (the rest end in "..." and show whole on hover)
            var f = Fonts.Get(Dpi, 9.5f);
            var widths = rows.OfType<Check>().Select(c => Measure.Text(CheckRows.Text(c), f).Width).OrderBy(w => w).ToList();
            int need = widths.Count == 0 ? Px(250) : widths[Math.Min(widths.Count - 1, widths.Count * 9 / 10)] + Px(46);
            need = Math.Max(Px(220), Math.Min(Px(440), need));
            int cols = Math.Max(1, (inner + need / 3) / need), cw = inner / cols, rh = Px(24), hh = Px(30);
            int y = Px(4), col = 0;
            foreach (var o in rows)
            {
                if (o is Head || o is MoreRow)
                {
                    if (col > 0)
                    {
                        y += rh;
                        col = 0;
                    }
                    int h = o is MoreRow ? Px(CheckRows.MoreHeight((MoreRow)o, inner, Dpi)) : hh;
                    cells.Add(new KeyValuePair<Rectangle, object>(new Rectangle(pad, y, inner, h), o));
                    y += h;
                }
                else
                {
                    cells.Add(new KeyValuePair<Rectangle, object>(new Rectangle(pad + col * cw, y, cw, rh), o));
                    if (++col == cols)
                    {
                        col = 0;
                        y += rh;
                    }
                }
            }
            if (col > 0) y += rh;
            Scroll.Content = y + Px(6);
            Scroll.Line = 24;
            Scroll.Clamp();
        }

        protected override void OnResize(EventArgs e) { planW = -1; base.OnResize(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Paper.Bg);
            Plan();
            int off = Scroll.Offset;
            foreach (var c in cells)
            {
                var r = c.Key; r.Offset(0, -off);
                if (r.Bottom < 0 || r.Top > Height) continue;
                var hd = c.Value as Head;
                var mr = c.Value as MoreRow;
                if (hd != null) CheckRows.DrawHead(g, r, hd, Dpi);
                else if (mr != null) CheckRows.DrawMore(g, r, mr, mr == hoverMore, Dpi);
                else
                {
                    var ch = (Check)c.Value;
                    CheckRows.DrawCheck(g, r, ch, ch == Selected, ch == hover, Dpi);
                }
            }
            Scroll.Draw(g);
        }

        Check At(Point p) { return AtAny(p) as Check; }

        object AtAny(Point p)
        {
            var q = new Point(p.X, p.Y + Scroll.Offset);
            foreach (var c in cells) if (c.Key.Contains(q)) return c.Value;
            return null;
        }

        MoreRow hoverMore;

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (Scroll.MouseMove(e) && Capture) return;
            var o = Scroll.InBar(e.Location) ? null : AtAny(e.Location);
            var m = o as MoreRow;
            if (m != hoverMore)
            {
                hoverMore = m;
                Cursor = m != null ? Cursors.Hand : Cursors.Default;
                Invalidate();
            }
            var c = o as Check;
            if (c != hover)
            {
                hover = c;
                Invalidate();
                if (c == null) Tips.Hide();
                else Tips.Show(CheckRows.Tip(c), PointToScreen(new Point(e.X + Px(16), e.Y + Px(18))), Dpi);
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e) { Scroll.Leave(); hover = null; hoverMore = null; Tips.Hide(); Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseUp(MouseEventArgs e) { Scroll.MouseUp(); base.OnMouseUp(e); }
        protected override void OnMouseWheel(MouseEventArgs e) { Tips.Hide(); Scroll.Wheel(e.Delta); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            Focus();
            if (Scroll.MouseDown(e)) return;
            var mr = AtAny(e.Location) as MoreRow;
            if (mr != null && e.Button == MouseButtons.Left && MoreClick != null)
            {
                MoreClick(mr);
                return;
            }
            var c = At(e.Location);
            if (c != null)
            {
                if (e.Button == MouseButtons.Left)
                {
                    Selected = c;
                    Invalidate();
                }
                if (CheckClick != null) CheckClick(c, e.Button);
            }
            base.OnMouseDown(e);
        }
    }

    // Status
    // The line at the bottom with the save, whether the game runs, hearts and tokens. Its parts wrap onto a second
    // line instead of being cut, and a part with more to say (the save's full path) says it on hover.
    public class StatusBar : UiControl, IFlow
    {
        public class Part { public string Text, Tip; public Color Colour; }
        public readonly List<Part> Parts = new List<Part>();
        readonly List<Rectangle> rects = new List<Rectangle>();
        string sig = "";
        int hover = -1;

        public StatusBar() { BackColor = Pal.Panel; }

        public bool SetParts(List<Part> parts)
        {
            string s = string.Join("\u0001", parts.Select(p => p.Text + "\u0002" + p.Colour.ToArgb() + "\u0002" + p.Tip).ToArray());
            if (s == sig) return false;
            bool relayout = HeightFor(Width, parts) != HeightFor(Width);
            sig = s;
            Parts.Clear(); Parts.AddRange(parts);
            rects.Clear();
            if (relayout && Parent != null) Parent.PerformLayout();
            Invalidate();
            return true;
        }

        public int HeightFor(int width) { return HeightFor(width, Parts); }

        int HeightFor(int width, List<Part> parts) { return Flow(width, parts, null); }

        int Flow(int width, List<Part> parts, List<Rectangle> outR)
        {
            var f = F(9f);
            int padX = Px(12), gap = Px(26), lh = Px(26), x = padX, y = 0, inner = width - 2 * padX;
            foreach (var p in parts)
            {
                var s = Measure.Text(p.Text, f);
                int w = s.Width, h = lh;
                if (w > inner)
                {
                    var ws = Measure.Wrapped(p.Text, f, inner);
                    w = inner;
                    h = ws.Height + Px(8);
                }
                if (x > padX && x + w > width - padX)
                {
                    x = padX;
                    y += lh;
                }
                if (outR != null) outR.Add(new Rectangle(x, y, w + Px(2), h));
                x += w + gap;
                if (h > lh) y += h - lh;
            }
            return y + lh;
        }

        protected override void OnLayout(LayoutEventArgs e) { rects.Clear(); base.OnLayout(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, 0, 0, Width, 0);
            if (rects.Count != Parts.Count)
            {
                rects.Clear();
                Flow(Width, Parts, rects);
            }
            var f = F(9f);
            Gfx.Smooth(g);
            for (int i = 0; i < Parts.Count; i++)
            {
                var r = rects[i];
                bool wrap = r.Height > Px(26);
                Gfx.Text(g, Parts[i].Text, f, wrap ? new Rectangle(r.X, r.Y + Px(4), r.Width, r.Height - Px(4)) : r, Parts[i].Colour,
                         wrap ? Gfx.Wrap : (Gfx.Left & ~TextFormatFlags.EndEllipsis));
                if (i > 0 && rects[i].Y == rects[i - 1].Y)
                {
                    float cx = rects[i - 1].Right + (r.X - rects[i - 1].Right) / 2f, cy = r.Y + Px(13);
                    Gfx.Fill(g, new RectangleF(cx - Px(2), cy - Px(2), Px(4), Px(4)), Px(2), Pal.GoldDim);
                }
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            int h = -1;
            for (int i = 0; i < rects.Count && i < Parts.Count; i++) if (rects[i].Contains(e.Location) && Parts[i].Tip != null) h = i;
            if (h != hover)
            {
                hover = h;
                if (h < 0) Tips.Hide();
                else Tips.Show(Parts[h].Tip, PointToScreen(new Point(e.X + Px(10), rects[h].Y - Px(60))), Dpi);
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e) { hover = -1; Tips.Hide(); base.OnMouseLeave(e); }
    }

    // The red line under the header once the spoiler was opened for this seed and save.
    public class Banner : UiControl, IFlow
    {
        public Banner() { BackColor = Pal.RedBg; }

        Font Font9 { get { return F(10f, FontStyle.Bold); } }

        public int HeightFor(int width)
        {
            if (string.IsNullOrEmpty(Text)) return 0;
            return Measure.Wrapped(Text, Font9, width - Px(32)).Height + Px(12);
        }

        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.RedBg);
            using (var pen = new Pen(Pal.Red)) g.DrawLine(pen, 0, Height - 1, Width, Height - 1);
            var s = Measure.Wrapped(Text, Font9, Width - Px(32));
            Gfx.Text(g, Text, Font9, new Rectangle(Px(16), (Height - s.Height) / 2, Width - Px(32), s.Height + Px(2)), Pal.Text,
                     Gfx.Wrap | TextFormatFlags.HorizontalCenter);
        }
    }

    // Menus
    // Parchment menus like the randomizer's, with brown ink and a gold tick, sized for the window's DPI each time
    // they open.
    public static class Menus
    {
        public static ContextMenuStrip New()
        {
            return new ContextMenuStrip { Renderer = new ParchmentMenuRenderer(), ShowImageMargin = false, ShowCheckMargin = true, DropShadowEnabled = true };
        }

        public static void Prepare(ContextMenuStrip m, int dpi)
        {
            m.Font = Fonts.Get(dpi, 10f);
            int v = 5 * dpi / 96;
            m.ImageScalingSize = new Size(16 * dpi / 96, 16 * dpi / 96);
            m.Padding = new Padding(0, 4 * dpi / 96, 0, 4 * dpi / 96);
            foreach (ToolStripItem it in m.Items)
            {
                it.Font = m.Font;
                if (it is ToolStripMenuItem) it.Padding = new Padding(4 * dpi / 96, v, 12 * dpi / 96, v);
                else if (it is ToolStripSeparator) it.Margin = new Padding(0, 3 * dpi / 96, 0, 3 * dpi / 96);
            }
        }
    }

    class ParchmentMenuRenderer : ToolStripProfessionalRenderer
    {
        public ParchmentMenuRenderer() : base(new Colours()) { RoundedEdges = false; }

        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = e.Item.Enabled ? Paper.Ink : Paper.InkFaint;
            base.OnRenderItemText(e);
        }

        protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e)
        {
            var g = e.Graphics;
            var r = e.ImageRectangle;
            int s = Math.Min(r.Width, r.Height);
            var box = new RectangleF(r.X + (r.Width - s) / 2f, r.Y + (r.Height - s) / 2f, s, s);
            var old = g.SmoothingMode;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Gfx.Fill(g, box, s / 5f, Paper.Gold);
            Gfx.Tick(g, box, Paper.Ink, Math.Max(1.5f, s / 9f));
            g.SmoothingMode = old;
        }

        class Colours : ProfessionalColorTable
        {
            public override Color ToolStripDropDownBackground { get { return Paper.Card; } }
            public override Color MenuBorder { get { return Pal.GoldDim; } }
            public override Color MenuItemBorder { get { return Paper.BorderHi; } }
            public override Color MenuItemSelected { get { return Paper.Hover; } }
            public override Color ImageMarginGradientBegin { get { return Paper.Card; } }
            public override Color ImageMarginGradientMiddle { get { return Paper.Card; } }
            public override Color ImageMarginGradientEnd { get { return Paper.Card; } }
            public override Color SeparatorDark { get { return Paper.Border; } }
            public override Color SeparatorLight { get { return Paper.Card; } }
            public override Color MenuItemSelectedGradientBegin { get { return Paper.Hover; } }
            public override Color MenuItemSelectedGradientEnd { get { return Paper.Hover; } }
            public override Color CheckBackground { get { return Paper.Card; } }
            public override Color CheckSelectedBackground { get { return Paper.Hover; } }
            public override Color CheckPressedBackground { get { return Paper.Hover; } }
        }
    }

    // Dialog
    // A small dialog in the app's look instead of the system's message box and Visual Basic's input box. It has a
    // gold heading, the message, an optional text field with quick picks under it, and the buttons.
    public class AskDialog : DpiForm
    {
        readonly string heading, message;
        readonly FlatButton ok, cancel;
        public readonly TextField Field;
        readonly List<string> picks;
        readonly List<Rectangle> pickR = new List<Rectangle>();
        Rectangle headR, msgR, picksLabelR;
        int hoverPick = -1;
        const int W = 470;

        AskDialog(string heading, string message, string okText, string cancelText, ButtonKind okKind, bool field, string value, string cue, List<string> picks)
        {
            this.heading = heading; this.message = message; this.picks = picks ?? new List<string>();
            Text = heading;
            Icon = AppIcon();
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.CenterParent;
            BackColor = Pal.Panel;
            KeyPreview = true;
            ok = new FlatButton { Text = okText, Kind = okKind, FontPt = okKind == ButtonKind.Primary ? 10f : 10f };
            ok.Click += (s, e) => { DialogResult = DialogResult.OK; Close(); };
            Controls.Add(ok);
            if (cancelText != null)
            {
                cancel = new FlatButton { Text = cancelText };
                cancel.Click += (s, e) => { DialogResult = DialogResult.Cancel; Close(); };
                Controls.Add(cancel);
            }
            if (field)
            {
                Field = new TextField { Cue = cue, FontPt = 10.5f, BackColor = Pal.Panel };
                Field.Text = value ?? "";
                Field.Box.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; DialogResult = DialogResult.OK; Close(); } };
                Controls.Add(Field);
            }
            ClientSize = new Size(W, 200);
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape)
            {
                DialogResult = cancel != null ? DialogResult.Cancel : DialogResult.OK;
                Close();
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.Enter && Field == null)
            {
                DialogResult = DialogResult.OK;
                Close();
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (Field != null) { Field.Box.Focus(); Field.Box.SelectAll(); } else ok.Focus();
        }

        protected override void OnDpiApplied()
        {
            ClientSize = new Size(Px(W), Plan(true));
        }

        int Plan(bool apply)
        {
            int pad = Px(20), w = Px(W) - 2 * pad, y = Px(16);
            var hs = Measure.Wrapped(heading, F13, w);
            if (apply) headR = new Rectangle(pad, y, w, hs.Height + Px(2));
            y += hs.Height + Px(8);
            var ms = Measure.Wrapped(message, F10, w);
            if (apply) msgR = new Rectangle(pad, y, w, ms.Height + Px(2));
            y += ms.Height + Px(12);
            if (Field != null)
            {
                if (apply) Field.SetBounds(pad, y, w, Px(34));
                y += Px(34) + Px(10);
            }
            if (picks.Count > 0)
            {
                var ls = Measure.Text("Saves found:", F9);
                if (apply)
                {
                    picksLabelR = new Rectangle(pad, y, ls.Width + Px(2), Px(26));
                    pickR.Clear();
                }
                int x = pad + ls.Width + Px(8), lineH = Px(26), gap = Px(6);
                foreach (var p in picks)
                {
                    int cw = Measure.Text(Label(p), F9).Width + Px(20);
                    cw = Math.Min(cw, w);
                    if (x + cw > pad + w)
                    {
                        x = pad;
                        y += lineH + gap;
                    }
                    if (apply) pickR.Add(new Rectangle(x, y, cw, lineH));
                    x += cw + gap;
                }
                y += lineH + Px(14);
            }
            int bh = Px(34), bw1 = Math.Max(Px(96), Measure.Text(ok.Text, Fonts.Get(Dpi, 11f, FontStyle.Bold, Fonts.Serif)).Width + Px(32));
            int bw2 = cancel == null ? 0 : Math.Max(Px(96), Measure.Text(cancel.Text, F10).Width + Px(32));
            if (apply)
            {
                ok.SetBounds(pad + w - bw1, y, bw1, bh);
                if (cancel != null) cancel.SetBounds(ok.Left - Px(8) - bw2, y, bw2, bh);
            }
            return y + bh + Px(18);
        }

        static string Label(string p) { return string.IsNullOrEmpty(p) ? "Newest save" : p; }

        Font F13 { get { return Fonts.Get(Dpi, 13f, FontStyle.Bold, Fonts.Serif); } }
        Font F10 { get { return Fonts.Get(Dpi, 10f); } }
        Font F9 { get { return Fonts.Get(Dpi, 9f); } }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            Gfx.Text(g, heading, F13, headR, Pal.Gold, Gfx.Wrap);
            Gfx.Text(g, message, F10, msgR, Pal.Text, Gfx.Wrap);
            if (picks.Count > 0)
            {
                Gfx.Text(g, "Saves found:", F9, picksLabelR, Pal.TextDim, Gfx.Left & ~TextFormatFlags.EndEllipsis);
                Gfx.Smooth(g);
                for (int i = 0; i < pickR.Count; i++)
                {
                    var r = new RectangleF(pickR[i].X + 0.5f, pickR[i].Y + 0.5f, pickR[i].Width - 1, pickR[i].Height - 1);
                    bool sel = Field != null && string.Equals(Field.Text.Trim(), picks[i], StringComparison.OrdinalIgnoreCase);
                    Gfx.Fill(g, r, Px(4), sel ? Pal.Gold : i == hoverPick ? Pal.Hover : Pal.Raised);
                    Gfx.Stroke(g, r, Px(4), sel ? Pal.GoldHi : Pal.Border, Math.Max(1f, S));
                    Gfx.Text(g, Label(picks[i]), F9, pickR[i], sel ? Pal.GoldInk : Pal.Text, Gfx.Center & ~TextFormatFlags.EndEllipsis);
                }
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            int h = -1;
            for (int i = 0; i < pickR.Count; i++) if (pickR[i].Contains(e.Location)) h = i;
            if (h != hoverPick)
            {
                hoverPick = h;
                Cursor = h >= 0 ? Cursors.Hand : Cursors.Default;
                Invalidate();
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            for (int i = 0; i < pickR.Count; i++)
                if (pickR[i].Contains(e.Location) && Field != null)
                {
                    Field.Text = picks[i];
                    Invalidate();
                    Field.Box.Focus();
                }
            base.OnMouseDown(e);
        }

        public static bool Confirm(IWin32Window owner, string heading, string message, string okText, string cancelText, bool danger)
        {
            using (var d = new AskDialog(heading, message, okText, cancelText, danger ? ButtonKind.Danger : ButtonKind.Primary, false, null, null, null))
                return d.ShowDialog(owner) == DialogResult.OK;
        }

        public static void Tell(IWin32Window owner, string heading, string message)
        {
            using (var d = new AskDialog(heading, message, "OK", null, ButtonKind.Primary, false, null, null, null))
                d.ShowDialog(owner);
        }

        // for the screenshot mode (--dialog), the dialog as it would open
        public static AskDialog ForTest(string kind)
        {
            if (kind == "spoiler")
                return new AskDialog("Open the spoiler", "Show every check's item?\n\nThis marks this seed and save as spoiled, for good.", "Show the items", "Cancel", ButtonKind.Danger, false, null, null, null);
            return new AskDialog("Save slot", "Track one save slot only (e.g. slot_03), or leave it empty for the newest save of any slot.", "Use it", "Cancel",
                                 ButtonKind.Primary, true, "slot_03", "Empty: the newest save", new List<string> { "", "slot_01", "slot_02", "slot_03", "slot_04" });
        }
        /// <summary>The text typed (empty allowed), or null when cancelled.</summary>
        public static string AskText(IWin32Window owner, string heading, string message, string value, string cue, List<string> picks)
        {
            using (var d = new AskDialog(heading, message, "Use it", "Cancel", ButtonKind.Primary, true, value, cue, picks))
                return d.ShowDialog(owner) == DialogResult.OK ? d.Field.Text : null;
        }
    }
}
