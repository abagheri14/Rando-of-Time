// A small dialog in the app's look instead of the system's message box. It has a gold heading, the message (wrapped,
// never cut) and buttons sized to their words. The tracker has the same kind of thing (tracker/app/TrackerUi.cs).
using System;
using System.Drawing;
using System.Windows.Forms;
using RemakeUi;

namespace RandoOfTime
{
    class AskDialog : DpiForm
    {
        readonly string heading, message;
        readonly FlatButton ok, cancel;
        Rectangle headR, msgR;
        const int W = 500;
        public int ForceDpi;  // for testing (--dpi), lays it out as at that scaling

        public AskDialog(string heading, string message, string okText, string cancelText, ButtonKind okKind)
        {
            this.heading = heading;
            this.message = message;
            Text = heading;
            Icon = AppIcon();
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.CenterParent;
            BackColor = Pal.Panel;
            KeyPreview = true;
            ok = new FlatButton { Text = okText, Kind = okKind, FontPt = 10f };
            ok.Click += (s, e) =>
            {
                DialogResult = DialogResult.OK;
                Close();
            };
            Controls.Add(ok);
            if (cancelText != null)
            {
                cancel = new FlatButton { Text = cancelText, FontPt = 10f };
                cancel.Click += (s, e) =>
                {
                    DialogResult = DialogResult.Cancel;
                    Close();
                };
                Controls.Add(cancel);
            }
            ClientSize = new Size(W, 200);
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

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape)
            {
                DialogResult = cancel != null ? DialogResult.Cancel : DialogResult.OK;
                Close();
                e.Handled = true;
            }
            base.OnKeyDown(e);
        }

        // the safe choice gets the focus, so Enter on a question cancels and Enter on a message closes it
        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (cancel != null) cancel.Focus(); else ok.Focus();
        }

        protected override void OnDpiApplied() { ClientSize = new Size(Px(W), Plan()); }

        Font Head { get { return Fonts.Get(Dpi, 13f, FontStyle.Bold, Fonts.Serif); } }
        Font Body { get { return Fonts.Get(Dpi, 10f); } }

        static Size Wrapped(string s, Font f, int width)
        {
            return TextRenderer.MeasureText(string.IsNullOrEmpty(s) ? " " : s, f, new Size(Math.Max(1, width), int.MaxValue), Gfx.Wrap);
        }

        int ButtonWidth(FlatButton b, Font f)
        {
            int w = TextRenderer.MeasureText(b.Text, f, new Size(int.MaxValue, int.MaxValue), TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix).Width;
            return Math.Max(Px(96), w + Px(32));
        }

        // lays the dialog out at its width; returns the height it needs
        int Plan()
        {
            int pad = Px(22), w = Px(W) - 2 * pad, y = Px(18);
            var hs = Wrapped(heading, Head, w);
            headR = new Rectangle(pad, y, w, hs.Height + Px(2));
            y += hs.Height + Px(10);
            var ms = Wrapped(message, Body, w);
            msgR = new Rectangle(pad, y, w, ms.Height + Px(2));
            y += ms.Height + Px(18);
            int bh = Px(36);
            int bw1 = ButtonWidth(ok, ok.Kind == ButtonKind.Primary ? Fonts.Get(Dpi, 11f, FontStyle.Bold, Fonts.Serif) : Body);
            int bw2 = cancel == null ? 0 : ButtonWidth(cancel, Body);
            if (bw1 + bw2 + Px(8) > w)  // never at this width with our words, buttons stack rather than cut
            {
                ok.SetBounds(pad, y, w, bh);
                if (cancel != null)
                {
                    y += bh + Px(8);
                    cancel.SetBounds(pad, y, w, bh);
                }
            }
            else
            {
                ok.SetBounds(pad + w - bw1, y, bw1, bh);
                if (cancel != null) cancel.SetBounds(ok.Left - Px(8) - bw2, y, bw2, bh);
            }
            return y + bh + Px(20);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Pal.Panel);
            Gfx.Text(g, heading, Head, headR, Pal.Gold, Gfx.Wrap);
            Gfx.Text(g, message, Body, msgR, Pal.Text, Gfx.Wrap);
            using (var pen = new Pen(Pal.GoldDim)) g.DrawLine(pen, 0, 0, Width, 0);
        }

        public static bool Confirm(IWin32Window owner, string heading, string message, string okText, int forceDpi = 0)
        {
            using (var d = new AskDialog(heading, message, okText, "Cancel", ButtonKind.Primary) { ForceDpi = forceDpi })
                return d.ShowDialog(owner) == DialogResult.OK;
        }

        public static void Tell(IWin32Window owner, string heading, string message, int forceDpi = 0)
        {
            using (var d = new AskDialog(heading, message, "OK", null, ButtonKind.Primary) { ForceDpi = forceDpi })
                d.ShowDialog(owner);
        }
    }
}
