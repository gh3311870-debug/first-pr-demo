import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_util as U
import rifle
U.reset_scene()
r = rifle.build()
out = sys.argv[-1]
U.preview(out + "_side.png", target=(0, 0.1, 0.02), cam_loc=(1.3, 0.1, 0.05), lens=50)
U.preview(out + "_34.png", target=(0, 0.1, 0.02), cam_loc=(0.8, -0.7, 0.45), lens=50)
