# Examples

The models aren't included (they belong to their projects); the specs show how each piece was described, and the reports show what came back.

## krenov-sawhorse
A Krenov-style sawhorse in yellow poplar with a cushion, 31.5 in to the seat, 2.6 kg, checked for a 113 kg sitter.
- `krenov_sawhorse.seatcheck.json`: rail glued into the leg slots. `krenov_sawhorse_dry_rail.seatcheck.json`: the same rail just dropped in, without glue.
- What it found, at two cell sizes (3.3 mm and 2.9 mm):
  - The edge test tips it (0.72). It's a light piece with the rail running past the feet. Feet out 0.48 in, or the rail ends in 0.5 in.
  - The glue lines at the rail and stretcher are at about 0.85 to 0.95, leaning on end grain. Give them long-grain cheeks or a pin.
  - Splitting across the grain at the slot, mortise and foot corners comes out at 0.33 to 0.52 and drops as the cells get finer. Those are sharp inside corners, so the numbers aren't converged: they show where to look, not how far over. Round the corners, or pin across the grain.
  - With the rail dry, the rail lifts off the far leg when someone sits hard on one end. That's expected, and it's only a warning.

## metal-sawhorse
A metal sawhorse in two builds:
- `rest_printed_bolted_sections.seatcheck.json`: the Rest as binder-jet 316L sections, bolted. Every split is described as a cut with its bolts.
- `*_17-4ph.seatcheck.json`: the same sawhorse cast in 17-4PH H1150 as one piece.
- What it found:
  - Rest: strength margin about 9. The feet have a belly, so it stands on a 2 cm strip and rocks about 5 degrees side to side before the foot ends land. That's a WARN; flatten the feet or add glides. Leaning is right on the line (1.01).
  - Thread r7, with its thin strands: 1.22 in 17-4PH H1150 at 2.2 mm cells, but 0.77 at 2.7 mm. The strands are only about 4 cells across, so the stress hasn't settled. It passes at both sizes only from 17-4PH H900 up. This is the two-cell-size rule doing its job.
