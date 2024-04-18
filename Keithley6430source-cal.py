# -*- coding: utf-8 -*-
"""
Keithley6430source-cal.py

Program to calibrate the I-source ranges of a Keithley 6430 Remoter source-meter.
Two measurement techniques are used:
 1. Ranges 10 pA to 100 uA: Measure voltage drop across a sense resistor Rs,
 2. Ranges 100 uA to 10 mA: Measure the current directly with a calibrated I-meter (3458A).
"""

import os
import sys
import GTC
import pyvisa as visa
import json
import datetime as dt
import time
import math
import gmhstuff as gmh

N_READINGS = 10
POLARITY_MASK = [0, 1, -1, 0, -1, 1, 0]
DELAYS = {'C10G': 100,
          'C1G': 30,
          'C9620': 10,
          'C9736': 5,
          'Al969': 2,
          'G493': 1
          }
BEST_R_FOR_I = {1e-12: 'C10G',  # Based on Table 9 in 'Keithley 6430 Calibration Notes'
                1e-11: 'C9620',
                1e-10: 'C1G',
                1e-9: 'C9620',
                1e-8: 'C9736',
                1e-7: 'C9736',  # or 'C9620'
                1e-6: 'G493',
                1e-5: 'G493',
                1e-4: 'G493'
                }
DVM452_I_CORRECTIONS = {1e-4: GTC.ureal(1.0000024, 2.3e-6, 87),
                        1e-3: GTC.ureal(0.99999672, 7.7e-7, 29),
                        1e-2: GTC.ureal(0.99999394, 9.8e-7, 64)
                        }
