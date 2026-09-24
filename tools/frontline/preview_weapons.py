import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_util as U
import rifle, weapons_extra as W
U.reset_scene()
out = sys.argv[-1]
roots = [rifle.build(""), rifle.build("DMR_", variant="dmr"), W.build_shotgun(), W.build_pistol()]
for i, r in enumerate(roots):
    r.location.z = -i * 0.3
U.preview(out + "_side.png", target=(0, 0.15, -0.45), cam_loc=(2.6, 0.15, -0.45), lens=50, res=(1100, 900), samples=16)
U.preview(out + "_34.png", target=(0, 0.15, -0.45), cam_loc=(1.6, -1.3, 0.6), lens=50, res=(1100, 900), samples=16)
