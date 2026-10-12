"""Harvey animation library, authored as functions of time and baked at 30 fps.

Rotations are Euler degrees (x, y, z) in world-aligned bone space (all rest rotations are identity):
  +X = pitch forward (nod down / lean forward / raise tail), -X on an arm = raise it forward,
  +Y = turn toward the character's left, +Z = roll toward the character's right
  (on upper_arm.L +Z lifts the arm outward; on upper_arm.R use -Z).
Every animation keys every bone so cross-fades in Godot are always fully determined.

Principles used (so motion reads as alive rather than mechanical):
  * weight shift: hips sway/roll, chest counter-rotates, head stabilises against the body
  * drag / overlap: arms, hands and head lag the torso by a phase offset
  * irregular rhythm: gestures are key poses at uneven times, not a single sine
  * anticipation + overshoot on one-shots (ease_back / settle)
  * ears and tail get extra follow-through at runtime from Godot's SpringBoneSimulator3D
"""
import numpy as np
from scipy.spatial.transform import Rotation

FPS = 30
TAU = 2 * np.pi


def sm(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def back(x, k=1.6):
    """Ease with overshoot (goes past 1 then settles), x in 0..1."""
    x = np.clip(x, 0.0, 1.0)
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def keys(t, ks, ease=sm, loop=None):
    """Interpolate through [(time, value), ...]. With loop=L the last key wraps to the first."""
    if loop is not None:
        t = t % loop
    ts = [k[0] for k in ks]
    if t <= ts[0]:
        return np.asarray(ks[0][1], float)
    for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
        if t <= t1:
            a = ease((t - t0) / (t1 - t0))
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
    return sm(t / fade) * sm((length - t) / fade)


# ---------------------------------------------------------------------------------------------
def base(t, p, amt=1.0, tail_amp=8.0, tail_period=3.0, L=6.0):
    """Living idle layer: breathing, weight shift, drag. All periods divide the loop length L=6."""
    br = s(t, 3.0)                       # breathing, 2 breaths per loop
    sw = s(t, 6.0)                       # slow weight shift side to side
    sw_lag = s(t, 6.0, -0.9)             # what the arms/head do slightly later
    p.add("hips", z=1.6 * amt * sw, y=1.2 * amt * s(t, 6.0, 0.6))
    p.add("spine", z=-0.9 * amt * sw, x=-0.5 * amt * br)
    p.add("chest", z=-0.7 * amt * sw, x=-1.4 * amt * br, y=-0.8 * amt * s(t, 6.0, 0.6))
    p.add("neck", x=0.6 * amt * br)
    # head stabilises (counter-rolls the body sway) and drifts on its own slow curve
    p.add("head", z=amt * (-0.6 * sw + 1.6 * s(t, 6.0, 1.9)), y=amt * (2.2 * s(t, 6.0, 2.4) + 0.8 * s(t, 2.0, 0.3)),
          x=amt * (1.0 * s(t, 3.0, 1.1) + 0.6))
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * amt * (1.8 + 1.4 * sw_lag * sg + 0.6 * br), x=-amt * (1.5 + 1.0 * s(t, 6.0, 0.4 + sg)))
        p.add(f"forearm.{sd}", x=-amt * (4.0 + 1.6 * s(t, 3.0, -1.2)), z=-sg * amt * 1.5)
        p.add(f"hand.{sd}", z=sg * amt * 2.0 * s(t, 6.0, -1.6), x=-amt * 1.5 * s(t, 3.0, -1.8))
        # weight on one leg: that knee straightens, the other softens
        bend = 0.5 + 0.5 * sw * sg
        p.add(f"thigh.{sd}", x=-amt * 2.0 * bend, z=-amt * 0.8 * sw)
        p.add(f"shin.{sd}", x=amt * 3.5 * bend)
        p.add(f"foot.{sd}", x=-amt * 1.5 * bend)
        p.add(f"ear.{sd}", z=-sg * amt * 1.2 * s(t, 6.0, 0.5 + sg))
    for i in range(4):
        p.add(f"tail.{i + 1}", y=tail_amp * s(t, tail_period, -0.8 * i) * (0.6 + 0.2 * i),
              x=2.0 * s(t, 6.0, -0.6 * i) + 2.0)
    return p, {"hips": np.array([0.010 * amt * sw, -0.004 * amt * (0.5 + 0.5 * br), 0.0])}


