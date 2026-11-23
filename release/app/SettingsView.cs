// One control draws and edits all the settings, in section cards on the parchment page. Switching pages or
// searching rebuilds the row list and repaints, without a window for each setting.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using RemakeUi;

namespace RandoOfTime
{
    class Setting
    {
        public string Name, Label, Tooltip, Summary, Type, Tab, Section;
        public object Default;
        public List<string[]> Choices = new List<string[]>();
        public int Min, Max = 1000, Step = 1;
        public List<KeyValuePair<string, List<string>>> Disable = new List<KeyValuePair<string, List<string>>>();
        // Display state: B for bool, I for int, C for choice index, On for list membership, T for text.
        public bool B;
        public int I, C = -1;
        public HashSet<string> On = new HashSet<string>();
        public List<string> ListOrder = new List<string>();  // a list's order as loaded (OoTR's seed depends on it)
        public string T = "";
        public bool Off;  // greyed out by another setting (OoTR's disable rules)
    }

    class Page
    {
        public string Title, Blurb;
        public bool Search;  // a search's hits: every match is shown, greyed-out ones too
        public List<KeyValuePair<string, List<Setting>>> Sections = new List<KeyValuePair<string, List<Setting>>>();
        public IEnumerable<Setting> All { get { return Sections.SelectMany(s => s.Value); } }
    }

    class SettingsView : UiControl
    {
        enum RowKind { Title, Section, Setting, Empty }

        class Row
        {
            public RowKind Kind;
            public Setting St;
            public string Text;
            public int Y, H;          // at the current DPI
            public int LabelH, SumH;  // the name's and the summary's wrapped heights
            public int Card = -1;     // the section card it belongs to
        }

        readonly List<Row> rows = new List<Row>();
        readonly List<Rectangle> cards = new List<Rectangle>();  // content coordinates
        public readonly ScrollCore Scroll;
        readonly TextBox editor = new TextBox { BorderStyle = BorderStyle.None, Visible = false, BackColor = Paper.Field, ForeColor = Paper.Ink };
        readonly Timer tipTimer = new Timer { Interval = 550 };
        readonly ContextMenuStrip menu = new ContextMenuStrip();
        static readonly TipWindow tip = new TipWindow();
        Setting editing;
        Row hover, focus, tipRow;
        bool hoverControl;
        Page page;
        string query;
        int builtDpi, builtWidth;
        Popup popup;

        public Func<Setting, bool> IsChanged = s => false;
        public Func<Setting, string> Shown = s => "";
        public event Action<Setting> Changed;
        public event Action<Setting> ResetOne;

        public SettingsView()
        {
            Scroll = new ScrollCore(this) { OnPaper = true };
            BackColor = Paper.Bg;
            Controls.Add(editor);
            editor.KeyDown += (s, e) =>
            {
                if (e.KeyCode == Keys.Enter)
                {
                    Commit();
                    e.SuppressKeyPress = true;
                    Focus();
                }
                if (e.KeyCode == Keys.Escape)
                {
                    editing = null;
                    editor.Visible = false;
                    e.SuppressKeyPress = true;
                    Focus();
                }
            };
            editor.LostFocus += (s, e) => Commit();
            tipTimer.Tick += (s, e) =>
            {
                tipTimer.Stop();
                if (hover != null && hover == tipRow && hover.St != null && !string.IsNullOrEmpty(hover.St.Tooltip) && popup == null)
                {
                    string t = hover.St.Tooltip + (hover.St.Off ? "\n\nTurned off by another setting." : "");
                    var p = MousePosition;
                    tip.ShowAt(t, new Point(p.X + Px(14), p.Y + Px(20)), Dpi);
                }
            };
            menu.Renderer = new DarkMenuRenderer();
            menu.Items.Add("Reset to its default", null, (s, e) => { var r = menu.Tag as Setting; if (r != null && ResetOne != null) ResetOne(r); });
            TabStop = true;
        }

