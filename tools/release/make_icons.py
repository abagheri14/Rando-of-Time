"""Draws the app and tracker icons (common/ui/randomizer.ico, tracker.ico and their 256 px PNGs).

Everything is drawn at 1024 px and scaled down; the 16-32 px sizes use a simpler drawing (thicker ring, no holes or
ticks) so they stay readable in the taskbar. Run: python tools/release/make_icons.py [OUT_DIR] (default common/ui)."""
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 1024
GOLD_HI, GOLD, GOLD_LO = (255, 236, 170, 255), (226, 182, 86, 255), (150, 104, 36, 255)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def vgrad(size, top, bottom):
    w, h = size
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        col.putpixel((0, y), lerp(top, bottom, y / max(1, h - 1)))
    return col.resize((w, h))


def radial(size, inner, outer, cx, cy, r):
    w, h = size
    small = Image.new("RGBA", (w // 8, h // 8))
    px = small.load()
    for y in range(h // 8):
        for x in range(w // 8):
            t = min(1.0, math.hypot(x * 8 - cx, y * 8 - cy) / r)
            px[x, y] = lerp(inner, outer, t)
    return small.resize((w, h), Image.BICUBIC)


def mask_rr(box, r, size=(S, S)):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, r, fill=255)
    return m


def fill(mask, paint):
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    if isinstance(paint, tuple):
        paint = Image.new("RGBA", mask.size, paint)
    out.paste(paint, (0, 0), mask)
    return out


def shadow(mask, off, blur, alpha):
    m = mask.point(lambda v: v * alpha // 255)
    m = ImageChops.offset(m, off[0], off[1]).filter(ImageFilter.GaussianBlur(blur))
    s = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    s.putalpha(m)
    return s


def tile(top, bottom, glow):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m_outer = mask_rr((40, 40, S - 40, S - 40), 210)
    img.alpha_composite(shadow(m_outer, (0, 14), 18, 110))
    img.alpha_composite(fill(m_outer, vgrad((S, S), GOLD_HI, GOLD_LO)))          # gold rim
    m_in = mask_rr((70, 70, S - 70, S - 70), 182)
    img.alpha_composite(fill(m_in, (60, 40, 14, 255)))                            # dark line inside the rim
    m_in2 = mask_rr((78, 78, S - 78, S - 78), 175)
    body = vgrad((S, S), top, bottom)
    body.alpha_composite(radial((S, S), glow, glow[:3] + (0,), S / 2, S * 0.40, S * 0.50))
    img.alpha_composite(fill(m_in2, body))
    sheen = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sheen).ellipse((-200, -620, S + 200, 380), fill=34)
    sheen = ImageChops.multiply(sheen, m_in2)
    s = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    s.putalpha(sheen)
    img.alpha_composite(s)
    return img


def gold_shape(img, m, drop=10):
    img.alpha_composite(shadow(m, (0, drop), 10, 130))
    img.alpha_composite(fill(m, vgrad((S, S), GOLD_HI, GOLD_LO)))
    edge = ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(5)))
    e = Image.new("RGBA", (S, S), (100, 62, 16, 0))
    e.putalpha(edge.point(lambda v: v * 150 // 255))
    img.alpha_composite(e)


def ring_arrows(img, cx, cy, r, w, gaps, ticks=True):
    """Two gold arcs sweeping clockwise with arrowheads (the shuffle), with a clock's ticks inside (the time)."""
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    box = (cx - r, cy - r, cx + r, cy + r)
    arcs = [(gaps[0][1], gaps[1][0]), (gaps[1][1], gaps[0][0] + 360)]
    rc = r - w / 2
    for a0, a1 in arcs:
        d.arc(box, a0, a1, fill=255, width=w)
        t = math.radians(a1)
        ex, ey = cx + rc * math.cos(t), cy + rc * math.sin(t)
        tx, ty = -math.sin(t), math.cos(t)
        nx, ny = math.cos(t), math.sin(t)
        length, half = w * 1.5, w * 1.2
        d.polygon([(ex + tx * length, ey + ty * length), (ex + nx * half, ey + ny * half), (ex - nx * half, ey - ny * half)],
                  fill=255)
        t0 = math.radians(a0)
        sx, sy = cx + rc * math.cos(t0), cy + rc * math.sin(t0)
        d.ellipse((sx - w / 2, sy - w / 2, sx + w / 2, sy + w / 2), fill=255)
    if ticks:
        for k in range(12):
            t = math.radians(k * 30 - 90)
            major = k % 3 == 0
            rr = r - w - (44 if major else 36)
            size = 19 if major else 11
            x, y = cx + rr * math.cos(t), cy + rr * math.sin(t)
            d.ellipse((x - size, y - size, x + size, y + size), fill=255)
    gold_shape(img, m)


def ocarina(img, cx, cy, scale, angle, holes=True):
    """A blue ocarina: a sweet-potato body, a silver mouthpiece with a gold band, finger holes."""
    W = S
    ox, oy = W / 2, W / 2
    bw, bh = 330 * scale, 200 * scale
    body = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(body)
    d.ellipse((ox - bw, oy - bh, ox + bw * 0.55, oy + bh), fill=255)
    top, bot = [], []
    for i in range(41):
        u = i / 40
        x = ox + bw * 0.05 + u * bw * 1.1
        hh = bh * (1 - u ** 1.7)
        top.append((x, oy - hh))
        bot.append((x, oy + hh * 0.9))
    d.polygon(top + bot[::-1], fill=255)
    d.ellipse((ox + bw * 1.06, oy - 30 * scale, ox + bw * 1.22, oy + 26 * scale), fill=255)
    body = body.filter(ImageFilter.GaussianBlur(4)).point(lambda v: 255 if v > 127 else 0)
    # the mouthpiece: a rounded duct rising out of the body's upper left
    mp = Image.new("L", (W, W), 0)
    md = ImageDraw.Draw(mp)
    mx, my = ox - bw * 0.50, oy - bh * 0.42           # where it leaves the body
    ang = math.radians(-130)                            # pointing up and to the left
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -uy, ux
    length, half = 250 * scale, 50 * scale
    ex, ey = mx + ux * length, my + uy * length
    md.polygon([(mx + vx * half, my + vy * half), (ex + vx * half * 0.86, ey + vy * half * 0.86),
                (ex - vx * half * 0.86, ey - vy * half * 0.86), (mx - vx * half, my - vy * half)], fill=255)
    md.ellipse((ex - half * 0.86, ey - half * 0.86, ex + half * 0.86, ey + half * 0.86), fill=255)
    mp = mp.filter(ImageFilter.GaussianBlur(3)).point(lambda v: 255 if v > 127 else 0)
    whole = ImageChops.lighter(body, mp)
    o = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    outline = ImageChops.subtract(whole.filter(ImageFilter.MaxFilter(13)), whole)
    o.alpha_composite(fill(outline, (12, 26, 64, 255)))
    o.alpha_composite(fill(mp, vgrad((W, W), (252, 252, 255, 255), (130, 140, 162, 255))))
    blue = vgrad((W, W), (118, 186, 255, 255), (20, 60, 156, 255))
    blue.alpha_composite(radial((W, W), (200, 230, 255, 190), (200, 230, 255, 0), ox - bw * 0.25, oy - bh * 0.5, bw * 0.95))
    o.alpha_composite(fill(body, blue))
    band = Image.new("L", (W, W), 0)                    # a gold collar where the duct meets the body
    bx, by = mx + ux * 70 * scale, my + uy * 70 * scale
    ImageDraw.Draw(band).line([(bx + vx * half * 1.4, by + vy * half * 1.4), (bx - vx * half * 1.4, by - vy * half * 1.4)],
                              fill=255, width=int(36 * scale))
    band = ImageChops.multiply(band, mp)
    # the duct's dark opening at its tip
    tipm = Image.new("L", (W, W), 0)
    tx, ty = ex + ux * half * 0.35, ey + uy * half * 0.35
    ImageDraw.Draw(tipm).line([(tx + vx * half * 0.45, ty + vy * half * 0.45), (tx - vx * half * 0.45, ty - vy * half * 0.45)],
                              fill=255, width=int(16 * scale))
    tipm = ImageChops.multiply(tipm, mp)
    o.alpha_composite(fill(band, vgrad((W, W), GOLD_HI, GOLD_LO)))
    o.alpha_composite(fill(tipm, (40, 44, 60, 255)))
    hl = Image.new("L", (W, W), 0)
    ImageDraw.Draw(hl).ellipse((ox - bw * 0.78, oy - bh * 0.9, ox + bw * 0.5, oy - bh * 0.30), fill=120)
    hl = ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(22)), body)
    h = Image.new("RGBA", (W, W), (255, 255, 255, 0))
    h.putalpha(hl)
    o.alpha_composite(h)
    if holes:
        dd = ImageDraw.Draw(o)
        for hx, hy, hr in [(-0.34, -0.30, 31), (0.0, -0.40, 31), (0.33, -0.36, 28), (0.62, -0.22, 23), (0.12, 0.30, 19)]:
            x, y, rr = ox + hx * bw, oy + hy * bh + 30 * scale, hr * scale
            dd.ellipse((x - rr - 6, y - rr - 6, x + rr + 6, y + rr + 6), fill=(150, 200, 255, 255))
            dd.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(8, 20, 54, 255))
    o = o.rotate(angle, resample=Image.BICUBIC, center=(ox, oy))
    o = o.transform((S, S), Image.AFFINE, (1, 0, ox - cx, 0, 1, oy - cy), resample=Image.BICUBIC)
    img.alpha_composite(shadow(o.getchannel("A"), (0, 18), 16, 160))
    img.alpha_composite(o)


