"""Harvey avatar build pipeline.

source/fox_raw.glb + source/fox_reference.jpg  ->  godot/avatar/harvey.glb + harvey_albedo.png

Steps: decimate -> clean-plate texture (face features painted out) -> front-projection UVs ->
front visibility -> vertex colours for hidden surfaces -> skeleton -> skin weights ->
animations (tools/animations.py) -> glTF 2.0 binary.

Build-time only (nothing here ships in the app). Run: python3 tools/build_avatar.py
"""
import json, os, struct, sys
import numpy as np
import trimesh, fast_simplification
from PIL import Image
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from render import zbuffer_screen  # noqa: E402
import animations  # noqa: E402

OUT_DIR = os.path.join(ROOT, "godot", "avatar")
TARGET_TRIS = 30000

# Mesh -> reference-image similarity transform (fitted by silhouette IoU, see docs/BUILD_LOG.md)
ALIGN_SC, ALIGN_TX, ALIGN_TY = 320.80, 248.23, 366.12

# Face features in reference-image pixels. Shared with the shader (godot/avatar/harvey_face.gdshader).
EYES = [((190.0, 237.0), (30.0, 29.0)), ((315.0, 232.0), (31.0, 28.0))]
BROWS = [((165, 196), (187, 168), (207, 174)), ((289, 170), (310, 164), (337, 189))]
MOUTH = ((256.0, 306.0), 60.0, 9.0)  # centre, half width, half height of the paint-out band


def log(*a):
    print("[build]", *a, flush=True)


# ----------------------------------------------------------------------------------------------
# 1. mesh
def load_and_decimate():
    m = trimesh.load(os.path.join(ROOT, "source", "fox_raw.glb"), force="mesh")
    V, F = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32),
                                        target_count=TARGET_TRIS)
    d = trimesh.Trimesh(V, F, process=True)
    d.remove_unreferenced_vertices()
    d.update_faces(d.nondegenerate_faces())
    trimesh.repair.fix_normals(d)
    log(f"decimated {len(m.faces)} -> {len(d.faces)} tris, {len(d.vertices)} verts, watertight={d.is_watertight}")
    return np.asarray(d.vertices, np.float64), np.asarray(d.faces, np.int64), np.asarray(d.vertex_normals, np.float64)


# ----------------------------------------------------------------------------------------------
# 2. texture
def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def harmonic_inpaint(img, hole):
    """Fill `hole` pixels by solving Laplace's equation (smooth membrane) per channel."""
    H, W = hole.shape
    idx = -np.ones((H, W), np.int64)
    ys, xs = np.nonzero(hole)
    idx[ys, xs] = np.arange(len(ys))
    n = len(ys)
    rows, cols, vals = [], [], []
    b = np.zeros((n, img.shape[2]))
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = np.clip(ys + dy, 0, H - 1), np.clip(xs + dx, 0, W - 1)
        nb = idx[ny, nx]
        inside = nb >= 0
        rows += [np.arange(n)[inside]]; cols += [nb[inside]]; vals += [-np.ones(inside.sum())]
        b[~inside] += img[ny[~inside], nx[~inside]]
    A = sparse.csr_matrix((np.concatenate(vals + [np.full(n, 4.0)]),
                           (np.concatenate(rows + [np.arange(n)]), np.concatenate(cols + [np.arange(n)]))), (n, n))
    out = img.copy()
    for ch in range(img.shape[2]):
        out[ys, xs, ch] = spsolve(A, b[:, ch])
    return out


def quad_bezier(p0, p1, p2, n=64):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2 = map(np.asarray, (p0, p1, p2))
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2


