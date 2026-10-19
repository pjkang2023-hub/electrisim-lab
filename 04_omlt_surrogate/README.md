# 04 - A surrogate of the factory island in EMT, and the least store rating that holds the 800 V (OMLT)

**Question.** The 800 VDC factory islanded at full load (the grid lost at 20 ms, the turbine off):
Electrisim's EMT study shows the racks ride through on bus stores of 7 MW (6 MW in Hall B), and are
lost on the drawn 2.5 MW. What is the least store-converter rating that holds every 800 V bus at
0.92 pu or above with no rack lost - searched over a surrogate of EMT, not run by run?

**Inputs** (each EMT run, `emt_sample.py`, Electrisim's own Python, read-only, 50-80 s):
lineup store converters (Lineup A, B and the catcher's, each) 2.5-8 MW; Hall B's two store
converters 2.5-7 MW; the easing floor of all twelve lineup rectifiers and Hall B's three SSTs
(each easing below 0.85 pu, back over 5 s) 0.1-1.0. **Output:** the lowest 800 V bus voltage over
300 ms, racks lost, converters blocked. **Cost** to minimise: 3 lineup + 2 Hall B converter MW.

**Method.**
1. `sweep.py`: 96 Latin-hypercube points and the 8 corners, five EMT runs at a time (about 1.5 h).
2. `surrogate.py`: a ReLU network (scikit-learn, 16 x 16) fitted to the lowest 800 V; its weights
   written into OMLT's network definition; the least converter rating subject to the network's
   800 V at the limit - an exact MILP of the network, solved with HiGHS; checked in EMT.
3. `adaptive.py`: the same over an ensemble of three networks (every one must predict the limit),
   checked in EMT each round; a design that fails joins the data and the networks are refitted.
4. Probes by hand in EMT around the best confirmed design, along what the runs showed matters.

125 EMT runs in all (`samples.jsonl`).

## Results (18-19 October 2026)

**The sweep: a cliff.** 104 runs, none failed. 74 of 105 lose racks (the lowest 800 V near 0); 15
hold 0.92 pu. Two ways to fail: **Catcher B's rectifiers block** (the 800 V near 0.79-0.81 pu, a
rack or more lost), or **Hall B collapses** (its SSTs and stores blocking). Neighbouring designs can
land on either side. The best sweep run that holds: 28.5 MW.

**One surrogate alone: wrong.** Cross-validated error 0.13 pu on average, 0.50 pu at the 90th
percentile; pass/fail right 89.5 % of the time. Its optimum - 22.7 MW, "0.92 pu" - in EMT: Hall B
collapses, 10 racks lost. The optimiser went straight to where the surrogate was most wrong.

**Ensemble, verified and refitted.**

| Loop | Round | Lineup (MW) | Hall B (MW) | Floor | Total (MW) | EMT lowest 800 V | Racks lost |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 4.30 | 5.11 | 0.66 | 23.13 | 0.797 pu | 1 |
| 1 | 2 | 4.72 | 4.43 | 0.92 | 23.00 | 0.916 pu | 0 (under the limit) |
| 1 | 3 | 5.70 | 4.62 | 1.00 | 26.33 | 0.935 pu | 0 - confirmed |
| 2 | 1 | 3.77 | 4.36 | 0.10 | **20.02** | 0.944 pu | 0 - confirmed |
| 3 | 1-3 | 4.58 / 4.12 / 4.99 | 4.63 / 5.11 / 4.61 | 0.88 / 0.79 / 0.72 | 23.0 / 22.6 / 24.2 | 0.911 / 0.794 / 0.921 | 0 / 1 / 0 |

The loop does not improve steadily: each round goes where the networks are unsure, and the third
never returned to the 20 MW region. It finds designs that hold; it does not find the least.

**Probes around 20 MW** (floor 0.1 unless stated):

| Lineup (MW) | Hall B (MW) | Total (MW) | Lowest 800 V | Racks lost |
|---|---|---|---|---|
| 3.77 | 4.36, floor **0.2** | 20.0 | 0.227 pu | 12 - the floor is the knife-edge |
| 3.58 | 4.14 | 19.0 | 0.942 pu | 0 |
| 3.20 | 3.80 | **17.2** | **0.935 pu** | **0** |
| 2.90 | 3.80 | **16.3** | 0.923 pu | 0 - just |
| 3.20 | 3.65 | 16.9 | 0.919 pu | 10 |
| 3.00 | 3.50 | 16.0 | collapses | 10 |
| 2.60 | 3.80 | 15.4 | collapses | 22 |

## What it shows

1. **17.2 MW of store converters holds the island** - lineup stores 3.2 MW each, Hall B's 3.8 MW
   each, the rectifiers and SSTs easing to a 0.1 floor - at 0.935 pu with no rack lost: **half the
   study's 33 MW variant (7 and 6 MW)**. 16.3 MW (2.9 MW lineup stores) holds too, at 0.923 pu, on
   the edge.
2. **Easing makes it possible, and its floor is the knife-edge.** At a 0.1 floor the rectifiers and
   SSTs hand their buses to the stores and nothing but the eSTATCOM blocks; at 0.2 the same stores
   collapse the lineups (12 racks lost); at 1.0 (no easing) it takes 26 MW. The stores must then
   carry their bus: Hall B's racks draw about 7.3 MW at the training cycle's mean, and its two stores
   hold from 3.8 MW each, not 3.5 or 3.65.
3. **A surrogate over a cliff proposes; EMT decides.** One network proposed a design that lost ten
   racks; an ensemble that must agree, checked in EMT each round, found designs that hold (26.3, then
   20.0 MW); the runs it produced then pointed the probes to 17.2 MW. Surrogate, verification and
   physical reasoning together - none alone.
4. **For the design:** the rectifiers' and SSTs' easing floor is worth specifying as tightly as the
   store converters' rating (a question for the vendors, beside the 800 VDC study's F-01 and F-07).

## Limits

- One scenario (islanding at full load at 20 ms), 300 ms of EMT; one easing threshold (0.85 pu);
  the stores' energy is not the limit over 300 ms.
- The lineup and catcher stores share one rating, Hall B's two another.
- 16.3-17.2 MW is the least found, not proven: the floor between 0.1 and 0.2, and unequal lineup
  ratings, were not searched.
