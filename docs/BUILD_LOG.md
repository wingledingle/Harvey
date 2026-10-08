# Harvey Avatar — Build Log (for external review / oversight)

Format: `[step] timestamp (UTC) — action — result/evidence`. Every claim here is reproducible
from the scripts in `tools/` and the Godot project in `godot/`.

## Deliverables checklist
- [x] D1 Repo scaffold, MIT license, this log
- [x] D2 Mesh cleanup + decimation to mobile budget
- [x] D3 Colorization (reference image projection + hidden-side rules) and face clean-plate
- [x] D4 Skeleton (Godot Skeleton3D-compatible) + automatic skin weights
- [x] D5 Procedural face shader (eyes/blink/gaze, brows, talking mouth, blush)
- [x] D6 Animation library
- [x] D7 `Avatar.gd` runtime API (states, emotes, lip-sync, look-at)
- [x] D8 Mobile config (Compatibility renderer, Android export preset) + verification renders
- [x] D9 Docs + final report

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

[D2] 20:50 — Decimation with fast-simplification (quadric, MIT) 303,464 → 30,000 tris. After part
separation: 14,990 verts / 29,961 tris. Budget rationale: Moto G Play (Adreno 610/619 or PowerVR
GE8320 depending on year) handles a single 30k-tri GPU-skinned mesh in one draw call comfortably.

[D3] 20:55 — Texture = reference image, background replaced by nearest-character colour
(distance-transform fill), mask clipped to the mesh's own projected silhouette (drops floor shadow).
Eyes, brows and mouth painted out via harmonic (Laplace) inpainting → `harvey_albedo.png`
("clean plate"; procedural features are drawn by the shader). UV = front projection with the fitted
transform. Front visibility from a 2× z-buffer + normal ramp → per-vertex blend weight in COLOR.a.
Hidden surfaces: rule colours (back of head/ears orange, jacket back, sleeves/paws, trousers/shoes,
tail orange→cream tip) + harmonic diffusion on the mesh graph for everything else.
Bug found+fixed: first mask cut at a fixed row removed the shoes (would be painted orange).

[D4] 21:05 — Skeleton: 26 bones (root, hips, spine, chest, neck, head, ear/ear_tip ×2,
upper_arm/forearm/hand ×2, thigh/shin/foot ×2, tail.1–4; tail centreline auto-fitted from slices).
All rest rotations identity (world-aligned) → animation Euler angles are world-axis intuitive.
Labels: nearest bone segment minus 0.5×bone radius, with anatomical gating, largest-island cleanup.
Weights: label diffusion (24 iters) restricted to edges between related (parent/child) bones; top-4.
Bug found+fixed: plain nearest-segment let tail bones claim the lower back (fat torso) → radius-aware
distance + stricter tail gate.

[D4] 21:15 — MAJOR ISSUE: scan fuses arms to the jacket along their full length (and paw↔hip,
thigh↔thigh, tail↔leg). Raising an arm dragged a sheet of torso with it (see preview renders).
Fix: `cut_webs` deletes the 402 faces bridging unrelated parts (keeps shoulder cap above the
armpit, neck, hips, tail root), then each opened rim loop is closed per body part with a
minimum-area (Liepa-style DP) triangulation using that part's rim vertices in loop order.
Iterations: centroid fans → starburst artifacts; per-group open runs → zero-area slivers (window
through torso in arms-up pose); final per-part cyclic polygons → closed. Residual: 36 open
half-edges (tiny slits where 3 parts meet near the hip) — cosmetic, only visible in extreme poses.

[D4] 21:40 — Revised separation: bridging faces are no longer deleted (that left see-through
slits at rest) but re-owned by one part (priority torso > legs > head > tail > arms); the other
part's rim vertices are duplicated. Caps get their own vertex copies with rim weights copied
(no cracks) and plain vertex colour (no projected texture on caps).
Bug found+fixed: cap islands made the harmonic colour solve singular → NaN → black smudges in
renders. Caps are now pinned; asserts added for non-finite colours/weights.

[D5] 21:30 — `harvey_face.gdshader`: analytic eyes (sclera, iris gradient, pupil dilation,
2 highlights + emission, outline, upper-lid blink, happy-eye arcs, wink, wide), Bezier brows
(raise / inner / asymmetry), mouth (smile curve, opening, "oo"/"ee" width, tongue), blush, rim.
Feature mask in UV2 (front half of head) — first version used COLOR.a and dropped the upward-
facing brow ridge (broken brows in renders) → fixed.

[D6] 21:35 — 11 clips at 30 fps, every bone keyed: idle, listen, think, talk, happy, sad (loops);
wave, nod, shake, surprised, celebrate (one-shots). Think pose paw-to-chin angles solved with
Nelder-Mead IK (tip error < 2 mm, elbow constrained outside torso).

[D7] 21:35 — `avatar.gd` (HarveyAvatar): states, emotes w/ auto-return, expression presets with
smooth blending, natural blinks (incl. random double blinks), saccades, idle glances, camera
attention while listening/talking, look-at via custom `SkeletonModifier3D`, lip-sync from audio
(spectrum analyser on a dedicated bus), from text (syllable timeline), or external visemes.

[D8] 21:50 — Godot project: GL Compatibility renderer, portrait 720×1280, ETC2/ASTC, Android
arm64 preset. Verification: 17 screenshots rendered by Godot 4.3 itself (Xvfb + Mesa llvmpipe,
same GLES3 path) → `previews/`. Scripts parse/compile with no errors. FPS shown in renders
(15–19) is CPU software rendering in the container, NOT phone performance.
Not verified: on-device FPS (no physical device available) and audio lip-sync with real audio
(dummy audio driver in container; code path is standard AudioEffectSpectrumAnalyzer).

[D9] 21:55 — README with API, run/export steps, licensing and known limitations.