def build_texture(V, F):
    im = np.asarray(Image.open(os.path.join(ROOT, "source", "fox_reference.jpg")).convert("RGB")).astype(np.float64) / 255
    H, W, _ = im.shape
    # character mask: smooth polynomial background model
    yy, xx = np.mgrid[0:H, 0:W]
    X, Y = xx / W, yy / H
    basis = lambda X, Y: np.stack([np.ones_like(X), X, Y, X * X, X * Y, Y * Y, X ** 3, Y ** 3, X * X * Y, X * Y * Y], -1)
    bgm = np.zeros((H, W), bool); bgm[:, :25] = 1; bgm[:, -25:] = 1; bgm[:15] = 1
    coef, *_ = np.linalg.lstsq(basis(X[bgm], Y[bgm]), im[bgm], rcond=None)
    mask = np.linalg.norm(im - basis(X, Y) @ coef, axis=2) > 0.1
    mask = ndimage.binary_fill_holes(ndimage.binary_opening(mask, iterations=1))
    lab, n = ndimage.label(mask)
    mask = lab == (np.argmax(ndimage.sum(mask, lab, range(1, n + 1))) + 1)
    # keep only pixels covered by the mesh's own projected silhouette (drops the floor shadow)
    S = np.stack([ALIGN_SC * V[:, 0] + ALIGN_TX, -ALIGN_SC * V[:, 1] + ALIGN_TY, V[:, 2]], 1)
    sil = np.isfinite(zbuffer_screen(S, F, W, H))
    mask &= ndimage.binary_dilation(sil, iterations=3)
    core = ndimage.binary_erosion(mask, iterations=2)  # avoid anti-aliased edge pixels
    # extend character colours outward so silhouette samples never pick up background
    _, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
    tex = im[iy, ix]
    # clean plate: paint out eyes, brows, mouth (they are redrawn procedurally by the shader)
    hole = np.zeros((H, W), bool)
    for (cx, cy), (rx, ry) in EYES:
        hole |= ((xx - cx) / (rx + 5)) ** 2 + ((yy - cy) / (ry + 5)) ** 2 < 1
    for b in BROWS:
        pts = quad_bezier(*b)
        d = np.min(np.hypot(xx[..., None] - pts[:, 0], yy[..., None] - pts[:, 1]), axis=-1)
        hole |= d < 9
    (mx, my), mhw, mhh = MOUTH
    hole |= (np.abs(xx - mx) < mhw) & (np.abs(yy - my - 0.0018 * (xx - mx) ** 2 * -1) < mhh)
    hole |= ((xx - 188) / 16) ** 2 + ((yy - 294) / 9) ** 2 < 1   # mouth-corner shadows
    hole |= ((xx - 320) / 16) ** 2 + ((yy - 288) / 9) ** 2 < 1
    tex = harmonic_inpaint(tex, hole)
    # light blur inside the patch boundary to hide the seam
    soft = ndimage.gaussian_filter(hole.astype(float), 1.5)
    blurred = np.stack([ndimage.gaussian_filter(tex[..., c], 1.2) for c in range(3)], -1)
    tex = tex * (1 - soft[..., None]) + blurred * soft[..., None]
    Image.fromarray((np.clip(tex, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT_DIR, "harvey_albedo.png"))
    log(f"texture {W}x{H}, painted out {hole.sum()} face-feature pixels")
    return tex, mask, (W, H)


def sample(tex, px, py):
    H, W, _ = tex.shape
    px = np.clip(px - 0.5, 0, W - 1.001); py = np.clip(py - 0.5, 0, H - 1.001)
    x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
    fx, fy = (px - x0)[:, None], (py - y0)[:, None]
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x0 + 1] * fx * (1 - fy)
            + tex[y0 + 1, x0] * (1 - fx) * fy + tex[y0 + 1, x0 + 1] * fx * fy)


# ----------------------------------------------------------------------------------------------
# 3. skeleton.  All bones have identity rest rotation (world-aligned axes) so that animation
# rotations are expressed directly in world axes: +X pitch = lean/nod forward, +Y = turn to the
# character's left, +Z = roll toward the character's right.  Character left = +X ("L").
def tail_chain(V):
    x, y, z = V.T
    pts = []
    for zz in (-0.06, -0.24, -0.42, -0.60, -0.78):
        m = (np.abs(z - zz) < 0.04) & (y < -0.25) & (y > -0.88) & (x > -0.08)
        pts.append([x[m].mean(), y[m].mean(), zz])
    pts = np.array(pts)
    pts[0] = [0.04, -0.60, -0.02]
    tip = pts[-1] + (pts[-1] - pts[-2]) * 0.6
    return pts, tip


