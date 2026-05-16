#!/usr/bin/env python3
"""
Analyse rendering complexity per zoom level from a compiled Mapnik XML file.

For each zoom level (0-20), counts the number of active rendering rules.
A high rule count at a zoom level indicates more rendering work for Mapnik.

Usage:
    python3 scripts/benchmark_compilation.py mapnik.xml
    python3 scripts/benchmark_compilation.py mapnik.xml --json results.json
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import prettytable

# Scale denominator for each OSM zoom level: 559082264 / 2^z
ZOOM_SCALE = {z: 559082264.028717 / (2 ** z) for z in range(21)}


def count_rules_per_zoom(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    zoom_counts = defaultdict(int)
    total_rules = 0

    for rule in root.iter('Rule'):
        total_rules += 1
        max_sd_text = rule.findtext('MaxScaleDenominator')
        min_sd_text = rule.findtext('MinScaleDenominator')
        max_sd = float(max_sd_text) if max_sd_text else float('inf')
        min_sd = float(min_sd_text) if min_sd_text else 0.0

        for z, scale in ZOOM_SCALE.items():
            if min_sd <= scale <= max_sd:
                zoom_counts[z] += 1

    return zoom_counts, total_rules


def render_table(zoom_counts):
    peak_zoom = max(zoom_counts, key=zoom_counts.get)
    peak_rules = zoom_counts[peak_zoom]

    table = prettytable.PrettyTable()
    table.field_names = ['Zoom', 'Active rules', 'Relative complexity']
    table.align['Active rules'] = 'r'
    table.align['Relative complexity'] = 'l'

    bar_width = 30
    for z in range(21):
        count = zoom_counts[z]
        bar = '█' * int(round(count / peak_rules * bar_width)) if peak_rules else ''
        table.add_row([z, count, bar])

    return table, peak_zoom, peak_rules


def main():
    parser = argparse.ArgumentParser(description='Analyse Mapnik XML rendering complexity per zoom level')
    parser.add_argument('mapnik_xml', help='Compiled Mapnik XML file')
    parser.add_argument('--json', dest='json_output', metavar='FILE',
                        help='Save results as JSON to FILE')
    args = parser.parse_args()

    zoom_counts, total_rules = count_rules_per_zoom(args.mapnik_xml)
    table, peak_zoom, peak_rules = render_table(zoom_counts)

    print(table)
    print(f"Total rules in stylesheet: {total_rules}")
    print(f"Peak rendering complexity: zoom {peak_zoom} ({peak_rules} active rules)")

    if args.json_output:
        data = {
            'total_rules': total_rules,
            'peak_zoom': peak_zoom,
            'peak_rules': peak_rules,
            'rules_per_zoom': {str(z): zoom_counts[z] for z in range(21)},
        }
        with open(args.json_output, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Results saved to {args.json_output}")


if __name__ == '__main__':
    main()