def idle(t):
    p, tr = base(t, Pose())
    tw = keys(t, [(3.6, 0), (3.7, 1), (3.82, 0.15), (3.9, 0.8), (4.05, 0)])  # ear flick
    p.add("ear.L", x=-12 * tw, z=-6 * tw).add("ear_tip.L", x=-8 * tw)
    return p, tr


def listen(t):
    p, tr = base(t, Pose(), amt=0.6, tail_amp=5.0, tail_period=6.0)
    tilt = keys(t, [(0, -8), (2.6, -8), (3.4, 6), (5.6, 6), (6.0, -8)], loop=6.0)  # slow head-tilt change
    nod = keys(t, [(0, 0), (1.3, 0), (1.55, 1), (1.9, 0), (4.6, 0), (4.85, 0.8), (5.2, 0), (6, 0)])
    p.add("chest", x=4.0).add("spine", x=1.5).add("neck", x=3.0)
    p.add("head", x=3.0 + 6.0 * nod, z=tilt, y=-2.0 * np.sign(tilt))
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"ear.{sd}", x=9.0, z=sg * 3.0).add(f"ear_tip.{sd}", x=4.0)
        p.add(f"forearm.{sd}", x=-6.0)
    return p, tr


def think(t):
    p, tr = base(t, Pose(), amt=0.5, tail_amp=4.0, tail_period=6.0)
    tap = keys(t, [(0, 0), (0.9, 0), (1.05, 1), (1.2, 0), (1.35, 1), (1.5, 0), (4.1, 0), (4.25, 1), (4.4, 0), (6, 0)])
    look = keys(t, [(0, 0), (2.4, 0), (3.2, 1), (5.2, 1), (6.0, 0)])
    p.add("chest", x=-1.5, y=4.0).add("neck", x=-3.0)
    p.add("head", x=-9.0 - 2.0 * look, y=9.0 - 12.0 * look, z=-7.0 + 10.0 * look)
    # right paw under the chin (angles solved by IK, see docs/BUILD_LOG.md); left arm relaxed
    p.add("upper_arm.R", x=-71.4, y=11.8, z=1.1)
    p.add("forearm.R", x=-35.2 + 4.0 * tap, y=21.3, z=42.1)
    p.add("hand.R", x=-6.0 * tap)
    p.add("upper_arm.L", x=-10.0, z=4.0)
    p.add("forearm.L", x=-24.0)
    p.add("ear.L", x=-4.0, z=-3.0 * look).add("ear.R", x=3.0)
    return p, tr


def talk(t):
    """Conversational beat gestures at uneven times, alternating hands, with head accents."""
    p, tr = base(t, Pose(), amt=0.6, tail_amp=6.0, tail_period=2.0)
    L = 6.0
    # [upper_arm x, upper_arm z(out), forearm x, forearm z(in), hand z] key poses per arm
    rest = [0, 0, 0, 0, 0]
    openL = [-18, 10, -42, -14, 16]
    beatL = [-14, 6, -52, -10, 6]
    openR = [-16, 8, -40, -12, 14]
    beatR = [-12, 4, -50, -8, 4]
    kl = keys(t, [(0, rest), (0.5, openL), (0.9, beatL), (1.25, openL), (2.2, rest), (3.6, rest),
                  (4.1, beatL), (4.45, openL), (5.4, rest), (6.0, rest)], loop=L)
    kr = keys(t, [(0, rest), (1.5, rest), (2.0, openR), (2.35, beatR), (2.7, openR), (3.1, beatR),
                  (3.9, rest), (4.6, openR), (5.1, beatR), (6.0, rest)], loop=L)
    for sd, sg, k in (("L", 1, kl), ("R", -1, kr)):
        p.add(f"upper_arm.{sd}", x=k[0], z=sg * k[1])
        p.add(f"forearm.{sd}", x=k[2], z=-sg * k[3])
        p.add(f"hand.{sd}", z=sg * k[4])
    acc = keys(t, [(0, 0), (0.8, 0), (0.95, 1), (1.3, 0), (2.25, 0), (2.4, 1), (2.7, 0), (3.0, 0.7), (3.3, 0),
                   (4.3, 0), (4.45, 1), (4.8, 0), (6, 0)])
    turn = keys(t, [(0, -4), (1.6, 3), (3.0, 5), (4.2, -2), (6.0, -4)], loop=L)
    p.add("chest", y=turn * 0.6, x=1.0 * acc)
    p.add("head", x=4.0 * acc + 1.5, y=turn, z=-1.5 * turn * 0.4)
    for sd in ("L", "R"):
        p.add(f"ear.{sd}", x=3.0 * acc)
    return p, tr


