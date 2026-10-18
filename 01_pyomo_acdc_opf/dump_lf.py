"""
Electrisim's load-flow answer for a captured net, as plain JSON (the yardstick for the OPF).
Run with Electrisim's Python after capture_net.py:  ..\\..\\electrisim\\.venv\\Scripts\\python.exe dump_lf.py
"""
import json
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = sys.argv[1] if len(sys.argv) > 1 else 'reference_pcs3750_mv'
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'electrisim', 'backend'))
with open(os.path.join(HERE, f'{NAME}.lf_net.pkl'), 'rb') as fh:
    net = pickle.load(fh)

aux = lambda df, i: 'electrisim_aux' in df.columns and bool(df.at[i, 'electrisim_aux'] is True)
out = {'buses': {}, 'trafos': {}, 'gens': {}, 'vscs': {}, 'loads': {}, 'ext_grid': {}}
for i in net.bus.index:
    if not aux(net.bus, i):
        out['buses'][str(net.bus.at[i, 'name'])] = {
            'vn_kv': float(net.bus.at[i, 'vn_kv']), 'vm_pu': float(net.res_bus.at[i, 'vm_pu']),
            'va_degree': float(net.res_bus.at[i, 'va_degree']),
            'min_vm_pu': float(net.bus.at[i, 'min_vm_pu']), 'max_vm_pu': float(net.bus.at[i, 'max_vm_pu'])}
for i in net.trafo.index:
    out['trafos'][str(net.trafo.at[i, 'name'])] = {
        k: float(net.trafo.at[i, k]) for k in ('sn_mva', 'vn_hv_kv', 'vn_lv_kv', 'vk_percent', 'vkr_percent', 'pfe_kw', 'i0_percent')}
    out['trafos'][str(net.trafo.at[i, 'name'])].update(
        p_hv_mw=float(net.res_trafo.at[i, 'p_hv_mw']), q_hv_mvar=float(net.res_trafo.at[i, 'q_hv_mvar']),
        pl_mw=float(net.res_trafo.at[i, 'pl_mw']))
for i in net.gen.index:
    out['gens'][str(net.gen.at[i, 'name'])] = {
        'p_mw': float(net.res_gen.at[i, 'p_mw']), 'q_mvar': float(net.res_gen.at[i, 'q_mvar']),
        'vm_pu': float(net.res_gen.at[i, 'vm_pu']), 'sn_mva': float(net.gen.at[i, 'sn_mva'])}
for i in net.vsc.index:
    out['vscs'][str(net.vsc.at[i, 'name'])] = {
        'aux': aux(net.vsc, i), 'p_mw': float(net.res_vsc.at[i, 'p_mw']), 'q_mvar': float(net.res_vsc.at[i, 'q_mvar']),
        'p_dc_mw': float(net.res_vsc.at[i, 'p_dc_mw'])}
for i in net.load.index:
    out['loads'][str(net.load.at[i, 'name'])] = {'p_mw': float(net.res_load.at[i, 'p_mw']), 'q_mvar': float(net.res_load.at[i, 'q_mvar'])}
eg = net.ext_grid.index[0]
out['ext_grid'] = {'p_mw': float(net.res_ext_grid.at[eg, 'p_mw']), 'q_mvar': float(net.res_ext_grid.at[eg, 'q_mvar'])}
with open(os.path.join(HERE, f'{NAME}.lf_result.json'), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({k: (v if k == 'ext_grid' else len(v)) for k, v in out.items()}))
print('buses', {k: round(v['vm_pu'], 4) for k, v in out['buses'].items()})
print('trafo', next(iter(out['trafos'].values())))
print('gens', list(out['gens'].items())[:2])
print('vscs (not aux)', [(k, round(v['p_mw'], 4), round(v['p_dc_mw'], 4), round(v['q_mvar'], 4)) for k, v in out['vscs'].items() if not v['aux']][:3])
print('loads', out['loads'])
