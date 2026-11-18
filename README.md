# Seating load check skill

A Claude skill that checks anything people sit on (chairs, stools, benches, sawhorses, metal or printed seating) from its CAD model: will it hold the person sitting on it, including dropping in, perching on an edge and leaning back, and will it tip? It gives a pass / warn / fail report with margins and the fixes.

It goes with [hardwood-furniture-cad](https://github.com/alicanrowe/hardwood-furniture-cad): that skill checks joinery and wood movement, this one checks loads and stability.

## What's in it
- **`SKILL.md`**: the workflow Claude follows: get the model ready, write the spec, run, read, fix and re-run.
- **`scripts/seatcheck.py`**: reads a GLB/STL assembly (one mesh per part), turns it into a voxel finite-element model with each part's own material, and checks:
  - every part's strength at its worst point: bending, splitting across the grain, crushing, shear and rolling shear in wood (along its grain); yield in metal; plus crushing along the grain and buckling for struts
  - glued joints on the glue line (long grain vs end grain), dry joints that lift off or slide, bolts in tension and shear (with the size that would pass), screws pulling out
  - bolted splits through a one-piece body (printed or cast sections), described as cut planes
  - metal fatigue under the everyday sit
  - tipping about every edge of the footprint: an edge test modelled on EN 1022, perching with full weight on the edge, leaning, and the push it takes to tip it, each with how far to move the feet or seat edge or how much weight would fix it
  - feet that aren't flat and rock
  - seat sink and feet spreading on a slippery floor
  - load cases: sitting, dropping in (2x), sitting hard on each edge (1.5x), leaning each way, and optionally standing on it
- **`scripts/materials.json`**: 10 woods (Wood Handbook clear-wood values); printed 316L, Ti-6Al-4V and maraging steel; wrought and cast stainless, 17-4PH, silicon bronze, steel, aluminium, brass, sterling; bolt sizes and grades.
- **`scripts/seatsheet.py`**: a one-page PNG: where the piece works hardest (front and side), the footprint with the loads that tip it, and the results table.
- **`references/`**: `spec.md` (every setting), `materials.md` (where the numbers come from, safety factors), `reading-the-report.md` (each check and its usual fix).
- **`scripts/tests/`**: builds small seats with known answers and planted mistakes and checks the checker against them: midspan bending stress against the hand calculation, tipping margin against the hand calculation, load sharing between supports, a thin plank, an overhanging stool, a seat hung on dry blocks, and undersized bolts in a metal stool.
- **`examples/`**: a wooden Krenov-style sawhorse with a cushion, and a 3D-printed stainless sawhorse made of bolted sections.

## Install
- **Claude.ai / Claude app:** zip this folder and upload it under Settings > Capabilities > Skills.
- **Claude Code:** copy the folder to `~/.claude/skills/seating-load-check/`.
- Requirements: `pip install trimesh numpy scipy pyamg shapely rtree pillow`, and `pypardiso` for a much faster solve (it falls back to multigrid without it). About 6 GB of memory for a 120k-cell model (memory grows with the cell count, so the finer check run may need a bigger machine; at least run a second, coarser size to see the trend).

## Quick start
```
python3 scripts/seatcheck.py stool.glb --spec stool.seatcheck.json
```
```json
{"units": "mm", "up": "z", "material": "white oak",
 "parts": {"^Seat$": {"grain": "x"}, "^Leg_": {"grain": "z"}, "^Cushion$": {"role": "pad"}},
 "seat": "^Cushion$",
 "joints": [{"between": ["^Seat$", "^Leg_"], "type": "glued"},
            {"between": ["^Rail$", "^Leg_"], "type": "dry"}],
 "occupant_kg": 113, "stand": false}
```

## Limits
- It's a second pair of eyes, not a certification. For a product sold to the public, test real ones to EN 1022 / EN 12520 / ANSI/BIFMA X5.1.
- Wood is clear, straight grain at 12% moisture, grain along x, y or z. Real boards are weaker; that's what the 2.5 safety factor is for. It doesn't see knots, runout, short grain in curved parts, glue quality, print porosity or welds.
- Parts that touch are bonded unless the joint is dry; glued joints are then checked from the forces they carry.
- Voxel stresses at sharp inside corners depend on the cell size: run at two sizes and trust what holds at both. Thin parts need at least 3 cells through them; the report warns when a part comes out the wrong volume.
- Tipping is rigid-body on a floor that doesn't slip.
- Wood values were typed in from the Wood Handbook; check the ones you rely on.

## Authors
- **Alican Rowe** ([@alicanrowe](https://github.com/alicanrowe))
- Claude (Anthropic)

## License
MIT. See [LICENSE](LICENSE).
