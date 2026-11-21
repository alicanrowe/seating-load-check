---
name: seating-load-check
description: Use when designing, modelling or reviewing anything people sit on (chairs, stools, benches, sawhorses, perches, metal or printed seating) to check that it holds a sitter, including drop-in, edge and leaning loads, joints and fasteners, wood and metal strength, and that it won't tip. Reads a GLB/STL model and gives a pass/fail report with margins and fixes.
metadata:
  author: Alican Rowe (@alicanrowe)
---

# Seating load and tipping check

Check that a seat holds the person on it and doesn't tip, from the CAD model, before anything is cut or printed. Pairs with the hardwood-furniture-cad skill: that one checks joinery and wood movement; this one checks loads and stability. Run both on a wooden piece.

The scripts (`scripts/seatcheck.py`, `seatsheet.py`, `materials.json`, tests) and references ship with the skill folder, from the GitHub repo `alicanrowe/seating-load-check`. If they aren't next to this file, get them from there.

## 1. Get the model ready
- Export the assembled piece as GLB (or one STL per part, or one STL), every part a closed solid (overlapping or un-booleaned shells are fine; it fills by winding number), one mesh per part, in place. Name parts so the spec can match them (`Leg_L`, `Seat`, `Cushion`).
- Upholstery, leather, foam and straps are **pads**: they carry no load in the model, they pass the sitter's load to whatever they rest on. Names with cushion, pad, leather, foam or strap are taken as pads automatically.
- Model the seat the way it is really made: straps of constant leather thickness that rest on or wrap the frame, closures (toggles, buckles) that actually fasten, and nothing passing through the metal. A seat that only stays on because a strap is fused into the rail gives a load path that doesn't exist. For cast-metal pieces run the sculpted-metal-casting skill's `check_soft_parts.py` first. A seat that lifts off is a `dry` joint to the frame.
- A one-piece body that is really several sections bolted together (printed metal, a casting in parts) can stay one mesh: describe each split as a `cut` in the spec (point, normal, a radius that takes in only that section, bolts). Parts modelled separately are checked at every face where they touch.
- Moving parts (a turning seat, a sliding or rocking part) need a load-check copy of the model. A gap smaller than about one cell closes in the model and the parts bond, so a seat that turns on balls inside a 3 mm running clearance gets welded to the frame around it and the load skips the real path. In the check copy, open every running clearance to over 1.5 cells (shrink the moving part, or deepen a step), turn rows of balls or rollers into one ring at the same height, and drop loose keys; mark the bearing joints `dry` with a low `mu` (0.05 for wood on wood balls). Say in the report which clearances were opened and by how much.
- Parametric CAD (Onshape, Fusion): export the current version and write its hash in the report, as the furniture-cad skill does.

## 2. Write the spec (`<piece>.seatcheck.json`)
Read `references/spec.md` for every key. The minimum:

