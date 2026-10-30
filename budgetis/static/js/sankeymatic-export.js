const EXPORT_SCALE = 6;
const RENDERER_TIMEOUT_MS = 30000;
const BLOB_LIFETIME_MS = 30000;

function loadRenderer(frame, url) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("SankeyMATIC renderer timed out")), RENDERER_TIMEOUT_MS);
    frame.onload = () => {
      clearTimeout(timer);
      if (typeof frame.contentWindow?.renderSankeymaticPNG !== "function") {
        reject(new Error("SankeyMATIC renderer unavailable"));
        return;
      }
      resolve(frame.contentWindow);
    };
    frame.onerror = () => {
      clearTimeout(timer);
      reject(new Error("SankeyMATIC renderer failed to load"));
    };
    frame.src = url;
    document.body.append(frame);
  });
}

function downloadImage(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), BLOB_LIFETIME_MS);
}

const button = document.getElementById("sm-export-png");
const status = document.getElementById("sm-export-status");

button?.addEventListener("click", async () => {
  if (button.disabled) return;
  const year = document.getElementById("year").value;
  const isBudget = document.getElementById("is_budget").checked;
  if (!year) {
    status.textContent = button.dataset.noData;
    return;
  }

  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  status.textContent = button.dataset.loading;
  const frame = document.createElement("iframe");
  frame.className = "sankeymatic-renderer";
  frame.setAttribute("aria-hidden", "true");
  frame.tabIndex = -1;
  frame.title = "SankeyMATIC";

  try {
    const params = new URLSearchParams({ year, budget: isBudget });
    const response = await fetch(`${button.dataset.exportUrl}?${params}`, {
      headers: { "X-Requested-With": "fetch" },
    });
    if (!response.ok || !response.headers.get("Content-Type")?.startsWith("text/plain")) {
      throw new Error("SankeyMATIC source unavailable");
    }
    const source = await response.text();
    // Do not export the renderer's sample diagram when this selection has no flows.
    if (!/^.+ \[[1-9]\d*\] .+$/m.test(source)) {
      status.textContent = button.dataset.noData;
      return;
    }

    const renderer = await loadRenderer(frame, button.dataset.rendererUrl);
    const { blob, width, height } = await renderer.renderSankeymaticPNG(source, EXPORT_SCALE);
    const kind = isBudget ? "budget" : "comptes";
    downloadImage(blob, `sankeymatic_${kind}_${year}_${width}x${height}.png`);
    status.textContent = "";
  } catch (error) {
    console.error("SankeyMATIC PNG export failed", error);
    status.textContent = button.dataset.error;
  } finally {
    frame.remove();
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
});
