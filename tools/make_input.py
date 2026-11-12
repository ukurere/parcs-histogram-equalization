"""
Prepare an input file for the PARCS job.

Converts any image (jpg/png/...) to binary PGM (P5) or PPM (P6), optionally
resizes it and squeezes its contrast so that equalization is clearly visible.
If no source image is given, a synthetic low-contrast test image is generated.

    python tools/make_input.py --out data/input_gray.txt --mode L --size 4000x3000
    python tools/make_input.py photo.jpg --out data/input_rgb.txt --mode RGB --size 3000x2000

The output has a .txt extension only because the PARCS web form expects
"Input File"; the content is a regular binary PNM image.
"""
import argparse

import numpy as np
from PIL import Image


def synthetic(w, h, mode, seed=42):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    base = (np.sin(x / w * 9) + np.cos(y / h * 7) + np.sin((x + y) / (w + h) * 23)) / 3
    img = 0.5 + 0.5 * base + rng.normal(0, 0.05, (h, w))
    if mode == 'L':
        arr = img
    else:
        arr = np.stack([img, np.roll(img, w // 7, axis=1), np.roll(img, h // 5, axis=0)], axis=-1)
    arr = np.clip(arr, 0, 1)
    return Image.fromarray((arr * 255).astype(np.uint8), 'L' if mode == 'L' else 'RGB')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src', nargs='?', help='source image (omit for synthetic)')
    p.add_argument('--out', required=True)
    p.add_argument('--mode', choices=['L', 'RGB'], default='L')
    p.add_argument('--size', default=None, help='WxH, e.g. 4000x3000')
    p.add_argument('--low', type=int, default=70, help='min level after contrast squeeze')
    p.add_argument('--high', type=int, default=150, help='max level after contrast squeeze')
    a = p.parse_args()

    size = tuple(int(v) for v in a.size.split('x')) if a.size else None
    if a.src:
        img = Image.open(a.src).convert(a.mode)
        if size:
            img = img.resize(size, Image.LANCZOS)
    else:
        img = synthetic(*(size or (2000, 1500)), mode=a.mode)

    arr = np.asarray(img).astype(np.float32) / 255.0
    arr = a.low + arr * (a.high - a.low)  # low-contrast version
    img = Image.fromarray(arr.round().astype(np.uint8), a.mode)

    magic = b'P5' if a.mode == 'L' else b'P6'
    with open(a.out, 'wb') as f:
        f.write(magic + b'\n%d %d\n255\n' % img.size)
        f.write(img.tobytes())
    print('written %s: %dx%d %s, %.1f MB' % (a.out, img.size[0], img.size[1], a.mode,
                                             len(img.tobytes()) / 1e6))


if __name__ == '__main__':
    main()