        public bool Searching { get { return !string.IsNullOrEmpty(query); } }

        public void ShowPage(Page p) { page = p; query = null; Rebuild(true); }

        public void ShowSearch(string q, IEnumerable<Page> pages)
        {
            query = q;
            var hits = new Page { Title = "Search: " + q, Blurb = "", Search = true };
            string ql = q.ToLowerInvariant();
            foreach (var pg in pages)
            {
                var found = pg.All.Where(s => s.Label.ToLowerInvariant().Contains(ql) || (s.Tooltip ?? "").ToLowerInvariant().Contains(ql)
                                              || s.Name.ToLowerInvariant().Contains(ql)).ToList();
                if (found.Count > 0) hits.Sections.Add(new KeyValuePair<string, List<Setting>>(pg.Title, found));
            }
            int n = hits.All.Count();
            hits.Blurb = n == 0 ? "No setting matches." : n + " setting" + (n == 1 ? "" : "s") + " match.";
            page = hits;
            Rebuild(true);
        }

        public void Rebuild(bool top = false)
        {
            Commit();
            HidePopup();
            rows.Clear(); cards.Clear();
            builtDpi = Dpi;
            builtWidth = Width;
            if (page == null)
            {
                Invalidate();
                return;
            }
            Scroll.Top = HeaderHeight();
            int y = 0;
            Action<Row, int> add = (r, h) => { r.Y = y; r.H = h; rows.Add(r); y += h; };
            if (!page.Sections.Any()) add(new Row { Kind = RowKind.Empty, Text = "Nothing here." }, Px(40));
            foreach (var sec in page.Sections)
            {
                // Normal pages hide disabled rows, search still shows them greyed out.
                var shown = sec.Value.Where(s => page.Search || !s.Off).ToList();
                if (shown.Count == 0) continue;
                add(new Row { Kind = RowKind.Section, Text = string.IsNullOrEmpty(sec.Key) ? "General" : sec.Key }, Px(38));
                int top0 = y, card = cards.Count;
                foreach (var st in shown)
                {
                    // Both lines are measured at the real text width so they fit in narrow windows.
                    var row = new Row { Kind = RowKind.Setting, St = st, Card = card };
                    int tw = TextWidth(st);
                    row.LabelH = TextRenderer.MeasureText(st.Label, F(10.5f), new Size(tw, 2000), Gfx.Wrap).Height;
                    row.SumH = string.IsNullOrEmpty(st.Summary) ? 0
                             : TextRenderer.MeasureText(st.Summary, F(9f), new Size(tw, 4000), Gfx.Wrap).Height;
                    int h = row.SumH == 0 ? Math.Max(Px(44), row.LabelH + Px(20)) : Px(7) + row.LabelH + Px(2) + row.SumH + Px(9);
                    add(row, h);
                }
                cards.Add(new Rectangle(0, top0, 0, y - top0));
                y += Px(10);
            }
            Scroll.Content = y + Px(20);
            Scroll.Line = 50;
            if (top) Scroll.Offset = 0;
            Scroll.Clamp();
            hover = focus = null;
            Invalidate();
        }

        // the width a setting's name and summary get, from the card's left padding to its control
        int TextWidth(Setting st)
        {
            var col = Column();
            int w;
            switch (st.Type)
            {
                case "bool": w = Px(42); break;
                case "int": w = Px(130); break;
                default: w = Math.Min(Px(330), col.Width * 2 / 5); break;
            }
            return Math.Max(Px(80), col.Width - Px(16) - w - Px(18) - Px(18));
        }

        // room kept at the right of the page's header (the search box sits there)
        public int HeaderReserveRight;

        // The title and blurb stay above the scrolling rows. The blurb is measured wrapped, so it gets enough height
        // in narrow windows.
        int HeaderHeight()
        {
            if (page == null) return Px(52);
            int w = Math.Max(Px(120), Column().Width - HeaderReserveRight - Px(6));
            int bh = string.IsNullOrEmpty(page.Blurb) ? 0 : TextRenderer.MeasureText(page.Blurb, F(10f), new Size(w, 2000), Gfx.Wrap).Height;
            return Px(12) + Px(34) + bh + Px(10);
        }

