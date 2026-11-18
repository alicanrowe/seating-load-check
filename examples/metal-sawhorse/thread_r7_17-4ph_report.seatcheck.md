# Seat check: MB-SH-01_thread_r7_17-4PH

**PASS.** Lowest margin 1.22 (1.00 is the line). Model `thread_r7.glb` sha 17d3f7eaeca5, 120232 cells of 2.2 mm. Piece weighs 12.0 kg; seat top 75.48 cm. Design sitter 113 kg.

| | Check | Case | Margin | Notes |
|---|---|---|---|---|
| PASS | strength: Metal_Frame | drop in, 2.0 x weight centred | 1.22 | yield (von Mises), at [0.28, 0.1, 72.29] (17-4PH H1150 cast, safety factor 1.5 wanted, 1.8 there) |
| PASS | tipping: lean | over the edge facing +y | 1.55 | 113 kg centred, pushing 0.15 x weight outward at seat height |
| PASS | tipping: push to tip (seated) | toward +y | 1.55 | 258 N (58 lbf) sideways at the seat tips it with a 113 kg sitter; lean case asks for 0.15 x weight |
| PASS | fatigue: Metal_Frame | everyday sit, repeated | 1.74 | 174 MPa peak vs 454 MPa allowed for 0-to-peak cycling (Goodman, Se 300 MPa), at [0.28, -0.12, 72.29] |
| PASS | tipping: edge test | over the edge facing +x | 2.04 | 600 N 60 mm in from the seat edge + 20 N outward |
| PASS | tipping: perch on the edge | over the edge facing +x | 2.30 | the whole 113 kg perched 50 mm in from the seat edge |
| PASS | stiffness: seat sink | sit | 9.70 | 0.5 mm under the sitter (warns past 5.0 mm: feels bouncy) |

## Fixes

- None needed.

## Parts

| Part | Material | Grain | Mass kg |
|---|---|---|---|
| Metal_Frame | 17-4PH H1150 cast | - | 10.60 |
| Cushion | pad (no stiffness, passes load down) | - | 1.39 |

## What it assumed

- Safety factors wanted: wood 2.5 on mean clear-wood strength, metal 1.5 on yield, glue 2.5, bolts 2.0, fatigue 1.5.
- Loads: sit 113 kg on a 200 mm pad; drop 2.0x; edges 1.5x on a 120 mm pad 60 mm in; lean 0.15 x weight sideways at seat height.
- Floor: slippery for the sit, drop and edge cases (feet free to spread), gripping for the lean cases. Joints that touch are bonded in the stiffness model; glued, dry and bolted joints are then checked from the forces they carry.
- Wood is clear, straight grain at 12% moisture. Knots, runout and short grain are not seen: look at the boards.
- Voxel stresses at sharp inside corners depend on the cell size. Rerun at a finer --res and trust what holds at both.
