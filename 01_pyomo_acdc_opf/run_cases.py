"""Runs every case of experiment 01 and writes results.json beside this script."""
import json
import os

import acdc_opf as A

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = [
    # (label, reference, mode, blocks out, batteries, branch limits, lf load-side voltage)
    ('3 blocks: load-flow check', 'reference_pcs3750_mv', 'lf', (), False, False, 0.99771),
    ('3 blocks: OPF, ratings off', 'reference_pcs3750_mv', 'opf', (), False, False, None),
    ('3 blocks: OPF, transformer ratings on', 'reference_pcs3750_mv', 'opf', (), False, True, None),
    ('3 blocks: OPF, ratings on, batteries may help', 'reference_pcs3750_mv', 'opf', (), True, True, None),
    ('3 blocks: least shed, ratings on', 'reference_pcs3750_mv', 'shed', (), False, True, None),
    ('3 blocks, Block 3 out: least shed, ratings off', 'reference_pcs3750_mv', 'shed', ('B3',), False, False, None),
    ('3 blocks, Block 3 out: least shed, ratings off, batteries', 'reference_pcs3750_mv', 'shed', ('B3',), True, False, None),
    ('3 blocks, Block 3 out: least shed, ratings on', 'reference_pcs3750_mv', 'shed', ('B3',), False, True, None),
    ('3 blocks, Block 3 out: least shed, ratings on, batteries', 'reference_pcs3750_mv', 'shed', ('B3',), True, True, None),
    ('9 blocks: OPF, ratings on', 'reference_pcs3750_mv_9blocks', 'opf', (), False, True, None),
    ('9 blocks, Block 9 out: least shed, ratings off', 'reference_pcs3750_mv_9blocks', 'shed', ('B9',), False, False, None),
    ('9 blocks, Block 9 out: least shed, ratings on', 'reference_pcs3750_mv_9blocks', 'shed', ('B9',), False, True, None),
    ('9 blocks, Block 9 out: least shed, ratings on, batteries', 'reference_pcs3750_mv_9blocks', 'shed', ('B9',), True, True, None),
]

results = []
for label, ref, mode, out, bats, limits, v_load in CASES:
    with open(os.path.join(A.LAB, 'refs', f'{ref}.spec.json'), encoding='utf-8') as fh:
        spec = json.load(fh)
    m = A.build(spec, mode, out, bats, branch_limits=limits)
    if v_load:
        for g in m.G:
            m.V[m.meta['G'][g]['bus']].fix(v_load)
    status = A.solve(m)
    r = A.report(m, label)
    r['status'] = status
    results.append(r)
    t = r['trafo_loading_pct']
    print(f"{label:60s} {status:10s} grid {r['grid_p_mw']:8.4f} MW  racks {r['racks_served_mw']:7.4f}  "
          f"shed {sum(r['racks_shed_mw'].values()):6.4f}  batt {r['battery_mw']:6.4f}  "
          f"GFM {r['gfm_loading_pct']:6.2f} %  T max {max(t.values()):6.1f} %  V max {max(r['v_pu'].values()):.4f}")
with open(os.path.join(HERE, 'results.json'), 'w', encoding='utf-8') as fh:
    json.dump(results, fh, indent=1)