        // the content column is the page's width less a margin, at most 1040 wide (centred beyond that)
        Rectangle Column()
        {
            int w = Math.Min(Width - Px(44), Px(1040));
            return new Rectangle(Math.Max(Px(20), (Width - w) / 2), 0, w, 0);
        }

        Rectangle ControlRect(Row r)
        {
            var col = Column();
            var st = r.St;
            int cy = Scroll.Top + r.Y - Scroll.Offset + r.H / 2;
            int w, h = Px(30);
            switch (st.Type)
            {
                case "bool": w = Px(42); h = Px(22); break;
                case "int": w = Px(130); break;
                default: w = Math.Min(Px(330), col.Width * 2 / 5); break;
            }
            return new Rectangle(col.Right - Px(16) - w, cy - h / 2, w, h);
        }

        protected override void OnResize(EventArgs e)
        {
            if (builtDpi != 0 && (builtDpi != Dpi || builtWidth != Width)) Rebuild();
            else
            {
                Scroll.Top = HeaderHeight();
                Scroll.Clamp();
                PlaceEditor();
            }
            base.OnResize(e);
        }

        public void Restyle() { Rebuild(); }

        // Paint
        protected override void OnPaint(PaintEventArgs e)
        {
            if (builtDpi != Dpi) Rebuild();
            var g = e.Graphics;
            g.Clear(Paper.Bg);
            Gfx.Smooth(g);
            var col = Column();
            int top0 = Scroll.Top, off = Scroll.Offset - top0;  // content y -> window y: y - off
            g.SetClip(new Rectangle(0, top0, Width, Math.Max(0, Height - top0)));
            for (int i = 0; i < cards.Count; i++)
            {
                var c = new Rectangle(col.X, cards[i].Y - off, col.Width, cards[i].Height);
                if (c.Bottom < top0 || c.Top > Height) continue;
                Gfx.Fill(g, c, Px(6), Paper.Card);
                Gfx.Stroke(g, c, Px(6), Paper.Border, 1f);
            }
            foreach (var r in rows)
            {
                int top = r.Y - off;
                if (top > Height || top + r.H < top0) continue;
                var rr = new Rectangle(col.X, top, col.Width, r.H);
                switch (r.Kind)
                {
                    case RowKind.Section:
                    {
                        var hf = F(12f, FontStyle.Bold, Fonts.Serif);
                        var tr = new Rectangle(rr.X + Px(3), rr.Y + Px(8), rr.Width, Px(28));
                        Gfx.Text(g, r.Text, hf, tr, Paper.Ink, Gfx.Left);
                        int tw = TextRenderer.MeasureText(g, r.Text, hf, tr.Size, Gfx.Left).Width;
                        using (var pen = new Pen(Paper.Border)) g.DrawLine(pen, tr.X + tw + Px(10), tr.Y + tr.Height / 2, rr.Right, tr.Y + tr.Height / 2);
                        break;
                    }
                    case RowKind.Empty:
                        Gfx.Text(g, r.Text, F(10f), rr, Paper.InkDim, Gfx.Left);
                        break;
                    case RowKind.Setting:
                        DrawSetting(g, r, rr);
                        break;
                }
            }
            g.ResetClip();
            if (page != null)  // fixed header, title and wrapped explanation, a hairline once the page scrolls
            {
                int w = Math.Max(Px(120), col.Width - HeaderReserveRight - Px(6));
                Gfx.Text(g, page.Title, F(17f, FontStyle.Bold, Fonts.Serif), new Rectangle(col.X + Px(2), Px(12), w, Px(34)), Paper.Ink, Gfx.Left);
                if (!string.IsNullOrEmpty(page.Blurb))
                    Gfx.Text(g, page.Blurb, F(10f), new Rectangle(col.X + Px(3), Px(46), w, top0 - Px(46)), Paper.InkDim, Gfx.Wrap);
                if (Scroll.Offset > 0) using (var pen = new Pen(Paper.Border)) g.DrawLine(pen, 0, top0 - 1, Width, top0 - 1);
            }
            Scroll.Draw(g);
        }

