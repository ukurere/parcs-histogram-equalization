"""
Inspect the PARCS output file: print timing stats from the header,
convert input/output to PNG and draw a before/after figure with histograms.

    python tools/show_result.py data/input_gray.txt results/output_w4.pgm --png results/compare.png
"""
import argparse

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def read_stats(path):
    stats = {}
    with open(path, 'rb') as f:
        f.readline()
        while True:
            line = f.readline()
            if not line.startswith(b'#'):
                break
            k, _, v = line[1:].strip().decode().partition('=')
            stats[k] = v
    return stats


def gray(img):
    return np.asarray(img.convert('L')).ravel()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('output')
    p.add_argument('--png', default=None, help='save before/after figure')
    a = p.parse_args()

    stats = read_stats(a.output)
    for k, v in stats.items():
        print('%-14s %s' % (k, v))

    if a.png:
        src, dst = Image.open(a.input), Image.open(a.output)
        fig, ax = plt.subplots(2, 2, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
        for col, (img, title) in enumerate([(src, 'Вхід (низький контраст)'),
                                            (dst, 'Після вирівнювання гістограми')]):
            ax[0, col].imshow(img, cmap='gray' if img.mode == 'L' else None, vmin=0, vmax=255)
            ax[0, col].set_title(title)
            ax[0, col].axis('off')
            ax[1, col].hist(gray(img), bins=256, range=(0, 255), color='#4a6fa5')
            ax[1, col].set_xlim(0, 255)
            ax[1, col].set_yticks([])
        fig.tight_layout()
        fig.savefig(a.png, dpi=110)
        print('saved', a.png)


if __name__ == '__main__':
    main()
