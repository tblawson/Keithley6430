# -*- coding: utf-8 -*
"""
General-purpose input-Z measurement routine for 3458A DVMs (Step 2).

This script is the second stage in a 2-step process to obtain the input impedance
of a meter.

The value of Ib obtained from Ib_Rin.py can be used as input.

Workflow progresses by connecting a known resistor in series with a source across the dvm input
and measuring the voltage both with and without the resistor shorted.

Rin = R*V/(Vs - V + Ib*R) is then calculated from a table of known resistor values, Ib and
the mean of the voltage readings in each circuit configuration.

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


def measure(vset):
    """
    Measurement loop function.
    vset: str (Nominal source voltage setting)
    rtn: ureal (mean measured voltage)
    """
    # Prepare DVM and SRC for measurement
    dvm.write(f'DCV {vset}')
    time.sleep(0.1)

    src.write(f'OUT {vset}V,0Hz')
    src.write('OPER')
    time.sleep(60)

    dvm.write(f'LFREQ LINE')
    time.sleep(1)
    dvm.write('AZERO ONCE')
    time.sleep(1)

    # Measurement loop - V
    v_readings = []
    for n in range(N_READINGS):
        reading = dvm.read()  # dvm.query('READ?')
        if abs(float(reading)) > 10*float(vset):
            print(f'{reading} too high! - skipped')
            continue
        print(reading)
        v_readings.append(float(reading))
    if len(v_readings) > 1:
        v_av = GTC.ta.estimate(v_readings)
    else:
        v_av = 0  # No valid readings!

    # Set DVM and SRC to 'safe mode'
    dvm.write('AZERO ON')
    src.write('OUT 0V,0Hz')
    src.write('STBY')
    return v_av, v_readings


def dud_ureal(u_lst):
    """
    Check for dof=NaN in a list of GTC.ureals.
    Return True if dof=NaN is present, False otherwise.
    :param u_lst: list of ureals
    :return: boolean
    """
    for u in u_lst:
        if u.df == float('NaN'):
            return True
    return False
# --------------------------------------------------


"""
---------------------------------
I/O Section & data storage
---------------------------------
"""
# import Resistor info to RESISTORS dict
with open('RESISTORS.json', 'r') as Resistors_fp:
    RESISTORS = json.load(Resistors_fp, object_hook=as_ureal)

# Data files
folder = r'G:\My Drive\TechProcDev\Keithley6430-src-meter_Light'
sn = input('\nEnter last 3 digits of 3458A serial number: ')
results_filename = os.path.join(folder, f'HP3458A-{sn}_Rin.json')
ib_Rin_filename = os.path.join(folder, f'HP3458A-{sn}_Ib_Rin.json')

"""
---------------------------------
Instruments Section
---------------------------------
"""
# GPIB connection
RM = visa.ResourceManager()
print('\navailable visa resources:'
      f'\n{RM.list_resources()}')

# dvm initialisation
addr_dvm = input('\nEnter dvm GPIB address: ')  # 25
try:
    dvm = RM.open_resource(f'GPIB1::{addr_dvm}::INSTR')
    dvm.read_termination = '\r\n'
    dvm.write_termination = '\r\n'
    dvm.timeout = 2000
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to dvm!')  # 4
dvm.write('DCV 100; NPLC 20; AZERO ON')  # Set DVM to high range, initially, for safety

# Source initialisation
addr_src = input('\nEnter source GPIB address: ')
try:
    src = RM.open_resource(f'GPIB1::{addr_src}::INSTR')
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to src!')

# GMH probe setup
port = input('\nEnter GMH-probe COM-port number: ')  # 4
gmh530 = gmh.GMHSensor(port)
print(f'gmh530 test-read: {gmh530.measure("T")}')

"""
-------------------------------
Measurement Section starts here:
-------------------------------
"""
try:
    with open(f'{results_filename}', 'r') as Rin_fp:  # Open existing results file so we can add to it.
        results = json.load(Rin_fp, object_hook=as_ureal)
except (FileNotFoundError, IOError):
    results = {}  # Create results dict, if it doesn't exist as a json file yet.
while True:  # 1 loop for each [Rs, Vset] combination
    while True:  # Check test parameters:
        R_name = input(f'\nSelect shunt resistor - ENSURE IT IS NOT SHORTED!\n{RESISTORS.keys()}: ')
        R0 = RESISTORS[R_name]['R0']
        alpha = RESISTORS[R_name]['alpha']
        T0 = RESISTORS[R_name]['T0']
        gamma = RESISTORS[R_name]['gamma']
        V0 = RESISTORS[R_name]['V0']
        tau = RESISTORS[R_name]['tau']
        t0 = RESISTORS[R_name]['t0']
        t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')

        Vset = input('\nSupply voltage: ')
        nom_current = float(Vset)/R0.x
        resp = input(f'Nominal current = {nom_current:.1e} A. Continue with test (y/n)?')
        if resp == 'y':
            break  # Parameters locked-in

    # Grab a temperature reading
    T = GTC.ureal(float(gmh530.measure('T')[0]), 0.05, 8, 'T')  # Resistor temp with type-B uncert.

    # Grab a timestamp
    t = dt.datetime.now()
    t_str = t.strftime('%d/%m/%Y %H:%M:%S')
    print(f'Timestamp: {t_str}\n')
    delta_t = t - t0_dt  # datetime.timedelta object
    delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds / 86400 + delta_t.microseconds / 8.64e10, 0.1, 8,
                             'delta_t_days')

    # The actual measurements happen here:
    V_av, V_readings = measure(Vset)  # Measure V with Rs connected (ureal)
    dummy = input(f'Bypass Rs, then press ENTER when completed.')
    Vs_av, Vs_readings = measure(Vset)  # Measure Vs with Rs shorted (ureal, list of floats)

    # NOTE: Rs voltage-drop is (Vs_av - V_av)!
    R = R0 * (1 + alpha * (T - T0) + gamma * ((Vs_av - V_av) - V0) + tau * delta_t_days)

    # import Ib info
    with open(f'{ib_Rin_filename}', 'r') as ib_Rin_fp:
        ib_Rin_dict = json.load(ib_Rin_fp, object_hook=as_ureal)
    Ib_approx = ib_Rin_dict[R_name]['Ib_approx']  # Rs-specific Ib
    Ib = ib_Rin_dict['Ib']  # Ib from fit of all Rs's - may not be as accurate!

    # Calculate Rin and collate data
    Rin = R*V_av/(Vs_av - V_av + Ib*R)
    Rin_approx = R * V_av / (Vs_av - V_av + Ib_approx*R)  # Use this value!
    print(f'\nRin = {Rin}\nRin_approx = {Rin_approx}')
    result = {f'{R_name}_V{Vset}': {'t': t_str, 'Rs': R,
                                    'Vs': Vs_av, 'Vs_data': Vs_readings,
                                    'V': V_av, 'V_data': V_readings,
                                    'Rin': Rin, 'Rin_approx': Rin_approx
                                    }
              }
    if dud_ureal([Rin, Rin_approx]):
        print('This test is dud and will be skipped!')
    else:
        results.update(result)
        print('Saving data...')
        with open(f'{results_filename}', 'w') as Rin_results_fp:
            json.dump(results, Rin_results_fp, indent=4, cls=UrealEncoder)
    resp = input('Continue with another Rs / test-V (y/n)? ')
    if resp == 'n':
        break

dvm.close()
src.close()
RM.close()

# print('Saving data...')
# with open(f'{results_filename}', 'w') as Rin_results_fp:
#     json.dump(results, Rin_results_fp, indent=4, cls=UrealEncoder)
