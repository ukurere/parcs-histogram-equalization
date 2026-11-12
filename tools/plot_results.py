"""
Build the results table (Markdown) and the time-vs-workers plot from a
benchmark CSV produced by tools/benchmark.py.

    python tools/plot_results.py results/gcp.csv --title "GCP, e2-medium, 3000x2000 RGB"
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from statistics import mean

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser()
    p.add_argument('csv')
    p.add_argument('--title', default='')
    p.add_argument('--out', default=None, help='png path (default: <csv>.png)')
    a = p.parse_args()

    rows = defaultdict(list)
    with open(a.csv) as f:
        for r in csv.DictReader(f):
            rows[int(r['workers'])].append(r)
    ns = sorted(rows)
    avg = {n: {k: mean(float(r[k]) for r in rows[n])
               for k in ('t_total', 't_map_hist', 't_map_apply', 't_reduce_lut', 't_split', 't_read')}
           for n in ns}
    t1 = avg[ns[0]]['t_total'] * ns[0]  # baseline (N=1 if present)

    lines = ['| Воркери | Прогонів | Гістограма (MAP-1), с | LUT (REDUCE), с | Застосування (MAP-2), с | Загальний час, с | Прискорення | Ефективність |',
             '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for n in ns:
        s = t1 / avg[n]['t_total']
        lines.append('| %d | %d | %.2f | %.3f | %.2f | **%.2f** | %.2f× | %.0f%% |' % (
            n, len(rows[n]), avg[n]['t_map_hist'], avg[n]['t_reduce_lut'], avg[n]['t_map_apply'],
            avg[n]['t_total'], s, 100 * s / n))
    table = '\n'.join(lines)
    print(table)
    md = os.path.splitext(a.csv)[0] + '_table.md'
    with open(md, 'w', encoding='utf-8') as f:
        f.write(table + '\n')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    hist = [avg[n]['t_map_hist'] for n in ns]
    apply_ = [avg[n]['t_map_apply'] for n in ns]
    other = [avg[n]['t_total'] - avg[n]['t_map_hist'] - avg[n]['t_map_apply'] for n in ns]
    ax1.bar(ns, hist, color='#4a6fa5', label='MAP-1: гістограми')
    ax1.bar(ns, apply_, bottom=hist, color='#e09f3e', label='MAP-2: застосування LUT')
    ax1.bar(ns, other, bottom=[h + p for h, p in zip(hist, apply_)], color='#9e9e9e',
            label='читання / розбиття / REDUCE')
    for n in ns:
        ax1.text(n, avg[n]['t_total'], '%.1f с' % avg[n]['t_total'], ha='center', va='bottom')
    ax1.set_xlabel('Кількість воркерів')
    ax1.set_ylabel('Час, с')
    ax1.set_xticks(ns)
    ax1.set_title('Час виконання')
    ax1.legend(fontsize=8)

    ax2.plot(ns, [t1 / avg[n]['t_total'] for n in ns], 'o-', color='#4a6fa5', label='фактичне')
    ax2.plot(ns, ns, '--', color='#9e9e9e', label='ідеальне (лінійне)')
    ax2.set_xlabel('Кількість воркерів')
    ax2.set_ylabel('Прискорення T1 / TN')
    ax2.set_xticks(ns)
    ax2.set_title('Прискорення')
    ax2.legend()
    if a.title:
        fig.suptitle(a.title)
    fig.tight_layout()
    out = a.out or os.path.splitext(a.csv)[0] + '.png'
    fig.savefig(out, dpi=120)
    print('saved', out, 'and', md)


if __name__ == '__main__':
    main()
