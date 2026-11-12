"""
Local run of the PARCS solver without a cluster.

Each "worker" is an in-process object that calls the same static methods the
real PARCS worker would call (data still goes through base64 like on the wire).
Used for: correctness check, sequential baseline (N=1), quick debugging.

    python tools/local_run.py data/input_gray.txt data/output_local.pgm --workers 4
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'solver'))
from histeq_solver import Solver  # noqa: E402


class LocalWorker:
    def local_histogram(self, *a):
        return Solver.local_histogram(*a)

    def apply_lut(self, *a):
        return Solver.apply_lut(*a)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('output')
    p.add_argument('--workers', type=int, default=1)
    a = p.parse_args()
    Solver([LocalWorker() for _ in range(a.workers)], a.input, a.output).solve()


if __name__ == '__main__':
    main()
