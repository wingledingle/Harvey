"""Harvey animation library, authored as smooth functions of time and baked at 30 fps.

Rotations are Euler degrees (x, y, z) in world-aligned bone space (all rest rotations are identity):
  +X = pitch forward (nod down / lean forward / raise tail), -X on an arm = raise it forward,
  +Y = turn toward the character's left, +Z = roll toward the character's right
  (on upper_arm.L +Z lifts the arm outward; on upper_arm.R use -Z).
Every animation keys every bone so cross-fades in Godot are always fully determined.
"""
import numpy as np
from scipy.spatial.transform import Rotation

FPS = 30
TAU = 2 * np.pi


def sm(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def keys(t, ks):
    """Piecewise smoothstep interpolation through [(time, value), ...]."""
    ts = [k[0] for k in ks]
    if t <= ts[0]:
        return np.asarray(ks[0][1], float)
    for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
        if t <= t1:
            a = sm((t - t0) / (t1 - t0))
            return np.asarray(v0, float) * (1 - a) + np.asarray(v1, float) * a
    return np.asarray(ks[-1][1], float)


def s(t, period, phase=0.0):
    return np.sin(TAU * t / period + phase)


class Pose(dict):
    def add(self, bone, x=0.0, y=0.0, z=0.0):
        v = self.get(bone, np.zeros(3))
        self[bone] = v + np.array([x, y, z], float)
        return self


def env(t, length, fade=0.25):
    """0 at both ends of a one-shot, 1 in the middle."""
    return sm(t / fade) * sm((length - t) / fade)


# ---------------------------------------------------------------------------------------------
def base_idle(t, p, amt=1.0, tail_amp=7.0, tail_period=2.0):
    b = s(t, 4.0)
    p.add("hips", z=1.0 * amt * s(t, 4.0, 0.4))
    p.add("spine", x=-0.6 * amt * b, z=-0.5 * amt * s(t, 4.0, 0.4))
    p.add("chest", x=-1.2 * amt * b)
    p.add("neck", x=0.5 * amt * s(t, 4.0, 1.0))
    p.add("head", x=1.4 * amt * s(t, 4.0, 1.2), y=2.5 * amt * s(t, 4.0, 2.0), z=2.0 * amt * s(t, 4.0, -0.4))
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * (1.2 + 1.0 * b) * amt, x=-0.8 * amt * s(t, 4.0, 0.8))
        p.add(f"forearm.{sd}", x=-1.5 * amt * s(t, 4.0, 1.4))
        p.add(f"ear.{sd}", z=-sg * 1.5 * amt * s(t, 4.0, 0.5 + (sd == "R")))
        p.add(f"ear_tip.{sd}", z=-sg * 2.5 * amt * s(t, 4.0, 0.1 + (sd == "R")))
    for i in range(4):
        p.add(f"tail.{i + 1}", y=tail_amp * s(t, tail_period, -0.75 * i), x=1.5 * s(t, 4.0, -0.5 * i))
    return p


def idle(t):
    p = base_idle(t, Pose())
    tw = keys(t, [(2.5, 0), (2.6, 1), (2.75, 0), (2.85, 0.7), (3.0, 0)])  # left-ear twitch
    p.add("ear.L", x=-10 * tw, z=-6 * tw).add("ear_tip.L", x=-8 * tw)
    return p, {}


def listen(t):
    p = base_idle(t, Pose(), amt=0.6, tail_amp=5.0, tail_period=4.0)
    nod = max(0.0, s(t, 2.0)) ** 2
    p.add("chest", x=3.0).add("neck", x=2.0)
    p.add("head", x=4.0 + 3.0 * nod, z=-9.0, y=-4.0)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"ear.{sd}", x=7.0, z=sg * 3.0).add(f"ear_tip.{sd}", x=4.0)
    return p, {}


def think(t):
    p = base_idle(t, Pose(), amt=0.5, tail_amp=4.0, tail_period=4.0)
    p.add("chest", x=-1.5, y=4.0).add("neck", x=-3.0)
    p.add("head", x=-9.0 + 1.0 * s(t, 4.0), y=10.0, z=-7.0)
    tap = max(0.0, s(t, 1.0)) * (s(t, 4.0) > -0.3)
    # right paw under the chin (angles solved by a small IK fit, see docs/BUILD_LOG.md),
    # left arm relaxed slightly forward
    p.add("upper_arm.R", x=-71.4, y=11.8, z=1.1)
    p.add("forearm.R", x=-35.2 + 3.0 * tap, y=21.3, z=42.1)
    p.add("hand.R", x=-4.0 * tap)
    p.add("upper_arm.L", x=-10.0, z=4.0)
    p.add("forearm.L", x=-22.0)
    p.add("ear.L", x=-4.0, z=-3.0).add("ear.R", x=3.0)
    return p, {}