```json
{"units": "in", "up": "z", "material": "white oak",
 "parts": {"^Seat$": {"grain": "x"}, "^Leg_": {"grain": "z"}, "^Cushion$": {"role": "pad"}},
 "seat": "^Cushion$",
 "joints": [{"between": ["^Seat$", "^Leg_"], "type": "glued"}]}
```
- Material per part from `scripts/materials.json` (`references/materials.md` says where the numbers come from and when to replace them). Printed metal: ask which process (laser powder bed or binder jet) and finish, and use the bureau's data sheet if there is one.
- Grain: set it for every wood part whose grain doesn't run along its longest side, and check the guessed ones in the parts table.
- Joints: `glued`, `dry` (rests or bears, can't take tension), `bolted` (`bolt`, `grade`, `count` or `at`), `screwed`. Anything not listed is glued between woods and bolted between metals. A rail dropped into an open slot without glue is `dry`.
- Who sits on it: default 113 kg (250 lb) design sitter. Raise `occupant_kg` for a heavier user or public seating; set `"stand": true` if people will stand on it (sawhorses, step stools).

## 3. Run it
```
pip install trimesh numpy scipy pyamg shapely rtree pillow
python3 scripts/seatcheck.py MODEL.glb --spec piece.seatcheck.json
```
It picks a cell size from the volume (and at least 3 cells through the thinnest part). Then run once more at a finer `--res` (about 0.7 x the first cell, in model units) and only trust results that hold at both. Memory grows with the cell count (about 6 GB at 120k cells); if the finer run won't fit, run a coarser one (about 1.25 x) and say so. A number that keeps moving between sizes is a thin part or a sharp inside corner (see the reading guide). Writes `<name>.seatcheck.md`, `.json` and a one-page `.png`.

## 4. Read the report
Margin = capacity / demand after the safety factor; 1.00 is the line, under 1.20 is a warning. `references/reading-the-report.md` explains each check and its usual fix. In short:
- **strength**: each part at its worst point and load case, with the failure mode (bending along the grain, splitting across it, crushing, shear, rolling shear, metal yield), plus crushing along the grain and buckling for struts.
- **joint**: glue lines (long grain vs end grain), dry joints (lifts off, slides), bolts (tension and shear on the worst bolt, the size that would pass), screws (withdrawal).
- **fatigue**: metal under the everyday sit, cycled.
- **tipping**: edge test (600 N 60 mm in from the edge plus 20 N out, modelled on EN 1022's edge test), perching with full weight right on the edge, leaning, and the sideways push that tips it, each with how far to move the feet or seat edge or how much weight to add. Feet that aren't flat are checked after the piece has rocked onto them, and the rock itself is a warning.
- **stiffness**: how far the seat sinks.
If a resting joint lifts off, fix that first: the rest of the numbers around it don't mean much until it holds.

## 5. Fix and re-run (make-and-check)
When a piece fails and the owner likes the design as drawn, try a stronger material first (17-4 stainless, silicon bronze, printed maraging steel, titanium, a harder wood) at the current sizes, and only thicken or reshape the parts that no material can save. Say which those are. Fix a rocking foot with a glide or a flat under the foot end before changing the leg.

Change the model, export a new numbered version, re-run, and compare with the last run. Repeat until there is no FAIL and every WARN is understood and written down. Only show a result that passed, with the report and sheet. Then cut a section by eye through anything the checker flagged: it doesn't see knots, runout, short grain, glue quality, print defects or weld quality.

After changing `scripts/seatcheck.py`: `cd scripts/tests && python3 make_fixtures.py && python3 run_tests.py`. Every check must pass (hand calculations within tolerance, every planted mistake caught, no false alarms).

## Limits
It's a second pair of eyes, not a certification. Wood is clear, straight-grained, 12% moisture; real boards are weaker, which is what the 2.5 safety factor is for. Every face where parts touch is bonded except dry joints, so a glued joint is as stiff as solid wood. Grain runs along x, y or z (no curved grain). Stresses at sharp inside corners depend on the cell size. Tipping is rigid-body and assumes the floor doesn't slip. For a product sold to the public, test to the standard (EN 1022 / EN 12520 / ANSI/BIFMA X5.1) on a real one.

## Excuses that don't count
Each of these is a shortcut that ends in a broken result. If you catch yourself thinking the left column, do the right column.

| The excuse | What to do instead |
|---|---|
| "It's solid hardwood, it'll hold" | Write the spec and run the check, including drop-in, edge and leaning loads. |
| "Tipping isn't a risk for this one" | Run the tip check for the leaning case anyway. |
| "One warning is fine" | Fix and re-run until the report is clean, or write down why a warning stands. |
| "While I'm in here I'll also tidy/refactor this other bit" | Change only what the task needs. Smallest diff that works; no new options, helpers or files nobody asked for. Note other ideas for later instead. |

## Keep this skill improving
When a real piece fails in a way the check didn't predict, or the owner flags a result as wrong, write the lesson into `references/reading-the-report.md` or `references/materials.md` in the same session, add a planted case to `scripts/tests/`, and re-run the tests. Then publish the skill.