def build_skeleton(V):
    tp, ttip = tail_chain(V)
    B = []  # (name, parent, head, tail)

    def add(name, parent, head, tail):
        B.append((name, parent, np.array(head, float), np.array(tail, float)))

    add("root", None, (0, -1.0, 0.17), (0, -0.62, 0.18))
    add("hips", "root", (0, -0.60, 0.18), (0, -0.44, 0.19))
    add("spine", "hips", (0, -0.44, 0.19), (0, -0.25, 0.19))
    add("chest", "spine", (0, -0.25, 0.19), (0, -0.06, 0.18))
    add("neck", "chest", (0, -0.06, 0.18), (0, 0.0, 0.17))
    add("head", "neck", (0, 0.0, 0.17), (0, 0.70, 0.15))
    for s, sx in (("L", 1), ("R", -1)):
        add(f"ear.{s}", "head", (0.29 * sx, 0.50, 0.20), (0.33 * sx, 0.72, 0.20))
        add(f"ear_tip.{s}", f"ear.{s}", (0.33 * sx, 0.72, 0.20), (0.39 * sx, 0.99, 0.24))
        add(f"upper_arm.{s}", "chest", (0.26 * sx, -0.09, 0.18), (0.37 * sx, -0.34, 0.20))
        add(f"forearm.{s}", f"upper_arm.{s}", (0.37 * sx, -0.34, 0.20), (0.345 * sx, -0.47, 0.24))
        add(f"hand.{s}", f"forearm.{s}", (0.345 * sx, -0.47, 0.24), (0.31 * sx, -0.62, 0.25))
        add(f"thigh.{s}", "hips", (0.13 * sx, -0.64, 0.17), (0.13 * sx, -0.78, 0.19))
        add(f"shin.{s}", f"thigh.{s}", (0.13 * sx, -0.78, 0.19), (0.15 * sx, -0.90, 0.17))
        add(f"foot.{s}", f"shin.{s}", (0.15 * sx, -0.90, 0.17), (0.18 * sx, -0.97, 0.32))
    for i in range(4):
        add(f"tail.{i + 1}", "hips" if i == 0 else f"tail.{i}", tp[i], tp[i + 1] if i < 3 else ttip)
    return B


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1), t


RADIUS = {"hips": 0.24, "spine": 0.24, "chest": 0.24, "neck": 0.2, "head": 0.45, "ear": 0.1, "ear_tip": 0.08,
          "upper_arm": 0.08, "forearm": 0.08, "hand": 0.08, "thigh": 0.1, "shin": 0.09, "foot": 0.08,
          "tail.1": 0.08, "tail.2": 0.12, "tail.3": 0.18, "tail.4": 0.2}
GROUP = lambda nm: ("torso" if nm in ("hips", "spine", "chest", "neck") else "head" if nm == "head" or nm.startswith("ear")
                    else "tail" if nm.startswith("tail") else ("arm" if nm.split(".")[0] in ("upper_arm", "forearm", "hand")
                    else "leg") + nm[-2:])


