# -*- coding: utf-8 -*
"""
General-purpose input-Z measurement routine for 3458A DVMs (Step 2).

This script is the second stage in a 2-step process to obtain the input impedance
of a meter.

The value of Ib obtained from Ib_Rin.py can be used as input.

Workflow progresses by connecting [a known resistor in series with a source] across the dvm input
and measuring the voltage both with and without the resistor shorted (Vs is the source voltage,
obtained when the resistor is shorted).

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
import winsound as ws
import gmhstuff as gmh

N_READINGS = 10
POLARITY_MASK = [0, 1, -1, 0, -1, 1, 0]
DELAYS = {'C 10G': 100,  # 100
          'C 1G': 30,
          'C9620 100M': 10,
          'G003 100M': 10,
          'C9736 10M': 5,
          'Al969 1M': 2,
          'G493 100k': 1,
          'short': 1
          }

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


def measure(R_name, vset):
    """
    Measurement loop function.
    vset: str (Nominal source voltage setting)
    rtn: ureal (mean measured voltage)
    """
    az_delay = soak_delay = DELAYS[R_name]
    v_readings = {-1: [], 0: [], 1: []}  # Dict of empty lists for readings

    for pol in POLARITY_MASK:
        v_src = vset*pol
        print(f'\nv_src = {v_src} V')
        # Prepare DVM and SRC for measurement
        dvm.write(f'DCV {v_src}')
        time.sleep(0.1)

        src.write(f'OUT {v_src}V,0Hz')
        src.write('OPER')
        print(f'Voltage soak delay ({soak_delay} s)...')
        time.sleep(soak_delay)

        dvm.write(f'DCV {vset}')  # Set appropriate dvm range
        dvm.write('LFREQ LINE')
        time.sleep(1)
        dvm.write('AZERO ONCE')
        print(f'AZERO delay ({az_delay} s)...')
        time.sleep(az_delay)

        # Measurement loop - V
        for n in range(N_READINGS):
            reading = dvm.read()  # dvm.query('READ?')
            if abs(float(reading)) > abs(10*v_src) and pol != 0:  # Catch overloads
                print(f'{reading} too high! - skipped')
                continue
            print(reading)
            v_readings[pol].append(float(reading))

        # Set DVM and SRC to 'safe mode'
        dvm.write('AZERO ON')
        src.write('OUT 0V,0Hz')
        src.write('STBY')

    return v_readings


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

# Data files
folder = input('Data directory: ')
# folder = r'G:\My Drive\TechProcDev\Keithley6430-src-meter_Light'
sn = input('\nEnter last 3 digits of 3458A serial number: ')
results_filename = os.path.join(folder, f'HP3458A-{sn}_Rin.json')
ib_Rin_filename = os.path.join(folder, f'HP3458A-{sn}_Ib_Rin.json')

# import Resistor info to RESISTORS dict
resistors_filename = os.path.join(folder, 'RESISTORS.json')
with open(resistors_filename, 'r') as Resistors_fp:
    RESISTORS = json.load(Resistors_fp, object_hook=as_ureal)

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
addr_dvm = input('\nEnter dvm GPIB address (just the number): ')  # 25
try:
    dvm = RM.open_resource(f'GPIB0::{addr_dvm}::INSTR')
    dvm.read_termination = '\r\n'
    dvm.write_termination = '\r\n'
    dvm.timeout = 2000
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to dvm!')  # 4

rply = dvm.query('ID?')
print(f'DVM at GPIB addr {addr_dvm} response: {rply}')
dvm.write('DCV 1000; NPLC 20; AZERO ON')  # Set DVM to highest range, initially, for safety


# Source initialisation
addr_src = input('\nEnter source GPIB address (just the number): ')
try:
    src = RM.open_resource(f'GPIB0::{addr_src}::INSTR')
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

        Vset = float(input('\nSupply voltage: '))
        nom_current = Vset/R0.x
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

    # ************ The actual measurements happen here: *******************
    V_readings = measure(R_name, Vset)  # Measure V with Rs connected (dict of lists)
    if len(V_readings[1]) < 1:
        continue  # Skip, if no valid readings
    ws.Beep(1000, 500)  # Keyboard beep for 500 ms
    print(input(f'Bypass Rs, then press ENTER when ready.'))
    Vs_readings = measure('short', Vset)  # Measure Vs with Rs shorted (dict of lists)
    if len(Vs_readings[1]) < 1:
        continue  # Skip, if no valid readings
    # *********************************************************************

    # ************************** Calculations *****************************
    V_drift = GTC.ta.estimate(V_readings[0])  # Zero-drift at mid-point
    Vp = GTC.ta.estimate(V_readings[1]) - V_drift  # Drift-corrected - subtract zero-drift at mid-point
    Vn = GTC.ta.estimate(V_readings[-1]) - V_drift  # Drift-corrected - subtract zero-drift at mid-point
    V_off = (Vp + Vn)/2  # Offset in Rs-loaded voltage
    V_av = (Vp - Vn)/2 - V_off

    Vs_drift = GTC.ta.estimate(Vs_readings[0])  # Zero-drift at mid-point
    Vsp = GTC.ta.estimate(Vs_readings[1]) - V_drift/2  # Drift-corrected - subtract zero-drift at mid-point
    Vsn = GTC.ta.estimate(Vs_readings[-1]) - V_drift/2  # Drift-corrected - subtract zero-drift at mid-point
    Vs_off = (Vsp + Vsn) / 2  # Offset in source voltage
    Vs_av = (Vsp - Vsn) / 2 - Vs_off

    # Rs correction - NOTE: Rs voltage-drop is (Vs_av - V_av)!
    R = R0 * (1 + alpha * (T - T0) + gamma * ((Vs_av - V_av) - V0) + tau * delta_t_days)

    # import Ib info
    with open(f'{ib_Rin_filename}', 'r') as ib_Rin_fp:
        ib_Rin_dict = json.load(ib_Rin_fp, object_hook=as_ureal)
    Ib_approx = ib_Rin_dict[R_name]['Ib_approx']  # Rs-specific Ib
    Ib = ib_Rin_dict['Ib']  # Ib from fit of all Rs's

    # Calculate Rin and collate data
    Rin = R*V_av/(Vs_av - V_av + Ib*R)
    Rin_approx = R * V_av / (Vs_av - V_av + Ib_approx*R)  # **** This is probably the more reliable value *****
    print(f'\nRin = {Rin}\nRin_approx = {Rin_approx}')
    result = {f'{R_name}_V{Vset}': {'t': t_str, 'Rs': R, 'Vs': Vs_av, 'V': V_av,
                                    'Vsn_data': Vs_readings[-1], 'Vs0_data': Vs_readings[0], 'Vsp_data': Vs_readings[1],
                                    'Vn_data': V_readings[-1], 'V0_data': V_readings[0], 'Vp_data': V_readings[1],
                                    'Rin': Rin, 'Rin_approx': Rin_approx
                                    }
              }
    # *********************************************************************

    if dud_ureal([Rin, Rin_approx]):
        print('This test is dud and will be skipped!')
    else:
        results.update(result)
        print('Saving data...')
        with open(f'{results_filename}', 'w') as Rin_results_fp:
            json.dump(results, Rin_results_fp, indent=4, cls=UrealEncoder)
    ws.Beep(1000, 500) # Keyboard beep for 500 ms
    resp = input('Continue with another Rs / test-V (y/n)? ')
    if resp == 'n':
        break

dvm.close()
src.close()
RM.close()
