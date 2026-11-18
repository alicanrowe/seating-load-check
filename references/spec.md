# The spec file (`<piece>.seatcheck.json`)

Everything except `material` (or a material per part) has a default.

| Key | Default | What it does |
|---|---|---|
| `name` | model file name | used for the output files |
| `units` | `m` | `in`, `mm`, `cm`, `m` |
| `up` | `z` | `y` for a Blender GLB (metres, Y up) |
| `material` | none | default material for every structural part, a name or alias from `scripts/materials.json` |
| `parts` | | `{regex: {...}}`, first match wins: `material`, `grain` (`x`/`y`/`z`), `role` (`structure`, `pad`, `ignore`), `finish` (`as_built`, `polished`, metal fatigue), `density` (pads, kg/m3) |
| `seat` | pads, else the highest part | regex for the part(s) people sit on; its top surface is the seat |
| `joints` | glued (wood-wood), bolted (metal) | list of `{"between": [regexA, regexB], "type": ...}` |
| `cuts` | none | bolted splits through a one-piece body (below) |
| `occupant_kg` | 113 | design sitter (250 lb). EN 1022 covers adults up to 110 kg; use more for public or heavy-duty seating |
| `dynamic_factor` | 2.0 | dropping onto the seat, x weight |
| `edge_factor` | 1.5 | sitting down hard on an edge or end, x weight |
| `lean_frac` | 0.15 | sideways push at seat height while leaning or rocking, x weight |
| `stand` | false | also check someone standing on it (1.5 x weight on a 100 mm pad, centre and ends) |
| `pad_d_mm`, `edge_pad_d_mm`, `edge_in_mm` | 200, 120, 60 | load pad sizes and how far in from the edge edge loads sit |
| `tip_edge_N`, `tip_edge_push_N` | 600, 20 | edge stability test loads |
| `perch_must_hold` | true | full weight right on the edge must not tip it (set false for a chair you can't perch on, like one with arms) |
| `sf` | wood 2.5, crush_perp 1.25, metal 1.5, fatigue 1.5, glue 2.5, bolt 2.0, screw 1.0 | safety factors wanted |
| `warn_margin` | 1.2 | margins under this are WARN |
| `mu_floor` | 0.3 | floor friction (reported, not used to fail) |
| `deflection_warn_mm` | 5 | seat sink that feels bouncy |
| `floor_tol_mm` | 2 | how close to the floor a vertex must be to count as resting on it |
| `rock_tol_mm`, `rock_max_deg` | 15, 6 | feet that aren't flat: bottom points up to this high that it can rock onto within this tilt |
| `rock_warn_mm` | 5 | warn when rocking moves the seat top more than this |

## Joints

```json
{"between": ["^Rail$", "^Leg_"], "type": "dry", "mu": 0.4}
{"between": ["^Seat$", "^Leg_"], "type": "glued"}
{"between": ["^Arm$", "^Post$"], "type": "bolted", "bolt": "M8", "grade": "A4-70", "count": 2}
{"between": ["^Arm$", "^Post$"], "type": "bolted", "bolt": "1/4-20", "grade": "18-8", "at": [[x, y, z], [x, y, z]]}
{"between": ["^Cleat$", "^Seat$"], "type": "screwed", "screw": {"D_in": 0.19, "thread_in": 1.0, "count": 4}}
```
- `glued`: checked on the glue line from the stresses across it. Faces where either side is end grain don't count (end-grain glue joints are weak), and the rest is scaled up for the share they lose.
- `dry`: the two parts get their own surfaces and only press on each other: where they pull apart, they let go. Reports how much of the contact still bears, the sideways force against friction (`mu`, default 0.4) and if it lifts off completely.
- `bolted`: elastic bolt-group method on the worst bolt, tension from pull and bending, shear from sideways force and twist; capacity is the bolt's proof stress (tension) and 0.6 x tensile strength on the stress area (shear). Without `at`, the bolts are spread across the contact patch 1.5 diameters in from its edges, and the report says the positions were assumed and whether they fit.
- `screwed`: withdrawal per NDS (2850 G^2 D lb per inch of thread, side grain). It doesn't check lateral screw load.
- `welded` / `fused`: one piece, strength is in the parts.

## Cuts (sections of a one-piece body)

```json
"cuts": [{"name": "leg L to foot", "point": [-30, 0, 7], "normal": [0, 0, 1], "radius": 6,
          "type": "bolted", "bolt": "M6", "grade": "A4-70", "count": 2}]
```
`point` and `radius` are in model units. The section is the part of the plane inside the sphere: make the radius take in just the member being split. The forces through the cut come from the FE model, then the bolts are checked like a bolted joint. Model the flange or boss the bolts go through if there is one; otherwise the bolts are placed in the member's own section, and "don't fit" means it needs a flange.
