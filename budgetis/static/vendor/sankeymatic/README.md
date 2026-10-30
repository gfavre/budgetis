# SankeyMATIC PNG renderer

Upstream: https://github.com/nowthis/sankeymatic
Pinned revision: `a6d8053e766c45336ec3a0b7fb778d71eef8245c` (2026-07-13).
SankeyMATIC is Copyright Steve Bogart, distributed under the included ISC license.

The build files are copied verbatim except for `index.html`: D3 and Canvg script
URLs point to local, pinned copies; unused images are removed; and the Budgetis
adapter `../../js/sankeymatic-renderer.js` is loaded after the engine.
The Canvg bundle's reference to its unpublished source map is removed so Django's
static-file manifest can process the bundle without a missing-file error.

Dependencies: D3 7.9.0 (ISC), Canvg 3.0.9 (MIT), and upstream's bundled LZ-String
(MIT). Their licenses are included alongside the files. The Canvg bundle includes
its dependencies and notices. Do not run formatters on these third-party files.

The export button lazily creates an offscreen iframe, imports exactly the same
source as the existing text download (including its settings), renders using the
same scaling and offsets as SankeyMATIC's Huge 6x PNG export, downloads a Blob,
and removes the iframe. With the current 1200 x 1020 settings the result is
7200 x 6120 pixels. No accounts or settings are written and no diagram data is
sent to SankeyMATIC or any external service.