        void DrawSetting(Graphics g, Row r, Rectangle rr)
        {
            var st = r.St;
            var card = cards[r.Card];
            bool firstInCard = r.Y == card.Y, lastInCard = r.Y + r.H == card.Bottom;
            if (r == hover && !st.Off)
            {
                var hr = new Rectangle(rr.X + 1, rr.Y + (firstInCard ? 1 : 0), rr.Width - 2, rr.Height - (firstInCard ? 1 : 0) - (lastInCard ? 1 : 0));
                Gfx.Fill(g, hr, firstInCard || lastInCard ? Px(5) : 0, Paper.Hover);
            }
            if (!firstInCard)
                using (var pen = new Pen(Paper.Line)) g.DrawLine(pen, rr.X + Px(14), rr.Y, rr.Right - Px(14), rr.Y);
            if (r == focus && Focused)
                Gfx.Stroke(g, new Rectangle(rr.X + Px(3), rr.Y + Px(3), rr.Width - Px(6), rr.Height - Px(6)), Px(4), Paper.Gold, Math.Max(1f, S));
            var ctl = ControlRect(r);
            int tx = rr.X + Px(18);
            if (IsChanged(st) && !st.Off)
                Gfx.Fill(g, new RectangleF(rr.X + Px(3), rr.Y + Px(8), Px(3), rr.Height - Px(16)), Px(1.5f), Paper.Gold);
            int tw = ctl.Left - tx - Px(18);
            Color lc = st.Off ? Paper.InkFaint : Paper.Ink, sc = st.Off ? Paper.InkFaint : Paper.InkDim;
            if (r.SumH == 0)
                Gfx.Text(g, st.Label, F(10.5f), new Rectangle(tx, rr.Y + (rr.Height - r.LabelH) / 2, tw, r.LabelH), lc, Gfx.Wrap);
            else
            {
                Gfx.Text(g, st.Label, F(10.5f), new Rectangle(tx, rr.Y + Px(7), tw, r.LabelH), lc, Gfx.Wrap);
                Gfx.Text(g, st.Summary, F(9f), new Rectangle(tx, rr.Y + Px(9) + r.LabelH, tw, r.SumH), sc, Gfx.Wrap);
            }
            DrawControl(g, r, ctl);
        }

        static readonly string MinusSign = ((char)0x2212).ToString(), Pencil = ((char)0x270E).ToString();

