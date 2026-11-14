---
title: AmesWeb, Metric Tap Drill Chart (coarse thread)
url: https://amesweb.info/Screws/metric-tap-drill-chart.aspx
retrieved: 2026-11-11
license: own-summary
subject: metric-tapped-holes
aliases:
- metric tap drill
- coarse metric threads
- internal thread minor diameter
---

## Tap drill versus finished minor diameter
<!-- keys: tap drill, pilot hole, internal thread, minor diameter, 6H, coarse pitch -->
The chart separates drill size from the minimum and maximum internal-thread minor diameters. The drill size is a preparation dimension; it is not the same quantity as the finished minor-diameter range.

The existing table uses the coarse-thread rows and the class 6H upper limit with the listed common lower limit. Fine-pitch, roll-form tapping and insert preparation require their own evidence.

## M2 tapped holes
<!-- keys: M2 tap drill, M2 tapped hole, M2 thread, minor diameter, pitch -->
Exact fastener-table key: `M2`, tapped group. The source coarse-thread row is "M2 x 0.4 2 0.4 1.657 1.679 - 1.567 1.60". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M3 tapped holes
<!-- keys: M3 tap drill, M3 tapped hole, M3 thread, minor diameter, pitch -->
Exact fastener-table key: `M3`, tapped group. The source coarse-thread row is "M3 x 0.5 3 0.5 2.571 2.599 2.639 2.459 2.50". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M4 tapped holes
<!-- keys: M4 tap drill, M4 tapped hole, M4 thread, minor diameter, pitch -->
Exact fastener-table key: `M4`, tapped group. The source coarse-thread row is "M4 x 0.7 4 0.7 3.382 3.422 3.466 3.242 3.30". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M5 tapped holes
<!-- keys: M5 tap drill, M5 tapped hole, M5 thread, minor diameter, pitch -->
Exact fastener-table key: `M5`, tapped group. The source coarse-thread row is "M5 x 0.8 5 0.8 4.294 4.334 4.384 4.134 4.20". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M6 tapped holes
<!-- keys: M6 tap drill, M6 tapped hole, M6 thread, minor diameter, pitch -->
Exact fastener-table key: `M6`, tapped group. The source coarse-thread row is "M6 x 1 6 1 5.107 5.153 5.217 4.917 5.00". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M8 tapped holes
<!-- keys: M8 tap drill, M8 tapped hole, M8 thread, minor diameter, pitch -->
Exact fastener-table key: `M8`, tapped group. The source coarse-thread row is "M8 x 1.25 8 1.25 6.859 6.912 6.982 6.647 6.80". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M10 tapped holes
<!-- keys: M10 tap drill, M10 tapped hole, M10 thread, minor diameter, pitch -->
Exact fastener-table key: `M10`, tapped group. The source coarse-thread row is "M10 x 1.5 10 1.5 8.612 8.676 8.751 8.376 8.50". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## M12 tapped holes
<!-- keys: M12 tap drill, M12 tapped hole, M12 thread, minor diameter, pitch -->
Exact fastener-table key: `M12`, tapped group. The source coarse-thread row is "M12 x 1.75 12 1.75 10.371 10.441 10.531 10.106 10.20". Its columns are tap designation, basic major diameter, pitch, class 5H maximum, class 6H maximum, class 7H maximum, common minimum minor diameter, and drill size, with dimensions in millimetres. A dash means the source supplies no value in that column.

The product table takes its minor-diameter maximum from 6H and keeps the tap-drill diameter as a separate field.

## What the CAD holes check establishes
<!-- keys: holes check, limitations, thread strength, engagement -->
Product integration note: the holes check measures round-hole diameters and count. The requirement selects the exact fastener-table key and intended fit. Diameter evidence alone does not establish thread engagement, preload, stripping strength or a manufactured thread profile. Non-round openings may leave the result unknown.

See the [product check contract](https://github.com/laminarityai/cad/blob/HEAD/SPEC.md) for the application behavior; the dimensional source above is not a description of the CAD implementation.