def happy(t):
    p, tr = base(t, Pose(), amt=0.4, tail_amp=22.0, tail_period=0.5)
    hop = np.abs(np.sin(np.pi * t / 0.5)) ** 1.5
    sway = s(t, 1.0)
    p.add("hips", z=5.0 * sway)
    p.add("chest", z=-3.5 * s(t, 1.0, 0.5), x=-2.5)
    p.add("head", z=7.0 * s(t, 1.0, 1.0), x=-3.0 + 2.0 * hop)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * (6.0 + 3.0 * hop), x=-12.0 + 3.0 * s(t, 1.0, sg))
        p.add(f"forearm.{sd}", x=-34.0 + 6.0 * hop, z=-sg * 8.0)
        p.add(f"hand.{sd}", z=sg * 8.0 * s(t, 0.5, 0.7))
        p.add(f"ear.{sd}", z=-sg * 5.0 * s(t, 0.5, 0.8 * sg), x=5.0)
        p.add(f"thigh.{sd}", x=-5.0 * (1 - hop))
        p.add(f"shin.{sd}", x=8.0 * (1 - hop))
        p.add(f"foot.{sd}", x=-3.0 * (1 - hop))
    tr["hips"] = tr["hips"] + np.array([0.0, 0.03 * hop - 0.018, 0.0])
    return p, tr


def sad(t):
    p, tr = base(t, Pose(), amt=0.35, tail_amp=2.0, tail_period=6.0)
    sigh = keys(t, [(0, 0), (1.5, 0), (2.4, 1), (3.6, 0), (6, 0)])
    p.add("chest", x=8.0 - 3.0 * sigh).add("spine", x=3.0).add("neck", x=5.0)
    p.add("head", x=14.0 - 4.0 * sigh, z=5.0)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"ear.{sd}", z=-sg * 30.0, x=-14.0).add(f"ear_tip.{sd}", z=-sg * 16.0, x=-6.0)
        p.add(f"upper_arm.{sd}", x=-6.0, z=-sg * 3.0)
        p.add(f"forearm.{sd}", x=-12.0)
    for i in range(4):
        p.add(f"tail.{i + 1}", x=-10.0 + 2.0 * i)
    tr["hips"] = tr["hips"] + np.array([0.0, -0.012, 0.0])
    return p, tr


def wave(t, L=3.0):
    p, tr = base(t, Pose(), amt=0.5)
    # anticipation dip -> raise with overshoot -> 3 waves -> lower with follow-through
    up = keys(t, [(0, 0), (0.15, -0.08), (0.6, 1.0), (2.3, 1.0), (3.0, 0)], ease=lambda x: back(x, 1.2))
    wv = s(t - 0.6, 0.48) * keys(t, [(0.5, 0), (0.7, 1), (2.05, 1), (2.3, 0)])
    wv_lag = s(t - 0.68, 0.48) * keys(t, [(0.55, 0), (0.75, 1), (2.1, 1), (2.35, 0)])
    p.add("upper_arm.L", z=84.0 * up, x=-20.0 * up)
    p.add("forearm.L", z=58.0 * up + 22.0 * wv, x=-14.0 * up)
    p.add("hand.L", z=8.0 * up + 16.0 * wv_lag)
    p.add("chest", z=-4.0 * up, y=-4.0 * up)
    p.add("spine", z=-2.0 * up)
    p.add("head", z=-8.0 * up + 2.0 * wv, x=-3.0 * up)
    p.add("ear.L", x=6.0 * up).add("ear.R", x=6.0 * up)
    for i in range(4):
        p.add(f"tail.{i + 1}", y=14.0 * up * s(t, 0.6, -0.8 * i))
    return p, tr


def nod(t, L=1.4):
    p, tr = base(t, Pose(), amt=0.5)
    n = keys(t, [(0, 0), (0.12, -3), (0.35, 15), (0.6, -2), (0.85, 10), (1.1, -1), (1.4, 0)])
    p.add("head", x=n).add("neck", x=0.35 * n).add("chest", x=0.12 * n)
    p.add("ear.L", x=-0.4 * n).add("ear.R", x=-0.4 * n)
    return p, tr


