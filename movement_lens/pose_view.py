"""Display-only framing using Touchline's tracked-player crop convention.

No descriptors or source pixels are changed. The separate pose follows the
padded player box, resize and letterbox of a 256x512 Touchline player clip.
"""
import numpy as np


def player_pose(points, boxes, valid, source_width, source_height):
    frames = []
    for p, box, mask in zip(points, boxes, valid):
        x1, y1, x2, y2 = box
        width, height = x2-x1, y2-y1
        left, right = max(0, int(x1-.125*width)), min(source_width, int(x2+.125*width))
        top, bottom = max(0, int(y1-.125*height)), min(source_height, int(y2+.125*height))
        if width <= 0 or height <= 0 or right <= left or bottom <= top:
            frames.append([None]*len(p))
            continue
        scale = min(256/(right-left), 512/(bottom-top))
        rw, rh = max(1, int((right-left)*scale)), max(1, int((bottom-top)*scale))
        offset = np.array([(256-rw)//2, (512-rh)//2])
        mapped = (p-np.array([left, top])) * np.array([rw/(right-left), rh/(bottom-top)]) + offset
        frames.append([[round(float(x), 4) for x in point] if ok and np.isfinite(point).all() else None
                       for point, ok in zip(mapped, mask)])
    return {'frames': frames, 'view_box': [0, 0, 256, 512], 'basis': 'tracked_player_crop',
            'label': 'Player-scaled pose'}
