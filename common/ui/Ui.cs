// The WinForms controls and the wood, gold and parchment colours both apps share. DpiForm.Px scales from 96 DPI
// and Fonts.Get makes pixel fonts at the window's DPI. With PerMonitorV2, WM_DPICHANGED lays the window out again
// when it moves to a display with a different scale, so it stays sharp instead of stretching a bitmap.
// UiControl and VirtualList draw the lists, menus and buttons. A list is one window handle and only paints the
// visible rows. It's double buffered so it doesn't flicker, and scrolling skips layout so it stays quick on
// slower PCs.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace RemakeUi
{
    static class Native
    {
        [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] static extern int SetWindowTheme(IntPtr hwnd, string app, string id);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd, int msg, IntPtr w, string l);
        [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        public static int Dpi(IntPtr hwnd)
        {
            try { uint d = GetDpiForWindow(hwnd); if (d > 0) return (int)d; } catch (Exception) { }
            using (var g = Graphics.FromHwnd(hwnd)) return (int)g.DpiX;
        }

        public static int SystemDpi()
        {
            using (var g = Graphics.FromHwnd(IntPtr.Zero)) return (int)g.DpiX;
        }

        // the dark title bar (Windows 10 1809+) and, on Windows 11, the caption in the app's own colours
        public static void DarkTitle(IntPtr hwnd, Color caption, Color text)
        {
            try
            {
                int on = 1;
                if (DwmSetWindowAttribute(hwnd, 20, ref on, 4) != 0) DwmSetWindowAttribute(hwnd, 19, ref on, 4);
                int c = caption.R | (caption.G << 8) | (caption.B << 16);
                DwmSetWindowAttribute(hwnd, 35, ref c, 4);
                int t = text.R | (text.G << 8) | (text.B << 16);
                DwmSetWindowAttribute(hwnd, 36, ref t, 4);
                int b = c;
                DwmSetWindowAttribute(hwnd, 34, ref b, 4);
            }
            catch (Exception) { }
        }

        // dark scroll bars and borders on a standard control (a multi-line text box)
        public static void DarkControl(Control c)
        {
            try { SetWindowTheme(c.Handle, "DarkMode_Explorer", null); } catch (Exception) { }
        }

        public static void Cue(TextBox t, string text)
        {
            try { SendMessage(t.Handle, 0x1501, (IntPtr)1, text); } catch (Exception) { }
        }
    }

    public static class Pal
    {
        // the frame: dark wood, gold lettering
        public static readonly Color Bg = Color.FromArgb(46, 32, 20);
        public static readonly Color Panel = Color.FromArgb(62, 44, 28);
        public static readonly Color Raised = Color.FromArgb(76, 54, 34);
        public static readonly Color Hover = Color.FromArgb(90, 65, 41);
        public static readonly Color Border = Color.FromArgb(98, 74, 46);
        public static readonly Color BorderHi = Color.FromArgb(150, 122, 62);
        public static readonly Color Deep = Color.FromArgb(30, 21, 13);
        public static readonly Color Text = Color.FromArgb(236, 222, 186);
        public static readonly Color TextDim = Color.FromArgb(198, 180, 142);
        public static readonly Color TextFaint = Color.FromArgb(146, 124, 90);
        public static readonly Color Gold = Color.FromArgb(214, 178, 92);
        public static readonly Color GoldHi = Color.FromArgb(232, 200, 120);
        public static readonly Color GoldDim = Color.FromArgb(150, 122, 62);
        public static readonly Color GoldInk = Color.FromArgb(52, 36, 22);
        public static readonly Color Green = Color.FromArgb(150, 196, 110);
        public static readonly Color Red = Color.FromArgb(226, 120, 96);
        public static readonly Color RedBg = Color.FromArgb(120, 30, 20);
    }

    // the pages: parchment, brown ink, gold for what's chosen
    public static class Paper
    {
        public static readonly Color Bg = Color.FromArgb(236, 222, 186);
        public static readonly Color Card = Color.FromArgb(244, 234, 208);
        public static readonly Color Hover = Color.FromArgb(232, 216, 176);
        public static readonly Color Line = Color.FromArgb(218, 200, 158);
        public static readonly Color Border = Color.FromArgb(200, 178, 130);
        public static readonly Color BorderHi = Color.FromArgb(170, 138, 72);
        public static readonly Color Field = Color.FromArgb(250, 244, 228);
        public static readonly Color Ink = Color.FromArgb(52, 36, 22);
        public static readonly Color InkDim = Color.FromArgb(116, 94, 64);
        public static readonly Color InkFaint = Color.FromArgb(166, 148, 114);
        public static readonly Color Gold = Color.FromArgb(196, 154, 60);
        public static readonly Color Done = Color.FromArgb(120, 112, 98);
    }

    public static class Fonts
    {
        static readonly Dictionary<string, Font> cache = new Dictionary<string, Font>();
        public const string Ui = "Segoe UI", UiSemi = "Segoe UI Semibold", Mono = "Consolas", Serif = "Palatino Linotype";

        // a font of `pt` points for a window at `dpi`, in pixels: the same physical size on every screen
        public static Font Get(int dpi, float pt, FontStyle style = FontStyle.Regular, string family = Ui)
        {
            string key = family + "|" + pt + "|" + (int)style + "|" + dpi;
            Font f;
            if (!cache.TryGetValue(key, out f))
            {
                try { f = new Font(family, pt * dpi / 72f, style, GraphicsUnit.Pixel); }
                catch (Exception) { f = new Font(Ui, pt * dpi / 72f, style, GraphicsUnit.Pixel); }
                cache[key] = f;
            }
            return f;
        }
    }

    public static class Gfx
    {
        public static GraphicsPath Round(RectangleF r, float rad)
        {
            var p = new GraphicsPath();
            float d = Math.Max(0.1f, Math.Min(rad * 2, Math.Min(r.Width, r.Height)));
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        public static void Fill(Graphics g, RectangleF r, float rad, Color c)
        {
            if (r.Width <= 0 || r.Height <= 0) return;
            using (var p = Round(r, rad)) using (var b = new SolidBrush(c)) g.FillPath(b, p);
        }

        public static void Stroke(Graphics g, RectangleF r, float rad, Color c, float w)
        {
            if (r.Width <= 0 || r.Height <= 0) return;
            var rr = new RectangleF(r.X + w / 2, r.Y + w / 2, r.Width - w, r.Height - w);
            using (var p = Round(rr, rad)) using (var pen = new Pen(c, w)) g.DrawPath(pen, p);
        }

        public static void Smooth(Graphics g)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        }

        public const TextFormatFlags Left = TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis
                                            | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine;
        public const TextFormatFlags Right = TextFormatFlags.Right | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis
                                             | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine;
        public const TextFormatFlags Center = TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter
                                              | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine;
        public const TextFormatFlags Wrap = TextFormatFlags.Left | TextFormatFlags.Top | TextFormatFlags.WordBreak
                                            | TextFormatFlags.NoPrefix | TextFormatFlags.TextBoxControl;

        // GDI ignores the clip by default. On the settings page that let scrolling text paint over
        // the fixed header.
        public static void Text(Graphics g, string s, Font f, Rectangle r, Color c, TextFormatFlags flags)
        {
            TextRenderer.DrawText(g, s ?? "", f, r, c, flags | TextFormatFlags.PreserveGraphicsClipping);
        }

        // a downward chevron centred in r
        public static void Chevron(Graphics g, RectangleF r, Color c, float w, bool up = false)
        {
            float cx = r.X + r.Width / 2, cy = r.Y + r.Height / 2, s = Math.Min(r.Width, r.Height) / 4;
            using (var pen = new Pen(c, w) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
                g.DrawLines(pen, up ? new[] { new PointF(cx - s, cy + s / 2), new PointF(cx, cy - s / 2), new PointF(cx + s, cy + s / 2) }
                                    : new[] { new PointF(cx - s, cy - s / 2), new PointF(cx, cy + s / 2), new PointF(cx + s, cy - s / 2) });
        }

        public static void Tick(Graphics g, RectangleF r, Color c, float w)
        {
            using (var pen = new Pen(c, w) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
                g.DrawLines(pen, new[] { new PointF(r.X + r.Width * 0.2f, r.Y + r.Height * 0.52f), new PointF(r.X + r.Width * 0.42f, r.Y + r.Height * 0.74f),
                                         new PointF(r.X + r.Width * 0.8f, r.Y + r.Height * 0.28f) });
        }

        public static Color Mix(Color a, Color b, float t)
        {
            return Color.FromArgb((int)(a.A + (b.A - a.A) * t), (int)(a.R + (b.R - a.R) * t), (int)(a.G + (b.G - a.G) * t), (int)(a.B + (b.B - a.B) * t));
        }
    }

    // A window that lays itself out for its screen's DPI and has a dark title bar.
    public class DpiForm : Form
    {
        public int Dpi = 96;
        public event EventHandler DpiApplied;

        public DpiForm()
        {
            AutoScaleMode = AutoScaleMode.None;
            BackColor = Pal.Bg;
            ForeColor = Pal.Text;
            DoubleBuffered = true;
        }

        public float S { get { return Dpi / 96f; } }
        public int Px(float v) { return (int)Math.Round(v * Dpi / 96f); }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            Dpi = Native.Dpi(Handle);
            Native.DarkTitle(Handle, Pal.Bg, Pal.Text);
            ApplyDpi();
        }

        // the first size, written for 96 DPI and scaled for the screen the window opens on
        public void SetLogicalSize(int w, int h, int minW, int minH)
        {
            int dpi = IsHandleCreated ? Dpi : Native.SystemDpi();
            var wa = Screen.PrimaryScreen.WorkingArea;
            Size = new Size(Math.Min(wa.Width - 40, w * dpi / 96), Math.Min(wa.Height - 40, h * dpi / 96));
            MinimumSize = new Size(Math.Min(wa.Width - 40, minW * dpi / 96), Math.Min(wa.Height - 40, minH * dpi / 96));
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == 0x02E0)  // WM_DPICHANGED, the window moved to a screen with other scaling
            {
                int dpi = (int)((long)m.WParam & 0xFFFF);
                var r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                float k = dpi / (float)Dpi;
                Dpi = dpi;
                MinimumSize = new Size((int)(MinimumSize.Width * k), (int)(MinimumSize.Height * k));
                Native.SetWindowPos(Handle, IntPtr.Zero, r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top, 0x0014);
                ApplyDpi();
                m.Result = IntPtr.Zero;
                return;
            }
            base.WndProc(ref m);
        }

        [StructLayout(LayoutKind.Sequential)]
        struct RECT { public int Left, Top, Right, Bottom; }

        void ApplyDpi()
        {
            Font = Fonts.Get(Dpi, 10f);
            OnDpiApplied();
            if (DpiApplied != null) DpiApplied(this, EventArgs.Empty);
            PerformLayout();
            Invalidate(true);
        }

        protected virtual void OnDpiApplied() { }

        // the window's icon from the exe (Windows picks the right size for the title bar and the taskbar)
        public static Icon AppIcon()
        {
            try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { return SystemIcons.Application; }
        }

        public static Image Logo(string name)
        {
            try
            {
                var s = typeof(DpiForm).Assembly.GetManifestResourceStream(name);
                return s == null ? null : Image.FromStream(s);
            }
            catch (Exception) { return null; }
        }
    }

    // A control the app draws itself, double-buffered, sized for its window's DPI.
    public class UiControl : Control
    {
        public int ForcedDpi;  // a popup's list: the DPI of the window that opened it

        public UiControl()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint
                     | ControlStyles.ResizeRedraw | ControlStyles.Selectable, true);
            BackColor = Pal.Bg;
            ForeColor = Pal.Text;
        }

        public int Dpi
        {
            get
            {
                if (ForcedDpi > 0) return ForcedDpi;
                var f = FindForm() as DpiForm;
                if (f != null) return f.Dpi;
                return IsHandleCreated ? Native.Dpi(Handle) : 96;
            }
        }

        public float S { get { return Dpi / 96f; } }
        public int Px(float v) { return (int)Math.Round(v * Dpi / 96f); }
        public Font F(float pt, FontStyle st = FontStyle.Regular, string fam = Fonts.Ui) { return Fonts.Get(Dpi, pt, st, fam); }
    }

    public enum ButtonKind { Primary, Secondary, Ghost, Danger, Paper }

    public class FlatButton : UiControl
    {
        public ButtonKind Kind = ButtonKind.Secondary;
        public float FontPt = 10f;
        public string Glyph;  // an optional symbol before the text (Segoe UI Symbol / Segoe MDL2 Assets)
        bool hover, down;

        public FlatButton() { Cursor = Cursors.Hand; TabStop = true; }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) { down = true; Invalidate(); } base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }
        protected override void OnEnabledChanged(EventArgs e) { Invalidate(); base.OnEnabledChanged(e); }
        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter)
            {
                OnClick(EventArgs.Empty);
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : Pal.Bg);
            Gfx.Smooth(g);
            var r = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
            float rad = Px(4);
            Color bg, fg, border;
            Color faint = Pal.TextFaint;
            switch (Kind)
            {
                case ButtonKind.Primary:
                    bg = !Enabled ? Pal.GoldDim : down ? Gfx.Mix(Pal.Gold, Color.Black, 0.12f) : hover ? Pal.GoldHi : Pal.Gold;
                    fg = Pal.GoldInk; border = bg; break;
                case ButtonKind.Danger:
                    bg = hover ? Gfx.Mix(Pal.RedBg, Pal.Red, 0.3f) : Pal.RedBg; fg = Pal.Text; border = Pal.Red; break;
                case ButtonKind.Ghost:
                    bg = down ? Pal.Raised : hover ? Pal.Hover : (Parent != null ? Parent.BackColor : Pal.Bg);
                    fg = Enabled ? Pal.Text : Pal.TextFaint; border = hover ? Pal.GoldDim : bg; break;
                case ButtonKind.Paper:
                    bg = down ? Paper.Line : hover ? Paper.Hover : Paper.Card;
                    fg = Enabled ? Paper.Ink : Paper.InkFaint; border = hover ? Paper.BorderHi : Paper.Border; faint = Paper.InkFaint; break;
                default:  // wood with a gold rim
                    bg = down ? Pal.Deep : hover ? Pal.Raised : Pal.Bg;
                    fg = Enabled ? Pal.Text : Pal.TextFaint; border = Enabled ? (hover ? Pal.GoldHi : Pal.Gold) : Pal.Border; break;
            }
            Gfx.Fill(g, r, rad, bg);
            Gfx.Stroke(g, r, rad, Focused && ShowFocusCues ? Pal.GoldHi : border, Math.Max(1f, S));
            var font = Kind == ButtonKind.Primary ? F(FontPt + 1f, FontStyle.Bold, Fonts.Serif) : F(FontPt);
            string text = string.IsNullOrEmpty(Glyph) ? Text : Glyph + "  " + Text;
            Gfx.Text(g, text, font, ClientRectangle, Enabled || Kind == ButtonKind.Primary ? fg : faint, Gfx.Center);
        }
    }

    // A single-line text field: the standard edit box without its 3D border, in a rounded frame.
    public class TextField : UiControl
    {
        public readonly TextBox Box = new TextBox { BorderStyle = BorderStyle.None, BackColor = Pal.Deep, ForeColor = Pal.Text };
        public float FontPt = 10f;
        public string Cue;
        public string FontFamily = Fonts.Ui;
        public FontStyle FontStyle = FontStyle.Regular;
        bool hover, onPaper, wrap;

        // A long value (a folder path) wraps onto more lines instead of running past the box's edge. The owner asks
        // HeightFor and lays the box out that tall. Line breaks typed or pasted in are dropped, since it stays one
        // value.
        public bool WrapLines
        {
            get { return wrap; }
            set
            {
                wrap = value;
                Box.Multiline = value; Box.WordWrap = value; Box.AcceptsReturn = false; Box.ScrollBars = ScrollBars.None;
            }
        }

        // a little extra room per wrapped line, since at 200% the underscores on the sixth line got cut off
        // with just the font height
        int LineHeight(Font f) { return f.Height + Math.Max(1, Px(1)); }

        /// <summary>The height the box needs at a width to show its whole value (at least minH).</summary>
        public int HeightFor(int width, int minH)
        {
            if (!wrap) return minH;
            var f = F(FontPt, FontStyle, FontFamily);
            int inner = Math.Max(Px(20), width - 2 * Px(10) - Px(6));  // the edit control's own margins
            // We ask the edit box how it really wrapped the path. TextRenderer broke it at different points and cut
            // a deep folder path after four lines.
            int lines;
            if (Box.IsHandleCreated)
            {
                Box.Font = f;
                int bw = Math.Max(10, width - 2 * Px(10));
                if (Box.Width != bw) Box.Width = bw;
                lines = Box.TextLength == 0 ? 1 : Box.GetLineFromCharIndex(Box.TextLength) + 1;
            }
            else
            {
                int one = TextRenderer.MeasureText(Box.Text.Length == 0 ? " " : Box.Text, f, new Size(int.MaxValue, int.MaxValue),
                                                   TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix).Width;
                lines = (one + inner - 1) / inner;  // an estimate until the control exists, then we ask again
            }
            lines = Math.Max(1, Math.Min(10, lines));
            return Math.Max(minH, lines * LineHeight(f) + Px(12));
        }

        // a field on a parchment page: light, with brown ink
        public bool OnPaper
        {
            get { return onPaper; }
            set { onPaper = value; Box.BackColor = Fill; Box.ForeColor = value ? Paper.Ink : Pal.Text; Invalidate(); }
        }

        Color Fill { get { return onPaper ? (Enabled ? Paper.Field : Paper.Hover) : (Enabled ? Pal.Deep : Pal.Panel); } }

        public TextField()
        {
            Controls.Add(Box);
            Box.GotFocus += (s, e) => Invalidate();
            Box.LostFocus += (s, e) => Invalidate();
            // HeightFor can ask it now
            Box.HandleCreated += (s, e) => { if (wrap && Parent != null) Parent.PerformLayout(); };
            Box.TextChanged += (s, e) =>
            {
                if (wrap && (Box.Text.IndexOf('\n') >= 0 || Box.Text.IndexOf('\r') >= 0))
                {
                    int at = Box.SelectionStart;
                    Box.Text = Box.Text.Replace("\r", "").Replace("\n", "");
                    Box.SelectionStart = Math.Min(at, Box.TextLength);
                }
            };
            Box.MouseEnter += (s, e) => { hover = true; Invalidate(); };
            Box.MouseLeave += (s, e) => { hover = false; Invalidate(); };
            Cursor = Cursors.IBeam;
            TabStop = false;
        }

        public override string Text { get { return Box.Text; } set { Box.Text = value; } }

        protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); if (Cue != null) Native.Cue(Box, Cue); }
        protected override void OnMouseDown(MouseEventArgs e) { Box.Focus(); base.OnMouseDown(e); }
        protected override void OnEnabledChanged(EventArgs e) { Box.Enabled = Enabled; Box.BackColor = Fill; Invalidate(); base.OnEnabledChanged(e); }

        protected override void OnLayout(LayoutEventArgs e)
        {
            Box.Font = F(FontPt, FontStyle, FontFamily);
            int pad = Px(10);
            if (wrap)
            {
                int lineH = LineHeight(Box.Font), lines = Math.Max(1, (Height - Px(12)) / Math.Max(1, lineH));
                int bh = lines * lineH;
                Box.SetBounds(pad, Math.Max(0, (Height - bh) / 2), Math.Max(10, Width - 2 * pad), bh);
            }
            else
            {
                int h = Box.PreferredHeight;
                Box.SetBounds(pad, Math.Max(0, (Height - h) / 2), Math.Max(10, Width - 2 * pad), h);
            }
            base.OnLayout(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : Pal.Bg);
            Gfx.Smooth(g);
            var r = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
            Gfx.Fill(g, r, Px(4), Fill);
            Color edge = onPaper ? (Box.Focused ? Paper.Gold : hover ? Paper.BorderHi : Paper.Border)
                                 : (Box.Focused ? Pal.Gold : hover ? Pal.GoldDim : Pal.Border);
            Gfx.Stroke(g, r, Px(4), edge, Math.Max(1f, Box.Focused ? 1.5f * S : S));
        }
    }

    // A dark tooltip that wraps long explanations. The caller shows it (no activation, no taskbar entry).
    public class TipWindow : Form
    {
        string text = "";
        int dpi = 96;

        public TipWindow()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            BackColor = Paper.Card;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x08000000 | 0x00000080 | 0x00000008;  // no activate, tool window, topmost
                cp.ClassStyle |= 0x00020000;  // drop shadow
                return cp;
            }
        }

        public void ShowAt(string t, Point screen, int forDpi)
        {
            text = t ?? "";
            dpi = forDpi;
            var f = Fonts.Get(dpi, 9.5f);
            int pad = 12 * dpi / 96, maxW = 460 * dpi / 96;
            var sz = TextRenderer.MeasureText(text, f, new Size(maxW, 2000), Gfx.Wrap);
            int w = Math.Min(maxW, sz.Width) + 2 * pad, h = sz.Height + 2 * pad;
            var wa = Screen.FromPoint(screen).WorkingArea;
            int x = Math.Max(wa.Left, Math.Min(screen.X, wa.Right - w)), y = screen.Y;
            if (y + h > wa.Bottom) y = Math.Max(wa.Top, screen.Y - h - 30 * dpi / 96);
            Native.SetWindowPos(Handle, (IntPtr)(-1), x, y, w, h, 0x0010 | 0x0040);  // topmost, no activate, show
            Invalidate();
        }

        // it's shown with SetWindowPos (no activation), so Visible may not know. Hide it the same way, whatever it
        // says.
        public void HideTip()
        {
            if (IsHandleCreated) Native.SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0080 | 0x0010 | 0x0001 | 0x0002 | 0x0004);
            if (Visible) Hide();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Paper.Card);
            using (var pen = new Pen(Pal.GoldDim)) g.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
            int pad = 12 * dpi / 96;
            Gfx.Text(g, text, Fonts.Get(dpi, 9.5f), new Rectangle(pad, pad, Width - 2 * pad, Height - 2 * pad), Paper.Ink, Gfx.Wrap);
        }
    }

    // Vertical scrolling for a custom-drawn control: the offset, the wheel and a slim bar that grows on hover.
    public class ScrollCore
    {
        readonly UiControl owner;
        public int Offset, Content, Line = 40;
        public int Top;  // a fixed header above the scrolled part (pixels)
        public bool OnPaper;
        bool dragging, hover;
        int dragY, dragOffset;

        public ScrollCore(UiControl c) { owner = c; }

        int View { get { return Math.Max(1, owner.Height - Top); } }
        public int Max { get { return Math.Max(0, Content - View); } }
        public bool Needed { get { return Content > View; } }

        public void Clamp() { Offset = Math.Max(0, Math.Min(Max, Offset)); }

        int wheelRest;  // sub-notch touchpad deltas kept until they add up

        public void Wheel(int delta)
        {
            int step = owner.Px(Line) * 3 / 2;  // per notch (120)
            int moved = (delta * step + wheelRest) / 120;
            wheelRest = (delta * step + wheelRest) - moved * 120;
            Offset -= moved;
            Clamp();
            owner.Invalidate();
        }

        public void ScrollTo(int top, int bottom)
        {
            if (top < Offset) Offset = top;
            else if (bottom > Offset + View) Offset = bottom - View;
            Clamp();
        }

        Rectangle Thumb()
        {
            int h = View;
            int th = Math.Max(owner.Px(36), h * h / Math.Max(1, Content));
            int ty = Max == 0 ? 0 : (h - th) * Offset / Max;
            int w = owner.Px(hover || dragging ? 8 : 5);
            return new Rectangle(owner.Width - w - owner.Px(3), Top + ty, w, th);
        }

        public bool InBar(Point p) { return Needed && p.Y >= Top && p.X >= owner.Width - owner.Px(14); }

        public bool MouseDown(MouseEventArgs e)
        {
            if (!InBar(e.Location)) return false;
            var t = Thumb();
            if (e.Y < t.Top || e.Y > t.Bottom)
            {
                Offset = (e.Y - Top - t.Height / 2) * Max / Math.Max(1, View - t.Height);
                Clamp();
            }
            dragging = true; dragY = e.Y; dragOffset = Offset;
            owner.Capture = true;
            owner.Invalidate();
            return true;
        }

        public bool MouseMove(MouseEventArgs e)
        {
            bool h = InBar(e.Location);
            if (h != hover)
            {
                hover = h;
                owner.Invalidate();
            }
            if (!dragging) return h;
            var t = Thumb();
            Offset = dragOffset + (e.Y - dragY) * Max / Math.Max(1, View - t.Height);
            Clamp();
            owner.Invalidate();
            return true;
        }

        public bool MouseUp() { bool was = dragging; dragging = false; if (was) owner.Capture = false; return was; }
        public void Leave() { if (hover) { hover = false; owner.Invalidate(); } }

        public void Draw(Graphics g)
        {
            if (!Needed) return;
            var t = Thumb();
            Gfx.Fill(g, t, t.Width / 2f, OnPaper ? (hover || dragging ? Paper.BorderHi : Paper.Border) : (hover || dragging ? Pal.GoldDim : Pal.Border));
        }
    }

    public class ItemState
    {
        public bool Hover, Selected, Focused;
    }

    // A list that only draws its visible rows. The caller paints each row (DrawRow) from its own objects.
    public class VirtualList : UiControl
    {
        public readonly List<object> Items = new List<object>();
        public int RowHeight = 28;  // at 96 DPI
        public Func<int, int> RowHeightOf;  // optional: a row's own height at 96 DPI (section headers)
        public Func<int, bool> Selectable = i => true;
        public Action<Graphics, Rectangle, int, ItemState> DrawRow;
        public event Action<int, MouseEventArgs> RowClick;
        public event Action<int> RowDoubleClick;
        public event Action<int> SelectedIndexChanged;
        public event Action<int, Point> RowHover;
        public readonly ScrollCore Scroll;
        public int Selected = -1, HoverIndex = -1;
        public Color Back = Pal.Panel;
        int[] tops = new int[0];

        public VirtualList()
        {
            Scroll = new ScrollCore(this);
            TabStop = true;
        }

        public object SelectedItem { get { return Selected >= 0 && Selected < Items.Count ? Items[Selected] : null; } }

        public void SetItems(IEnumerable items, bool keepScroll = false)
        {
            object sel = SelectedItem;
            Items.Clear();
            foreach (var x in items) Items.Add(x);
            Selected = sel == null ? -1 : Items.IndexOf(sel);
            HoverIndex = -1;
            Measure();
            if (!keepScroll) Scroll.Offset = 0;
            Scroll.Clamp();
            Invalidate();
        }

        public void Measure()
        {
            tops = new int[Items.Count + 1];
            int y = 0;
            for (int i = 0; i < Items.Count; i++)
            {
                tops[i] = y;
                y += Px(RowHeightOf != null ? RowHeightOf(i) : RowHeight);
            }
            tops[Items.Count] = y;
            Scroll.Content = y;
            Scroll.Line = RowHeight;
        }

        public Rectangle RowRect(int i)
        {
            if (i < 0 || i >= Items.Count || tops.Length != Items.Count + 1) return Rectangle.Empty;
            return new Rectangle(0, tops[i] - Scroll.Offset, Width, tops[i + 1] - tops[i]);
        }

        public int IndexAt(Point p)
        {
            if (tops.Length != Items.Count + 1) return -1;
            int y = p.Y + Scroll.Offset;
            int lo = 0, hi = Items.Count - 1;
            while (lo <= hi)
            {
                int mid = (lo + hi) / 2;
                if (y < tops[mid]) hi = mid - 1;
                else if (y >= tops[mid + 1]) lo = mid + 1;
                else return mid;
            }
            return -1;
        }

        public void Select(int i, bool raise = true)
        {
            if (i < -1 || i >= Items.Count || (i >= 0 && !Selectable(i))) return;
            Selected = i;
            if (i >= 0)
            {
                var r = RowRect(i);
                Scroll.ScrollTo(r.Top + Scroll.Offset, r.Bottom + Scroll.Offset);
            }
            Invalidate();
            if (raise && SelectedIndexChanged != null) SelectedIndexChanged(i);
        }

        protected override void OnResize(EventArgs e) { Measure(); Scroll.Clamp(); base.OnResize(e); }
        protected override void OnMouseWheel(MouseEventArgs e) { Scroll.Wheel(e.Delta); UpdateHover(PointToClient(MousePosition)); }

        void UpdateHover(Point p)
        {
            int i = Scroll.InBar(p) ? -1 : IndexAt(p);
            if (i != HoverIndex)
            {
                HoverIndex = i;
                Invalidate();
                if (RowHover != null) RowHover(i, p);
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (Scroll.MouseMove(e) && Capture) return;
            UpdateHover(e.Location);
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            Scroll.Leave();
            if (HoverIndex != -1)
            {
                HoverIndex = -1;
                Invalidate();
                if (RowHover != null) RowHover(-1, Point.Empty);
            }
            base.OnMouseLeave(e);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            Focus();
            if (Scroll.MouseDown(e)) return;
            int i = IndexAt(e.Location);
            if (i >= 0 && e.Button == MouseButtons.Left && Selectable(i)) Select(i);
            if (i >= 0 && RowClick != null) RowClick(i, e);
            base.OnMouseDown(e);
        }

        protected override void OnMouseUp(MouseEventArgs e) { Scroll.MouseUp(); base.OnMouseUp(e); }

        protected override void OnMouseDoubleClick(MouseEventArgs e)
        {
            int i = IndexAt(e.Location);
            if (i >= 0 && RowDoubleClick != null) RowDoubleClick(i);
            base.OnMouseDoubleClick(e);
        }

        protected override bool IsInputKey(Keys k) { return k == Keys.Up || k == Keys.Down || k == Keys.PageUp || k == Keys.PageDown || base.IsInputKey(k); }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            int step = e.KeyCode == Keys.Up ? -1 : e.KeyCode == Keys.Down ? 1 : e.KeyCode == Keys.PageUp ? -10 : e.KeyCode == Keys.PageDown ? 10 : 0;
            if (step != 0 && Items.Count > 0)
            {
                int i = Selected < 0 ? 0 : Selected;
                int dir = Math.Sign(step);
                for (int n = 0; n < Math.Abs(step); n++)
                {
                    int j = i + dir;
                    while (j >= 0 && j < Items.Count && !Selectable(j)) j += dir;
                    if (j < 0 || j >= Items.Count) break;
                    i = j;
                }
                Select(i);
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Back);
            if (tops.Length != Items.Count + 1) Measure();
            int first = Math.Max(0, IndexAt(new Point(0, 0)));
            var st = new ItemState();
            for (int i = first; i < Items.Count; i++)
            {
                var r = RowRect(i);
                if (r.Top > Height) break;
                if (r.Bottom < 0) continue;
                st.Hover = i == HoverIndex; st.Selected = i == Selected; st.Focused = Focused;
                if (DrawRow != null) DrawRow(g, r, i, st);
            }
            Scroll.Draw(g);
        }
    }

    // A drop-down list, a popup under its owner holding a VirtualList (one pick, or several with ticks).
    public class Popup : ToolStripDropDown
    {
        public readonly VirtualList List = new VirtualList { Back = Paper.Card, RowHeight = 30 };
        public int ExtraTop;  // room for controls above the list (a filter box), in pixels
        readonly ToolStripControlHost host;

        public Popup()
        {
            Padding = Margin = Padding.Empty;
            BackColor = Paper.Card;
            DropShadowEnabled = true;
            List.Scroll.OnPaper = true;
            AutoSize = false;
            host = new ToolStripControlHost(List) { Padding = Padding.Empty, Margin = Padding.Empty, AutoSize = false };
            Items.Add(host);
            Renderer = new PopupRenderer();
        }

        class PopupRenderer : ToolStripRenderer
        {
            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e) { e.Graphics.Clear(Paper.Card); }
            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
            {
                using (var pen = new Pen(Pal.GoldDim)) e.Graphics.DrawRectangle(pen, 0, 0, e.ToolStrip.Width - 1, e.ToolStrip.Height - 1);
            }
        }

        public void ShowUnder(Control owner, Rectangle anchor, int dpi, int width, int rows)
        {
            List.ForcedDpi = dpi;
            int h = 0;
            for (int i = 0; i < List.Items.Count && i < rows; i++)
                h += (List.RowHeightOf != null ? List.RowHeightOf(i) : List.RowHeight) * dpi / 96;
            h = Math.Max(h, List.RowHeight * dpi / 96);
            int pad = 4 * dpi / 96;
            List.Size = new Size(width - 2, h);
            host.Size = new Size(width - 2, h);
            Size = new Size(width, h + 2 + pad * 2 + ExtraTop);
            Padding = new Padding(1, 1 + pad, 1, 1 + pad);
            List.Measure();
            if (List.Selected >= 0)
            {
                var r = List.RowRect(List.Selected);
                List.Scroll.ScrollTo(r.Top + List.Scroll.Offset - h / 3, r.Bottom + List.Scroll.Offset);
            }
            var p = owner.PointToScreen(new Point(anchor.Left, anchor.Bottom + 2 * dpi / 96));
            var wa = Screen.FromControl(owner).WorkingArea;
            if (p.Y + Height > wa.Bottom) p.Y = owner.PointToScreen(new Point(0, anchor.Top)).Y - Height - 2 * dpi / 96;
            Show(p);
            List.Focus();
        }
    }
}
