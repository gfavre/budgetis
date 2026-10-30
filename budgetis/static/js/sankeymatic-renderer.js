// Adapter for the pinned, unmodified SankeyMATIC engine in its own document.
// Keep the PNG scaling/offsets identical to upstream's scaledPNG(). Await Canvg
// before reading the canvas and return a Blob to avoid a large base64 copy.
window.renderSankeymaticPNG = async (source, scale) => {
  const transfer = new DataTransfer();
  transfer.items.add(new File([source], "diagram.txt", { type: "text/plain" }));
  document.getElementById("load_diagram_from_file").files = transfer.files;
  await window.loadDiagramFile();
  await document.fonts.ready;

  const svg = document.getElementById("sankey_svg");
  if (!svg.querySelector(".node")) throw new Error("SankeyMATIC diagram has no nodes");
  const chart = document.getElementById("chart");
  const width = chart.clientWidth * scale;
  const height = chart.clientHeight * scale;
  const canvas = document.getElementById("png_preview");
  canvas.width = width;
  canvas.height = height;

  const renderer = window.canvg.Canvg.fromString(
    canvas.getContext("2d"),
    new XMLSerializer().serializeToString(svg),
    {
      ignoreMouse: true,
      ignoreAnimation: true,
      ignoreDimensions: true,
      scaleWidth: width,
      scaleHeight: height,
      offsetX: (width - chart.clientWidth) / (2 * scale),
      offsetY: (height - chart.clientHeight) / (2 * scale),
    },
  );
  await renderer.render();
  const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("SankeyMATIC PNG canvas could not be exported");
  return { blob, width, height };
};