def talk(t):
    p = base_idle(t, Pose(), amt=0.6, tail_amp=6.0, tail_period=1.5)
    g = 0.5 + 0.5 * s(t, 3.0)
    p.add("chest", y=4.0 * s(t, 3.0, 0.3), x=1.0 * s(t, 0.75))
    p.add("head", x=2.5 * s(t, 0.75, 0.6) + 1.5, y=5.0 * s(t, 3.0, 0.9), z=2.0 * s(t, 1.5))
    p.add("upper_arm.L", x=-16.0 * g, z=6.0 * g)
    p.add("forearm.L", x=-38.0 * g - 6.0 * s(t, 0.75), z=-8.0 * g)
    p.add("hand.L", z=10.0 * g)
    g2 = 0.5 + 0.5 * s(t, 3.0, np.pi * 0.8)
    p.add("upper_arm.R", x=-14.0 * g2, z=-6.0 * g2)
    p.add("forearm.R", x=-34.0 * g2 - 5.0 * s(t, 0.75, 1.0), z=8.0 * g2)
    p.add("hand.R", z=-10.0 * g2)
    for sd in ("L", "R"):
        p.add(f"ear.{sd}", x=3.0 * s(t, 0.75, 0.2))
    return p, {}


def happy(t):
    p = base_idle(t, Pose(), amt=0.5, tail_amp=20.0, tail_period=0.5)
    hop = abs(np.sin(np.pi * t / 0.5))
    p.add("hips", z=4.0 * s(t, 1.0))
    p.add("chest", z=-3.0 * s(t, 1.0, 0.4), x=-2.0)
    p.add("head", z=6.0 * s(t, 1.0, 0.8), x=-3.0)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * (7.0 + 4.0 * hop), x=-12.0)
        p.add(f"forearm.{sd}", x=-30.0, z=-sg * 10.0)
        p.add(f"ear.{sd}", z=-sg * 4.0 * s(t, 0.5, 0.6 * sg), x=4.0)
        p.add(f"thigh.{sd}", x=-4.0 * hop)
        p.add(f"shin.{sd}", x=6.0 * hop)
    return p, {"hips": np.array([0.0, 0.035 * hop - 0.012, 0.0])}


def sad(t):
    p = base_idle(t, Pose(), amt=0.4, tail_amp=3.0, tail_period=4.0)
    p.add("chest", x=7.0).add("spine", x=3.0).add("neck", x=5.0)
    p.add("head", x=13.0 + 1.0 * s(t, 4.0, 1.0), z=4.0)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"ear.{sd}", z=-sg * 28.0, x=-12.0).add(f"ear_tip.{sd}", z=-sg * 14.0, x=-6.0)
        p.add(f"upper_arm.{sd}", x=-8.0, z=-sg * 3.0)
        p.add(f"forearm.{sd}", x=-10.0)
    for i in range(4):
        p.add(f"tail.{i + 1}", x=-9.0 + 2.0 * i)
    return p, {"hips": np.array([0.0, -0.01, 0.0])}


def wave(t, L=2.6):
    p = base_idle(t, Pose(), amt=0.5)
    e = keys(t, [(0, 0), (0.45, 1), (2.05, 1), (2.6, 0)])
    w = s(t - 0.45, 0.42) * keys(t, [(0.4, 0), (0.6, 1), (1.85, 1), (2.05, 0)])
    p.add("upper_arm.L", z=82.0 * e, x=-18.0 * e)
    p.add("forearm.L", z=62.0 * e + 20.0 * w, x=-12.0 * e)
    p.add("hand.L", z=10.0 * e + 10.0 * w)
    p.add("chest", z=-3.0 * e, y=-3.0 * e)
    p.add("head", z=-7.0 * e, x=-2.0 * e)
    p.add("ear.L", x=5.0 * e).add("ear.R", x=5.0 * e)
    for i in range(4):
        p.add(f"tail.{i + 1}", y=10.0 * e * s(t, 0.65, -0.7 * i))
    return p, {}


