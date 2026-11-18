# Seat check: MB-SH-01_rest_17-4PH

**PASS with warnings.** Lowest margin 0.07 (1.00 is the line). Model `rest.glb` sha cb4738278e7a, 120635 cells of 3.1 mm. Piece weighs 29.3 kg; seat top 81.28 cm. Design sitter 113 kg.

| | Check | Case | Margin | Notes |
|---|---|---|---|---|
| WARN | stability: rocks on its feet | toward +y | 0.07 | the feet aren't flat: it stands on a narrow strip and can rock up to 5.4 deg (77 mm at the seat) onto the rest of its feet; tipping is checked after it has rocked. Flatten the feet or add glides |
| WARN | tipping: lean | over the edge facing -y | 1.01 | 113 kg centred, pushing 0.15 x weight outward at seat height; to reach 1.2: feet out 1.8 cm or 28.4 kg low in the base |
| WARN | tipping: push to tip (seated) | toward -y | 1.01 | 168 N (38 lbf) sideways at the seat tips it with a 113 kg sitter; lean case asks for 0.15 x weight |
| PASS | tipping: perch on the edge | over the edge facing -x | 3.67 | the whole 113 kg perched 50 mm in from the seat edge |
| PASS | tipping: edge test | over the edge facing -x | 3.77 | 600 N 60 mm in from the seat edge + 20 N outward |
| PASS | strength: Metal_Frame | lean / rock toward +x, weight + 0.15 x weight sideways | 9.16 | yield (von Mises), at [-14.05, -0.35, 17.64] (17-4PH H1150 cast, safety factor 1.5 wanted, 13.7 there) |
| PASS | fatigue: Metal_Frame | everyday sit, repeated | 31.29 | 10 MPa peak vs 454 MPa allowed for 0-to-peak cycling (Goodman, Se 300 MPa), at [-7.84, 0.27, 68.21] |
| PASS | stiffness: seat sink | sit | 99.00 | 0.0 mm under the sitter (warns past 5.0 mm: feels bouncy) |

## Fixes

- Tipping, lean over the edge facing -y: 1.2: feet out 1.8 cm or 28.4 kg low in the base.
- Feet push outward: add a low stretcher between the feet or rubber pads.
- Tipping, push to tip (seated) toward -y: 168 N (38 lbf) sideways at the seat tips it with a 113 kg sitter; lean case asks for 0.15 x weight.

## Parts

| Part | Material | Grain | Mass kg |
|---|---|---|---|
| Metal_Frame | 17-4PH H1150 cast | - | 27.94 |
| Cushion | pad (no stiffness, passes load down) | - | 1.32 |

## What it assumed

- Safety factors wanted: wood 2.5 on mean clear-wood strength, metal 1.5 on yield, glue 2.5, bolts 2.0, fatigue 1.5.
- Loads: sit 113 kg on a 200 mm pad; drop 2.0x; edges 1.5x on a 120 mm pad 60 mm in; lean 0.15 x weight sideways at seat height.
- Floor: slippery for the sit, drop and edge cases (feet free to spread), gripping for the lean cases. Joints that touch are bonded in the stiffness model; glued, dry and bolted joints are then checked from the forces they carry.
- Wood is clear, straight grain at 12% moisture. Knots, runout and short grain are not seen: look at the boards.
- Voxel stresses at sharp inside corners depend on the cell size. Rerun at a finer --res and trust what holds at both.
