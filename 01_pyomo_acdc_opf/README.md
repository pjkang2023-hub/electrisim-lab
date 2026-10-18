# 01 - An AC/DC optimal power flow on the PCS3750C-MV reference (Pyomo + Ipopt)

**Question.** Electrisim's OPF (pandapower's `runopp`) leaves the DC network out and treats each
grid-forming inverter as a generator in a P-Q box. Can an AC/DC OPF that keeps the DC buses, each
converter's rating circle and the 0.6 S reactive cap, and the batteries, answer what Electrisim's
cannot: the least load to shed when no dispatch exists?

**Model** (`acdc_opf.py`), built from `refs/<ref>.spec.json`, not Electrisim's internal network:
polar AC power flow per unit on 1 MVA (lines as pi sections; transformers with their 2.25 kW iron
loss and 0.1 % magnetising current, as Electrisim's builder sets them); each DC quadrant a node where
its AFE (reactor loss r S^2 / V^2) and batteries feed its grid-forming inverter (98.5 %); each AFE and
inverter within its derated rating (994 kVA at 40 C) times min(V, 1); inverter |Q| <= 0.6 S; each SST
a constant-power MV load (99 % DC/DC and 98.5 % rectifier, 7 kW no-load each). Batteries discharge
only when allowed, priced at twice the grid's energy; no export at the POI.

**Run.** `..\.venv\Scripts\python.exe run_cases.py` (all cases, `results.json`), or
`acdc_opf.py --mode lf|opf|shed [--out B3] [--batteries] [--no-branch-limits] [--ref ...]`.
`capture_net.py` and `dump_lf.py` (run with Electrisim's own Python, read-only) give the yardstick:
Electrisim's load flow, `reference_pcs3750_mv.lf_result.json`.

## Results (18 October 2026)

| Case | Ipopt | Grid (MW) | Racks served (MW) | Shed (MW) | Batteries (MW) | Inverters | Transformers max |
|---|---|---|---|---|---|---|---|
| 3 blocks: load-flow check (Electrisim's controls) | optimal | 11.6628 | 10.80 | 0 | 0 | 94.1 % | 103.9 % |
| 3 blocks: OPF, ratings off | optimal | 11.6459 | 10.80 | 0 | 0 | 93.9 % | 103.5 % |
| 3 blocks: OPF, transformer ratings on | **infeasible** | - | - | - | - | - | - |
| 3 blocks: OPF, ratings on, batteries may help | optimal | 11.25 | 10.80 | 0 | 0.38 | 93.9 % | 100 % |
| 3 blocks: least shed, ratings on | optimal | 11.25 | 10.44 | 0.36 | 0 | 90.8 % | 100 % |
| Block 3 out: least shed, ratings off | optimal | 7.96 | 7.36 | 3.44 | 0 | 96.2 % | 106.1 % |
| Block 3 out: ratings off, batteries | optimal | 7.96 | 7.65 | 3.15 | 0.31 | 100 % | 106.1 % |
| Block 3 out: ratings on | optimal | 7.50 | 6.94 | 3.86 | 0 | 90.8 % | 100 % |
| Block 3 out: ratings on, batteries | optimal | 7.50 | 7.65 | 3.15 | 0.74 | 100 % | 100 % |
| 9 blocks: OPF, ratings on | optimal | 32.29 | 30.00 | 0 | 0 | 86.9 % | 95.7 % |
| 9 blocks, Block 9 out: ratings off | optimal | 31.84 | 29.49 | 0.51 | 0 | 96.2 % | 106.1 % |
| 9 blocks, Block 9 out: ratings on | optimal | 30.00 | 27.83 | 2.17 | 0 | 90.8 % | 100 % |
| 9 blocks, Block 9 out: ratings on, batteries | optimal | 30.00 | 30.00 | 0 | 2.29 | 98.3 % | 100 % |

## What it shows

1. **The model reproduces Electrisim's load flow.** With Electrisim's controls (AFEs at no Q, the
   inverters sharing equally, the load-side buses at 0.99771 pu): grid 11.6628 MW and 0.7299 Mvar
   against 11.6635 and 0.7303; each inverter 0.9345 MW and 0.0456 Mvar against 0.9345 and 0.0455;
   each AFE 0.9633 MW; every bus voltage to four decimals.
2. **Optimised, it saves 17 kW** (11.6459 MW): the backbone raised to its 1.1 pu limit (as
   pandapower's OPF also does) and the AFEs supplying reactive power to hold their 505 V buses up.
3. **New finding: at full load each block's T1 is at 103.9 % of its 3.75 MVA.** Electrisim's load flow
   does not enforce branch ratings, and its OPF leaves the DC side out, so neither says so. With the
   transformers' ratings enforced no dispatch exists at 40 C; the least fix is 0.36 MW of racks shed,
   or 0.38 MW from the batteries for as long as they last, or a larger T1 (the block is rated
   3.977 MVA at 40 C; its T1 3.75 MVA). T2 sits at 100 %.
4. **Block 3 out: the least shed is 3.15 MW** (7.65 of 10.8 MW of racks served) - where Electrisim's
   OPF can only say that no dispatch exists. Without the batteries it is 3.44 MW: the AFEs, current-limited
   on their 0.99 pu buses, bind before the inverters (as Electrisim's study found); with T1's rating
   also enforced, 3.86 MW. Hall 3, next to the lost block, sheds the most.
5. **Nine blocks:** the OPF is feasible at full load (transformers at 95.7 %). With Block 9 out, 0.51 MW
   must go without batteries (Electrisim's load flow has the batteries give 0.65 MW instead); with T1's
   rating enforced 2.17 MW, or 2.29 MW from the batteries and nothing shed.

## Limits of the model

- Steady state at continuous ratings: no short-time overload (Electrisim's load flow lets the
  inverters share an overload within 150 % for 1 s; this OPF does not).
- No transformer taps; the utility holds the POI at 1.0 pu.
- The DC buses as single nodes (the batteries set their voltage; the DC cables' 0.1 mOhm left out).
- Batteries as power within their C-rates, not energy: "0.38 MW from the batteries" holds only for
  their 6.2 MWh a bus.
- Transformer and inverter ratings scale with voltage below nominal (current limits), as the
  specification's derating does; above nominal they hold their MVA.