        void DrawControl(Graphics g, Row r, Rectangle c)
        {
            var st = r.St;
            bool hot = r == hover && hoverControl && !st.Off;
            float bw = Math.Max(1f, S);
            switch (st.Type)
            {
                case "bool":
                {
                    Color track = st.Off ? Paper.Hover : st.B ? Paper.Gold : (hot ? Paper.Line : Paper.Hover);
                    Gfx.Fill(g, c, c.Height / 2f, track);
                    Gfx.Stroke(g, c, c.Height / 2f, st.Off ? Paper.Line : st.B ? Paper.BorderHi : Paper.Border, bw);
                    int d = c.Height - Px(8);
                    float kx = st.B ? c.Right - Px(4) - d : c.X + Px(4);
                    Gfx.Fill(g, new RectangleF(kx, c.Y + Px(4), d, d), d / 2f, st.Off ? Paper.InkFaint : st.B ? Paper.Card : Paper.InkDim);
                    break;
                }
                case "int":
                {
                    Gfx.Fill(g, c, Px(4), st.Off ? Paper.Hover : Paper.Field);
                    Gfx.Stroke(g, c, Px(4), hot ? Paper.BorderHi : Paper.Border, bw);
                    int bwid = c.Height;
                    var minus = new Rectangle(c.X, c.Y, bwid, c.Height);
                    var plus = new Rectangle(c.Right - bwid, c.Y, bwid, c.Height);
                    Color fg = st.Off ? Paper.InkFaint : Paper.Ink;
                    Gfx.Text(g, MinusSign, F(12f), minus, st.Off || st.I <= st.Min ? Paper.InkFaint : Paper.InkDim, Gfx.Center);
                    Gfx.Text(g, "+", F(12f), plus, st.Off || st.I >= st.Max ? Paper.InkFaint : Paper.InkDim, Gfx.Center);
                    if (editing != st)
                        Gfx.Text(g, st.I.ToString(), F(10.5f, FontStyle.Bold), new Rectangle(minus.Right, c.Y, plus.Left - minus.Right, c.Height), fg, Gfx.Center);
                    break;
                }
                default:
                {
                    Gfx.Fill(g, c, Px(4), st.Off ? Paper.Hover : Paper.Field);
                    Gfx.Stroke(g, c, Px(4), hot ? Paper.BorderHi : Paper.Border, bw);
                    if (editing == st) break;
                    var tr = new Rectangle(c.X + Px(10), c.Y, c.Width - Px(36), c.Height);
                    string text = Shown(st);
                    Gfx.Text(g, text == "" ? "(none)" : text, F(10f), tr, st.Off ? Paper.InkFaint : text == "" ? Paper.InkDim : Paper.Ink, Gfx.Left);
                    if (st.Type == "choice" || st.Type == "list")
                        Gfx.Chevron(g, new RectangleF(c.Right - Px(28), c.Y, Px(22), c.Height), st.Off ? Paper.InkFaint : Paper.InkDim, Math.Max(1.4f, 1.6f * S));
                    else
                        Gfx.Text(g, Pencil, F(10f, FontStyle.Regular, "Segoe UI Symbol"), new Rectangle(c.Right - Px(28), c.Y, Px(22), c.Height), Paper.InkDim, Gfx.Center);
                    break;
                }
            }
        }

        // Input
        Row RowAt(Point p)
        {
            if (p.Y < Scroll.Top) return null;
            int y = p.Y - Scroll.Top + Scroll.Offset;
            var col = Column();
            if (p.X < col.X || p.X > col.Right) return null;
            foreach (var r in rows) if (r.Kind == RowKind.Setting && y >= r.Y && y < r.Y + r.H) return r;
            return null;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (Scroll.MouseMove(e) && Capture) return;
            var r = Scroll.InBar(e.Location) ? null : RowAt(e.Location);
            bool hc = r != null && ControlRect(r).Contains(e.Location);
            if (r != hover || hc != hoverControl)
            {
                if (r != hover)
                {
                    tip.HideTip();
                    tipTimer.Stop();
                    tipRow = r;
                    if (r != null) tipTimer.Start();
                }
                hover = r; hoverControl = hc;
                Cursor = r != null && !r.St.Off ? Cursors.Hand : Cursors.Default;
                Invalidate();
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            Scroll.Leave();
            tip.HideTip(); tipTimer.Stop();
            if (hover != null)
            {
                hover = null;
                Invalidate();
            }
            base.OnMouseLeave(e);
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            Commit();
            tip.HideTip();
            Scroll.Wheel(e.Delta);
            OnMouseMove(new MouseEventArgs(MouseButtons.None, 0, PointToClient(MousePosition).X, PointToClient(MousePosition).Y, 0));
        }

        protected override void OnMouseUp(MouseEventArgs e) { Scroll.MouseUp(); base.OnMouseUp(e); }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            Focus();
            tip.HideTip(); tipTimer.Stop();
            if (Scroll.MouseDown(e)) return;
            var r = RowAt(e.Location);
            if (r == null) return;
            focus = r;
            if (e.Button == MouseButtons.Right)
            {
                menu.Tag = r.St;
                menu.Items[0].Enabled = IsChanged(r.St) && !r.St.Off;
                menu.Font = F(10f);
                menu.Show(this, e.Location);
                return;
            }
            if (e.Button != MouseButtons.Left || r.St.Off)
            {
                Invalidate();
                return;
            }
            Activate(r, e.Location);
        }

