"""Make Jarvis's icons and companion stickers from your images (run again if you change the images).

    python tools/make_brand_assets.py --logo LOGO.png --stickers A.png B.png

- logo: the app icon (browser tab, phone home screen, Android launcher) is cropped from the round
  robot emblem; the full logo is kept for the About screen.
- stickers: Study Buddy sticker sheets on a transparent background; each sticker is found and cut out.
  From the art itself it also makes: eyes-closed and half-closed frames (so she can blink), a relaxed
  pose with her eyes closed (breaks), and a pouty face (narrowed eyes, small frown, anger mark).
Outputs go to jarvis/static/icons, jarvis/static/companion, android/app/res and android/app/assets.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "jarvis" / "static" / "icons"
COMPANION = ROOT / "jarvis" / "static" / "companion"
RES = ROOT / "android" / "app" / "res"
DARK = (2, 6, 18)

# Where things are in the images you gave (fractions of width/height, so other sizes of the same art work).
LOGO_EMBLEM = (0.232, 0.088, 0.768, 0.622)  # the ring with the robot face
# Moods of the six stickers on each sheet, left to right, top to bottom.
STICKER_MOODS = ["cheer", "code", "study", "idea", "sleepy", "celebrate"]
# Where her irises are in each full-size sticker (fractions of its width/height), measured once from the
# art: (sheet, sticker) -> [left iris box, right iris box]. Stickers left out (yawning, winking, eyes
# already closed) keep their eyes exactly as drawn.
IRISES = {
    (1, 1): [(0.4675, 0.3243, 0.5163, 0.3638), (0.6138, 0.3742, 0.6545, 0.4158)],
    (1, 2): [(0.4366, 0.4156, 0.4692, 0.4473), (0.5471, 0.3776, 0.5870, 0.4156)],
    (1, 3): [(0.4224, 0.3533, 0.4673, 0.3905), (0.5694, 0.3120, 0.6061, 0.3492)],
    (1, 4): [(0.4329, 0.3374, 0.4756, 0.3778), (0.5793, 0.3677, 0.6280, 0.4101)],
    (2, 1): [(0.4407, 0.3561, 0.4862, 0.3934), (0.5909, 0.3975, 0.6324, 0.4348)],
    (2, 2): [(0.4412, 0.4571, 0.4706, 0.4871), (0.5625, 0.4249, 0.5974, 0.4571)],
    (2, 3): [(0.4344, 0.3820, 0.4734, 0.4196), (0.5799, 0.4301, 0.6230, 0.4676)],
    (2, 4): [(0.4260, 0.3499, 0.4660, 0.3857), (0.5680, 0.3757, 0.6160, 0.4135)],
}
MOUTHS = {(1, 2): (0.5054, 0.4789, 0.5471, 0.4979), (2, 2): (0.5129, 0.5322, 0.5368, 0.5472)}  # coding pose
CLOSED, HALF, NARROW = 0.72, 0.42, 0.34  # where the upper lid ends, from the top (0) to the bottom (1) of the eye


def crop_frac(im: Image.Image, box) -> Image.Image:
    w, h = im.size
    l, t, r, b = box
    return im.crop((round(l * w), round(t * h), round(r * w), round(b * h)))


def square(im: Image.Image) -> Image.Image:
    s = max(im.size)
    out = Image.new(im.mode, (s, s), DARK + ((255,) if im.mode == "RGBA" else ()))
    out.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out


def round_badge(im: Image.Image, size: int, ring: tuple | None = None) -> Image.Image:
    """A circle with soft edges (drawn 4x larger, then scaled down)."""
    big = size * 4
    src = square(im.convert("RGB")).resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(src, (0, 0), mask)
    if ring:
        ImageDraw.Draw(out).ellipse([4, 4, big - 5, big - 5], outline=ring, width=max(4, big // 60))
    return out.resize((size, size), Image.LANCZOS)


def find_stickers(sheet: Image.Image, count: int) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of the `count` largest opaque areas, in reading order (rows, then columns)."""
    alpha = sheet.getchannel("A")
    step = 4
    small = alpha.resize((sheet.width // step, sheet.height // step), Image.NEAREST)
    w, h = small.size
    px = small.load()
    seen = [[False] * w for _ in range(h)]
    boxes = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or px[x, y] < 128:
                continue
            q = deque([(x, y)])
            seen[y][x] = True
            x0 = x1 = x
            y0 = y1 = y
            area = 0
            while q:
                cx, cy = q.popleft()
                area += 1
                x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and px[nx, ny] >= 128:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            boxes.append((area, (x0 * step, y0 * step, (x1 + 1) * step, (y1 + 1) * step)))
    boxes = [b for _, b in sorted(boxes, reverse=True)[:count]]
    rows = sorted(boxes, key=lambda b: b[1])
    ordered, row = [], []
    for b in rows:  # group into rows by vertical overlap
        if row and b[1] > max(r[3] for r in row) - (b[3] - b[1]) * 0.5:
            ordered += sorted(row, key=lambda r: r[0])
            row = []
        row.append(b)
    return ordered + sorted(row, key=lambda r: r[0])


def cut_sticker(sheet: Image.Image, box, size: int) -> Image.Image:
    pad = 6
    l, t, r, b = box
    im = sheet.crop((max(0, l - pad), max(0, t - pad), min(sheet.width, r + pad), min(sheet.height, b + pad)))
    a = im.getchannel("A").point(lambda v: 255 if v >= 245 else v)  # the art is 99% opaque: make it solid
    im.putalpha(a)
    bbox = a.point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def save_webp(im: Image.Image, path: Path) -> None:
    im.save(path, "WEBP", quality=88, method=6)


def make_icons(logo: Image.Image) -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    emblem = crop_frac(logo.convert("RGB"), LOGO_EMBLEM)
    emblem = square(emblem)
    full_bg = Image.new("RGB", (1024, 1024), logo.convert("RGB").getpixel((5, 5)))
    for size, name in [(192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png"), (64, "favicon-64.png")]:
        emblem.resize((size, size), Image.LANCZOS).save(ICONS / name, optimize=True)
    # Maskable: launchers cut a circle/squircle out of the middle 80%, so add a margin.
    masked = full_bg.copy()
    inner = emblem.resize((820, 820), Image.LANCZOS)
    masked.paste(inner, (102, 102))
    masked.resize((512, 512), Image.LANCZOS).save(ICONS / "icon-maskable-512.png", optimize=True)
    round_badge(emblem, 96).save(ICONS / "logo-mark.png", optimize=True)  # header and chat avatar
    full = logo.convert("RGB")
    full.thumbnail((640, 640), Image.LANCZOS)
    full.save(ICONS / "logo-full.jpg", quality=86, optimize=True, progressive=True)

    # Android: legacy icons (round) + adaptive layers.
    for folder, size in {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96, "mipmap-xxhdpi": 144,
                         "mipmap-xxxhdpi": 192}.items():
        round_badge(emblem, size).save(RES / folder / "ic_launcher.png", optimize=True)
    bg = Image.new("RGB", (432, 432), logo.convert("RGB").getpixel((5, 5)))
    bg.save(RES / "drawable-nodpi" / "ic_launcher_background.png", optimize=True)
    fg = Image.new("RGBA", (432, 432), (0, 0, 0, 0))
    disc = round_badge(emblem, 300)  # stays inside the launcher's safe zone (the middle 66 dp of 108 dp)
    fg.paste(disc, (66, 66), disc)
    fg.save(RES / "drawable-nodpi" / "ic_launcher_foreground.png", optimize=True)


KEY = (254, 255, 254)  # transparent colour for the Windows floating window (Tk can key out one exact colour)


def anger_mark(im: Image.Image) -> Image.Image:
    """Add an anime anger mark (four red curves around a point) near the top right: the pouty pose."""
    im = im.copy()
    w, h = im.size
    size = int(w * 0.24)
    s4 = size * 4
    big = Image.new("RGBA", (s4, s4), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c, r, g, width = s4 // 2, s4 // 4, s4 // 30, max(6, s4 // 7)
    quarters = ((-1, -1, 0), (1, -1, 90), (1, 1, 180), (-1, 1, 270))  # one quarter circle per corner
    for colour, extra in (((255, 255, 255, 255), 12), ((229, 57, 53, 255), 0)):  # white edge, then red
        for sx, sy, start in quarters:
            ox, oy = c + sx * (r + g), c + sy * (r + g)
            d.arc([ox - r, oy - r, ox + r, oy + r], start, start + 90, fill=colour, width=width + extra)
    mark = big.resize((size, size), Image.LANCZOS)
    im.alpha_composite(mark, (min(w - size, int(w * 0.80) - size // 2), max(0, int(h * 0.12) - size // 2)))
    return im


# ---------------------------------------------------------------- her expressions, drawn from the sticker itself
def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _skinlike(p, skin) -> bool:
    """Skin, blush or soft shading: near her skin colour, not the white of an eye, not a dark line."""
    hi, lo = max(p[:3]), min(p[:3])
    value, sat = hi / 255, (hi - lo) / hi if hi else 0
    return _dist(p[:3], skin) < 45 and sat >= 0.12 and value >= 0.86


def _box(im: Image.Image, frac) -> tuple[int, int, int, int]:
    w, h = im.size
    return round(frac[0] * w), round(frac[1] * h), round(frac[2] * w), round(frac[3] * h)


def skin_tone(im: Image.Image, c1, c2) -> tuple[int, int, int]:
    """Her skin colour: the median of the bright pixels on the nose bridge, between and below the eyes."""
    px = im.load()
    cx, cy, d = (c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2, _dist(c1, c2)
    vals = [px[x, y][:3] for y in range(int(cy + 0.15 * d), int(cy + 0.45 * d)) for x in range(int(cx - 0.12 * d), int(cx + 0.12 * d))
            if px[x, y][3] > 250 and max(px[x, y][:3]) > 204]
    vals.sort(key=sum)
    return vals[len(vals) // 2]


def eye_pixels(im: Image.Image, box, skin, outer: int) -> set[tuple[int, int]]:
    """The eye (whites, iris, lashes): everything that isn't skin, connected to the iris, near it.
    `outer` is -1 for the eye on the left of the picture, 1 for the right one (eyes reach further outwards)."""
    px = im.load()
    x0, y0, x1, y1 = box
    iw, ih = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2 + outer * 0.08 * iw, (y0 + y1) / 2 - 0.15 * ih
    a, b = 1.62 * iw, 1.28 * ih
    start = (int((x0 + x1) / 2), int((y0 + y1) / 2))
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in seen and ((n[0] - cx) / a) ** 2 + ((n[1] - cy) / b) ** 2 <= 1 and _dist(px[n][:3], skin) > 38:
                seen.add(n)
                q.append(n)
    return seen


def _quadratic(points):
    """Least-squares v = a*u^2 + b*u + c through (u, v) points; returns the function."""
    n = len(points)
    s = [sum(u ** k for u, _ in points) for k in range(5)]
    t = [sum(v * u ** k for u, v in points) for k in range(3)]
    m = [[s[4], s[3], s[2], t[2]], [s[3], s[2], s[1], t[1]], [s[2], s[1], n, t[0]]]
    for i in range(3):  # Gaussian elimination
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        for r in range(3):
            if r != i and m[i][i]:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    a, b, c = (m[i][3] / m[i][i] if m[i][i] else 0.0 for i in range(3))
    return lambda u: a * u * u + b * u + c


def inpaint_skin(im: Image.Image, mask: set, skin) -> None:
    """Fill the masked pixels with the surrounding skin colours (blush and shading included), growing in
    from the edge; hair, lashes and the whites of the eyes next to the hole are never copied in."""
    px = im.load()
    inside = lambda p: 0 <= p[0] < im.width and 0 <= p[1] < im.height  # noqa: E731
    # take the soft (anti-aliased) edge of the hole too, so no faint outline is left behind
    edge = {(x + dx, y + dy) for x, y in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    mask = set(mask) | {p for p in edge if inside(p) and _dist(px[p][:3], skin) > 14}
    todo, need = set(mask), 3
    while todo:
        grown = {}
        for x, y in todo:
            near = [px[n] for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1))
                    if n not in todo and inside(n) and px[n][3] > 200 and _skinlike(px[n], skin)]
            if len(near) >= need:
                grown[(x, y)] = tuple(round(sum(c[i] for c in near) / len(near)) for i in range(3)) + (px[x, y][3],)
        if not grown:
            if need > 1:
                need -= 1
                continue
            for p in todo:  # closed in by hair: plain skin
                px[p] = tuple(skin) + (px[p][3],)
            break
        for p, c in grown.items():
            px[p] = c
        todo -= set(grown)
    # match the filled patch to the skin right around it (diffusion drifts a little lighter)
    ring = {(x + dx, y + dy) for x, y in mask for dx in (-4, 0, 4) for dy in (-4, 0, 4)} - mask
    ring = [px[p][:3] for p in ring if inside(p) and px[p][3] > 200 and _skinlike(px[p], skin)]
    if ring and mask:
        want = [sum(c[i] for c in ring) / len(ring) for i in range(3)]
        have = [sum(px[p][i] for p in mask) / len(mask) for i in range(3)]
        shift = [0.7 * (w - h) for w, h in zip(want, have)]
        for p in mask:
            c = px[p]
            px[p] = tuple(max(0, min(255, round(c[i] + shift[i]))) for i in range(3)) + (c[3],)
    hole = Image.new("L", im.size, 0)
    hp = hole.load()
    for p in mask:
        hp[p] = 255
    im.paste(im.filter(ImageFilter.GaussianBlur(1.4)), (0, 0), hole.filter(ImageFilter.GaussianBlur(1.6)))


def _stroke(im: Image.Image, centre, normal, widths, colour) -> None:
    """A tapered line (a filled band around `centre` points), drawn 4x larger for smooth edges."""
    up = [(x - nx * w / 2, y - ny * w / 2) for (x, y), (nx, ny), w in zip(centre, normal, widths)]
    down = [(x + nx * w / 2, y + ny * w / 2) for (x, y), (nx, ny), w in zip(centre, normal, widths)]
    pts = up + down[::-1]
    x0, y0 = int(min(p[0] for p in pts)) - 2, int(min(p[1] for p in pts)) - 2
    w, h = int(max(p[0] for p in pts)) - x0 + 3, int(max(p[1] for p in pts)) - y0 + 3
    S = 4
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon([((x - x0) * S, (y - y0) * S) for x, y in pts], fill=tuple(colour) + (255,))
    im.alpha_composite(layer.resize((w, h), Image.LANCZOS), (x0, y0))


def lids(im: Image.Image, key, closure: float) -> Image.Image:
    """Her eyes `closure` of the way shut: CLOSED (a soft closed-eye line), HALF (mid-blink) or NARROW (annoyed)."""
    im = im.copy()
    boxes = [_box(im, b) for b in IRISES[key]]
    centres = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes]
    skin = skin_tone(im, *centres)
    angle = math.atan2(centres[1][1] - centres[0][1], centres[1][0] - centres[0][0])  # head tilt
    cos, sin = math.cos(angle), math.sin(angle)
    px = im.load()
    for side, (box, (cx, cy)) in enumerate(zip(boxes, centres)):
        eye = eye_pixels(im, box, skin, -1 if side == 0 else 1)
        lash = sorted((px[p][:3] for p in eye), key=sum)[len(eye) // 12]  # the dark lash colour
        cols = defaultdict(list)
        for x, y in eye:
            cols[round((x - cx) * cos + (y - cy) * sin)].append(-(x - cx) * sin + (y - cy) * cos)
        us = sorted(u for u in cols for _ in cols[u])
        lo, hi = us[len(us) // 25], us[len(us) - 1 - len(us) // 25]
        top = _quadratic([(u, min(cols[u])) for u in cols if lo <= u <= hi])
        bottom = _quadratic([(u, max(cols[u])) for u in cols if lo <= u <= hi])
        lid = lambda u: top(u) + closure * (bottom(u) - top(u))  # noqa: E731
        hidden = {(x, y) for x, y in eye if -(x - cx) * sin + (y - cy) * cos < lid((x - cx) * cos + (y - cy) * sin) + 1.5} \
            if closure < CLOSED else eye
        inpaint_skin(im, hidden, skin)
        # the lid line: thickest in the middle, a little heavier at the outer corner
        width = hi - lo
        thick = max(2.2, 0.085 * width) * (1.15 if closure <= NARROW else 1.0)
        steps = 28
        centre, normal, widths = [], [], []
        for i in range(steps + 1):
            u = lo + (hi - lo) * (0.04 + 0.92 * i / steps)
            s = 2 * i / steps - 1  # -1 .. 1 across the eye
            outer = -s if side == 0 else s
            v = lid(u)
            centre.append((cx + u * cos - v * sin, cy + u * sin + v * cos))
            normal.append((-sin, cos))
            widths.append(thick * (0.22 + 0.78 * math.sqrt(max(0.0, 1 - s * s))) * (1 + 0.3 * max(0.0, outer)))
        _stroke(im, centre, normal, widths, lash)
        if closure >= CLOSED:  # a few lashes at the outer corner, pointing down and out
            ex, ey = centre[0] if side == 0 else centre[-1]
            out = -1 if side == 0 else 1
            for k, (du, dv) in enumerate(((0.16, 0.10), (0.10, 0.17))):
                tip = (ex + out * du * width * cos - dv * width * sin, ey + out * du * width * sin + dv * width * cos)
                _stroke(im, [(ex, ey), tip], [(-sin, cos)] * 2, [thick * (0.8 - 0.2 * k), 0.4], lash)
    return im


def pout(im: Image.Image, key) -> Image.Image:
    """Replace her mouth with a small frown (the pouty face)."""
    im = im.copy()
    px = im.load()
    boxes = [_box(im, b) for b in IRISES[key]]
    skin = skin_tone(im, *[((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes])
    x0, y0, x1, y1 = _box(im, MOUTHS[key])
    area = [(x, y) for y in range(y0 - 3, y1 + 4) for x in range(x0 - 3, x1 + 4)]
    mouth = {p for p in area if _dist(px[p][:3], skin) > 45}
    colour = sorted((px[p][:3] for p in mouth), key=sum)[len(mouth) // 6] if mouth else (150, 70, 70)
    inpaint_skin(im, mouth, skin)
    cx, cy, w = (x0 + x1) / 2, (y0 + y1) / 2 + 1, (x1 - x0) * 0.62
    pts = [(cx + w / 2 * s, cy - 0.30 * w * (1 - s * s)) for s in [i / 10 - 1 for i in range(21)]]  # a little arch
    thick = max(1.8, 0.11 * w)
    _stroke(im, pts, [(0, 1)] * len(pts), [thick * (0.35 + 0.65 * math.sqrt(max(0.0, 1 - (i / 10 - 1) ** 2))) for i in range(21)], colour)
    return im


def overlay_png(im: Image.Image, size: int, path: Path) -> None:
    """A PNG for the Windows floating window: flattened on the key colour, which Tk makes transparent."""
    im = im.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    flat = Image.new("RGB", im.size, KEY)
    alpha = im.getchannel("A")
    flat.paste(im.convert("RGB"), (0, 0), alpha.point(lambda v: 255 if v >= 128 else 0))
    px = flat.load()
    a = alpha.load()
    for y in range(flat.height):  # keep real pixels from being the key colour by accident
        for x in range(flat.width):
            if a[x, y] >= 128 and px[x, y] == KEY:
                px[x, y] = (255, 255, 255)
    flat.save(path, optimize=True)


def make_companion(sheets: list[Image.Image]) -> None:
    """Study Buddy: every sticker becomes a pose (plus a pouty one) for the app and the floating window."""
    COMPANION.mkdir(parents=True, exist_ok=True)
    overlay = COMPANION / "overlay"
    overlay.mkdir(exist_ok=True)
    for old in [*COMPANION.glob("*.webp"), *overlay.glob("*.png")]:
        old.unlink()
    def shrink(im: Image.Image) -> Image.Image:
        im = im.copy()
        im.thumbnail((300, 300), Image.LANCZOS)
        return im

    def save(im: Image.Image, name: str, with_overlay: bool = True) -> None:
        save_webp(shrink(im), COMPANION / f"{name}.webp")
        if with_overlay:
            overlay_png(im, 170, overlay / f"{name}.png")

    packs = []
    for n, sheet in enumerate(sheets, start=1):
        sheet = sheet.convert("RGBA")
        boxes = find_stickers(sheet, len(STICKER_MOODS))
        if len(boxes) != len(STICKER_MOODS):
            raise SystemExit(f"Sticker sheet {n}: found {len(boxes)} stickers, expected {len(STICKER_MOODS)}.")
        items = []
        poses = {}
        for i, (box, mood) in enumerate(zip(boxes, STICKER_MOODS), start=1):
            sticker = cut_sticker(sheet, box, 100_000)  # full size: the expressions are drawn at this size
            poses[mood] = (i, sticker)
            name = f"study-buddy-{n}-{i}"
            save(sticker, name)
            item = {"file": f"{name}.webp", "overlay": f"overlay/{name}.png", "mood": mood}
            if (n, i) in IRISES:  # she can blink: eyes closed, and half closed on the way
                save(lids(sticker, (n, i), CLOSED), f"{name}-blink")
                save(lids(sticker, (n, i), HALF), f"{name}-half", with_overlay=False)
                item.update(blink=f"{name}-blink.webp", half=f"{name}-half.webp", overlay_blink=f"overlay/{name}-blink.png")
            items.append(item)
        # relaxed (breaks): the study pose with her eyes peacefully closed
        i = poses["study"][0]
        if (n, i) in IRISES:
            items.append({"file": f"study-buddy-{n}-{i}-blink.webp", "overlay": f"overlay/study-buddy-{n}-{i}-blink.png", "mood": "relax"})
        # pouty: the coding pose with narrowed eyes and a small frown; "plain" has no anger mark (the app
        # animates its own), "file" has it drawn in (notifications, the floating windows)
        i, code = poses["code"]
        name = f"study-buddy-{n}-pouty"
        item = {"file": f"{name}.webp", "overlay": f"overlay/{name}.png", "mood": "pouty"}
        if (n, i) in IRISES and (n, i) in MOUTHS:
            face = pout(lids(code, (n, i), NARROW), (n, i))
            shut = pout(lids(code, (n, i), CLOSED), (n, i))
            save(face, f"{name}-face", with_overlay=False)
            save(shut, f"{name}-face-blink", with_overlay=False)
            save(anger_mark(shut), f"{name}-blink")
            item.update(plain=f"{name}-face.webp", plain_blink=f"{name}-face-blink.webp", blink=f"{name}-blink.webp",
                        overlay_blink=f"overlay/{name}-blink.png")
        else:
            face = code
        save(anger_mark(face), name)
        items.append(item)
        packs.append({"id": f"study-buddy-{n}", "name": f"Study Buddy {n}", "items": items})
    (COMPANION / "packs.json").write_bytes(json.dumps({"packs": packs}, indent=2).encode("utf-8"))
    android = ROOT / "android" / "app" / "assets" / "companion"  # bundled into the phone app (floating bubble)
    android.mkdir(parents=True, exist_ok=True)
    for old in android.glob("*"):
        old.unlink()
    for f in COMPANION.glob("*.webp"):
        (android / f.name).write_bytes(f.read_bytes())
    (android / "packs.json").write_bytes((COMPANION / "packs.json").read_bytes())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--stickers", nargs="*", default=[], help="Study Buddy sticker sheets (transparent PNG)")
    args = ap.parse_args()
    make_icons(Image.open(args.logo))
    if args.stickers:
        make_companion([Image.open(p) for p in args.stickers])
    print("Icons:", ", ".join(sorted(p.name for p in ICONS.iterdir())))
    print("Companion:", ", ".join(sorted(p.name for p in COMPANION.iterdir())))


if __name__ == "__main__":
    main()
