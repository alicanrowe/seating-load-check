"""Build small seats with known answers (hand calculations) and planted mistakes.

  python3 make_fixtures.py      -> writes fixtures/*.glb and fixtures/*.seatcheck.json
Units: mm, Z up.
"""
import os, json, math
import numpy as np, trimesh

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(OUT, exist_ok=True)


def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]); return b


def save(name, parts, spec):
    sc = trimesh.Scene()
    for k, m in parts.items():
        sc.add_geometry(m, node_name=k, geom_name=k)
    sc.export(os.path.join(OUT, name + ".glb"))
    spec = dict(spec); spec.setdefault("units", "mm"); spec.setdefault("up", "z"); spec["name"] = name
    json.dump(spec, open(os.path.join(OUT, name + ".seatcheck.json"), "w"), indent=1)


# 1. bench plank on two solid blocks: midspan bending stress is a hand calc (statically determinate)
def bench(name, t, material="white oak", span=800, legs_glued=True):
    W, B = 300, 1000
    parts = {"Seat": box(-B / 2, B / 2, -W / 2, W / 2, 150, 150 + t)}
    for s in (-1, 1):
        x0 = s * span / 2
        parts[f"Leg_{'L' if s < 0 else 'R'}"] = box(min(x0, x0 + s * 60), max(x0, x0 + s * 60), -W / 2, W / 2, 0, 150)
    spec = {"material": material, "parts": {"^Seat$": {"grain": "x"}, "^Leg_": {"grain": "z"}}, "seat": "^Seat$",
            "joints": [{"between": ["^Seat$", "^Leg_"], "type": "glued" if legs_glued else "dry"}]}
    save(name, parts, spec)


bench("bench_ok", 45, legs_glued=False)        # thick oak: passes
bench("bench_thin", 12, legs_glued=False)      # 12 mm oak over 800 mm: bending fails

# 2. square stool: tipping is a rigid-body hand calc
def stool(name, overhang, seat_w=350, foot=300, h=450, material="sugar maple"):
    parts = {"Seat": box(-seat_w / 2, seat_w / 2 + overhang, -seat_w / 2, seat_w / 2, h - 30, h)}
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (foot / 2 - 20), sy * (foot / 2 - 20)
            parts[f"Leg_{sx}{sy}".replace("-1", "m").replace("1", "p")] = box(cx - 20, cx + 20, cy - 20, cy + 20, 0, h - 30)
    spec = {"material": material, "parts": {"^Seat$": {"grain": "x"}, "^Leg_": {"grain": "z"}}, "seat": "^Seat$",
            "joints": [{"between": ["^Seat$", "^Leg_"], "type": "glued"}]}
    save(name, parts, spec)


stool("stool_ok", 0)
stool("stool_overhang", 250)   # seat runs 250 mm past the legs on +x: perching there tips it

# 3. hanging seat: a seat board hung below a beam on dry blocks pulls the dry joint apart
def hang(name, joint):
    parts = {"Post_L": box(-420, -380, -40, 40, 0, 600), "Post_R": box(380, 420, -40, 40, 0, 600),
             "Beam": box(-420, 420, -40, 40, 600, 660), "Hanger_L": box(-200, -170, -40, 40, 470, 600),
             "Hanger_R": box(170, 200, -40, 40, 470, 600), "Seat": box(-250, 250, -150, 150, 440, 470)}
    spec = {"material": "white oak", "parts": {"^Post": {"grain": "z"}, "^Beam": {"grain": "x"}, "^Hanger": {"grain": "z"}, "^Seat$": {"grain": "x"}},
            "seat": "^Seat$", "joints": [{"between": ["^Hanger", "^Beam"], "type": joint}, {"between": ["^Hanger", "^Seat"], "type": "glued"}]}
    save(name, parts, spec)


hang("hang_dry", "dry")

# 4. one-piece steel pedestal stool (base plate, square post, seat plate) bolted together in the post
def pedestal(name, bolt):
    import manifold3d as m3
    ms = [box(-200, 200, -200, 200, 0, 10), box(-30, 30, -30, 30, 0, 450), box(-175, 175, -175, 175, 450, 460)]
    u = None
    for b_ in ms:
        mf = m3.Manifold(m3.Mesh(np.asarray(b_.vertices, np.float32), np.asarray(b_.faces, np.uint32)))
        u = mf if u is None else u + mf
    mm = u.to_mesh(); fr = trimesh.Trimesh(mm.vert_properties[:, :3], mm.tri_verts)
    spec = {"material": "mild steel", "seat": "^Frame$",
            "cuts": [{"name": "post split at 300", "point": [0, 0, 300], "normal": [0, 0, 1], "radius": 60,
                      "type": "bolted", "bolt": bolt, "grade": "A2-70", "count": 2}]}
    save(name, {"Frame": fr}, spec)


pedestal("metal_bolt_ok", "M10")
pedestal("metal_bolt_small", "M3")
print("fixtures in", OUT)
