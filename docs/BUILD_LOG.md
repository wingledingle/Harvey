# Harvey Avatar — Build Log (for external review / oversight)

Format: `[step] timestamp (UTC) — action — result/evidence`. Every claim here is reproducible
from the scripts in `tools/` and the Godot project in `godot/`.

## Deliverables checklist
- [x] D1 Repo scaffold, MIT license, this log
- [ ] D2 Mesh cleanup + decimation to mobile budget
- [ ] D3 Colorization (reference image projection + hidden-side rules) and face clean-plate
- [ ] D4 Skeleton (Godot Skeleton3D-compatible) + automatic skin weights
- [ ] D5 Procedural face shader (eyes/blink/gaze, brows, talking mouth, blush)
- [ ] D6 Animation library
- [ ] D7 `Avatar.gd` runtime API (states, emotes, lip-sync, look-at)
- [ ] D8 Mobile config (Compatibility renderer, Android export preset) + verification renders
- [ ] D9 Docs + final report

## Log

[D1] 2026-10-08 20:34 — Inspected input `source/fox_raw.glb` — trimesh-generated image-to-3D mesh:
151,734 verts / 303,464 tris, watertight, 1 body, POSITION + indices only (no normals, UVs,
colors, materials). Y-up, faces +Z, ~2.0 units tall, tail toward -Z/+X.
Conclusion: too heavy for a Moto G Play and colorless → must decimate, color, rig, animate.

[D1] 20:36 — Licensing policy. Shipped runtime = Godot 4.3 (MIT) + our scripts/shaders (MIT) +
generated assets. Build-time tools (not shipped): Python stdlib, trimesh (MIT),
fast-simplification (MIT), Pillow (MIT-CMU/HPND), numpy & scipy (BSD-3). Build tools do not
impose license terms on their output; BSD-3 is permissive and commercial-safe. No GPL tool
(e.g. Blender) is used anywhere.

[D1] 20:38 — Aligned mesh front silhouette to `source/fox_reference.jpg` (polynomial background
model → mask → Nelder-Mead over scale/translation). IoU = 0.938 (above feet). Transform:
px = 320.80*x + 248.23, py = -320.80*y + 366.12. Overlay inspected visually: tight fit;
the tail is slightly larger in the mesh than in the image (tail will use rule-based color).

[D1] 20:40 — Verified Godot 4.3 renders headlessly under Xvfb/llvmpipe with the
`gl_compatibility` renderer (same renderer used on device) → screenshot-based verification possible.
