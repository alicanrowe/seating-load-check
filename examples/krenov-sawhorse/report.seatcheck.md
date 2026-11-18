# Seat check: krenov_sawhorse_vB_glued

**FAIL.** Lowest margin 0.36 (1.00 is the line). Model `krenov_sawhorse_vB.glb` sha 15e9b12a0465, 122446 cells of 3.3 mm. Piece weighs 2.6 kg; seat top 31.50 in. Design sitter 113 kg.

| | Check | Case | Margin | Notes |
|---|---|---|---|---|
| FAIL | strength: Top_Rail | drop in, 2.0 x weight centred | 0.36 | tension across the grain (splitting), at [-12.29, -0.03, 27.12] (yellow poplar, safety factor 2.5 wanted, 0.9 there) |
| FAIL | strength: Leg_R | lean / rock toward +x, weight + 0.15 x weight sideways | 0.49 | tension across the grain (splitting), at [11.32, 0.23, 13.11] (yellow poplar, safety factor 2.5 wanted, 1.2 there) |
| FAIL | strength: Leg_L | lean / rock toward -x, weight + 0.15 x weight sideways | 0.49 | tension across the grain (splitting), at [-11.39, 0.23, 13.11] (yellow poplar, safety factor 2.5 wanted, 1.2 there) |
| FAIL | strength: Foot_R | lean / rock toward +y, weight + 0.15 x weight sideways | 0.51 | tension across the grain (splitting), at [12.1, -1.2, 1.69] (yellow poplar, safety factor 2.5 wanted, 1.3 there) |
| FAIL | strength: Foot_L | lean / rock toward +y, weight + 0.15 x weight sideways | 0.52 | tension across the grain (splitting), at [-11.52, -1.2, 1.69] (yellow poplar, safety factor 2.5 wanted, 1.3 there) |
| FAIL | tipping: edge test | over the edge facing -x | 0.72 | 600 N 60 mm in from the seat edge + 20 N outward; to reach 1.2: feet out 0.48 in or seat edge in 0.50 in or 2.5 kg low in the base |
| FAIL | joint: Leg_L ~ Stretcher | lean / rock toward -x, weight + 0.15 x weight sideways | 0.94 | glued: glue line: pulling apart across the grain, 72% of the load on end grain; carries 145 N, 41 N m |
| FAIL | joint: Leg_L ~ Top_Rail | drop in, 2.0 x weight centred | 0.95 | glued: glue line: pulling apart across the grain, 52% of the load on end grain; carries 1118 N, 41 N m |
| FAIL | joint: Leg_R ~ Top_Rail | drop in, 2.0 x weight centred | 0.95 | glued: glue line: pulling apart across the grain, 52% of the load on end grain; carries 1123 N, 41 N m |
| FAIL | joint: Leg_R ~ Stretcher | lean / rock toward +x, weight + 0.15 x weight sideways | 0.96 | glued: glue line: pulling apart across the grain, 71% of the load on end grain; carries 145 N, 41 N m |
| WARN | strength: Stretcher | lean / rock toward -x, weight + 0.15 x weight sideways | 1.20 | tension across the grain (splitting), at [-12.29, -0.03, 10.51] (yellow poplar, safety factor 2.5 wanted, 3.0 there) |
| PASS | tipping: lean | over the edge facing +y | 1.30 | 113 kg centred, pushing 0.15 x weight outward at seat height |
| PASS | tipping: push to tip (seated) | toward +y | 1.30 | 216 N (49 lbf) sideways at the seat tips it with a 113 kg sitter; lean case asks for 0.15 x weight |
| PASS | joint: Foot_R ~ Leg_R | lean / rock toward +y, weight + 0.15 x weight sideways | 1.55 | glued: glue line: pulling apart across the grain, 83% of the load on end grain; carries 564 N, 60 N m |
| PASS | joint: Foot_L ~ Leg_L | lean / rock toward +y, weight + 0.15 x weight sideways | 1.60 | glued: glue line: pulling apart across the grain, 83% of the load on end grain; carries 574 N, 60 N m |
| PASS | tipping: perch on the edge | over the edge facing -x | 1.79 | the whole 113 kg perched 50 mm in from the seat edge |
| PASS | strength: Leg_R (buckling) | sit hard on the +x edge, 1.5 x weight | 2.73 | pinned-end Euler, thinnest section |
| PASS | strength: Leg_L (buckling) | sit hard on the -x edge, 1.5 x weight | 2.74 | pinned-end Euler, thinnest section |
| PASS | stiffness: seat sink | sit | 4.39 | 1.1 mm under the sitter (warns past 5.0 mm: feels bouncy) |

## Fixes

- Foot_R: the load pulls across the grain near [12.1, -1.2, 1.69] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x2.35.
- Leg_R: the load pulls across the grain near [11.32, 0.23, 13.11] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x2.46.
- Foot_L: the load pulls across the grain near [-11.52, -1.2, 1.69] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x2.31.
- Leg_L: the load pulls across the grain near [-11.39, 0.23, 13.11] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x2.45.
- Stretcher: the load pulls across the grain near [-12.29, -0.03, 10.51] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x1.00.
- Top_Rail: the load pulls across the grain near [-12.29, -0.03, 27.12] (it would split). Change the grain direction, move the joint, or pin across it with a bolt or dowel; more wood helps only about x3.35.
- Leg_L ~ Stretcher: leans on end-grain glue (72%). Give it long-grain cheeks (a real tenon or bridle) or a mechanical fastener.
- Leg_R ~ Stretcher: leans on end-grain glue (71%). Give it long-grain cheeks (a real tenon or bridle) or a mechanical fastener.
- Leg_L ~ Top_Rail: leans on end-grain glue (52%). Give it long-grain cheeks (a real tenon or bridle) or a mechanical fastener.
- Leg_R ~ Top_Rail: leans on end-grain glue (52%). Give it long-grain cheeks (a real tenon or bridle) or a mechanical fastener.
- Tipping, edge test over the edge facing -x: 1.2: feet out 0.48 in or seat edge in 0.50 in or 2.5 kg low in the base.

## Parts

| Part | Material | Grain | Mass kg |
|---|---|---|---|
| Foot_R | yellow poplar | y | 0.13 |
| Leg_R | yellow poplar | z | 0.41 |
| Foot_L | yellow poplar | y | 0.13 |
| Leg_L | yellow poplar | z | 0.41 |
| Stretcher | yellow poplar | x | 0.38 |
| Top_Rail | yellow poplar | x | 0.52 |
| Cushion | pad (no stiffness, passes load down) | - | 0.58 |

## What it assumed

- Safety factors wanted: wood 2.5 on mean clear-wood strength, metal 1.5 on yield, glue 2.5, bolts 2.0, fatigue 1.5.
- Loads: sit 113 kg on a 200 mm pad; drop 2.0x; edges 1.5x on a 120 mm pad 60 mm in; lean 0.15 x weight sideways at seat height.
- Floor: slippery for the sit, drop and edge cases (feet free to spread), gripping for the lean cases. Joints that touch are bonded in the stiffness model; glued, dry and bolted joints are then checked from the forces they carry.
- Wood is clear, straight grain at 12% moisture. Knots, runout and short grain are not seen: look at the boards.
- Voxel stresses at sharp inside corners depend on the cell size. Rerun at a finer --res and trust what holds at both.
