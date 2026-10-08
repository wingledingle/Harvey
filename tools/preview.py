"""Build-time preview: renders the built avatar (texture/vertex-colour blend, bone segmentation, or a
skinned animation frame) with the numpy rasterizer. Usage:
  python3 tools/preview.py colors|bones|anim:<name>:<time> out.png"""
import json, os, sys
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from render import rasterize
import animations

ROOT = os.path.dirname(HERE)
c = np.load(os.path.join(HERE, ".cache_build.npz"))
bones = json.load(open(os.path.join(HERE, ".cache_bones.json")))["bones"]
V, F, uv, rgba, J, Wt, lab = c["V"], c["F"], c["uv"], c["rgba"], c["joints"], c["weights"], c["lab"]
tex = np.asarray(Image.open(os.path.join(ROOT, "godot/avatar/harvey_albedo.png")).convert("RGB")) / 255.0


def lin2srgb(x):
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.clip(x, 0, 1), 1 / 2.4) - 0.055)


def colors():
    H, W, _ = tex.shape
    px = np.clip((uv[:, 0] * W).astype(int), 0, W - 1); py = np.clip((uv[:, 1] * H).astype(int), 0, H - 1)
    t = tex[py, px]
    w = rgba[:, 3:4]
    return lin2srgb(rgba[:, :3]) * (1 - w) + t * w


def skin(name, time):
    fn = {a[0]: a[1] for a in animations.ANIMS}[name]
    p, tr = fn(time)
    names = [b[0] for b in bones]
    heads = {b[0]: np.array(b[2]) for b in bones}
    par = {b[0]: b[1] for b in bones}
    G = {}
    for nm in names:  # parents precede children in the list
        R = Rotation.from_euler("xyz", p.get(nm, np.zeros(3)), degrees=True).as_matrix()
        loc = np.eye(4); loc[:3, :3] = R
        loc[:3, 3] = heads[nm] - (heads[par[nm]] if par[nm] else 0) + tr.get(nm, 0)
        G[nm] = (G[par[nm]] @ loc) if par[nm] else loc
    M = np.stack([G[nm] @ np.block([[np.eye(3), -heads[nm][:, None]], [np.zeros((1, 3)), 1]]) for nm in names])
    Vh = np.c_[V, np.ones(len(V))]
    out = np.zeros_like(V)
    for k in range(4):
        out += Wt[:, k:k + 1] * np.einsum("nij,nj->ni", M[J[:, k]], Vh)[:, :3]
    return out


mode, out = sys.argv[1], sys.argv[2]
Vr = V
if mode == "bones":
    rng = np.random.default_rng(3)
    pal = rng.uniform(0.2, 1, (len(bones), 3))
    col = (Wt[:, :, None] * pal[J]).sum(1)
else:
    col = colors()
    if mode.startswith("anim:"):
        _, nm, tm = mode.split(":")
        Vr = skin(nm, float(tm))
views = sys.argv[3].split(",") if len(sys.argv) > 3 else ["front", "right", "back"]
bounds = (np.array([0.0, -0.05]), 2.2)
imgs = [rasterize(Vr, F, v, 420, colors=col, bounds=bounds)[0] for v in views]
Image.fromarray((np.clip(np.concatenate(imgs, 1), 0, 1) * 255).astype(np.uint8)).save(out)