def compute_labels(V, F, B):
    x, y, z = V.T
    names = [b[0] for b in B]
    parent = {b[0]: b[1] for b in B}
    nb = len(B)
    D = np.full((len(V), nb), np.inf)
    T = np.zeros((len(V), nb))
    for j, (name, par, h, t) in enumerate(B):
        if name == "root":
            continue
        d, tt = seg_dist(V, h, t)
        d = d - 0.5 * RADIUS.get(name, RADIUS.get(name.split(".")[0], 0.1))
        side = 1 if name.endswith(".L") else -1 if name.endswith(".R") else 0
        if name in ("hips", "spine", "chest"):
            g = (np.abs(x) < 0.31) & (y < 0.02) & (z > -0.14) & (y > -0.70)
        elif name == "neck":
            g = (y > -0.16) & (y < 0.02) & (np.abs(x) < 0.27)
        elif name == "head":
            g = y > -0.03
        elif name.startswith("ear"):
            g = (y > 0.44) & (x * side > 0.11)
        elif name.startswith(("upper_arm", "forearm", "hand")):
            g = (x * side > 0.245) & (y < -0.0) & (y > -0.70) & (z > -0.06)
        elif name.startswith(("thigh", "shin", "foot")):
            g = (y < -0.58) & (x * side > -0.02) & (z > -0.13)
        elif name.startswith("tail"):
            g = ((z < -0.2) & (y < -0.25)) | ((z < -0.06) & (y < -0.45) & (y > -0.75))
        else:
            g = np.ones(len(V), bool)
        D[g, j] = d[g]; T[:, j] = tt
    lab = np.argmin(D, axis=1)
    lab[np.isinf(D.min(1))] = names.index("hips")

    # mesh graph
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    E = np.unique(np.sort(E, axis=1), axis=0)
    n = len(V)

    # connected-component cleanup: every bone keeps only its largest island
    for j in range(nb):
        m = lab == j
        if not m.any():
            continue
        e = E[m[E[:, 0]] & m[E[:, 1]]]
        G = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n))
        _, comp = sparse.csgraph.connected_components(G, directed=False)
        cs = comp[m]
        keep = np.bincount(cs).argmax()
        orphan = np.nonzero(m)[0][cs != keep]
        lab[orphan] = -1
    for _ in range(200):  # reassign orphans to the majority label of their neighbours
        orph = lab < 0
        if not orph.any():
            break
        a, b = E[:, 0], E[:, 1]
        for u, v in ((a, b), (b, a)):
            s = orph[u] & ~orph[v]
            lab[u[s]] = lab[v[s]]
    counts = np.bincount(lab, minlength=nb)
    log("vertices per bone: " + ", ".join(f"{names[j]}={counts[j]}" for j in range(nb)))
    return lab


def mesh_edges(F):
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    return np.unique(np.sort(E, axis=1), axis=0)


def cut_webs(V, F, N, lab, B):
    """The scan fuses parts that merely touch (arm against jacket, paw on hip, thigh against thigh).
    Delete faces bridging unrelated body groups, keep the real joins (shoulder, neck, hip, tail base),
    then cap each opened hole per group so every part stays closed when it moves away."""
    names = [b[0] for b in B]
    grp = np.array([GROUP(n) for n in names])[lab]
    y = V[:, 1]
    fg = grp[F]
    bridge = ~((fg[:, 0] == fg[:, 1]) & (fg[:, 1] == fg[:, 2]))
    # legitimate joins that must stay connected
    legit = np.zeros(len(F), bool)
    gs = [set(r) for r in fg]
    fy = y[F].mean(1)
    for i in np.nonzero(bridge)[0]:
        g = gs[i]
        if g <= {"torso", "head"}:
            legit[i] = True  # neck: head<->torso are joined through the neck bone
        elif g <= {"torso", "arm.L"} or g <= {"torso", "arm.R"}:
            legit[i] = fy[i] > -0.17  # shoulder cap only; below the armpit the arm just touches the jacket
        elif g <= {"torso", "leg.L"} or g <= {"torso", "leg.R"}:
            legit[i] = True
        elif g <= {"torso", "tail"}:
            legit[i] = np.linalg.norm(V[F[i]].mean(0) - np.array([0.04, -0.6, -0.04])) < 0.16
    cut = bridge & ~legit
    nv0 = len(V)
    keep = ~cut
    F2 = F[keep]
    log(f"cut {cut.sum()} bridging faces between touching parts")
    # Cap every opened hole: walk each rim loop, and for every body part on that rim fill the polygon
    # made of that part's rim vertices (in loop order) with a minimum-area triangulation.
    he = np.concatenate([F2[:, [0, 1]], F2[:, [1, 2]], F2[:, [2, 0]]])
    key = he[:, 0] * len(V) + he[:, 1]
    rkey = he[:, 1] * len(V) + he[:, 0]
    bnd = he[~np.isin(key, rkey)]
    Vn, Nn, labn, Fn = [V], [N], [lab], [F2]
    ncaps = 0
    for loop in order_chains(bnd):
        loop = np.array(loop)
        for g in np.unique(grp[loop]):
            poly = loop[grp[loop] == g]  # this part's rim, in cyclic order around the hole
            if len(poly) < 3:
                continue
            t = np.array(min_area_fill(V, poly))[:, ::-1]  # reverse: cap edges oppose the rim half-edges
            Fn.append(t); ncaps += 1
    V = np.concatenate(Vn); N = np.concatenate(Nn); lab = np.concatenate(labn); F = np.concatenate(Fn)
    loops = range(ncaps)
    used = np.zeros(len(V), bool); used[F.ravel()] = True
    remap = np.cumsum(used) - 1
    nv0 = int(used[:nv0].sum())
    V, N, lab, F = V[used], N[used], lab[used], remap[F]
    log(f"capped {len(loops)} boundary loops -> {len(V)} verts, {len(F)} tris")
    return V, F, N, lab


