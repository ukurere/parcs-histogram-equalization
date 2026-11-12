# -*- coding: utf-8 -*-
"""
PARCS-Python solver: parallel histogram equalization (topic 5.2).

Runs on the PARCS master (Python 2.7 inside hummer12007/parcs-node image).
The same file is shipped to every worker, which exposes the static
methods marked with @expose.

Input  file: binary PGM (P5, grayscale) or PPM (P6, RGB), 8-bit.
Output file: binary PGM/PPM with the equalized image. Timing info is
             written into the header as comment lines ("# key=value").

Algorithm (map -> reduce -> map):
  1. master splits the image into N horizontal strips (N = number of workers);
  2. MAP-1   : every worker builds a local 256-bin histogram of its strip
               (for RGB: of the luminance channel Y);
  3. REDUCE  : master sums the N histograms, computes the CDF and the
               look-up table  lut[v] = round((cdf[v]-cdf_min)/(total-cdf_min)*255);
  4. MAP-2   : every worker applies lut to its strip (for RGB the
               chroma Cb/Cr is kept, only Y is remapped);
  5. master concatenates the strips and writes the result.

The code is intentionally Python 2.7 / 3.x compatible and uses only the
standard library (the PARCS docker image has no numpy / Pillow).
"""
import base64
import threading
import time

try:
    from Pyro4 import expose
except ImportError:  # local run without Pyro4
    def expose(f):
        return f


def _to_wire(raw):
    """bytes -> ASCII str (base64) so that Pyro4/serpent sends it as one string."""
    s = base64.b64encode(raw)
    return s if isinstance(s, str) else s.decode('ascii')


def _from_wire(s):
    if not isinstance(s, bytes):
        s = s.encode('ascii')
    return bytearray(base64.b64decode(s))


def _value(res):
    """Pyro4 async proxies return FutureResult objects; plain proxies return the value."""
    return res.value if hasattr(res, 'value') else res