def shake(t, L=1.6):
    p, tr = base(t, Pose(), amt=0.5)
    y = keys(t, [(0, 0), (0.22, 16), (0.47, -16), (0.72, 12), (0.97, -9), (1.25, 4), (1.6, 0)])
    p.add("head", y=y, x=3.0 * env(t, L)).add("neck", y=0.3 * y).add("chest", y=-0.1 * y)
    p.add("ear.L", z=-0.25 * y).add("ear.R", z=-0.25 * y)
    return p, tr


def surprised(t, L=1.8):
    p, tr = base(t, Pose(), amt=0.4)
    e = keys(t, [(0, 0), (0.1, 1.15), (0.25, 1.0), (1.2, 1.0), (1.8, 0)])
    jolt = keys(t, [(0, 0), (0.08, 1), (0.3, 0.5), (1.2, 0.5), (1.8, 0)])
    p.add("chest", x=-8.0 * e).add("spine", x=-3.0 * e)
    p.add("head", x=-8.0 * e)
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * 12.0 * e, x=-20.0 * e)
        p.add(f"forearm.{sd}", x=-40.0 * e, z=sg * 6.0 * e)
        p.add(f"hand.{sd}", z=sg * 14.0 * e)
        p.add(f"ear.{sd}", x=10.0 * e, z=sg * 4.0 * e).add(f"ear_tip.{sd}", x=5.0 * e)
    for i in range(4):
        p.add(f"tail.{i + 1}", x=(16.0 - 2 * i) * e)
    tr["hips"] = tr["hips"] + np.array([0.0, 0.035 * jolt, -0.02 * e])
    return p, tr


def celebrate(t, L=2.4):
    p, tr = base(t, Pose(), amt=0.4, tail_amp=20.0, tail_period=0.5)
    crouch = keys(t, [(0, 0), (0.25, 1), (0.4, 0), (1.9, 0), (2.05, 0.6), (2.4, 0)])
    up = keys(t, [(0, 0), (0.3, -0.1), (0.55, 1), (1.9, 1), (2.4, 0)], ease=lambda x: back(x, 1.0))
    air = keys(t, [(0.35, 0), (0.6, 1), (0.9, 0.2), (1.15, 0.9), (1.45, 0), (2.4, 0)])
    for sd, sg in (("L", 1), ("R", -1)):
        p.add(f"upper_arm.{sd}", z=sg * 100.0 * up, x=-12.0 * up)
        p.add(f"forearm.{sd}", z=sg * (22.0 * up + 8.0 * s(t, 0.5) * up))
        p.add(f"hand.{sd}", z=sg * 12.0 * up)
        p.add(f"ear.{sd}", x=7.0 * up)
        p.add(f"thigh.{sd}", x=-14.0 * crouch - 4.0 * air).add(f"shin.{sd}", x=24.0 * crouch + 6.0 * air)
        p.add(f"foot.{sd}", x=-10.0 * crouch)
    p.add("head", x=-7.0 * up + 6.0 * crouch, z=5.0 * s(t, 1.0) * up)
    p.add("chest", x=-5.0 * up + 6.0 * crouch)
    tr["hips"] = tr["hips"] + np.array([0.0, 0.07 * air - 0.05 * crouch, 0.0])
    return p, tr


ANIMS = [
    # name, fn, length, loop
    ("idle", idle, 6.0, True),
    ("listen", listen, 6.0, True),
    ("think", think, 6.0, True),
    ("talk", talk, 6.0, True),
    ("happy", happy, 6.0, True),
    ("sad", sad, 6.0, True),
    ("wave", wave, 3.0, False),
    ("nod", nod, 1.4, False),
    ("shake", shake, 1.6, False),
    ("surprised", surprised, 1.8, False),
    ("celebrate", celebrate, 2.4, False),
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
        if loop:  # verify the loop is seamless (first and last frames match)
            for b in animated:
                assert abs(abs(np.dot(rot[b][0], rot[b][-1])) - 1) < 1e-3, f"{name}:{b} does not loop"
        out.append({"name": name, "times": times, "rot": rot, "pos": pos, "loop": loop})
    return out