def order_chains(E):
    """Split directed boundary edges into vertex chains (closed loops or open runs)."""
    from collections import defaultdict
    out_e = defaultdict(list); indeg = defaultdict(int)
    for a, b in E:
        out_e[a].append(b); indeg[b] += 1
    unused = {(a, b) for a, b in E}
    chains = []
    starts = [a for a in out_e if indeg[a] == 0] + [a for a, _ in E]
    for st in starts:
        if not any((st, b) in unused for b in out_e[st]):
            continue
        ch = [st]; cur = st
        while True:
            nx = [b for b in out_e[cur] if (cur, b) in unused]
            if not nx:
                break
            unused.discard((cur, nx[0])); cur = nx[0]
            if cur == st:
                break
            ch.append(cur)
        chains.append(ch)
    return chains


def min_area_fill(V, chain):
    """Minimum-total-area triangulation of a (possibly non-planar) polygon (Liepa 2003 style DP)."""
    P = V[chain]; n = len(P)
    W = np.zeros((n, n)); O = np.zeros((n, n), int)
    for gap in range(2, n):
        for i in range(0, n - gap):
            j = i + gap
            m = np.arange(i + 1, j)
            area = 0.5 * np.linalg.norm(np.cross(P[m] - P[i], P[j] - P[i]), axis=1)
            c = W[i, m] + W[m, j] + area
            best = np.argmin(c)
            W[i, j] = c[best]; O[i, j] = m[best]
    tris, stack = [], [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        m = O[i, j]
        tris.append([chain[i], chain[m], chain[j]])
        stack += [(i, m), (m, j)]
    return tris


def compute_weights(V, F, B, lab):
    names = [b[0] for b in B]
    parent = {b[0]: b[1] for b in B}
    nb = len(B)
    n = len(V)
    E = mesh_edges(F)

    # soft weights: diffuse one-hot labels only across edges joining related bones
    related = np.zeros((nb, nb), bool)
    for j, nm in enumerate(names):
        related[j, j] = True
        if parent[nm] is not None:
            p = names.index(parent[nm]); related[j, p] = related[p, j] = True
    ok = related[lab[E[:, 0]], lab[E[:, 1]]]
    e = E[ok]
    A = sparse.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), (n, n)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    A = sparse.diags(1 / np.maximum(deg, 1)) @ A
    Wt = np.zeros((n, nb)); Wt[np.arange(n), lab] = 1
    has_nb = (deg > 0)[:, None]
    for _ in range(24):
        Wt = np.where(has_nb, 0.5 * Wt + 0.5 * (A @ Wt), Wt)
    # top-4, normalise
    order = np.argsort(-Wt, axis=1)[:, :4]
    w4 = np.take_along_axis(Wt, order, 1)
    w4[w4 < 0.02] = 0
    w4 /= w4.sum(1, keepdims=True)
    return order.astype(np.uint16), w4.astype(np.float32), E


