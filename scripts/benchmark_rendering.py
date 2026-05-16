#!/usr/bin/env python3
"""
Benchmark actual tile rendering performance across zoom levels and locations.

REQUIREMENTS: mapnik Python bindings + a running PostGIS database with OSM data.
This script cannot run in the standard CI environment; use Docker or a full
local setup (see docker-compose.yml).

Usage:
    python3 scripts/benchmark_rendering.py --stylefile mapnik.xml
    python3 scripts/benchmark_rendering.py --stylefile mapnik.xml --runs 5 --json results.json
"""

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

import prettytable

# Representative locations covering different map densities and feature types
LOCATIONS = [
    {'name': 'Paris (urban)',       'lat': 48.8566, 'lon': 2.3522},
    {'name': 'Brussels (cycling)',  'lat': 50.8503, 'lon': 4.3517},
    {'name': 'Burgundy (rural)',    'lat': 47.0,    'lon': 4.5},
    {'name': 'Grenoble (mountain)', 'lat': 45.1667, 'lon': 5.7167},
]

# Zoom levels that cover global overview through street level
TEST_ZOOMS = [2, 5, 8, 10, 12, 14, 16, 18]


def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_bbox(tx, ty, zoom):
    initial_res = 20037508.342789244 * 2.0 / 256.0
    origin_shift = 20037508.342789244
    zoom2 = 2.0 ** zoom
    res = initial_res / zoom2
    mx = (res * 256 * (tx + 1)) - origin_shift
    my = (res * 256 * (zoom2 - ty)) - origin_shift
    mx1 = (res * 256 * tx) - origin_shift
    my1 = (res * 256 * (zoom2 - ty - 1)) - origin_shift
    return mx1, my1, mx, my


def render_tile(m, lat, lon, zoom):
    """Render one tile and return elapsed seconds. Raises on failure."""
    import mapnik
    x, y = deg2num(lat, lon, zoom)
    bbox_coords = tile_to_bbox(x, y, zoom)
    bbox = mapnik.Box2d(*bbox_coords)
    m.zoom_to_box(bbox)
    im = mapnik.Image(256, 256)
    t0 = time.perf_counter()
    mapnik.render(m, im)
    return time.perf_counter() - t0


def run_benchmarks(stylefile, runs, custom_fonts_dir):
    try:
        import mapnik
    except ImportError:
        print("ERROR: mapnik Python bindings not found.", file=sys.stderr)
        print("Install mapnik or run inside the Docker rendering container.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(stylefile):
        print(f"ERROR: style file not found: {stylefile}", file=sys.stderr)
        sys.exit(1)

    if os.path.isdir(custom_fonts_dir):
        mapnik.register_fonts(custom_fonts_dir)

    print(f"Loading style: {stylefile}")
    m = mapnik.Map(256, 256)
    mapnik.load_map(m, stylefile)
    print(f"Style loaded. Running {runs} render(s) per tile.\n")

    results = {}

    for loc in LOCATIONS:
        results[loc['name']] = {}
        for z in TEST_ZOOMS:
            times = []
            for _ in range(runs):
                try:
                    elapsed = render_tile(m, loc['lat'], loc['lon'], z)
                    times.append(elapsed)
                except Exception as e:
                    print(f"  WARNING: z{z} {loc['name']}: {e}", file=sys.stderr)
                    break
            if times:
                results[loc['name']][z] = {
                    'min': min(times),
                    'max': max(times),
                    'avg': sum(times) / len(times),
                    'runs': len(times),
                }

    return results


def print_results(results):
    for loc_name, zoom_data in results.items():
        print(f"\n{loc_name}")
        t = prettytable.PrettyTable(['Zoom', 'Min (s)', 'Avg (s)', 'Max (s)', 'Runs'])
        t.align['Zoom'] = 'r'
        for col in ('Min (s)', 'Avg (s)', 'Max (s)'):
            t.align[col] = 'r'
        for z in TEST_ZOOMS:
            if z in zoom_data:
                d = zoom_data[z]
                t.add_row([z, f"{d['min']:.3f}", f"{d['avg']:.3f}", f"{d['max']:.3f}", d['runs']])
            else:
                t.add_row([z, 'N/A', 'N/A', 'N/A', 0])
        print(t)


def main():
    parser = argparse.ArgumentParser(description='Benchmark CyclOSM tile rendering performance')
    parser.add_argument('--stylefile', default='mapnik.xml',
                        help='Compiled Mapnik XML style file (default: mapnik.xml)')
    parser.add_argument('--runs', type=int, default=3,
                        help='Number of renders per tile for averaging (default: 3)')
    parser.add_argument('--json', dest='json_output', metavar='FILE',
                        help='Save results as JSON to FILE')
    parser.add_argument('--fonts-dir', default='/etc/mapnik-osm-data/fonts/',
                        help='Directory with custom Mapnik fonts')
    args = parser.parse_args()

    results = run_benchmarks(args.stylefile, args.runs, args.fonts_dir)
    print_results(results)

    if args.json_output:
        # Convert integer zoom keys to strings for JSON serialisation
        serialisable = {
            loc: {str(z): data for z, data in zooms.items()}
            for loc, zooms in results.items()
        }
        with open(args.json_output, 'w') as f:
            json.dump(serialisable, f, indent=2)
        print(f"\nResults saved to {args.json_output}")


if __name__ == '__main__':
    main()