        void Activate(Row r, Point? at)
        {
            var st = r.St;
            var c = ControlRect(r);
            switch (st.Type)
            {
                case "bool": st.B = !st.B; Raise(st); break;
                case "int":
                    if (at.HasValue && at.Value.X < c.X + c.Height && at.Value.X >= c.X) Bump(st, -1);
                    else if (at.HasValue && at.Value.X > c.Right - c.Height && at.Value.X <= c.Right) Bump(st, 1);
                    else StartEdit(r, st.I.ToString());
                    break;
                case "choice": OpenChoice(r); break;
                case "list": OpenList(r); break;
                default: StartEdit(r, st.T); break;
            }
            Invalidate();
        }

        void Bump(Setting st, int dir)
        {
            int v = Math.Max(st.Min, Math.Min(st.Max, st.I + dir * st.Step));
            if (v != st.I)
            {
                st.I = v;
                Raise(st);
            }
        }

        void Raise(Setting st) { if (Changed != null) Changed(st); Invalidate(); }

        protected override bool IsInputKey(Keys k)
        {
            return k == Keys.Up || k == Keys.Down || k == Keys.Left || k == Keys.Right || k == Keys.Space || base.IsInputKey(k);
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            var settingRows = rows.Where(x => x.Kind == RowKind.Setting).ToList();
            int i = focus == null ? -1 : settingRows.IndexOf(focus);
            if (e.KeyCode == Keys.Down || e.KeyCode == Keys.Up)
            {
                int j = Math.Max(0, Math.Min(settingRows.Count - 1, i + (e.KeyCode == Keys.Down ? 1 : -1)));
                if (settingRows.Count > 0)
                {
                    focus = settingRows[j];
                    Scroll.ScrollTo(focus.Y - Px(60), focus.Y + focus.H + Px(20));
                    Invalidate();
                }
                e.Handled = true;
            }
            else if (focus != null && !focus.St.Off)
            {
                var st = focus.St;
                if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter)
                {
                    Activate(focus, null);
                    e.Handled = true;
                }
                else if ((e.KeyCode == Keys.Left || e.KeyCode == Keys.Right) && st.Type == "int")
                {
                    Bump(st, e.KeyCode == Keys.Right ? 1 : -1);
                    e.Handled = true;
                }
                else if ((e.KeyCode == Keys.Left || e.KeyCode == Keys.Right) && st.Type == "choice" && st.Choices.Count > 0)
                {
                    st.C = Math.Max(0, Math.Min(st.Choices.Count - 1, st.C + (e.KeyCode == Keys.Right ? 1 : -1)));
                    Raise(st); e.Handled = true;
                }
                else if ((e.KeyCode == Keys.Left || e.KeyCode == Keys.Right) && st.Type == "bool")
                {
                    st.B = e.KeyCode == Keys.Right;
                    Raise(st);
                    e.Handled = true;
                }
            }
            base.OnKeyDown(e);
        }

        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        // Editing
        void StartEdit(Row r, string text)
        {
            Commit();
            editing = r.St;
            editor.Font = F(10.5f, r.St.Type == "int" ? FontStyle.Bold : FontStyle.Regular, r.St.Type == "int" ? Fonts.UiSemi : Fonts.Ui);
            editor.TextAlign = r.St.Type == "int" ? HorizontalAlignment.Center : HorizontalAlignment.Left;
            editor.BackColor = Paper.Field;
            editor.Text = text;
            editor.Tag = r;
            PlaceEditor();
            editor.Visible = true;
            editor.Focus();
            editor.SelectAll();
        }