# ----------------------------------------------------------------------------------------------
# 4. colours
def compute_colors(V, F, N, tex, lab, names, E, B):
    H, W, _ = tex.shape
    px = ALIGN_SC * V[:, 0] + ALIGN_TX
    py = -ALIGN_SC * V[:, 1] + ALIGN_TY
    uv = np.stack([px / W, py / H], 1)
    # front visibility with a 2x z-buffer in image space (depth = +z, nearer camera = larger)
    S = np.stack([px * 2, py * 2, V[:, 2]], 1)
    zb = zbuffer_screen(S, F, 2 * W, 2 * H)
    zbm = ndimage.maximum_filter(zb, size=3)
    ix = np.clip((px * 2).astype(int), 0, 2 * W - 1); iy = np.clip((py * 2).astype(int), 0, 2 * H - 1)
    vis = V[:, 2] >= zbm[iy, ix] - 0.012
    facing = np.clip((N[:, 2] - 0.18) / 0.32, 0, 1)
    w = vis * facing
    part = np.array([names[l] for l in lab])
    is_tail = np.char.startswith(part, "tail")
    w[is_tail] = 0
    # erode front weight one ring so the texture never stretches over silhouettes
    for _ in range(2):
        mn = w.copy()
        np.minimum.at(mn, E[:, 0], w[E[:, 1]]); np.minimum.at(mn, E[:, 1], w[E[:, 0]])
        w = 0.5 * w + 0.5 * mn

    col = sample(tex, px, py)
    pick = lambda x, y, r=4: np.median(tex[y - r:y + r, x - r:x + r].reshape(-1, 3), 0)
    orange = pick(255, 160)
    jacket = pick(225, 520)
    pants = pick(200, 620, 3)
    cream = pick(118, 318, 3)
    shoe = pick(200, 690, 2)
    log("palette (sRGB) orange=%s jacket=%s pants=%s cream=%s shoe=%s" % tuple(
        np.round(c, 2) for c in (orange, jacket, pants, cream, shoe)))

    fixed = w > 0.6
    hidden = ~fixed
    tgt = col.copy()
    x, y, z = V.T
    is_head = np.isin(part, ["head", "neck"])
    is_ear = np.char.startswith(part, "ear")
    is_torso = np.isin(part, ["hips", "spine", "chest"])
    # back of head / ears: orange fur (front half below the chin stays free -> diffusion)
    m = hidden & (is_head | is_ear) & ((z < 0.12) | (N[:, 1] > 0.3)) & ~((N[:, 1] < -0.4) & (z > 0.05))
    tgt[m] = orange; fixed |= m
    # back of torso: jacket down to the hem, orange trousers below
    is_arm = np.array([p.startswith(("upper_arm", "forearm", "hand")) for p in part])
    m = hidden & ~is_tail & ~is_arm & (N[:, 2] < -0.05) & (y > -0.72) & (y < -0.02) & (np.abs(x) < 0.33)
    tgt[m] = np.where((y[m] > -0.63)[:, None], jacket, pants); fixed |= m
    # sleeves / paws and trousers / shoes on the hidden side of limbs
    is_leg = np.array([p.startswith(("thigh", "shin", "foot")) for p in part])
    m = hidden & is_arm & (N[:, 2] < 0.15)
    tgt[m] = np.where((y[m] > -0.42)[:, None], jacket, np.where((y[m] > -0.50)[:, None], orange, cream)); fixed |= m
    m = hidden & is_leg & (N[:, 2] < 0.15)
    tgt[m] = np.where((y[m] > -0.925)[:, None], pants, shoe); fixed |= m
    # tail: orange with a cream tip and a little cream on the underside
    tb = names.index("tail.1")
    t_par = np.zeros(len(V))
    for i in range(4):
        j = names.index(f"tail.{i + 1}")
        _, tt = seg_dist(V, B[j][2], B[j][3])
        sel = lab == j
        t_par[sel] = (i + tt[sel]) / 4
    tipmix = np.clip((t_par - 0.62) / 0.22, 0, 1) ** 1.5
    under = np.clip((-N[:, 1] - 0.4) / 0.6, 0, 1) * 0.35
    tm = np.clip(tipmix + under * (t_par > 0.25), 0, 1)
    tcol = orange * (1 - tm[:, None]) + cream * tm[:, None]
    tgt[is_tail] = tcol[is_tail]; fixed |= is_tail
    m = is_tail & (z > -0.16) & (y > -0.62)  # jacket hem overlaps the tail root
    tgt[m] = jacket
    # harmonic fill for every remaining hidden vertex (soles, underside of chin, limb backs...)
    free = ~fixed
    n = len(V)
    Ad = sparse.coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), (n, n)).tocsr()
    L = sparse.diags(np.asarray(Ad.sum(1)).ravel()) - Ad
    fi, xi = np.nonzero(free)[0], np.nonzero(~free)[0]
    if len(fi):
        Lff = L[fi][:, fi].tocsc(); Lfx = L[fi][:, xi]
        for ch in range(3):
            tgt[fi, ch] = spsolve(Lff, -Lfx @ tgt[xi, ch])
    # soften rule/diffusion seams (texture-covered vertices are left untouched)
    deg = np.asarray(Ad.sum(1)).ravel()
    An = sparse.diags(1 / deg) @ Ad
    for _ in range(4):
        sm = An @ tgt
        tgt = np.where((w > 0.95)[:, None], tgt, 0.5 * tgt + 0.5 * sm)
    rgba = np.concatenate([srgb_to_linear(np.clip(tgt, 0, 1)), w[:, None]], 1).astype(np.float32)
    log(f"front-textured verts {int((w > 0.5).sum())}/{n}, rule-coloured {int((fixed & hidden).sum())}, diffused {len(fi)}")
    return uv.astype(np.float32), rgba


