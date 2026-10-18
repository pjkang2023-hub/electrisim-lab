"""Checks the lab's solvers from Pyomo: HiGHS (LP/MILP) and Ipopt (NLP)."""
import os

import pyomo.environ as pyo

HERE = os.path.dirname(os.path.abspath(__file__))
IPOPT = os.path.join(HERE, 'data', 'ipopt', 'Ipopt-3.14.20-win64-msvs2022-md', 'bin', 'ipopt.exe')

# LP: max x + y with x + 2y <= 4, 3x + y <= 6 -> x = 1.6, y = 1.2
lp = pyo.ConcreteModel()
lp.x, lp.y = pyo.Var(within=pyo.NonNegativeReals), pyo.Var(within=pyo.NonNegativeReals)
lp.c1 = pyo.Constraint(expr=lp.x + 2 * lp.y <= 4)
lp.c2 = pyo.Constraint(expr=3 * lp.x + lp.y <= 6)
lp.obj = pyo.Objective(expr=lp.x + lp.y, sense=pyo.maximize)
pyo.SolverFactory('appsi_highs').solve(lp)
print('HiGHS:', round(pyo.value(lp.x), 6), round(pyo.value(lp.y), 6))

# NLP: min (x - 1)^2 + (y - 2)^2 on the unit circle -> (1, 2) / sqrt(5)
nlp = pyo.ConcreteModel()
nlp.x, nlp.y = pyo.Var(initialize=0.5), pyo.Var(initialize=0.5)
nlp.circle = pyo.Constraint(expr=nlp.x ** 2 + nlp.y ** 2 <= 1)
nlp.obj = pyo.Objective(expr=(nlp.x - 1) ** 2 + (nlp.y - 2) ** 2)
res = pyo.SolverFactory('ipopt', executable=IPOPT).solve(nlp)
print('Ipopt:', res.solver.termination_condition, round(pyo.value(nlp.x), 6), round(pyo.value(nlp.y), 6),
      'expected', round(1 / 5 ** 0.5, 6), round(2 / 5 ** 0.5, 6))
