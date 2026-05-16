#!/usr/bin/env python3
"""
Non-regression test for the CyclOSM CartoCSS style.

Compares metrics extracted from a compiled Mapnik XML file against a committed
baseline. Uses directional comparisons for performance metrics:

  - total_rules, rules_per_zoom : FAIL if value INCREASES (more rules = more
    render work). A decrease is an improvement: warns but does not fail.
  - layer_count : exact match in both directions (adding or removing a layer
    is always a functional change).

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
    """
    Returns (regressions, improvements) as lists of human-readable strings.

    Regressions cause exit 1; improvements are warnings that suggest --update.
    """
    regressions = []
    improvements = []

    # layer_count: exact match (functional change in both directions)
    cur_layers = current['layer_count']
    base_layers = baseline.get('layer_count')
    if base_layers is None:
        regressions.append(f"  layer_count : absent de la baseline (actuel : {cur_layers})")
    elif cur_layers != base_layers:
        delta = cur_layers - base_layers
        sign = '+' if delta > 0 else ''
        regressions.append(
            f"  layer_count : attendu {base_layers}, obtenu {cur_layers} ({sign}{delta})"
        )

    # total_rules: directional — fail only if increases
    cur_total = current['total_rules']
    base_total = baseline.get('total_rules')
    if base_total is None:
        regressions.append(f"  total_rules : absent de la baseline (actuel : {cur_total})")
    elif cur_total > base_total:
        delta = cur_total - base_total
        regressions.append(
            f"  total_rules : attendu ≤ {base_total}, obtenu {cur_total} (+{delta})"
        )
    elif cur_total < base_total:
        delta = base_total - cur_total
        improvements.append(
            f"  total_rules : était {base_total}, maintenant {cur_total} (-{delta})"
        )

    # rules_per_zoom: directional per zoom level
    base_zoom = baseline.get('rules_per_zoom', {})
    for z in range(21):
        key = str(z)
        cur_val = current['rules_per_zoom'][key]
        base_val = base_zoom.get(key)
        if base_val is None:
            regressions.append(f"  zoom {z:2d} : absent de la baseline (actuel : {cur_val})")
        elif cur_val > base_val:
            delta = cur_val - base_val
            regressions.append(
                f"  zoom {z:2d} : attendu ≤ {base_val} règles, obtenu {cur_val} (+{delta})"
            )
        elif cur_val < base_val:
            delta = base_val - cur_val
            improvements.append(
                f"  zoom {z:2d} : était {base_val} règles, maintenant {cur_val} (-{delta})"
            )

    return regressions, improvements


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
    peak_zoom = max(current['rules_per_zoom'], key=lambda z: current['rules_per_zoom'][z])
    print(f"  total_rules  : {current['total_rules']}")
    print(f"  layer_count  : {current['layer_count']}")
    print(f"  pic de complexité : zoom {peak_zoom} "
          f"({current['rules_per_zoom'][peak_zoom]} règles actives)")

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
    regressions, improvements = check_regression(current, baseline)

    if improvements and not regressions:
        print("\nAMÉLIORATION DÉTECTÉE (aucune régression) :")
        for line in improvements:
            print(line)
        print("\nPensez à mettre à jour la baseline pour verrouiller ces gains :")
        print(f"  python3 {__file__} {args.mapnik_xml} --update")
        sys.exit(0)

    if regressions:
        print("\nRÉGRESSION DÉTECTÉE :")
        for line in regressions:
            print(line)
        if improvements:
            print("\nAméliorations simultanées (non bloquantes) :")
            for line in improvements:
                print(line)
        print("\nSi ce changement est intentionnel, mettez à jour la baseline :")
        print(f"  python3 {__file__} {args.mapnik_xml} --update")
        sys.exit(1)

    print("\nAucune régression détectée.")
    sys.exit(0)


if __name__ == '__main__':
    main()
