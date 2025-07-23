# -*- coding: utf-8 -*
"""
General-purpose input-Z measurement routine for 3458A DVMs (Step 1).

This script is the first stage in a 2-step process to obtain the input bias current
of a meter. It also provides an (unreliable) estimate of the input impedance.

The value of Ib can be used as input to R_input.py which provides a more reliable
estimate of Rin

Workflow progresses by connecting a known resistor across the dvm input
and measuring the voltage drop. Ib= V/R is then calculated from the resistor value and
the mean of the voltage readings.

If enough sets of measurements (each with a different R) are taken, values of Ib and Rin
are calculated from a fit to the accumulated data.

RESISTORS data: All uncertainties are expressed in the quantity units.
u(t0) is in [days]; tau is in [days^-1].
"""
import os
import GTC
import pyvisa as visa
import json
import datetime as dt
import time
import gmhstuff as gmh

N_READINGS = 20

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


def measure():
    az_delay = float(input('AZERO delay (s): '))
    dvm.write('LFREQ LINE')
    time.sleep(1)
    dvm.write('AZERO ONCE')
    time.sleep(az_delay)
    v_readings = []
    for n in range(N_READINGS):
        reading = dvm.read()  # dvm.query('READ?')
        print(reading)
        v_readings.append(float(reading))
    dvm.write('AZERO ON')
    if len(v_readings) > 1:
        v_av = GTC.ta.estimate(v_readings)
    else:
        v_av = 0  # No valid readings!
    return v_av, v_readings

# --------------------------------


"""
---------------------------------
I/O Section & data storage
---------------------------------
"""
# import Resistor info to RESISTORS dict
with open('RESISTORS.json', 'r') as Resistors_fp:
    RESISTORS = json.load(Resistors_fp, object_hook=as_ureal)

# Data files
folder = input('Data directory: ')
# folder = r'G:\My Drive\TechProcDev\Keithley6430-src-meter_Light'
sn = input('\nEnter last 3 digits of 3458A serial number: ')
ib_Rin_filename = os.path.join(folder, f'HP3458A-{sn}_Ib_Rin.json')

"""
---------------------------------
Instruments Section
---------------------------------
"""
# GPIB connection and dvm initialisation
RM = visa.ResourceManager()
print('\navailable visa resources:'
      f'\n{RM.list_resources()}')
addr = input('\nEnter dvm GPIB address: ')
try:
    dvm = RM.open_resource(f'GPIB1::{addr}::INSTR')
    dvm.read_termination = '\r\n'
    dvm.write_termination = '\r\n'
    dvm.timeout = 2000
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection!')

rply = dvm.query('ID?')
print(f'DVM at GPIB addr {addr} response: {rply}')
dvm.write('DCV 0; NPLC 20; AZERO ON')  # DCV 100 mV range; Sample every 0.4 s; Autozero

# GMH probe setup
port = input('\nEnter GMH-probe COM port number: ')
gmh530 = gmh.GMHSensor(port)
print(f'gmh530 test-read: {gmh530.measure("T")}')

"""
-------------------------------
Measurement Section starts here:
-------------------------------
"""
try:
    with open(f'{ib_Rin_filename}', 'r') as Ib_Rin_fp:  # Open existing results file so we can add to it.
        results = json.load(Ib_Rin_fp, object_hook=as_ureal)
except (FileNotFoundError, IOError):
    results = {}  # Create results dict, if it doesn't exist as a json file yet.
while True:
    # Test setup
    R_name = input(f'\nSelect resistor connected across DVM output (or Enter to break loop)\n{RESISTORS.keys()}: ')
    if R_name == '':
        break  # END OF PROGRAM
    R0 = RESISTORS[R_name]['R0']
    alpha = RESISTORS[R_name]['alpha']
    T0 = RESISTORS[R_name]['T0']
    gamma = RESISTORS[R_name]['gamma']
    V0 = RESISTORS[R_name]['V0']
    tau = RESISTORS[R_name]['tau']
    t0 = RESISTORS[R_name]['t0']
    t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')

    # Grab a temperature reading
    T = GTC.ureal(float(gmh530.measure('T')[0]), 0.05, 8, 'T')  # Resistor temp with type-B uncert.
    t = dt.datetime.now()
    t_str = t.strftime('%d/%m/%Y %H:%M:%S')
    delta_t = t - t0_dt  # datetime.timedelta object
    delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds/86400 + delta_t.microseconds/8.64e10, 0.1, 8, 'delta_t_days')

    # The actual measurements happen here:
    V_av, V_readings = measure()  # Measure V with Rs connected (ureal, list of floats)

    # Calculate Ib and collate data
    R = R0*(1 + alpha * (T-T0) + gamma * (V_av - V0) + tau * delta_t_days)
    print(f'\nTest resistor (corrected) = {R:1.3e}')
    Ib_approx = V_av / R  # Approx calculation, using a specific shunt resistor
    print(f'Input bias I = {Ib_approx:1.3e}')

    # Compile results dict
    Ib_result = {R_name: {'T': T, 't': t_str, 'R': R,
                          'V': V_av, 'V_data': V_readings,
                          'Ib_approx': Ib_approx
                          }
                 }
    results.update(Ib_result)
# End of measurement loop for this resistor

print(f'\n{results}\n')

if len(results) > 3:
    # Do full calculation
    inv_R = []
    inv_V = []
    for res_name in results:
        if res_name not in ['Ib', 'Rin']:
            inv_R.append(1/results[res_name]['R'])
            inv_V.append(1/results[res_name]['V'])
    inv_R_vals = [r.x for r in inv_R]
    inv_R_uncs = [r.u for r in inv_R]
    inv_V_vals = [v.x for v in inv_V]
    inv_V_uncs = [v.u for v in inv_V]

    # c, m = GTC.ta.line_fit_wtls(inv_R_vals, inv_V_vals, inv_R_uncs, inv_V_uncs).a_b
    c, m = GTC.ta.line_fit_wls(inv_R_vals, inv_V_vals, inv_V_uncs).a_b

    Ib = 1/m  # Ib from fit of all Rs's
    Rin = m/c
    results.update({'Ib': Ib, 'Rin': Rin})
    print(f'Final calculated values:\nIb = {Ib}\nRin = {Rin}')

# Store data
print(f'Storing data in "{ib_Rin_filename}"...')
with open(f'{ib_Rin_filename}', 'w') as json_file:
    json.dump(results, json_file, indent=4, cls=UrealEncoder)
