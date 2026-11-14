---
title: "Printed polymer behavior: process, orientation and test evidence"
url: https://nvlpubs.nist.gov/nistpubs/ir/2015/NIST.IR.8059.pdf
retrieved: 2026-11-12
license: own-summary
subject: printed-part-behavior
aliases:
- "printed part behavior"
- "FDM anisotropy"
- "FFF layer bonding"
- "additive manufacturing properties"
---

## Printed specimens and bulk resin
<!-- keys: injection molded data, bulk polymer, printed coupon, process history -->
NIST's review explains why conventional polymer tests need careful application to additive manufacturing. Identify whether a datasheet describes feedstock, a molded specimen, or a printed specimen. A shared polymer name does not establish the properties of a finished printed part.

Source: NIST IR 8059, Materials Testing Standards for Additive Manufacturing of Polymer Materials. This historical testing review is not a current printer capability specification.

## Build orientation and layer bonding
<!-- keys: Z strength, XY strength, anisotropy, raster direction, layer adhesion -->
For material-extrusion prints, build orientation and deposited-road arrangement affect the loading path and response. Preserve the specimen orientation with a reported property. Rotating a part changes how its layers relate to the applied load; a favorable coupon result does not establish strength in every direction.

Source: NIST IR 8059, discussion of fused deposition modeling and mechanical testing.

## Process settings conditioning and post-processing
<!-- keys: layer height, infill, perimeters, drying, annealing, resin post cure -->
Keep the printer process, material preparation, build settings and post-processing with the test evidence. Internal structure and bonding can make a finished print differ from a nominal solid model. Do not assign one correction factor to every print of a material family.

Source: NIST IR 8059. For resin-specific washing and post-curing instructions, consult the actual manufacturer's material documentation; the existing [Clear Resin entry](formlabs-clear-resin-v5.md) identifies one product's evidence.

## Material selection and limits of a geometry check
<!-- keys: PLA, PETG, ABS, ASA, TPU, PC, printability, minimum wall -->
Prusa's material guide distinguishes printing requirements and service-related properties across filament families. Treat these as selection guidance for the stated materials and equipment, then consult the selected product's datasheet.

Supplemental source: [Prusa filament material guide](https://help.prusa3d.com/filament-material-guide).

Catalog policy: a closed solid or measured wall thickness does not establish layer bonding, support removal, or manufacturing capability. Keep those concerns explicit when no check covers them. See [polymer service conditions](polymer-service-conditions.md).
