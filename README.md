# electrisim-lab

Experiments with outside tools on Electrisim's reference networks, kept apart
from the Electrisim install (`../electrisim`). Nothing here edits Electrisim's
backend or frontend; anything worth keeping is brought into Electrisim later,
as a phase of its own.

## Rules

- Its own Python: `.venv` (Python 3.11). Never install into `../electrisim/.venv`.
- Reference networks are **copies** in `refs/`, taken from
  `electrisim/backend/tests/reference` at backend commit `3334758` (18 October 2026).
  Refresh them by copying again, never by editing them here.
- Where an experiment needs Electrisim's own result, it calls the backend
  read-only (importing it from `../electrisim/backend`) or the running app's
  API on 127.0.0.1:5000. It starts no server of its own.
- Downloads (datasets, solver binaries) go in `data/`, which git ignores.

## Setup

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ipopt (the NLP solver) is not on PyPI: COIN-OR's Windows build,
`Ipopt-3.14.20-win64-msvs2022-md.zip` from github.com/coin-or/Ipopt/releases,
unzipped into `data/ipopt/`. `check_solvers.py` checks HiGHS and Ipopt from Pyomo.

## Dashboard

Every experiment from one web page: double-click `start-dashboard.cmd` (or run
`.venv\Scripts\streamlit.exe run dashboard\app.py`), then open http://127.0.0.1:8502.
One page per experiment - set its inputs, run it, see its tables and charts. It listens on this
machine only, sends no usage statistics, and has no Deploy button (`.streamlit/config.toml`);
Electrisim's ports 5000 and 5501 are left alone. Pages 2 and 4 run Electrisim's studies with
Electrisim's own Python, read-only, as the scripts do.

## Experiments

| Folder | Question | Tools | Status |
|---|---|---|---|
| `01_pyomo_acdc_opf` | An AC/DC optimal power flow on the PCS3750C-MV reference: each inverter's S circle, the batteries on its DC buses, the 0.6 S reactive cap; and the least load to shed when no dispatch exists (Block 3 out) | Pyomo, Ipopt, HiGHS | done 18 Oct: see its README |
| `02_smartds_site_screening` | Where can a 5-10 MW data center connect on a realistic utility feeder? One SMART-DS feeder through Electrisim's site and DG interconnection screening | SMART-DS (OpenDSS), Electrisim | done 18 Oct: see its README |
| `03_pypsa_sizing` | The 800 VDC factory's substation storage and turbine sized over 8,760 h of the DGX training profile against a tariff | PyPSA, HiGHS | done 18 Oct: see its README |
| `04_omlt_surrogate` | A surrogate of the factory island's lowest 800 V from an EMT sweep, and the smallest store rating that keeps it above 0.9 pu | OMLT, Pyomo, PyTorch or ONNX | not started |

GridLAB-D is parked: its building and market models do not fit the data-center
references, and on Windows it needs Docker or a Linux VM.

## Reference networks in `refs/`

`reference_radial`, `reference_transmission`, `reference_ai_campus`,
`reference_ai_factory_800vdc`, `reference_pcs3750_mv`,
`reference_pcs3750_mv_9blocks`: each its spec (`.spec.json`) and the request
the drawn diagram sends (`.diagram_payload.json`).
