"""One-page sheet for a seatcheck run: where the piece works hardest, the footprint for tipping,
and the results table. White page, thin type, grey ink; the worst spots go black.

Uses a brand theme if SEATCHECK_THEME points to a folder with a theme.py (font(role, scale),
color(role), text(role, s)), otherwise plain fonts.
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 2400, 1900
S = W / 1440 * 1.25          # site px -> sheet px


def _theme():
    for p in (os.environ.get("SEATCHECK_THEME"),):
        if p and os.path.exists(os.path.join(p, "theme.py")):
            sys.path.insert(0, p)
            try:
                import theme as T
                return T
            except Exception:
                pass
    return None


T = _theme()
ROLE = {"label": "name_label"}          # sheet role -> theme role


def _r(role):
    return ROLE.get(role, role) if T and ROLE.get(role) in getattr(T, "THEME", {}).get("type", {}) else role


def font(role, mult=1.0):
    if T:
        f = T.font(_r(role), S * mult); return f
    size = {"title": 21, "body": 13.3, "spec": 11.5, "label": 13}[role] * S * mult
    for c in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(c):
            return ImageFont.truetype(c, int(size))
    return ImageFont.load_default()


def col(role):
    if T:
        return T.color(_r(role))
    return {"title": (82, 82, 82), "body": (64, 64, 64), "spec": (64, 64, 64), "label": (0, 0, 0)}[role]


def txt(role, s):
    return T.text(_r(role), s) if T else (s.upper() if role == "title" else s)


INK = (64, 64, 64); FILL = (243, 243, 243); MUTED = (140, 140, 140)


def ramp(u):
    """0 -> faint grey, 1 -> ink, over 1 -> black."""
    u = np.clip(u, 0, 1.0)
    lo = np.array([232, 232, 232.]); hi = np.array([64, 64, 64.])
    return lo + (hi - lo) * u[..., None] ** 0.8


def projection(model, env, axis_h, axis_v, depth_axis, px):
    ijk = model.ijk
    a = ijk[:, axis_h]; b = ijk[:, axis_v]
    nh, nv = model.shape[axis_h], model.shape[axis_v]
    grid = np.full((nh, nv), -1.0)
    np.maximum.at(grid, (a, b), env)
    img = np.full((nv, nh, 3), 255.0)
    m = grid >= 0
    c = ramp(grid)
    c[grid >= 1.0] = (0, 0, 0)
    img[m.T] = c.transpose(1, 0, 2)[m.T]
    img = img[::-1]                       # z up
    im = Image.fromarray(img.astype(np.uint8))
    sc = px / max(nh, nv)
    return im.resize((max(1, int(nh * sc)), max(1, int(nv * sc))), Image.NEAREST), sc


def make(model, env, res, rows, hull, fp, com, tip, out, units, zmin, name):
    sh = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(sh)
    g = int(40 * S / 2)
    x0 = int(64 * S / 2.0)
    d.text((x0, int(30 * S)), txt("title", "seat check"), font=font("title", 1.4), fill=col("title"))
    d.text((x0, int(30 * S) + int(48 * S)), name, font=font("body", 1.2), fill=col("body"))
    fails = [r for r in rows if r["status"] == "FAIL"]; warns = [r for r in rows if r["status"] == "WARN"]
    verdict = "FAIL" if fails else ("PASS, WITH WARNINGS" if warns else "PASS")
    specs = [f"{verdict}   lowest margin {min(r['margin'] for r in rows):.2f}",
             f"model sha {res['sha']}   {res['elements']} cells of {res['cell_mm']:.1f} mm",
             f"piece {res['mass_kg']:.1f} kg   sitter {res['occupant_kg']} kg   seat top {res['seat_top']:.2f} {units}"]
    y = int(30 * S) + int(78 * S)
    for s_ in specs:
        d.text((x0, y), s_, font=font("spec", 1.1), fill=col("spec")); y += int(17 * S)

    # projections
    top = y + int(24 * S)
    pw = int(W * 0.27)
    im1, _ = projection(model, env, 0, 2, 1, pw)
    im2, _ = projection(model, env, 1, 2, 0, pw)
    sh.paste(im1, (x0, top)); sh.paste(im2, (x0 + im1.width + int(40 * S), top))
    lab_y = top + max(im1.height, im2.height) + int(8 * S)
    d.text((x0, lab_y), txt("label", "front"), font=font("label"), fill=col("label"))
    d.text((x0 + im1.width + int(40 * S), lab_y), txt("label", "side"), font=font("label"), fill=col("label"))
    # legend
    ly = lab_y + int(28 * S)
    for i in range(200):
        c = tuple(int(v) for v in ramp(np.array(i / 199)))
        d.line([(x0 + i * 2, ly), (x0 + i * 2, ly + 14)], fill=c, width=2)
    d.rectangle([x0 + 410, ly, x0 + 440, ly + 14], fill=(0, 0, 0))
    d.text((x0, ly + 20), "0", font=font("spec"), fill=col("spec"))
    d.text((x0 + 370, ly + 20), "1.0", font=font("spec"), fill=col("spec"))
    d.text((x0 + 450, ly - 2), "over the limit", font=font("spec"), fill=col("spec"))
    d.text((x0, ly + 44), "share of the allowed stress, worst load case, safety factor included", font=font("spec"), fill=col("spec"))

    # plan view: footprint and tipping
    px0 = x0 + 2 * pw + int(80 * S); pwid = W - px0 - x0; ph = int(pw * 0.9)
    pts = [np.array(hull.exterior.coords)] + [np.array(gm.exterior.coords) for gm in getattr(fp, "geoms", [fp])]
    allp = np.vstack(pts)
    lo = allp.min(0); hi = allp.max(0); span = (hi - lo).max() * 1.15
    sc = min(pwid, ph) / span; c0 = (lo + hi) / 2
    P = lambda q: (px0 + pwid / 2 + (q[0] - c0[0]) * sc, top + ph / 2 - (q[1] - c0[1]) * sc)
    for gm in getattr(fp, "geoms", [fp]):
        d.polygon([P(q) for q in np.array(gm.exterior.coords)], fill=FILL, outline=MUTED)
    hp = [P(q) for q in np.array(hull.exterior.coords)]
    d.line(hp, fill=INK, width=2)
    cx, cy = P(com[:2]); r = 7
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=2)
    worst = {}
    for t in tip:
        if t["case"] in ("edge test", "perch on the edge") and t["margin"] < 1.0:
            if t["case"] not in worst or t["margin"] < worst[t["case"]]["margin"]:
                worst[t["case"]] = t
    for k, t in worst.items():
        p0, p1 = P(t["p0"]), P(t["p1"])
        d.line([p0, p1], fill=(0, 0, 0), width=5)
        lx, ly_ = P(t["load_point"])
        d.line([(lx - 9, ly_ - 9), (lx + 9, ly_ + 9)], fill=(0, 0, 0), width=3)
        d.line([(lx - 9, ly_ + 9), (lx + 9, ly_ - 9)], fill=(0, 0, 0), width=3)
        d.text((lx + 12, ly_ - 8), f"{k} {t['margin']:.2f}", font=font("spec"), fill=(0, 0, 0))
    d.text((px0, top + ph + int(8 * S)), txt("label", "plan"), font=font("label"), fill=col("label"))
    for i_, s_ in enumerate(["line: where it stands", "grey: seat", "circle: centre of weight", "x: load that tips it"]):
        d.text((px0, top + ph + int(28 * S) + i_ * int(17 * S)), s_, font=font("spec"), fill=col("spec"))

    # table
    ty = ly + int(80 * S)
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    rs = sorted(rows, key=lambda r: (order[r["status"]], r["margin"]))
    colx = [x0, x0 + int(70 * S), x0 + int(560 * S), x0 + int(660 * S)]
    hdr = ["", "check", "margin", "case"]
    for cxx, hh in zip(colx, hdr):
        d.text((cxx, ty), txt("label", hh), font=font("label"), fill=col("label"))
    ty += int(24 * S)
    d.line([(x0, ty - 4), (W - x0, ty - 4)], fill=(200, 200, 200), width=1)
    maxrows = int((H - ty - int(30 * S)) / int(17 * S))
    for r in rs[:maxrows]:
        fill = (0, 0, 0) if r["status"] == "FAIL" else col("spec")
        f = font("spec")
        d.text((colx[0], ty), r["status"], font=f, fill=fill)
        d.text((colx[1], ty), f"{r['group']}: {r['item']}"[:62], font=f, fill=fill)
        d.text((colx[2], ty), f"{min(r['margin'], 99):.2f}", font=f, fill=fill)
        d.text((colx[3], ty), r["case"][:70], font=f, fill=fill)
        ty += int(17 * S)
    if len(rs) > maxrows:
        d.text((colx[1], ty), f"+ {len(rs) - maxrows} more passing rows in the report", font=font("spec"), fill=MUTED)
    sh.save(out)
    return out
