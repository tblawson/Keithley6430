# -*- coding: utf-8 -*-
"""
Updated calculation of measured current uncertainty of a current source, using a
sense resistor, Rs, and DVM connected across Rs, accounting for dvm input impedance.
"""
import GTC
import json
import datetime as dt
import os


'''
# ------------------------
Useful Classes / Functions
--------------------------
'''


class UrealEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, GTC.lib.UncertainReal):
            return {'__ureal__': True, 'val': obj.x, 'unc': obj.u, 'dof': obj.df}
        return super().default(obj)


def as_ureal(dct):
    if '__ureal__' in dct:
        return GTC.ureal(dct['val'], dct['unc'], dct['dof'])
    else:
        return dct


# import Resistor info to RESISTORS dict
with open('RESISTORS.json', 'r') as Resistors_fp:
    RESISTORS = json.load(Resistors_fp, object_hook=as_ureal)

# import dvm R-input info to DVM_RIN dict
folder = r'G:\My Drive\TechProcDev\Keithley6430-src-meter_Light'
sn = '452'  # input('\nEnter last 3 digits of 3458A serial number: ')
dvm_Rin_filename = os.path.join(folder, f'HP3458A-{sn}_Rin.json')
with open(f'{dvm_Rin_filename}', 'r') as Rin_fp:
    DVM_RIN = json.load(Rin_fp, object_hook=as_ureal)


#  Rs
R_name = input(f'{RESISTORS.keys()}\nSelect sense resistor: ')

R0 = RESISTORS[R_name]['R0']
alpha = RESISTORS[R_name]['alpha']
T0 = RESISTORS[R_name]['T0']
gamma = RESISTORS[R_name]['gamma']
V0 = RESISTORS[R_name]['V0']
tau = RESISTORS[R_name]['tau']
t0 = RESISTORS[R_name]['t0']
t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')

#  V measurements

# Grab a temperature reading
T_val = 20.5  # input('Rs temperature?: ')
T = GTC.ureal(float(T_val), 0.05, 8, 'T')  # Resistor temp with type-B uncert.
t = dt.datetime.now()
t_str = t.strftime('%d/%m/%Y %H:%M:%S')
delta_t = t - t0_dt  # datetime.timedelta object
delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds / 86400 + delta_t.microseconds / 8.64e10, 0.1, 8,
                         'delta_t_days')

V_off = GTC.ureal(6e-7, 3e-8, 9, 'V_off')
V_on_val = float(input(f'Measured Vs value: '))
V_on = GTC.ureal(V_on_val, 1e-7, 9, 'V_on')

#  DVM input
key = f'{R_name}_V{V_on.x}'
Rdvm = DVM_RIN[key]['Rin_approx']  # GTC.ureal(1e12, 1.6e11, 10, 'Rdvm')

#  Sense Resistor
Rs = R0*(1 + alpha*(T - T0) + gamma*(V_on - V0) + tau*delta_t_days)

#  Total parallel resistance (including input-Z of DVM)
Rpar = Rs*Rdvm/(Rs+Rdvm)

#  Current:
Imeas = (V_on - V_off) / Rpar

params = {'V1': V_off,
          'V2': V_on,
          'R0': R0,
          'alpha': alpha,
          'T': T,
          'T0': T0,
          'gamma': gamma,
          'V0': V0,
          'tau': tau,
          'delta_t': delta_t_days,
          'Rdvm': Rdvm}

print('Parameter\tUncert. \tSens. coef.\tU contrib (A)')
for param in params:
    sens = GTC.reporting.sensitivity(Imeas, params[param])
    u_cont = GTC.component(Imeas, params[param])
    unc = params[param].u
    print(f'{param:9}\t{unc:9.3g}\t{sens:11.3g}\t{u_cont:13.3g}')

print(f'\nI = {Imeas.x:.6e} +/- {Imeas.u:.1e}, dof = {Imeas.df:.1f}')
