"""Tiny numpy software rasterizer used only for build-time previews/visibility (not shipped)."""
import numpy as np

def look_basis(view):
    # returns (right, up, forward) for named orthographic views; forward points from camera into scene
    v = {
        "front": ((1,0,0),(0,1,0),(0,0,-1)),
        "back":  ((-1,0,0),(0,1,0),(0,0,1)),
        "left":  ((0,0,-1),(0,1,0),(1,0,0)),   # camera on -X looking +X ... character's right side
        "right": ((0,0,1),(0,1,0),(-1,0,0)),
        "top":   ((1,0,0),(0,0,-1),(0,-1,0)),
    }[view]
    return [np.array(a, float) for a in v]

def rasterize(V, F, view="front", res=512, colors=None, bounds=None, light=(0.3,0.5,1.0)):
    """Orthographic z-buffer render. V (n,3), F (m,3), colors per-vertex (n,3) in 0..1 or None.
    Returns rgb image (res,res,3) float, depth (res,res), face id buffer, and the projection params."""
    r, u, f = look_basis(view)
    P = np.stack([V @ r, V @ u, -(V @ f)], 1)  # x,y, depth (bigger = closer)
    if bounds is None:
        c = (P[:, :2].max(0) + P[:, :2].min(0)) / 2
        s = (P[:, :2].max(0) - P[:, :2].min(0)).max() * 1.05
        bounds = (c, s)
    c, s = bounds
    px = (P[:, 0] - c[0]) / s * res + res / 2
    py = res / 2 - (P[:, 1] - c[1]) / s * res
    S = np.stack([px, py, P[:, 2]], 1)
    zbuf = np.full((res, res), -np.inf); fid = np.full((res, res), -1, np.int64)
    tri = S[F]
    xmin = np.clip(np.floor(tri[:, :, 0].min(1)), 0, res-1).astype(int)
    xmax = np.clip(np.ceil(tri[:, :, 0].max(1)), 0, res-1).astype(int)
    ymin = np.clip(np.floor(tri[:, :, 1].min(1)), 0, res-1).astype(int)
    ymax = np.clip(np.ceil(tri[:, :, 1].max(1)), 0, res-1).astype(int)
    bary = {}
    for i in range(len(F)):
        x0, x1, y0, y1 = xmin[i], xmax[i], ymin[i], ymax[i]
        if x1 < x0 or y1 < y0: continue
        gx, gy = np.meshgrid(np.arange(x0, x1+1) + .5, np.arange(y0, y1+1) + .5)
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri[i]
        d = (by-cy)*(ax-cx) + (cx-bx)*(ay-cy)
        if abs(d) < 1e-12: continue
        w0 = ((by-cy)*(gx-cx) + (cx-bx)*(gy-cy)) / d
        w1 = ((cy-ay)*(gx-cx) + (ax-cx)*(gy-cy)) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any(): continue
        z = w0*az + w1*bz + w2*cz
        ys, xs = np.nonzero(m)
        zz = z[m]; Y = ys + y0; X = xs + x0
        closer = zz > zbuf[Y, X]
        zbuf[Y[closer], X[closer]] = zz[closer]; fid[Y[closer], X[closer]] = i
    # shading
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    L = np.array(light, float); L = L[0]*r + L[1]*u - L[2]*f; L /= np.linalg.norm(L)
    img = np.ones((res, res, 3)) * np.array([0.85, 0.85, 0.9])
    hit = fid >= 0
    shade = np.clip(np.abs(fn[fid[hit]] @ L), 0, 1) * 0.75 + 0.25
    if colors is None:
        base = np.ones((hit.sum(), 3)) * 0.9
    else:
        base = colors[F[fid[hit]]].mean(1)
    img[hit] = base * shade[:, None]
    return img, zbuf, fid, (c, s), S


def zbuffer_screen(S, F, W, H):
    """Z-buffer for pre-projected screen-space vertices S (n,3: px, py, depth; larger depth = nearer)."""
    zbuf = np.full((H, W), -np.inf)
    tri = S[F]
    xmin = np.clip(np.floor(tri[:, :, 0].min(1)), 0, W - 1).astype(int)
    xmax = np.clip(np.ceil(tri[:, :, 0].max(1)), 0, W - 1).astype(int)
    ymin = np.clip(np.floor(tri[:, :, 1].min(1)), 0, H - 1).astype(int)
    ymax = np.clip(np.ceil(tri[:, :, 1].max(1)), 0, H - 1).astype(int)
    for i in range(len(F)):
        x0, x1, y0, y1 = xmin[i], xmax[i], ymin[i], ymax[i]
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri[i]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        w0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d
        w1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        z = (w0 * az + w1 * bz + w2 * cz)[m]
        ys, xs = np.nonzero(m)
        Y, X = ys + y0, xs + x0
        np.maximum.at(zbuf, (Y, X), z)
    return zbuf
