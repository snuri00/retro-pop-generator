const $ = (id) => document.getElementById(id);

const els = {
  status: $("status"),
  prompt: $("prompt"),
  negative: $("negative"),
  style: $("style"),
  weight: $("weight"),
  weightVal: $("weightVal"),
  weightRow: $("weightRow"),
  size: $("size"),
  steps: $("steps"),
  stepsVal: $("stepsVal"),
  guidance: $("guidance"),
  guidanceVal: $("guidanceVal"),
  palette: $("palette"),
  paletteRow: $("paletteRow"),
  pstrength: $("pstrength"),
  pstrengthVal: $("pstrengthVal"),
  pixelate: $("pixelate"),
  pixelColors: $("pixelColors"),
  pixelColorsVal: $("pixelColorsVal"),
  pixelColorsRow: $("pixelColorsRow"),
  seed: $("seed"),
  randomSeed: $("randomSeed"),
  go: $("go"),
  result: $("result"),
  placeholder: $("placeholder"),
  progress: $("progress"),
  progressText: $("progressText"),
  bar: document.querySelector(".bar i"),
  gallery: $("gallery"),
  galleryEmpty: $("galleryEmpty"),
};

const SIZE_LABELS = {
  square: "Square 768 × 768",
  landscape: "Landscape 960 × 640",
  portrait: "Portrait 640 × 960",
  wide: "Wide 1024 × 576",
};

const PALETTE_LABELS = {
  none: "Off",
  noon: "Noon",
  golden: "Golden hour",
  sunset: "Sunset",
  dusk: "Dusk",
};

let polling = null;
let ready = false;
let styleNegatives = {};

const bind = (range, out, digits) => {
  const sync = () => {
    out.textContent = Number(range.value).toFixed(digits);
  };
  range.addEventListener("input", sync);
  sync();
};

bind(els.weight, els.weightVal, 2);
bind(els.steps, els.stepsVal, 0);
bind(els.guidance, els.guidanceVal, 1);
bind(els.pstrength, els.pstrengthVal, 2);
bind(els.pixelColors, els.pixelColorsVal, 0);

els.pixelate.addEventListener("change", () => {
  els.pixelColorsRow.hidden = els.pixelate.value === "0";
});

const refreshGo = () => {
  els.go.disabled = !ready || els.prompt.value.trim().length === 0;
};

els.prompt.addEventListener("input", refreshGo);

const setRange = (el, value) => {
  if (typeof value !== "number") return;
  el.value = String(value);
  el.dispatchEvent(new Event("input"));
};

const applyPreset = (id) => {
  const spec = styleNegatives[id];
  if (!spec) return;

  els.weightRow.hidden = !spec.hasLora;
  if (spec.hasLora) setRange(els.weight, spec.weight);
  setRange(els.steps, spec.steps);
  setRange(els.guidance, spec.guidance);
  setRange(els.pixelColors, spec.pixelColors);

  els.pixelate.value = String(spec.pixelateTo ?? 0);
  els.pixelColorsRow.hidden = els.pixelate.value === "0";

  els.palette.value = spec.palette || "none";
  els.paletteRow.hidden = els.palette.value === "none";

  // The negative is typed text, so an edited one is never overwritten.
  const current = els.negative.value.trim();
  const isPreset = Object.values(styleNegatives).some(
    (s) => s.negative && s.negative.trim() === current,
  );
  if (spec.negative && (current === "" || isPreset)) {
    els.negative.value = spec.negative;
  }
};

els.style.addEventListener("change", () => applyPreset(els.style.value));

els.palette.addEventListener("change", () => {
  els.paletteRow.hidden = els.palette.value === "none";
});

els.randomSeed.addEventListener("click", () => {
  els.seed.value = Math.floor(Math.random() * 2147483647);
});

async function boot() {
  const cfg = await fetch("/api/config").then((r) => r.json());

  styleNegatives = Object.fromEntries(
    (cfg.styles || []).map((s) => [
      s.id,
      { ...s, negative: s.negative || "", hasLora: Boolean(s.hasLora) },
    ]),
  );

  if (!els.style.options.length) {
    els.style.innerHTML = cfg.styles
      .map((s) => `<option value="${s.id}">${s.label}</option>`)
      .join("");
    els.style.value = "ksenii";

    els.size.innerHTML = cfg.sizes
      .map((s) => `<option value="${s}">${SIZE_LABELS[s] || s}</option>`)
      .join("");

    els.pixelate.innerHTML = (cfg.pixelSizes || [0])
      .map((p) => `<option value="${p}">${p === 0 ? "Off" : `${p} px tall`}</option>`)
      .join("");

    els.palette.innerHTML = cfg.palettes
      .map((p) => `<option value="${p}">${PALETTE_LABELS[p] || p}</option>`)
      .join("");

    applyPreset("ksenii");
  }

  if (cfg.ready) {
    ready = true;
    els.status.textContent = "ready";
    refreshGo();
  } else {
    els.status.textContent = "loading the model, first run takes a while…";
    setTimeout(boot, 3000);
  }

  loadGallery();
}

async function loadGallery() {
  const items = await fetch("/api/gallery").then((r) => r.json());
  els.galleryEmpty.hidden = items.length > 0;
  els.gallery.innerHTML = items
    .map(
      (i) =>
        `<img src="/out/${i.file}" title="seed ${i.seed} · ${i.seconds}s" data-file="${i.file}" alt="" />`,
    )
    .join("");
  [...els.gallery.querySelectorAll("img")].forEach((img) => {
    img.addEventListener("click", () => show(img.dataset.file));
    img.addEventListener("error", () => {
      img.remove();
      els.galleryEmpty.hidden = els.gallery.children.length > 0;
    });
  });
}

function show(file) {
  els.result.src = `/out/${file}`;
  els.result.hidden = false;
  els.placeholder.hidden = true;
}

els.go.addEventListener("click", async () => {
  els.go.disabled = true;
  els.progress.hidden = false;
  els.progressText.textContent = "queued";
  els.bar.style.width = "0%";

  const body = {
    prompt: els.prompt.value.trim(),
    negative: els.negative.value,
    style: els.style.value,
    style_weight: Number(els.weight.value),
    steps: Number(els.steps.value),
    guidance: Number(els.guidance.value),
    size: els.size.value,
    seed: Number(els.seed.value),
    palette: els.palette.value,
    palette_strength: Number(els.pstrength.value),
    pixelate_to: Number(els.pixelate.value),
    pixel_colors: Number(els.pixelColors.value),
  };

  const { id } = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

  clearInterval(polling);
  polling = setInterval(async () => {
    const job = await fetch(`/api/job/${id}`).then((r) => r.json());

    if (job.status === "running" && job.total) {
      els.bar.style.width = `${(job.step / job.total) * 100}%`;
      els.progressText.textContent = `${job.step} / ${job.total}`;
    }

    if (job.status === "done") {
      clearInterval(polling);
      els.bar.style.width = "100%";
      els.progressText.textContent = `${job.seconds}s`;
      show(job.file);
      refreshGo();
      setTimeout(() => {
        els.progress.hidden = true;
      }, 1400);
      loadGallery();
    }

    if (job.status === "error") {
      clearInterval(polling);
      els.progressText.textContent = job.error;
      refreshGo();
    }
  }, 900);
});

boot();
