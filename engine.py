"""
SDXL generation engine for Retro Pop - Generator.

Holds one pipeline in memory, swaps style adapters per request, and optionally
remaps the result onto a fixed palette. Tuned for a 4 GB card via sequential
CPU offload.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import transformers.utils.generic as _tg

# A broken mlx install on Linux makes transformers raise inside is_tensor().
_tg.is_mlx_available = lambda: False

import numpy as np
import torch
from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLPipeline
from PIL import Image

from palettes import palette_rgb

BASE_MODEL = os.environ.get("LIDO_BASE", "stabilityai/stable-diffusion-xl-base-1.0")

STYLES: dict[str, dict[str, str]] = {
    "none": {"label": "None (prompt only)", "repo": "", "file": "", "prefix": ""},
    "kappa": {
        "label": "KappaNeuro (stable colour)",
        "repo": "KappaNeuro/hiroshi-nagai-style",
        "file": "Hiroshi Nagai Style.safetensors",
        "prefix": "Hiroshi Nagai Style - ",
    },
    "ksenii": {
        "label": "kseniiaNov (stronger drawing)",
        "repo": "kseniiaNov/hiroshi_nagai_style_LoRA",
        "file": "pytorch_lora_weights.safetensors",
        "prefix": "Hiroshi Nagai style, ",
    },
}

DEFAULT_NEGATIVE = (
    "photo, photorealistic, 3d render, blurry, text, watermark, signature, "
    "people, faces, black outlines, comic line art, cluttered, low quality"
)

SIZES: dict[str, tuple[int, int]] = {
    "square": (768, 768),
    "landscape": (960, 640),
    "portrait": (640, 960),
    "wide": (1024, 576),
}

_LOCK = threading.Lock()
_PIPE = None
_LOADED: set[str] = set()


@dataclass
class Request:
    prompt: str
    negative: str = DEFAULT_NEGATIVE
    style: str = "ksenii"
    style_weight: float = 0.35
    steps: int = 24
    guidance: float = 6.0
    size: str = "square"
    seed: int = -1
    palette: str = "none"
    palette_strength: float = 0.7


@dataclass
class Job:
    id: str
    request: Request
    status: str = "queued"
    step: int = 0
    total: int = 0
    error: str = ""
    filename: str = ""
    seconds: float = 0.0
    created: float = field(default_factory=time.time)


def _build():
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    pipe = StableDiffusionXLPipeline.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config, algorithm_type="dpmsolver++", use_karras_sigmas=True
    )
    pipe.set_progress_bar_config(disable=True)
    pipe.enable_attention_slicing()
    pipe.enable_sequential_cpu_offload()
    _PIPE = pipe
    return pipe


def warm() -> None:
    with _LOCK:
        _build()


def _ensure_adapter(pipe, style: str) -> None:
    spec = STYLES[style]
    if not spec["repo"] or style in _LOADED:
        return
    pipe.load_lora_weights(spec["repo"], weight_name=spec["file"], adapter_name=style)
    _LOADED.add(style)


_M_RGB2XYZ = np.array(
    [[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]],
    dtype=np.float32,
)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ).astype(np.float32)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    v = rgb / 255.0
    lin = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M_RGB2XYZ.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.stack(
        [116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]), 200.0 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f**3 > 0.008856, f**3, (f - 16.0 / 116.0) / 7.787) * _WHITE
    lin = xyz @ _M_XYZ2RGB.T
    lin = np.clip(lin, 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255)


def quantize(image: Image.Image, palette: str, strength: float) -> Image.Image:
    """
    Pull a generation onto a palette in two stages.

    Nearest neighbour alone cannot fix a hue drift: the closest entry to a
    magenta sky is a pink, never a blue. So the chroma channels are first
    matched to the palette's own statistics in Lab, which rotates the whole
    image toward the target hue family, and only then are pixels snapped.
    """
    colours = np.array(palette_rgb(palette), dtype=np.float32)
    source = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w, _ = source.shape

    src_lab = _rgb_to_lab(source.reshape(-1, 3))
    pal_lab = _rgb_to_lab(colours)

    shifted = src_lab.copy()
    for c in (1, 2):
        s_mean, s_std = src_lab[:, c].mean(), src_lab[:, c].std() + 1e-5
        p_mean, p_std = pal_lab[:, c].mean(), pal_lab[:, c].std()
        shifted[:, c] = (src_lab[:, c] - s_mean) * (p_std / s_std) + p_mean

    l_mean, l_std = src_lab[:, 0].mean(), src_lab[:, 0].std() + 1e-5
    pl_mean, pl_std = pal_lab[:, 0].mean(), pal_lab[:, 0].std()
    shifted[:, 0] = (src_lab[:, 0] - l_mean) * (0.5 + 0.5 * pl_std / l_std) + (
        0.35 * pl_mean + 0.65 * l_mean
    )

    transferred = _lab_to_rgb(shifted)

    snapped = np.empty_like(transferred)
    chunk = 200_000
    for start in range(0, transferred.shape[0], chunk):
        block = transferred[start : start + chunk]
        d = ((block[:, None, :] - colours[None, :, :]) ** 2).sum(axis=2)
        snapped[start : start + chunk] = colours[d.argmin(axis=1)]

    blended = transferred * (1.0 - strength) + snapped * strength
    original = source.reshape(-1, 3)
    mixed = original * (1.0 - min(1.0, strength + 0.25)) + blended * min(1.0, strength + 0.25)
    return Image.fromarray(mixed.reshape(h, w, 3).clip(0, 255).astype(np.uint8))


def generate(req: Request, out_dir: str, on_step: Callable[[int, int], None] | None = None):
    with _LOCK:
        pipe = _build()
        _ensure_adapter(pipe, req.style)

        if STYLES[req.style]["repo"]:
            pipe.set_adapters([req.style], adapter_weights=[req.style_weight])
        elif _LOADED:
            pipe.set_adapters(list(_LOADED), adapter_weights=[0.0] * len(_LOADED))

        width, height = SIZES.get(req.size, SIZES["square"])
        seed = req.seed if req.seed >= 0 else int.from_bytes(os.urandom(4), "big") % (2**31)
        prompt = STYLES[req.style]["prefix"] + req.prompt

        def callback(_pipe, step, _timestep, kwargs):
            if on_step:
                on_step(step + 1, req.steps)
            return kwargs

        started = time.time()
        image = pipe(
            prompt=prompt,
            negative_prompt=req.negative,
            num_inference_steps=req.steps,
            guidance_scale=req.guidance,
            width=width,
            height=height,
            generator=torch.Generator("cpu").manual_seed(seed),
            callback_on_step_end=callback,
        ).images[0]
        took = time.time() - started

        if req.palette != "none":
            image = quantize(image, req.palette, req.palette_strength)

        os.makedirs(out_dir, exist_ok=True)
        name = f"{int(time.time() * 1000)}-{seed}.png"
        image.save(os.path.join(out_dir, name))
        return name, seed, round(took, 1), width, height
