#!/usr/bin/env python3
"""
Non-regression test for the CyclOSM CartoCSS style.

Compares metrics extracted from a compiled Mapnik XML file against a committed
baseline. Fails (exit 1) if any metric has changed unexpectedly.

The build is deterministic: same project.mml → same mapnik.xml → same metrics.
Any unintended change to a .mss file or project.mml will be caught here.

Usage:
    # Run regression check (baseline must exist):
    python3 scripts/test_non_regression.py mapnik.xml

    # Generate or update the baseline:
    python3 scripts/test_non_regression.py mapnik.xml --update

    # Explicit baseline path:
    python3 scripts/test_non_regression.py mapnik.xml --baseline scripts/perf_baseline.json

Workflow for intentional style changes:
    ./kosmtik/node_modules/.bin/carto project.mml -f mapnik.xml
    python3 scripts/test_non_regression.py mapnik.xml --update
    git add scripts/perf_baseline.json && git commit -m "chore: update non-regression baseline"
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

DEFAULT_BASELINE = os.path.join(os.path.dirname(__file__), 'perf_baseline.json')

# OSM tile scale denominator per zoom level: 559082264 / 2^z
ZOOM_SCALE = {z: 559082264.028717 / (2 ** z) for z in range(21)}


def compute_metrics(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    zoom_counts = defaultdict(int)
    total_rules = 0
    layer_count = len(root.findall('.//Layer'))

    for rule in root.iter('Rule'):
        total_rules += 1
        max_sd = rule.findtext('MaxScaleDenominator')
        min_sd = rule.findtext('MinScaleDenominator')
        max_sd = float(max_sd) if max_sd else float('inf')
        min_sd = float(min_sd) if min_sd else 0.0

        for z, scale in ZOOM_SCALE.items():
            if min_sd <= scale <= max_sd:
                zoom_counts[z] += 1

    return {
        'total_rules': total_rules,
        'layer_count': layer_count,
        'rules_per_zoom': {str(z): zoom_counts[z] for z in range(21)},
    }


def load_baseline(path):
    with open(path) as f:
        return json.load(f)


def save_baseline(metrics, path):
    with open(path, 'w') as f:
        json.dump(metrics, f, indent=2)
        f.write('\n')


def check_regression(current, baseline):
    diffs = []

    for key in ('total_rules', 'layer_count'):
        cur_val = current[key]
        base_val = baseline.get(key)
        if base_val is None:
            diffs.append(f"  {key} : manquant dans la baseline (actuel : {cur_val})")
        elif cur_val != base_val:
            delta = cur_val - base_val
            sign = '+' if delta > 0 else ''
            diffs.append(f"  {key} : attendu {base_val}, obtenu {cur_val} ({sign}{delta})")

    base_zoom = baseline.get('rules_per_zoom', {})
    for z in range(21):
        key = str(z)
        cur_val = current['rules_per_zoom'][key]
        base_val = base_zoom.get(key)
        if base_val is None:
            diffs.append(f"  zoom {z:2d} : absent de la baseline (actuel : {cur_val})")
        elif cur_val != base_val:
            delta = cur_val - base_val
            sign = '+' if delta > 0 else ''
            diffs.append(f"  zoom {z:2d} : attendu {base_val} règles, obtenu {cur_val} ({sign}{delta})")

    return diffs


def main():
    parser = argparse.ArgumentParser(
        description='Non-regression test for CyclOSM Mapnik XML metrics')
    parser.add_argument('mapnik_xml', help='Compiled Mapnik XML file')
    parser.add_argument('--baseline', default=DEFAULT_BASELINE,
                        help=f'Baseline JSON file (default: {DEFAULT_BASELINE})')
    parser.add_argument('--update', action='store_true',
                        help='Generate or overwrite the baseline with current metrics')
    args = parser.parse_args()

    if not os.path.exists(args.mapnik_xml):
        print(f"Erreur : fichier introuvable : {args.mapnik_xml}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyse de {args.mapnik_xml} ...")
    current = compute_metrics(args.mapnik_xml)
    print(f"  total_rules  : {current['total_rules']}")
    print(f"  layer_count  : {current['layer_count']}")
    print(f"  pic de complexité : zoom {max(current['rules_per_zoom'], key=lambda z: current['rules_per_zoom'][z])} "
          f"({max(current['rules_per_zoom'].values())} règles actives)")

    if args.update:
        save_baseline(current, args.baseline)
        print(f"\nBaseline mise à jour : {args.baseline}")
        sys.exit(0)

    if not os.path.exists(args.baseline):
        save_baseline(current, args.baseline)
        print(f"\nBaseline créée : {args.baseline}")
        print("Committez ce fichier pour activer les tests de non-régression :")
        print(f"  git add {args.baseline}")
        sys.exit(0)

    baseline = load_baseline(args.baseline)
    diffs = check_regression(current, baseline)

    if not diffs:
        print("\nAucune régression détectée.")
        sys.exit(0)

    print("\nRÉGRESSION DÉTECTÉE :")
    for line in diffs:
        print(line)
    print("\nSi ce changement est intentionnel, mettez à jour la baseline :")
    print(f"  python3 {__file__} {args.mapnik_xml} --update")
    sys.exit(1)


if __name__ == '__main__':
    main()