        void PlaceEditor()
        {
            var r = editor.Tag as Row;
            if (editing == null || r == null) return;
            var c = ControlRect(r);
            int h = editor.PreferredHeight;
            if (r.St.Type == "int") editor.SetBounds(c.X + c.Height, c.Y + (c.Height - h) / 2, c.Width - 2 * c.Height, h);
            else editor.SetBounds(c.X + Px(10), c.Y + (c.Height - h) / 2, c.Width - Px(20), h);
        }

        public void Commit()
        {
            var st = editing;
            if (st == null) return;
            editing = null;
            editor.Visible = false;
            if (st.Type == "int")
            {
                int v;
                if (int.TryParse(editor.Text.Trim(), out v))
                {
                    v = Math.Max(st.Min, Math.Min(st.Max, v));
                    // rounds down to the step, so a 12-rupee price becomes 10 when prices go in fives
                    v = st.Min + (v - st.Min) / st.Step * st.Step;
                    if (v != st.I)
                    {
                        st.I = v;
                        Raise(st);
                    }
                }
            }
            else if (editor.Text != st.T)
            {
                st.T = editor.Text;
                Raise(st);
            }
            Invalidate();
        }

        void HidePopup()
        {
            if (popup != null)
            {
                var p = popup;
                popup = null;
                p.Close();
            }
        }

        Popup NewPopup(Row r)
        {
            HidePopup();
            tip.HideTip();
            var p = new Popup();
            p.List.Font = F(10f);
            p.Closed += (s, e) => { if (popup == p) popup = null; Invalidate(); };
            popup = p;
            return p;
        }

        void OpenChoice(Row r)
        {
            var st = r.St;
            var p = NewPopup(r);
            for (int i = 0; i < st.Choices.Count; i++) p.List.Items.Add(i);
            p.List.Selected = st.C;
            p.List.DrawRow = (g, rect, i, s) =>
            {
                int k = (int)p.List.Items[i];
                if (s.Hover || s.Selected) Gfx.Fill(g, new Rectangle(rect.X + Px(4), rect.Y + 1, rect.Width - Px(8), rect.Height - 2), Px(4), s.Hover ? Paper.Hover : Paper.Bg);
                if (k == st.C) Gfx.Fill(g, new RectangleF(rect.X + Px(8), rect.Y + rect.Height / 2f - Px(8), Px(3), Px(16)), Px(1.5f), Paper.Gold);
                Gfx.Text(g, st.Choices[k][1], F(10f, k == st.C ? FontStyle.Bold : FontStyle.Regular), new Rectangle(rect.X + Px(18), rect.Y, rect.Width - Px(26), rect.Height), Paper.Ink, Gfx.Left);
            };
            p.List.RowClick += (i, e) =>
            {
                if (e.Button != MouseButtons.Left) return;
                st.C = (int)p.List.Items[i];
                p.Close();
                Raise(st);
            };
            p.List.KeyDown += (s, e) =>
            {
                if (e.KeyCode == Keys.Enter && p.List.Selected >= 0)
                {
                    st.C = (int)p.List.Items[p.List.Selected];
                    p.Close();
                    Raise(st);
                }
                if (e.KeyCode == Keys.Escape) p.Close();
            };
            var c = ControlRect(r);
            p.ShowUnder(this, c, Dpi, Math.Max(c.Width, Px(260)), 12);
        }

