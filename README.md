# Retro Pop - Generator

A local web UI that generates 1980s resort illustration with SDXL, tuned to
run on a 4 GB card.

Type a prompt, pick a few settings, get an image. There is no scene editor and
no composition control: whatever the model draws is the output.

## Running it

```bash
pip install -r requirements.txt
python3 server.py
```

Opens on `http://127.0.0.1:7801`. The first launch downloads SDXL base (~7 GB)
and loads it, which takes a few minutes. After that a 768×768 image at 24 steps
takes about 55 seconds on an RTX 3050 Laptop 4 GB.

## Settings and what they actually do

These defaults were not guessed. They came out of a measured sweep, documented
below.

**Style model.** Three options.

- `none` is prompt only. It already produces credible city pop, because SDXL
  knows the idiom. Use it as the control.
- `kappa` (KappaNeuro/hiroshi-nagai-style) is colour stable. Measured sky red
  channel stays between 9% and 15% across the full weight range.
- `ksenii` (kseniiaNov/hiroshi_nagai_style_LoRA) is the strongest draughtsman of
  the three. Palms, clouds, foliage and water read best. But its sky drifts to
  magenta as weight rises: red channel 23% at 0.35, 30% at 0.70, **75% at 1.0**.

**Style weight.** Defaults to 0.35, which the sweep found to be the sweet spot:
strong enough to shape the drawing, low enough that the sky stays ultramarine.
`ksenii` at 1.0 draws better and colours worse, and the colour cannot be fixed
afterwards, so the low weight wins.

**Palette effect.** Matches the image's Lab chroma statistics to a fixed 26
colour palette (`noon`, `golden`, `sunset`, `dusk`) and then snaps pixels to
the nearest entry. Off by default.

It is a stylistic posterise, **not** a colour repair. This was built to rescue
`ksenii` at full weight, whose sky goes magenta, and it does not work. Plain
nearest neighbour cannot: the closest palette entry to a magenta sky is a pink,
never a blue. Adding the Lab statistics transfer moved the top of the sky to
blue and left the rest dusty pink, with hard banding at the seam. Two attempts,
both failed. The correct fix was in the sweep data all along: generate at
weight 0.35, where the sky is blue to begin with, instead of generating a broken
colour and repairing it. Hence the default.

**Negative prompt.** The single biggest quality lever found during testing.
Without `black outlines, comic line art, cluttered` in the negative, SDXL
produces outlined vector illustration of a cluttered modernist villa. With it,
the output becomes flat airbrushed and calm. The default is prefilled.

**Steps / guidance.** 24 steps and guidance 6.0 with DPM++ 2M Karras. Higher
guidance pushes toward posterised oversaturation.

## What was measured

| model | w=0.35 | w=0.70 | w=1.00 |
|---|---|---|---|
| kappa, sky red channel | 9% | 13% | 15% |
| ksenii, sky red channel | 23% | 30% | 75% |

An earlier sweep reported no difference between weights 0.8 and 1.0. That was a
bug: `fuse_lora(lora_scale=...)` is ignored by this diffusers version, and the
two runs came out byte identical. Adapter weights are the supported path:

```python
pipe.load_lora_weights(repo, weight_name=file, adapter_name=name)
pipe.set_adapters([name], adapter_weights=[w])
```

## Environment note

If `transformers` raises `libmlx.so: cannot open shared object file`, an mlx
package is installed without its native library, which happens on Linux. The
import check passes and the actual import then fails. `engine.py` patches
`is_mlx_available` to return False rather than touching the install, since mlx
may belong to another project on the same machine.

## Layout

```
server.py     FastAPI, single worker thread, job queue
engine.py     SDXL pipeline, adapter swapping, palette quantisation
palettes.py   four 26 colour palettes
static/       the UI
out/          generated images and gallery.json
```

Generation is serialised through one worker because the pipeline is a single
GPU resident object. Requests queue rather than compete.

## Note on the style models

Both adapters were trained on the work of a living, working illustrator. Using
them for private experimentation and study is one thing. Publishing or selling
the output under his name, or as though it were his work, is another.
