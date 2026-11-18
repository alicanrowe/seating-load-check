"""Check seatcheck against hand calculations and planted mistakes.

  python3 make_fixtures.py && python3 run_tests.py
"""
import os, sys, json, math, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); FX = os.path.join(HERE, "fixtures"); OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
SC = os.path.join(os.path.dirname(HERE), "seatcheck.py")


def run(name, *extra):
    r = subprocess.run([sys.executable, SC, os.path.join(FX, name + ".glb"), "--spec", os.path.join(FX, name + ".seatcheck.json"),
                        "--out", OUT, "--no-sheet", *extra], capture_output=True, text=True)
    if not os.path.exists(os.path.join(OUT, name + ".seatcheck.json")):
        print(r.stdout[-3000:], r.stderr[-3000:]); raise SystemExit(f"{name}: no result")
    return json.load(open(os.path.join(OUT, name + ".seatcheck.json")))


def rows(d, group=None, item=None):
    return [r for r in d["summary"] if (group is None or r["group"] == group) and (item is None or item in r["item"])]


results = []
def check(label, ok, got):
    results.append((label, ok)); print(("ok   " if ok else "MISS ") + label + f"  ({got})", flush=True)


W = 113 * 9.81
# 1. bending: 12 mm oak plank resting on blocks 800 mm apart (150 mm high), 3 cells through the board (--res 4)
d = run("bench_thin", "--res", "4", "--cases", "drop", "--probe", "0,0,150")
P = 2 * W; R = 0.1; L = 0.8; b = 0.3; t = 0.012
M = P / 2 * (L / 2 - 4 * R / (3 * math.pi)); hand = M / (b * t * t / 6) / 1e6
fe = d["probes"]["0,0,150"]["drop"]["S_MPa"][0]
check(f"midspan bending stress within 12% of hand calc {hand:.1f} MPa", abs(fe / hand - 1) < 0.12, f"{fe:.1f} MPa")
s = rows(d, "strength", "Seat")[0]
check("thin plank fails in strength", s["status"] == "FAIL", f"{s['status']} {s['margin']:.2f}")
# 2. thick plank passes
d = run("bench_ok", "--cases", "sit,drop,edge")
s = rows(d, "strength", "Seat")[0]
check("45 mm plank passes", s["status"] == "PASS", f"{s['status']} {s['margin']:.2f}")
j = rows(d, "joint")
check("plank resting on blocks: dry joints hold", all(r["status"] == "PASS" for r in j), [round(r["margin"], 2) for r in j])
# 3. tipping, hand calc: stool_overhang, perch on +x edge
d = run("stool_overhang", "--cases", "sit")
m = json.load(open(os.path.join(FX, "stool_overhang.seatcheck.json")))
tp = [r for r in d["tipping"] if r["case"] == "perch on the edge" and r["normal"][0] > 0.99]
# legs' outer face at +x: 150 mm; seat edge at 175 + 250 = 425 mm
mass = d["mass_kg"]; com_x = d["com"][0] / 1000
hand = (mass * 9.81 * (0.150 - com_x)) / (W * (0.425 - 0.050 - 0.150))   # perched 50 mm in from the edge
check(f"perch margin matches hand calc {hand:.3f}", tp and abs(tp[0]["margin"] / hand - 1) < 0.03, round(tp[0]["margin"], 3) if tp else None)
check("overhanging stool fails perch", rows(d, "tipping", "perch")[0]["status"] == "FAIL", rows(d, "tipping", "perch")[0]["margin"])
d = run("stool_ok", "--cases", "sit")
check("square stool passes tipping", all(r["status"] != "FAIL" for r in rows(d, "tipping")), [round(r["margin"], 2) for r in rows(d, "tipping")])
check("square stool passes strength", all(r["status"] != "FAIL" for r in rows(d, "strength")), [round(r["margin"], 2) for r in rows(d, "strength")])
# 4. joint statics: each leg of the symmetric bench carries half the drop load
d = run("bench_ok", "--cases", "drop")
F = [max(r["F_N"] for r in d["joints"][k]) for k in d["joints"]]
check(f"each support carries half of {P:.0f} N (+ seat weight)", all(abs(f / (P / 2) - 1) < 0.06 for f in F), [round(f) for f in F])
# 5. dry joint that has to hang: lifts off
d = run("hang_dry", "--cases", "sit")
check("hanging seat on dry blocks comes apart", any("Hanger" in x for x in d.get("lifted", [])), d.get("lifted"))
# 6. bolted cuts in a one-piece metal stool
d = run("metal_bolt_small", "--cases", "sit,edge")
check("M3 bolts in the pedestal post fail", any(r["status"] == "FAIL" for r in rows(d, "joint")), [round(r["margin"], 2) for r in rows(d, "joint")])
d = run("metal_bolt_ok", "--cases", "sit,edge")
check("M10 bolts in the pedestal post pass", all(r["status"] == "PASS" for r in rows(d, "joint")), [round(r["margin"], 2) for r in rows(d, "joint")])
n = sum(ok for _, ok in results)
print(f"\n{n} of {len(results)} checks pass")
sys.exit(0 if n == len(results) else 1)