        void OpenList(Row r)
        {
            var st = r.St;
            var p = NewPopup(r);
            Action<string> fill = q =>
            {
                var idx = Enumerable.Range(0, st.Choices.Count).Where(i => string.IsNullOrEmpty(q) || st.Choices[i][1].ToLowerInvariant().Contains(q.ToLowerInvariant())).Cast<object>();
                p.List.SetItems(idx);
            };
            fill(null);
            p.List.DrawRow = (g, rect, i, s) =>
            {
                int k = (int)p.List.Items[i];
                bool on = st.On.Contains(st.Choices[k][0]);
                if (s.Hover) Gfx.Fill(g, new Rectangle(rect.X + Px(4), rect.Y + 1, rect.Width - Px(8), rect.Height - 2), Px(4), Paper.Hover);
                var box = new RectangleF(rect.X + Px(12), rect.Y + rect.Height / 2f - Px(8), Px(16), Px(16));
                Gfx.Fill(g, box, Px(3), on ? Paper.Gold : Paper.Field);
                if (!on) Gfx.Stroke(g, box, Px(3), Paper.BorderHi, Math.Max(1f, S));
                else Gfx.Tick(g, box, Paper.Card, Math.Max(1.5f, 2f * S));
                Gfx.Text(g, st.Choices[k][1], F(10f), new Rectangle(rect.X + Px(38), rect.Y, rect.Width - Px(46), rect.Height), Paper.Ink, Gfx.Left);
            };
            Action<int> toggle = i =>
            {
                string key = st.Choices[(int)p.List.Items[i]][0];
                if (!st.On.Remove(key)) st.On.Add(key);
                p.List.Invalidate();
                Raise(st);
            };
            p.List.RowClick += (i, e) => { if (e.Button == MouseButtons.Left) toggle(i); };
            p.List.KeyDown += (s, e) =>
            {
                if ((e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter) && p.List.Selected >= 0)
                {
                    toggle(p.List.Selected);
                    e.Handled = true;
                }
                if (e.KeyCode == Keys.Escape) p.Close();
            };
            var c = ControlRect(r);
            int width = Math.Max(c.Width + Px(80), Px(380));
            if (st.Choices.Count > 14) AddSearch(p, fill, width);
            p.ShowUnder(this, c, Dpi, width, 14);
        }

        // a filter box over a long list (2,137 locations, 193 tricks), typing narrows the rows
        void AddSearch(Popup p, Action<string> fill, int width)
        {
            var box = new TextField { Cue = "Type to filter", FontPt = 10f, ForcedDpi = Dpi, BackColor = Paper.Card, OnPaper = true };
            box.Size = new Size(width - Px(18), Px(36));
            var host = new ToolStripControlHost(box) { AutoSize = false, Size = new Size(width - Px(18), Px(36)), Margin = new Padding(Px(8), Px(6), Px(8), Px(6)), Padding = Padding.Empty };
            p.Items.Insert(0, host);
            p.ExtraTop = Px(48);
            box.Box.TextChanged += (s, e) => fill(box.Box.Text);
            box.Box.KeyDown += (s, e) => { if (e.KeyCode == Keys.Down) { p.List.Focus(); p.List.Select(0); e.Handled = true; } if (e.KeyCode == Keys.Escape) p.Close(); };
            p.Opened += (s, e) => box.Box.Focus();
        }
    }

    class DarkMenuRenderer : ToolStripProfessionalRenderer
    {
        public DarkMenuRenderer() : base(new DarkColours()) { }
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = e.Item.Enabled ? Paper.Ink : Paper.InkFaint;
            base.OnRenderItemText(e);
        }

        class DarkColours : ProfessionalColorTable
        {
            public override Color ToolStripDropDownBackground { get { return Paper.Card; } }
            public override Color MenuBorder { get { return Pal.GoldDim; } }
            public override Color MenuItemBorder { get { return Paper.BorderHi; } }
            public override Color MenuItemSelected { get { return Paper.Hover; } }
            public override Color ImageMarginGradientBegin { get { return Paper.Card; } }
            public override Color ImageMarginGradientMiddle { get { return Paper.Card; } }
            public override Color ImageMarginGradientEnd { get { return Paper.Card; } }
            public override Color SeparatorDark { get { return Paper.Border; } }
            public override Color SeparatorLight { get { return Paper.Border; } }
            public override Color MenuItemSelectedGradientBegin { get { return Paper.Hover; } }
            public override Color MenuItemSelectedGradientEnd { get { return Paper.Hover; } }
            public override Color CheckBackground { get { return Paper.Gold; } }
            public override Color CheckSelectedBackground { get { return Paper.Gold; } }
        }
    }
}