def nod(t, L=1.3):
    p = base_idle(t, Pose(), amt=0.5)
    n = keys(t, [(0, 0), (0.25, 14), (0.5, -2), (0.78, 10), (1.05, -1), (1.3, 0)])
    p.add("head", x=n).add("neck", x=0.35 * n)
    p.add("ear.L", x=-0.3 * n).add("ear.R", x=-0.3 * n)
    return p, {}


def shake(t, L=1.5):
    p = base_idle(t, Pose(), amt=0.5)
    y = keys(t, [(0, 0), (0.2, 15), (0.45, -15), (0.7, 12), (0.95, -9), (1.2, 4), (1.5, 0)])
    p.add("head", y=y, x=3.0 * env(t, L)).add("neck", y=0.3 * y)
    p.add("ear.L", z=-0.2 * y).add("ear.R", z=-0.2 * y)
    return p, {}


def surprised(t, L=1.6):
    p = base_idle(t, Pose(), amt=0.4)
    e = keys(t, [(0, 0), (0.12, 1), (1.0, 1), (1.6, 0)])
    jolt = keys(t, [(0, 0), (0.1, 1), (0.3, 0.6), (1.0, 0.6), (1.6, 0)])
    p.add("chest", x=-7.0 * e).add("spine", x=-3.0 * e)
    p.add("head", x=-7.0 * e)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * 13.0 * e, x=-18.0 * e)
        p.add(f"forearm.{sd}", x=-32.0 * e, z=sg * 8.0 * e)
        p.add(f"hand.{sd}", z=sg * 12.0 * e)
        p.add(f"ear.{sd}", x=8.0 * e, z=sg * 4.0 * e).add(f"ear_tip.{sd}", x=4.0 * e)
    for i in range(4):
        p.add(f"tail.{i + 1}", x=(14.0 - 2 * i) * e)
    return p, {"hips": np.array([0.0, 0.04 * jolt, -0.015 * e])}


def celebrate(t, L=2.2):
    p = base_idle(t, Pose(), amt=0.4, tail_amp=18.0, tail_period=0.5)
    e = keys(t, [(0, 0), (0.35, 1), (1.8, 1), (2.2, 0)])
    hop = abs(np.sin(np.pi * np.clip(t - 0.3, 0, 1.5) / 0.5)) * keys(t, [(0.3, 0), (0.4, 1), (1.7, 1), (1.8, 0)])
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * 105.0 * e, x=-10.0 * e)
        p.add(f"forearm.{sd}", z=sg * 25.0 * e + sg * 8.0 * s(t, 0.5))
        p.add(f"hand.{sd}", z=sg * 10.0 * e)
        p.add(f"ear.{sd}", x=6.0 * e)
        p.add(f"thigh.{sd}", x=-5.0 * hop).add(f"shin.{sd}", x=8.0 * hop)
    p.add("head", x=-6.0 * e, z=5.0 * s(t, 1.0) * e)
    p.add("chest", x=-4.0 * e)
    return p, {"hips": np.array([0.0, 0.05 * hop, 0.0])}


ANIMS = [
    # name, fn, length, loop
    ("idle", idle, 4.0, True),
    ("listen", listen, 4.0, True),
    ("think", think, 4.0, True),
    ("talk", talk, 3.0, True),
    ("happy", happy, 2.0, True),
    ("sad", sad, 4.0, True),
    ("wave", wave, 2.6, False),
    ("nod", nod, 1.3, False),
    ("shake", shake, 1.5, False),
    ("surprised", surprised, 1.6, False),
    ("celebrate", celebrate, 2.2, False),
]


def bake_all(bones):
    out = []
    animated = [b for b in bones if b != "root"]
    for name, fn, length, loop in ANIMS:
        n = int(round(length * FPS)) + 1
        times = np.linspace(0, length, n)
        rot = {b: np.zeros((n, 4)) for b in animated}
        pos = {"hips": np.zeros((n, 3))}
        for i, t in enumerate(times):
            p, tr = fn(t)
            for b in animated:
                e = p.get(b, np.zeros(3))
                rot[b][i] = Rotation.from_euler("xyz", e, degrees=True).as_quat()
            for b, v in tr.items():
                pos[b][i] = v
        for b in animated:  # keep quaternion signs continuous for linear interpolation
            q = rot[b]
            for i in range(1, n):
                if np.dot(q[i], q[i - 1]) < 0:
                    q[i] = -q[i]
        out.append({"name": name, "times": times, "rot": rot, "pos": pos, "loop": loop})
    return out
