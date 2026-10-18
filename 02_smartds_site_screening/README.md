# 02 - Where can a data center connect on a real-looking utility feeder? (SMART-DS + Electrisim)

**Question.** Electrisim's Data Center Site Screening has only been run on hand-built networks. On a
realistic utility feeder, how much load can a site take, where, and what limits it?

**Data.** One SMART-DS substation (NREL, CC BY 4.0): Austin rural region P1R, 2018,
`base_timeseries/opendss_no_loadshapes/p1rhs0_1247` - a 16 MVA 69/12.47 kV substation with a voltage
regulator and two feeders, 357 distribution transformers, 8.44 MW at peak. 21 text files, 1.1 MB,
fetched by `fetch_smartds.py` into `../data/smartds/` (git-ignored).

**Method.** All three scripts run with Electrisim's own Python (it has OpenDSSDirect.py and
pandapower), and use Electrisim's backend read-only.

1. `convert_feeder.py` solves the substation in OpenDSS at its peak loads and reduces it to its
   medium-voltage network as a balanced pandapower net: every line between buses of 1 kV and above
   as a positive-sequence section (sections under 1 mOhm - switches and jumpers - as closed bus-bus
   switches), the substation transformer at the tap its regulator settled on (1.0375), and each
   distribution transformer with everything behind it as a load equal to the power OpenDSS has
   entering its primary.
2. `screen_sites.py` adds candidate sites - the substation's 12.47 kV bus, each feeder's head, and
   each feeder's electrical middle and far end (by impedance from the substation) - and calls
   Electrisim's `site_screening_analysis()`, the function the app's study runs: headroom by
   bisection, sizes 1, 2 and 5 MW at 0.95 pf, limits 0.95-1.05 pu and 100 % loading, N-1 of the
   substation transformer.
3. `binding_limits.py` sets each site 5 % past its headroom and lists what the screening counts.

## The conversion against OpenDSS

| | pandapower (balanced, MV) | OpenDSS (unbalanced, full) |
|---|---|---|
| Source | 8.437 MW, 2.322 Mvar | 8.442 MW, 2.364 Mvar |
| Bus voltages | mean difference 0.002 pu, worst 0.0097 pu | |
| Lowest voltage | 0.980 pu | 0.975 pu |

The worst differences are the phase unbalance a balanced model cannot carry.

## Results (18 October 2026)

| Site | Impedance from the substation | Headroom | What limits it |
|---|---|---|---|
| Substation 12.47 kV bus | 0 | **6.59 MW** | the 16 MVA substation transformer (102 % just past it) |
| Feeder 1 head | 0.004 ohm | 6.58 MW | the substation transformer |
| Feeder 1 middle | 3.95 ohm | 2.02 MW | voltage: 0.947 pu at the feeder's end |
| Feeder 1 far end | 7.88 ohm | 0.86 MW | voltage at the site itself |
| Feeder 2 head | 0.005 ohm | 4.23 MW | the feeder's first section (102 % of its 325 A) |
| Feeder 2 middle | 6.12 ohm | 0.96 MW | the feeder's head breaker section (101 %) |
| Feeder 2 far end | 11.75 ohm | 0.59 MW | voltage at the site itself |

N-1 of the substation transformer de-energises everything (one violation at every site): the
substation is radial, with no second transformer or tie.

## What it shows

1. **The screening works on a real-looking utility network**, converted automatically from OpenDSS.
2. **A 5-10 MW data center does not fit this rural substation as it is.** The most any site can take
   is 6.59 MW at the substation's 12.47 kV bus, set by the transformer's 16 MVA with the feeders' own
   8.4 MW on it. Five MW on Feeder 2's head overloads its first section (108 %).
3. **Headroom collapses along a rural feeder:** to 2 MW halfway along Feeder 1 and under 1 MW at the
   ends, set by voltage, not by thermal ratings. Feeder 2's head section limits everything on it.
4. **N-1 is meaningless here** without a second source; a data center on this substation would need
   a dedicated 69 kV supply or a second transformer, which the screening says plainly.

## Limits

- Balanced (positive-sequence) reduction: unbalance, single-phase laterals' phase voltages and the
  low-voltage networks are not screened (they are inside each lumped load).
- The regulator held at the tap OpenDSS settled on at peak; it does not move with the site's load.
- Peak load only (`opendss_no_loadshapes`); the 15-minute profiles would give an annual view.

## Next, if wanted

- The same on an urban SMART-DS region (P1U-P5U), with meshed sub-transmission and more transformers.
- Hand the converted net to the app as a drawing (Electrisim imports pandapower `.py` scripts).
