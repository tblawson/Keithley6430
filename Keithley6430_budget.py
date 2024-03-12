# -*- coding: utf-8 -*-
"""
Crude calculation of measured current uncertainty of a current source,
using a sense resistor, Rs, and DVM connected across Rs.
"""
import GTC

#  V measurements
V1 = GTC.ureal(1, 5e-7, 9, 'V1')
V2 = GTC.ureal(1e-5, 5e-7, 9, 'V2')
g1 = GTC.ureal(1.0000002, 4.2e-7, 121, 'g1')
g2 = GTC.ureal(0.99995, 0.00057, 121, 'g2')

#  DVM input
Rdvm = GTC.ureal(1e12, 1.6e11, 10, 'Rdvm')

#  Rs
R0 = GTC.ureal(999.9969, 5.0e-4, 10, 'R0')  # (999.9969, 5.0e-4, 10, 'R0') (92622082837, 1.23e8, 8.2, 'R0')
alpha = GTC.ureal(1.25e-6, 1.0e-7, 8, 'alpha')  # (1.25e-6, 1.0e-7, 8, 'alpha') (0, 1.25e-6, 8, 'alpha')
T = GTC.ureal(21.2, 0.2, 10, 'T')
T0 = GTC.ureal(21.0, 0.05, 10, 'T0')
gamma = GTC.ureal(0, 1e-9, 3, 'gamma')  # (0, 1e-9, 3, 'gamma') (-1.14e-6, 2.1e-6, 8, 'gamma')
V0 = GTC.ureal(1, 1e-6, 8, 'V0')  # (1, 1e-6, 8, 'V0') (200, 4.0e-4, 3, 'V0')
tau = GTC.ureal(8.95e-10, 6.9e-11, 5, 'tau')  # (8.95e-10, 6.9e-11, 5, 'tau') (1e-6, 1e-6, 35, 'tau')
t = GTC.ureal(45355.1, 0.1, 8, 't')
t0 = GTC.ureal(45355, 0.1, 8, 't0')

#  Sense Resistor
Rs = R0*(1 + alpha*(T-T0) + gamma*(V1-V0) + tau*(t-t0))

#  Total parallel resistance (including input-Z of DVM)
Rpar = Rs*Rdvm/(Rs+Rdvm)

#  Current:
I = (V1*g1 - V2*g2)/Rpar

params = {'V1': V1,
          'V2': V2,
          'g1': g1,
          'g2': g2,
          'R0': R0,
          'alpha': alpha,
          'T': T,
          'T0': T0,
          'gamma': gamma,
          'V0': V0,
          'tau': tau,
          't': t,
          't0': t0,
          'Rdvm': Rdvm}

for param in params:
     sens = GTC.reporting.sensitivity(I, params[param])
     u_cont = GTC.component(I, params[param])
     print(f'{param}.....Sens. coef = {sens}. U contrib = {u_cont} A')

print(f'\nI = {I.x:.6e} +/- {I.u:.1e}, dof = {I.df:.1f}')
