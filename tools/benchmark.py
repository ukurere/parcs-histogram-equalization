"""
Benchmark the solver on a running PARCS-Python cluster through its HTTP API
(the same API the web UI uses).

For every N in --workers it enables exactly N workers, submits the job,
waits for it, downloads the output and reads the timing header written by
the solver. Results are appended to a CSV.

    python tools/benchmark.py --master http://MASTER_EXTERNAL_IP:8080 \
        --input data/input_gray.txt --workers 1 2 3 4 --repeat 3 --csv results/gcp.csv

Endpoints used (parcs_py/parcs.py):
    GET  /api/worker                       -> list of workers
    POST /api/worker/<id>/enable|disable   -> choose how many workers take part
    POST /api/job  (job_name, solution_file, input_file)
    GET  /api/job/<id>/output              -> 400 until the job ends
"""
import argparse
import csv
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SOLVER = os.path.join(HERE, '..', 'solver', 'histeq_solver.py')


def set_workers(master, n):
    workers = sorted(requests.get(master + '/api/worker').json()['workers'], key=lambda w: w['id'])
    if len(workers) < n:
        raise SystemExit('only %d workers registered, need %d' % (len(workers), n))
    for i, w in enumerate(workers):
        state = 'enable' if i < n else 'disable'
        requests.post('%s/api/worker/%d/%s' % (master, w['id'], state)).raise_for_status()


def job_ids(master):
    html = requests.get(master + '/jobs').text
    return [int(x) for x in re.findall(r'/api/job/(\d+)/output', html)]


def submit(master, name, input_path):
    before = set(job_ids(master))
    with open(SOLVER, 'rb') as s, open(input_path, 'rb') as i:
        requests.post(master + '/api/job', data={'job_name': name},
                      files={'solution_file': s, 'input_file': i}).raise_for_status()
    for _ in range(30):
        new = set(job_ids(master)) - before
        if new:
            return max(new)
        time.sleep(0.5)
    raise RuntimeError('job id not found after submit')


def wait_output(master, job_id, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get('%s/api/job/%d/output' % (master, job_id))
        if r.status_code == 200:
            return r.content, time.time() - t0
        time.sleep(1)
    raise RuntimeError('job %d timed out' % job_id)


def parse_stats(data):
    stats = {}
    for line in data[:2048].split(b'\n')[1:]:
        if not line.startswith(b'#'):
            break
        k, _, v = line[1:].strip().decode().partition('=')
        stats[k] = v
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--master', default='http://localhost:8080')
    p.add_argument('--input', required=True)
    p.add_argument('--workers', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--csv', default='results/benchmark.csv')
    p.add_argument('--save-output', default=None, help='dir to save output images')
    p.add_argument('--timeout', type=int, default=1800)
    a = p.parse_args()
    master = a.master.rstrip('/')

    os.makedirs(os.path.dirname(a.csv) or '.', exist_ok=True)
    new_file = not os.path.exists(a.csv)
    with open(a.csv, 'a', newline='') as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(['workers', 'run', 'job_id', 'size', 'channels', 't_read', 't_split',
                        't_map_hist', 't_reduce_lut', 't_map_apply', 't_compute', 't_total',
                        'wall_client'])
        for n in a.workers:
            set_workers(master, n)
            for r in range(1, a.repeat + 1):
                job = submit(master, 'histeq_w%d_r%d' % (n, r), a.input)
                out, wall = wait_output(master, job, a.timeout)
                s = parse_stats(out)
                if not s:
                    raise RuntimeError('job %d failed: output has no stats (check /jobs page)' % job)
                w.writerow([n, r, job, s['size'], s['channels'], s['t_read'], s['t_split'],
                            s['t_map_hist'], s['t_reduce_lut'], s['t_map_apply'],
                            s['t_compute'], s['t_total'], '%.1f' % wall])
                f.flush()
                print('N=%d run=%d job=%d t_total=%ss (hist %s, apply %s)' % (
                    n, r, job, s['t_total'], s['t_map_hist'], s['t_map_apply']))
                if a.save_output and r == 1:
                    os.makedirs(a.save_output, exist_ok=True)
                    ext = '.ppm' if s['channels'] == '3' else '.pgm'
                    with open(os.path.join(a.save_output, 'output_w%d%s' % (n, ext)), 'wb') as o:
                        o.write(out)
    set_workers(master, max(a.workers))


if __name__ == '__main__':
    main()