class Solver:
    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name
        self.workers = workers
        print("Inited")

    # ------------------------------------------------------------------ master
    def solve(self):
        print("Job Started")
        n = len(self.workers)
        print("Workers %d" % n)
        t0 = time.time()

        magic, width, height, pixels = self.read_input()
        channels = 3 if magic == 'P6' else 1
        t_read = time.time()

        strips = self.split(pixels, width * channels, height, n)
        wire = [_to_wire(bytes(s)) for s in strips]
        t_split = time.time()

        # MAP-1: local histograms
        hists = self.parallel_call('local_histogram',
                                   [(w, channels) for w in wire])
        t_hist = time.time()

        # REDUCE: global histogram -> CDF -> LUT
        hist = Solver.merge_histograms(hists)
        lut = Solver.build_lut(hist)
        t_lut = time.time()

        # MAP-2: apply LUT
        results = self.parallel_call('apply_lut',
                                     [(w, channels, lut) for w in wire])
        out = bytearray()
        for r in results:
            out.extend(_from_wire(r))
        t_apply = time.time()

        stats = [
            ('workers', n),
            ('size', '%dx%d' % (width, height)),
            ('channels', channels),
            ('t_read', '%.3f' % (t_read - t0)),
            ('t_split', '%.3f' % (t_split - t_read)),
            ('t_map_hist', '%.3f' % (t_hist - t_split)),
            ('t_reduce_lut', '%.3f' % (t_lut - t_hist)),
            ('t_map_apply', '%.3f' % (t_apply - t_lut)),
            ('t_compute', '%.3f' % (t_apply - t_read)),
            ('t_total', '%.3f' % (t_apply - t0)),
        ]
        self.write_output(magic, width, height, out, stats)
        print("Job Finished: " + ", ".join("%s=%s" % kv for kv in stats))

    def parallel_call(self, method, args_list):
        """Call `method` on every worker concurrently (one thread per worker)."""
        results = [None] * len(args_list)
        errors = []

        def run(i):
            try:
                proxy = self.workers[i]
                results[i] = _value(getattr(proxy, method)(*args_list[i]))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(len(args_list))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if errors:
            raise errors[0]
        return results

    @staticmethod
    def split(pixels, row_bytes, height, parts):
        """Split image rows into `parts` nearly equal horizontal strips."""
        strips = []
        base, extra = divmod(height, parts)
        row = 0
        for i in range(parts):
            rows = base + (1 if i < extra else 0)
            strips.append(pixels[row * row_bytes:(row + rows) * row_bytes])
            row += rows
        return strips

    @staticmethod
    def merge_histograms(hists):
        total = [0] * 256
        for h in hists:
            for v in range(256):
                total[v] += h[v]
        return total

    @staticmethod
    def build_lut(hist):
        cdf = []
        acc = 0
        for c in hist:
            acc += c
            cdf.append(acc)
        total = cdf[-1]
        cdf_min = 0
        for c in cdf:
            if c > 0:
                cdf_min = c
                break
        if total == cdf_min:  # flat image
            return list(range(256))
        scale = 255.0 / (total - cdf_min)
        return [max(0, min(255, int(round((c - cdf_min) * scale)))) for c in cdf]

    # ------------------------------------------------------------------ worker
    @staticmethod
    @expose
    def local_histogram(strip_wire, channels):
        data = _from_wire(strip_wire)
        hist = [0] * 256
        if channels == 1:
            for p in data:
                hist[p] += 1
        else:
            for i in range(0, len(data), 3):
                y = Solver.luma(data[i], data[i + 1], data[i + 2])
                hist[y] += 1
        return hist

    @staticmethod
    @expose
    def apply_lut(strip_wire, channels, lut):
        data = _from_wire(strip_wire)
        if channels == 1:
            for i in range(len(data)):
                data[i] = lut[data[i]]
        else:
            for i in range(0, len(data), 3):
                r, g, b = data[i], data[i + 1], data[i + 2]
                y = 0.299 * r + 0.587 * g + 0.114 * b
                cb = -0.168736 * r - 0.331264 * g + 0.5 * b
                cr = 0.5 * r - 0.418688 * g - 0.081312 * b
                y = lut[Solver.clamp(int(y + 0.5))]
                data[i] = Solver.clamp(int(y + 1.402 * cr + 0.5))
                data[i + 1] = Solver.clamp(int(y - 0.344136 * cb - 0.714136 * cr + 0.5))
                data[i + 2] = Solver.clamp(int(y + 1.772 * cb + 0.5))
        return _to_wire(bytes(data))

    @staticmethod
    def luma(r, g, b):
        return Solver.clamp(int(0.299 * r + 0.587 * g + 0.114 * b + 0.5))

    @staticmethod
    def clamp(v):
        return 0 if v < 0 else (255 if v > 255 else v)

    # ------------------------------------------------------------------ I/O
    def read_input(self):
        f = open(self.input_file_name, 'rb')
        data = f.read()
        f.close()
        return Solver.parse_pnm(data)

    @staticmethod
    def parse_pnm(data):
        """Parse binary P5/P6 (maxval 255). Returns (magic, w, h, bytearray)."""
        tokens = []
        pos = 0
        while len(tokens) < 4:
            if pos >= len(data):
                raise ValueError('Truncated PNM header')
            while data[pos:pos + 1].isspace():
                pos += 1
            if data[pos:pos + 1] == b'#':
                while data[pos:pos + 1] not in (b'\n', b''):
                    pos += 1
                continue
            start = pos
            while not data[pos:pos + 1].isspace():
                pos += 1
            tokens.append(data[start:pos].decode('ascii'))
        pos += 1  # single whitespace after maxval
        magic, w, h, maxval = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
        if magic not in ('P5', 'P6') or maxval != 255:
            raise ValueError('Expected binary P5/P6 with maxval 255, got %s/%d' % (magic, maxval))
        size = w * h * (3 if magic == 'P6' else 1)
        return magic, w, h, bytearray(data[pos:pos + size])

    def write_output(self, magic, width, height, pixels, stats):
        header = magic + '\n'
        for k, v in stats:
            header += '# %s=%s\n' % (k, v)
        header += '%d %d\n255\n' % (width, height)
        f = open(self.output_file_name, 'wb')
        f.write(header.encode('ascii'))
        f.write(bytes(pixels))
        f.close()
        print("output done")