DVM452_V_CORRECTIONS = {1e-3: GTC.ureal(1.0000917, 1.5e-3, 60),  # Interpolated value. Data from S22139 (2023).
                        1e-2: GTC.ureal(0.9999985, 9.0e-6, 60),
                        1e-1: GTC.ureal(0.9999985, 2.0e-6, 60),
                        1: GTC.ureal(0.999993, 1.2e-6, 60),
                        10: GTC.ureal(0.9999991, 5.0e-7, 60)
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


def measure(test_dict):  # {'Iset': i_set[, 'Rname': R_name, 'Vrng': v_rng]}
    """
    Measurement loop function.
    test_dict: dict of test parameters
    rtn: Dict of lists for readings
    """

    readings = {-1: [], 0: [], 1: []}  # Dict of empty lists for readings
    time.sleep(5)

    for pol in POLARITY_MASK:
        i_set = test_dict['Iset']
        i_src = i_set*pol
        Rname = test_dict['Rname']
        print(f'\ni_src = {i_src} A')

        # Prepare 3458 and 6430 for measurement
        if 'Vrng' in test_dict:  # Low-current method - Measure V_Rs.
            az_delay = soak_delay = DELAYS[Rname]
            v_rng = test_dict['Vrng']
            dvm.write(f'DCV {v_rng}')  # Set DCV mode and range on meter
        else:  # High-current method - Measure I directly.
            az_delay = soak_delay = 5
            dvm.write(f'DCI {i_set}')  # Set DCI mode and range on meter
        time.sleep(0.1)

        K6430.write(f'SOUR:CURR:RANG {i_set};')
        time.sleep(0.1)
        K6430.write(f'SOUR:CURR:LEV {i_src};')
        K6430.write(f'OUTP ON;')
        time.sleep(1)

        print(f'Voltage soak delay ({soak_delay} s)...')
        time.sleep(soak_delay)

        dvm.write(f'LFREQ LINE')
        time.sleep(1)
        dvm.write('AZERO ONCE')
        print(f'AZERO delay ({az_delay} s)...')
        time.sleep(az_delay)

        # Measurement loop - I
        for n in range(N_READINGS):
            reading = dvm.read()
            if abs(float(reading)) > abs(10*i_src) and pol != 0:
                print(f'{reading} too high! - skipped')
                continue
            print(reading)
            readings[pol].append(float(reading))

        # Set 3458 and 6430 to 'safe mode'
        dvm.write('AZERO ON')
        K6430.write('SOURce:CURRent:RANGe 0;LEVel 0')
        time.sleep(0.1)
        K6430.write('OUTPut OFF')
    return readings


def get_Rin(rname, v):
    v_nom = pow(10, round(math.log10(v)))  # Nearest decade value
    if v_nom < 0.001:
        v_nom = 0.001
    key = f'{rname}_V{v_nom:f}'
    return R_IN_452[key]
# ----------------------------------------------------------------------


"""
---------------------------------
I/O Section & data storage / retreival
---------------------------------
"""
# import Resistor info to RESISTORS dict
with open('RESISTORS.json', 'r') as Resistors_fp:
    RESISTORS = json.load(Resistors_fp, object_hook=as_ureal)

# Data files
folder = r'G:\My Drive\TechProcDev\Keithley6430-src-meter_Light'
r_in_filename = os.path.join(folder, f'HP3458A-452_Rin.json')

# import input-R (s/n 452) info to R_IN_452 dict
with open(r_in_filename, 'r') as R_in_452_fp:
    R_IN_452 = json.load(R_in_452_fp, object_hook=as_ureal)

results_filename = os.path.join(folder, f'K6430-Isrc.json')
try:
    print(f'\nOpening {results_filename}...')
    with open(f'{results_filename}', 'r') as Rin_fp:  # Open existing results file so we can add to it.
        results = json.load(Rin_fp, object_hook=as_ureal)  # results dict
except (FileNotFoundError, IOError):
    print('No pre-existing results file found. Creating result dict from scratch...')
    results = {}  # Create empty results dict, if it doesn't exist as a json file yet.

"""
------------------------------------------------------------------
                    Instruments Section
------------------------------------------------------------------
"""
# GPIB connection
RM = visa.ResourceManager()
print('\navailable visa resources:'
      f'\n{RM.list_resources()}')

# Instrument initialisation
addr_dvm = 25  # Use 3458A, s/n452 at address 25
try:
    dvm = RM.open_resource(f'GPIB1::{addr_dvm}::INSTR')
    dvm.read_termination = '\r\n'
    dvm.write_termination = '\r\n'
    dvm.timeout = 2000
    rply = dvm.query('ID?')
    print(f'DVM response (addr{addr_dvm}): {rply}\n')
except visa.VisaIOError:
    sys.exit('ERROR - Failed to setup visa connection to dvm!')

addr_K6430 = 20  # input('\nEnter Keithley GPIB address: ')
try:
    K6430 = RM.open_resource(f'GPIB1::{addr_K6430}::INSTR')
    K6430.read_termination = '\n'
    K6430.write_termination = '\n'
    K6430.timeout = 2000
    rply = K6430.query('*IDN?')
    print(f'Keithley 6430 response (addr{addr_K6430}): {rply}\n')
    K6430.write('*RST')
    time.sleep(5)
    K6430.write('SOUR:FUNC CURR')  # SOURce:FUNCtion CURRent
    K6430.write('SOUR:CURR:MODE FIX')  # SOURce:CURRent:MODE FIXed
except visa.VisaIOError:
    sys.exit('ERROR - Failed to setup visa connection to Keithley 6430!')

# GMH
port = 4  # input('\nEnter GMH-probe COM-port number: ')
gmh530 = gmh.GMHSensor(port)
print(f'gmh530 test-read: {gmh530.measure("T")}')


"""
----------------------------------------------------------------
            Measurement Section starts here:
----------------------------------------------------------------
"""

while True:  # 1 loop for each I-setting or test
    # Gather info for this test
    high_i_method = None
    suffix = ''
    i_set = abs(float(input(f'\nEnter 6430 current source setting: ')))
    if i_set < 100e-6:
        high_i_method = False
    elif i_set > 100e-6:
        high_i_method = True
    else:  # 100 uA can be done using either method
        response = input('Use high-I method? (y / n)? ')
        if response == 'y':
            high_i_method = True
        else:
            high_i_method = False

    # Grab a timestamp
    t = dt.datetime.now()  # Precision to within ~12 hours is good enough.
    t_str = t.strftime('%d/%m/%Y %H:%M:%S')
    print(f'Timestamp: {t_str}\n')

    # ---------------------------------------------------------------------------------
    if high_i_method:  # >= 100 uA
        suffix = 'HI'
        dvm.write('DCI 0.01; NPLC 20; AZERO ON')  # Set DVM to high range, initially, for safety

        print(input(f'Ensure 6430 output is connected to I-meter input. Press ENTER when ready.'))

        test_params = {'Iset': i_set}
        i_readings = measure(test_params)  # 3458a current readings dictionary

        # ************************** Calculations *****************************
        corrn452 = DVM452_I_CORRECTIONS[abs(i_set)]  # IS CORRECTION POLARITY-DEPENDENT?
        I_drift = GTC.ta.estimate(i_readings[0])  # Zero-drift at mid-point
        Ip = (GTC.ta.estimate(i_readings[1]) - I_drift)*corrn452  # Drift- and gain-corrected
        In = (GTC.ta.estimate(i_readings[-1]) - I_drift)*corrn452  # Drift- and gain-corrected
        I_off = (Ip + In) / 2  # Offset
        I_av = (Ip - In) / 2 - I_off
        src_corrn = I_av / i_set

        # Calculations & write results
        test_key = f'K6430_{i_set:g}_{suffix}'
        result = {test_key: {'timestamp': t_str, 'data': i_readings, 'correction': src_corrn}
                  }
    # ---------------------------------------------------------------------------------
    else:  # <= 100 uA (low_i_method)
        suffix = 'LO'

        dvm.write(f'DCV AUTO; NPLC 20; AZERO ON')  # Set DVM to AUTO-range, initially, for safety

        R_name = BEST_R_FOR_I[i_set]  # R_name = input(f'\nSelect shunt resistor\n{RESISTORS.keys()}: ')
        print(input(f'Connect 6430 output to [{R_name} in parallel with dvm]. Press ENTER when ready.'))
        R0 = RESISTORS[R_name]['R0']
        alpha = RESISTORS[R_name]['alpha']
        T0 = RESISTORS[R_name]['T0']
        gamma = RESISTORS[R_name]['gamma']
        V0 = RESISTORS[R_name]['V0']
        tau = RESISTORS[R_name]['tau']
        t0 = RESISTORS[R_name]['t0']
        t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')
        T = GTC.ureal(float(gmh530.measure('T')[0]), 0.05, 8, 'T')  # Resistor temp with type-B uncert
        delta_t = t - t0_dt  # datetime.timedelta object
        delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds / 86400 + delta_t.microseconds / 8.64e10,
                                 0.1, 8, 'delta_t_days')
        V = abs(i_set*R0)  # Approximate V across Rs
        Rs = R0*(1 + alpha*(T - T0) + gamma*(V - V0) + tau*delta_t_days)  # Rs value now

        # Look up Rin for s/n 452
        Rin = get_Rin(R_name, V)
        R_parallel = Rs * Rin / (Rs + Rin)  # Correct for meter input-Z
        R_nom = pow(10, round(math.log10(R_parallel.x)))  # Nearest decade value
        v_rng = i_set*R_nom  # Use for voltmeter range

        test_params = {'Iset': i_set, 'Rname': R_name, 'Vrng': v_rng}
        v_readings = measure(test_params)  # 3458a voltage readings dictionary

        # ************************** Calculations *****************************
        corrn452 = DVM452_V_CORRECTIONS[abs(v_rng)]
        V_drift = GTC.ta.estimate(v_readings[0])  # Zero-drift at mid-point
        Vp = (GTC.ta.estimate(v_readings[1]) - V_drift)*corrn452  # Drift- and gain-corrected
        Vn = (GTC.ta.estimate(i_readings[-1]) - I_drift)*corrn452  # Drift- and gain-corrected
        V_off = (Vp + Vn) / 2  # Offset in Rs-loaded voltage
        V_av = (Vp - Vn) / 2 - V_off  # True voltage across true resistance
        I_av = V_av/R_parallel  # True current
        src_corrn = I_av / i_set
        test_key = f'K6430_{i_set:4g}_{suffix}'
        result = {test_key: {'timestamp': t_str, 'data': v_readings,
                             'Rname': R_name, 'Rs': Rs,
                             'correction': src_corrn
                             }
                  }
    # ---------------------------------------------------------------------------------
    results.update(result)
    print('Saving data...')
    with open(f'{results_filename}', 'w') as results_fp:
        json.dump(results, results_fp, indent=4, cls=UrealEncoder)

    resp = input('Continue with another test (y/n)? ')
    if resp == 'n':
        break

dvm.close()
K6430.close()
RM.close()
