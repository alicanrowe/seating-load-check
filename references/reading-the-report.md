# Reading the report

Every row: status, what was checked, the worst load case, the margin, notes. **Margin** = capacity / (demand x safety factor). Under 1.00 is FAIL, under 1.20 is WARN.

## Load cases (strength)
| Case | Load | Where |
|---|---|---|
| sit | the sitter's weight | 200 mm pad at the seat centre |
| drop | 2 x weight | same, sitting down hard |
| edge (4) | 1.5 x weight | 120 mm pad 60 mm in from each end and side |
| lean (4) | weight down + 0.15 x weight sideways at the seat | each direction, floor gripping |
| stand (option) | 1.5 x weight | 100 mm pad, centre and ends |
For the vertical cases the floor is slippery (the feet can spread), which is the worse case for splayed legs; for lean the floor grips. The report flags feet that spread more than 2 mm.

## Strength rows and their usual fixes
- **bending / along the grain**: deeper section (strength goes with depth squared), shorter span, or a brace near the load.
- **tension across the grain (splitting)**: more wood doesn't help much. Turn the grain, move the joint, or put a bolt or dowel across it.
- **crushing across the grain**: more bearing area (wider shoulder, washer, bearing block).
- **shear / rolling shear**: more section across the shear, shorter span.
- **yield (metal)**: thicker in the bending direction, a fillet at the inside corner, or a support closer.
- **crush along grain / buckling**: bigger or braced strut.
`at [x, y, z]` is in model units: look there in the model, and cut a section.

## Joints
- **glued**: the glue-line stress across long-grain faces, against the weaker wood's shear and cross-grain tension. "x% of the load on end grain" means part of the joint relies on end grain; at more than 30% it says to give it long-grain cheeks or a fastener.
- **dry**: "bears on x% of the contact" is normal for a resting part under an off-centre load. "lifts off completely" fails, and nothing else near it can be trusted until it's fixed.
- **bolted**: the worst bolt's tension and shear, and the bolt size that would pass with 20% to spare. "bolt positions assumed" means put the real positions in the spec.

## Tipping
Rigid-body moments about every edge of the footprint (the convex outline of everything touching the floor), with the piece's own weight from its volumes and densities.
- **edge test**: 600 N, 60 mm in from the seat edge, plus 20 N pushing outward at seat height. Modelled on the EN 1022 edge stability tests (seating for adults up to 110 kg); the loads are settings, check them against the current edition (EN 1022:2023) before claiming the standard.
- **perch on the edge**: the full design weight right on the seat edge. Sawhorses, benches and stools get perched on.
- **lean**: the sitter centred, pushing 0.15 x their weight outward at seat height.
- **push to tip**: the sideways force at the seat that tips it with the sitter centred; compare it with what people do (pushing back from a table, reaching).
- **rocks on its feet**: the feet aren't flat (a rocker curve, a belly, a nub under the middle), so it stands on a narrow strip. It's checked as if it has already rocked over onto the rest of the foot (up to `rock_max_deg`), with the sitter and the piece shifted outward by that tilt. A WARN, because it still holds; people feel it as a wobble. Flatten the feet or add glides at the ends.
Each failing tipping row says how far the floor contact would have to move out, or the seat edge come in, or how much weight low in the base would fix it (to a margin of 1.2).

## When a number keeps falling as the cells shrink
A stress at a sharp inside corner (mortise, slot or notch corners, the root of a strand) grows each time the cells get finer, because the real corner has no radius. If a FAIL sits on such a corner and drops between the two runs, it marks a real hot spot, but the margin isn't a measure of how far over it is. Round the corner in the model, or judge it by hand: a pin across the grain, a bigger radius. A FAIL away from corners that holds steady at both cell sizes is a real one.

## What isn't checked
- Stresses in the bottom 8 mm (the floor contact). A curved foot resting on a strip shows huge contact stress there; that's a dent, not a break.
- Welds, casting porosity and print defects, and the surface: fatigue uses as-built values unless the part says `"finish": "polished"`.

## Stiffness
Seat sink under the sitter. Over 5 mm feels bouncy (a WARN, not a FAIL).