def sparkle(img, x, y, r):
    m = Image.new("L", (S, S), 0)
    q = 0.2
    ImageDraw.Draw(m).polygon([(x, y - r), (x + r * q, y - r * q), (x + r, y), (x + r * q, y + r * q), (x, y + r),
                               (x - r * q, y + r * q), (x - r, y), (x - r * q, y - r * q)], fill=255)
    img.alpha_composite(fill(m.filter(ImageFilter.GaussianBlur(1)), (255, 246, 214, 255)))


def app_icon(detail=True):
    img = tile((36, 92, 68, 255), (10, 36, 26, 255), (90, 160, 115, 140))
    ring_arrows(img, S / 2, S / 2, 368 if detail else 380, 62 if detail else 96, [(-64, -28), (116, 152)], ticks=detail)
    ocarina(img, S / 2 + 44, S / 2 + 40, 0.70 if detail else 0.80, 4, holes=detail)
    if detail:
        sparkle(img, 744, 296, 42)
        sparkle(img, 296, 742, 28)
    return img


def tracker_icon(detail=True):
    img = tile((38, 62, 118, 255), (12, 20, 50, 255), (95, 125, 205, 130))
    x0, x1, x2, x3 = 216, 404, 604, 806
    ytop, ybot, dz = 280, 770, 36
    panels = [[(x0, ytop + dz), (x1, ytop), (x1, ybot - dz), (x0, ybot)],
              [(x1, ytop), (x2, ytop + dz), (x2, ybot), (x1, ybot - dz)],
              [(x2, ytop + dz), (x3, ytop), (x3, ybot - dz), (x2, ybot)]]
    m = Image.new("L", (S, S), 0)
    for p in panels:
        ImageDraw.Draw(m).polygon(p, fill=255)
    img.alpha_composite(shadow(m, (0, 16), 14, 150))
    for p, c in zip(panels, [(242, 228, 186, 255), (214, 194, 146, 255), (242, 228, 186, 255)]):
        pm = Image.new("L", (S, S), 0)
        ImageDraw.Draw(pm).polygon(p, fill=255)
        img.alpha_composite(fill(pm, vgrad((S, S), lerp(c, (255, 255, 255, 255), 0.12), lerp(c, (120, 90, 50, 255), 0.2))))
    d = ImageDraw.Draw(img)
    if detail:
        route = [(262, 700), (322, 650), (382, 668), (446, 610), (500, 572), (552, 598), (600, 540)]
        for (ax, ay), (bx, by) in zip(route, route[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / 27))
            for k in range(n):
                t = k / n
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(156, 74, 40, 255))
        for x, y in [(292, 396), (716, 664)]:
            d.line([(x - 18, y - 18), (x + 18, y + 18)], fill=(126, 62, 34, 255), width=11)
            d.line([(x - 18, y + 18), (x + 18, y - 18)], fill=(126, 62, 34, 255), width=11)
    cx, cy, r = (642, 430, 158) if detail else (590, 470, 210)
    sm = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sm).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    gold_shape(img, sm, drop=14)
    inner = Image.new("L", (S, S), 0)
    ImageDraw.Draw(inner).ellipse((cx - r + 24, cy - r + 24, cx + r - 24, cy + r - 24), fill=255)
    img.alpha_composite(fill(inner, vgrad((S, S), (238, 198, 106, 255), (172, 120, 44, 255))))
    ck = Image.new("L", (S, S), 0)
    k = r / 158
    pts = [(cx - 74 * k, cy + 2 * k), (cx - 20 * k, cy + 58 * k), (cx + 80 * k, cy - 60 * k)]
    cd = ImageDraw.Draw(ck)
    cd.line(pts, fill=255, width=int(50 * k), joint="curve")
    for x, y in (pts[0], pts[2]):
        cd.ellipse((x - 25 * k, y - 25 * k, x + 25 * k, y + 25 * k), fill=255)
    img.alpha_composite(fill(ck, (44, 30, 10, 255)))
    return img


SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def save_set(name, big, small, outdir):
    frames = []
    for s in SIZES:
        im = (small if s <= 32 else big).resize((s, s), Image.LANCZOS)
        if s <= 48:
            im = im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
        frames.append(im)
    frames[-1].save(os.path.join(outdir, f"{name}_256.png"))
    frames[-1].save(os.path.join(outdir, f"{name}.ico"), sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    return frames


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common", "ui")
    os.makedirs(out, exist_ok=True)
    fa = save_set("randomizer", app_icon(), app_icon(False), out)
    ft = save_set("tracker", tracker_icon(), tracker_icon(False), out)
    if "--preview" not in sys.argv:
        sys.exit(0)
    sheet = Image.new("RGBA", (1000, 620), (243, 236, 220, 255))
    ImageDraw.Draw(sheet).rectangle((0, 310, 1000, 620), fill=(43, 29, 18, 255))
    for band in (0, 1):
        for row, frames in enumerate((fa, ft)):
            x, y0 = 20, band * 310 + row * 150 + 12
            for im in [frames[-1].resize((128, 128), Image.LANCZOS), frames[6], frames[5], frames[3], frames[2], frames[0]]:
                sheet.alpha_composite(im, (x, y0 + (128 - im.size[1]) // 2))
                x += im.size[0] + 36
    sheet.save(os.path.join(out, "preview.png"))
    print("ok")
