"""Paths and helpers shared by the lab dashboard's pages."""
import json
import os
import subprocess
import sys

DASH = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(DASH)
EXP = {k: os.path.join(LAB, d) for k, d in (('opf', '01_pyomo_acdc_opf'), ('feeder', '02_smartds_site_screening'),
                                             ('year', '03_pypsa_sizing'), ('surrogate', '04_omlt_surrogate'))}
LAB_PY = os.path.join(LAB, '.venv', 'Scripts', 'python.exe')
# Electrisim's own Python: the scripts that call Electrisim's backend (read-only) run with it.
ELECTRISIM_PY = os.path.join(os.path.dirname(LAB), 'electrisim', '.venv', 'Scripts', 'python.exe')

for p in EXP.values():
    if p not in sys.path:
        sys.path.insert(0, p)


def run_script(python, script, args, cwd, timeout=3600):
    """Runs one of the experiments' scripts; returns (ok, stdout, stderr)."""
    res = subprocess.run([python, script, *map(str, args)], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return res.returncode == 0, res.stdout, res.stderr


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]
