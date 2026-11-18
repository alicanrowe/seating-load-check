# Materials

`scripts/materials.json` holds the numbers. Add a material by copying an entry.

## Wood
Clear, straight-grained wood at 12% moisture content, average values after the USDA Forest Products Laboratory *Wood Handbook* (FPL-GTR-282, 2021), Table 5-3: density, E along the grain, modulus of rupture (MOR), compression parallel and perpendicular to the grain, shear parallel, tension perpendicular. Check a value against the Handbook before relying on it for a species you use a lot; the table here was entered by hand.

How the checker uses them:
- **Bending and tension along the grain**: MOR (tension parallel is normally higher than MOR in clear wood, so this is on the safe side).
- **Compression along the grain**: section-average stress against compression parallel, and Euler buckling for struts.
- **Splitting**: the larger principal stress across the grain against tension perpendicular. This is the one that catches a leg mortise split open by a racking stretcher, or a seat pulled apart across its width.
- **Crushing across the grain**: against compression perpendicular, which is a proportional-limit value (it dents a little past it, it doesn't break), so it gets its own lower safety factor (1.25).
- **Shear along the grain** and **rolling shear** (shear across the grain in the cross-grain plane, taken as a quarter of shear parallel).
- Stiffness: transversely isotropic about the grain, E across = 0.075 E, shear modulus 0.07 E along / 0.018 E rolling.

Why 2.5 on wood: these are averages for perfect wood. The 5th percentile board is about three-quarters of the average, and grain slope, small knots and runout take off more. The dynamic and edge loads already carry their own factors.

## Metal
Typical values, not guaranteed minimums unless marked. Printed metal varies with the machine, build direction, heat treatment and surface; when the bureau sends a data sheet, put its yield, tensile and fatigue numbers in. If the process isn't known, `printed stainless` maps to binder-jet 316L, the weaker of the two common processes.

- **Yield**: von Mises stress against yield with a factor of 1.5 on the factored cases.
- **Fatigue**: the everyday sit is a 0-to-peak cycle repeated tens of thousands of times. The allowed peak comes from the Goodman line, 2 / (1/Se + 1/fu), with Se the fully reversed fatigue strength. As-printed surfaces have roughly half the fatigue strength of machined or polished ones; set `"finish": "polished"` on a part only if the highly stressed area really will be.
- Castings: CF8M (cast 316), silicon bronze C87300, 17-4PH H1150 (cast) and H900. Printed: 316L (two processes), Ti-6Al-4V (LPBF, HIPed) and maraging 1.2709 (aged). The high-strength fatigue values are low confidence; get the foundry's or bureau's numbers. 17-4PH H900 is strong but much less tough than H1150.
- Sterling, brass and aluminium are there for small parts; aluminium has no endurance limit and welds drop it to about T4. Sterling is annealed cast (120 MPa yield): a whole seat in sterling needs very heavy sections.
- One material throughout means the stresses don't depend on its stiffness, so a result re-rates to another alloy by the ratio of yields (and fatigue strengths). Only the piece's own weight and the sink change.

## Bolts
Stress areas (ISO 898 / ASME B1.1) and grades: ISO 3506 A2-70 / A4-70 (450 MPa proof, 700 MPa tensile), A2-50, 8.8, SAE grade 5. "18-8" is treated as A2-70; check the bolt's marking.

## Pads
Cushions, leather and foam carry no load in the model and weigh 120 kg/m3 unless the part sets `density`.