# ----------------------------------------------------------------------------------------------
# 5. glTF writer
class GLB:
    def __init__(self):
        self.bin = bytearray(); self.views = []; self.acc = []

    def add(self, arr, comp, typ, target=None, minmax=False, normalized=False):
        arr = np.ascontiguousarray(arr)
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin); self.bin += arr.tobytes()
        v = {"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes}
        if target:
            v["target"] = target
        self.views.append(v)
        a = {"bufferView": len(self.views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            flat = arr.reshape(arr.shape[0], -1)
            a["min"] = flat.min(0).tolist(); a["max"] = flat.max(0).tolist()
        self.acc.append(a)
        return len(self.acc) - 1


def write_glb(path, V, F, N, uv, rgba, joints, weights, B, anims):
    g = GLB()
    FLOAT, U16, U32 = 5126, 5123, 5125
    pos = g.add(V.astype(np.float32), FLOAT, "VEC3", 34962, minmax=True)
    nor = g.add(N.astype(np.float32), FLOAT, "VEC3", 34962)
    tc = g.add(uv, FLOAT, "VEC2", 34962)
    col = g.add(rgba, FLOAT, "VEC4", 34962)
    jnt = g.add(joints.astype(np.uint16), U16, "VEC4", 34962)
    wgt = g.add(weights, FLOAT, "VEC4", 34962)
    idx = g.add(F.astype(np.uint16 if len(V) < 65536 else np.uint32).reshape(-1),
                U16 if len(V) < 65536 else U32, "SCALAR", 34963)
    names = [b[0] for b in B]
    heads = {b[0]: b[2] for b in B}
    ibm = np.zeros((len(B), 16), np.float32)
    for i, b in enumerate(B):
        m = np.eye(4); m[:3, 3] = -b[2]
        ibm[i] = m.T.reshape(-1)  # column-major
    ibm_acc = g.add(ibm, FLOAT, "MAT4")
    nodes = [{"name": "Harvey", "children": [1, 2]},
             {"name": "Body", "mesh": 0, "skin": 0}]
    joint_node = {}
    for i, (name, par, h, t) in enumerate(B):
        joint_node[name] = 2 + i
    for i, (name, par, h, t) in enumerate(B):
        tr = h - (heads[par] if par else 0)
        nd = {"name": name, "translation": [float(v) for v in tr]}
        kids = [joint_node[c[0]] for c in B if c[1] == name]
        if kids:
            nd["children"] = kids
        nodes.append(nd)
    gl_anims = []
    for a in anims:
        samplers, channels = [], []
        tacc = g.add(a["times"].astype(np.float32), FLOAT, "SCALAR", minmax=True)
        for bone, q in a["rot"].items():
            o = g.add(q.astype(np.float32), FLOAT, "VEC4")
            samplers.append({"input": tacc, "output": o, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": joint_node[bone], "path": "rotation"}})
        for bone, p in a["pos"].items():
            o = g.add((p + (heads[bone] - heads[[b[1] for b in B if b[0] == bone][0]])).astype(np.float32), FLOAT, "VEC3")
            samplers.append({"input": tacc, "output": o, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": joint_node[bone], "path": "translation"}})
        gl_anims.append({"name": a["name"], "samplers": samplers, "channels": channels})
    doc = {
        "asset": {"version": "2.0", "generator": "harvey tools/build_avatar.py",
                  "copyright": "Harvey avatar - see LICENSE"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": [{"name": "Body", "primitives": [{
            "attributes": {"POSITION": pos, "NORMAL": nor, "TEXCOORD_0": tc, "COLOR_0": col,
                           "JOINTS_0": jnt, "WEIGHTS_0": wgt},
            "indices": idx, "material": 0, "mode": 4}]}],
        "materials": [{"name": "HarveyBody", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                       "metallicFactor": 0.0, "roughnessFactor": 0.85}}],
        "skins": [{"name": "HarveySkin", "joints": [joint_node[nm] for nm in names],
                   "inverseBindMatrices": ibm_acc, "skeleton": joint_node["root"]}],
        "animations": gl_anims,
        "accessors": g.acc, "bufferViews": g.views, "buffers": [{"byteLength": len(g.bin)}],
    }
    nodes[0]["children"] = [1, joint_node["root"]]
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(g.bin) % 4:
        g.bin.append(0)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(g.bin))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(g.bin), 0x004E4942) + bytes(g.bin)
    open(path, "wb").write(out)
    log(f"wrote {path} ({len(out) / 1e6:.2f} MB, {len(gl_anims)} animations)")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    V, F, N = load_and_decimate()
    tex, mask, _ = build_texture(V, F)
    B = build_skeleton(V)
    names = [b[0] for b in B]
    lab = compute_labels(V, F, B)
    V, F, N, lab = cut_webs(V, F, N, lab, B)
    joints, weights, E = compute_weights(V, F, B, lab)
    uv, rgba = compute_colors(V, F, N, tex, lab, names, E, B)
    anims = animations.bake_all(names)
    write_glb(os.path.join(OUT_DIR, "harvey.glb"), V, F, N, uv, rgba, joints, weights, B, anims)
    np.savez_compressed(os.path.join(ROOT, "tools", ".cache_build.npz"), V=V, F=F, N=N, uv=uv, rgba=rgba,
                        joints=joints, weights=weights, lab=lab)
    json.dump({"bones": [[b[0], b[1], b[2].tolist(), b[3].tolist()] for b in B]},
              open(os.path.join(ROOT, "tools", ".cache_bones.json"), "w"))


if __name__ == "__main__":
    main()
