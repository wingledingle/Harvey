import sys, numpy as np, trimesh, fast_simplification
from PIL import Image
sys.path.insert(0, 'tools'); from render import rasterize
m = trimesh.load('source/fox_raw.glb', force='mesh')
print('verts', len(m.vertices), 'faces', len(m.faces), 'watertight', m.is_watertight, 'bodies', len(m.split(only_watertight=False)))
V, F = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32), target_count=20000)
imgs = [rasterize(V, F, v, 384)[0] for v in ["front", "right", "back", "top"]]
Image.fromarray((np.concatenate(imgs, 1) * 255).astype(np.uint8)).save('/tmp/claude-0/-home-user-Harvey/9157746b-2543-5767-9ab2-afaddfcad330/scratchpad/views.png')
