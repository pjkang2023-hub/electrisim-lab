# 03 - The 800 VDC factory's storage and turbine over a year (PyPSA)

**Question.** Electrisim's studies check whether a design survives its disturbances; they do not
choose the design. Over a year of hourly operation against a tariff: how large a substation battery
pays for itself, how much should the gas turbine run, and what does the study's back-up requirement
(10 minutes of the whole site from storage) cost net of what the battery earns?

**Model** (`factory_year.py`, PyPSA 1.4 with HiGHS): the factory as one 34.5 kV bus, 8,760 hours.
Every figure below rests on these **assumptions** - none is from the whitepaper; all are set in
`CASE_DEFAULTS`:

| | Assumed |
|---|---|
| Load | racks at the training cycle's mean, 17.9 MW, flat all year; cooling 2.65 MW mean, +-30 % by season (July peak) and +-15 % by hour (15:00 peak) - the study's 20.55 MW day; 21.86 MW peak, 180 GWh a year |
| Utility | up to 40 MW (one 40 MVA transformer, N-1); 50 $/MWh off-peak (22:00-07:00), 70 mid, 150 on-peak (14:00-20:00, June-September); a demand charge of 15 $/kW-month in some cases |
| Gas turbine | 35 MW at 60 $/MWh (the study's marginal cost); linear, no minimum load; its fixed costs left out |
| Battery | power and energy sized by the optimiser; one converter, 96 % each way; 60,000 $/MW-yr and 25,000 $/MWh-yr annualised (about 450 $/kW and 190 $/kWh at 8 % over 15 years); no degradation |
| Back-up | when required: the converter at least the site's peak (21.86 MW) and never less than 10 minutes of it stored (3.8 MWh) |

## Results (18 October 2026)

| Case | Cost a year | Utility | Turbine | Battery |
|---|---|---|---|---|
| Turbine dispatched, no battery | 10.14 M$ | 66.5 GWh, off-peak only | 113.5 GWh (3,243 h at full load) | - |
| - battery sized freely | 10.14 M$ | the same | the same | **none built** |
| - back-up required | 11.54 M$ | the same | the same | 21.86 MW / 3.8 MWh, 1.41 M$, **0 cycles** |
| - demand charge 15 $/kW-month | 10.80 M$ | none | 180 GWh (5,143 h) | none built |
| - on-peak 300 $/MWh | 10.14 M$ | the same as base | the same | none built |
| - gas at 90 $/MWh | 11.59 M$ | 164 GWh | 15.8 GWh (452 h) | none built |
| Turbine on standby, no battery | 12.54 M$ | 180 GWh | - | - |
| - battery sized freely | 12.54 M$ | 180 GWh | - | none built |
| - back-up required | 13.94 M$ | 180 GWh | - | 21.86 MW / 3.8 MWh, 0 cycles |
| - demand charge, no battery | 16.33 M$ | 180 GWh, peak 21.86 MW | - | - |
| - demand charge, battery freely | 16.32 M$ | peak 21.60 MW | - | 0.27 MW / 1.57 MWh, 365 cycles |
| - demand charge, back-up required | 17.71 M$ | peak 21.48 MW | - | 21.86 MW / 6.33 MWh, 144 cycles |
| - demand charge, on-peak 300, battery freely | 18.65 M$ | peak 21.58 MW | - | 0.50 MW / 3.36 MWh, 338 cycles |

## What it shows

1. **No battery pays for itself here.** A 35 MW turbine at 60 $/MWh, larger than the whole site,
   caps every hour's price at 60 $/MWh: the utility is bought only off-peak at 50, and a battery's
   only arbitrage is the 10 $/MWh between them - less than its losses and capital. Even with the
   turbine on standby, the factory's flat load (racks run flat) leaves almost no peak to shave: a
   15 $/kW-month demand charge buys a 0.27 MW battery that saves 11 k$ a year.
2. **The back-up requirement is a pure cost: about 1.4 M$ a year**, 14 % of the site's energy bill,
   and 93 % of it is the converter's 21.86 MW, not the 3.8 MWh. It earns almost nothing back - no
   cycles at all while the turbine runs; with the turbine on standby and a demand charge it saves
   0.1 M$ of its 1.47 M$. This agrees with the Electrisim study: power, not stored energy, decides
   ride-through and back-up - and a year's dispatch adds that the power is what costs.
3. **Dispatching the turbine saves 2.4 M$ a year** over buying everything from the utility
   (10.14 against 12.54 M$, before the turbine's fixed costs); with a demand charge it runs flat
   all year (5,143 full-load hours) to keep the utility's peak at zero.
4. **The answer turns on the gas price:** at 90 $/MWh the turbine runs only 452 hours, in the
   on-peak afternoons.

## Limits

- One bus: no network limits (Electrisim's studies cover those); hourly steps, so the training
  cycle's sub-second swings and their storage tiers are not seen here.
- No unit commitment (minimum load, start costs) for the turbine; no battery degradation.
- The load and tariff are stylised, not a utility's; a real tariff and the site's measured load
  would replace them.
