# -*- coding: utf-8 -*-
"""
Keithley6430source-cal.py

Program to calibrate the I-source ranges of a Keithley 6430 Remoter source-meter.
Two measurement techniques are used:
 1. Ranges 10 pA to 100 uA: Measure voltage drop across a sense resistor Rs,
 2. Ranges 100 uA to 10 mA: Measure the current directly with a calibrated I-meter (3458A).
"""

import os
import GTC
import pyvisa as visa
import json
import datetime as dt
import time
import gmhstuff as gmh

N_READINGS = 10
POLARITY_MASK = [0, 1, -1, 0, -1, 1, 0]

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


def measure(iset):
    """
    Measurement loop function.
    iset: str (Nominal source voltage setting)
    rtn: Dict of lists for readings
    """
    az_delay = 5
    i_readings = {-1: [], 0: [], 1: []}  # Dict of empty lists for readings
    K6430.write('*RST')  # Reset 6430 to default state
    time.sleep(5)

    for pol in POLARITY_MASK:
        i_src = iset*pol
        print(f'\ni_src = {i_src} A')
        # Prepare 3458 and 6430 for measurement
        dvm.write(f'DCI {i_src}')  # Set DCI mode and range on meter
        time.sleep(0.1)

        K6430.write(f'SOUR:CURR:RANG {iset};')  # Timeout error here.
        time.sleep(0.1)
        K6430.write(f'SOUR:CURR:LEV {i_src};')
        K6430.write(f'OUTP ON;')
        time.sleep(1)

        # print(f'Voltage soak delay ({soak_delay} s)...')
        # time.sleep(soak_delay)

        dvm.write(f'LFREQ LINE')
        time.sleep(1)
        dvm.write('AZERO ONCE')
        print(f'AZERO delay ({az_delay} s)...')
        time.sleep(az_delay)

        # Measurement loop - I
        for n in range(N_READINGS):
            reading = dvm.read()  # dvm.query('READ?')
            if abs(float(reading)) > abs(10*i_src) and pol != 0:
                print(f'{reading} too high! - skipped')
                continue
            print(reading)
            i_readings[pol].append(float(reading))

        # Set 3458 and 6430 to 'safe mode'
        dvm.write('AZERO ON')
        K6430.write(f'SOURce:CURRent:RANGe {0};LEVel {0};OUTPut OFF')

    return i_readings
# ----------------------------------------------------------------------


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
results_filename = os.path.join(folder, f'K6430-Isrc.json')
try:
    print(f'\nOpening {results_filename}...')
    with open(f'{results_filename}', 'r') as Rin_fp:  # Open existing results file so we can add to it.
        results = json.load(Rin_fp, object_hook=as_ureal)  # results dict
except (FileNotFoundError, IOError):
    print('\nNo pre-existing results file found. Creating result dict from scratch...')
    results = {}  # Create empty results dict, if it doesn't exist as a json file yet.

"""
---------------------------------
Instruments Section
---------------------------------
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
    print('ERROR - Failed to setup visa connection to dvm!')

dvm452_I_corrections = {1e-4: GTC.ureal(1.0000024, 2.3e-6, 87),
                        1e-3: GTC.ureal(0.99999672, 7.7e-7, 29),
                        1e-2: GTC.ureal(0.99999394, 9.8e-7, 64)
                        }

addr_K6430 = 20  # input('\nEnter Keithley GPIB address: ')
try:
    K6430 = RM.open_resource(f'GPIB1::{addr_K6430}::INSTR')
    K6430.read_termination = '\n'
    K6430.write_termination = '\n'
    K6430.timeout = 2000
    rply = K6430.query('*IDN?')
    print(f'Keithley 6430 response (addr{addr_K6430}): {rply}\n')
    k6430.write('*RST')
    time.sleep(5)
    K6430.write('SOUR:FUNC "CURR"')  # SOURce:FUNCtion CURRent
    K6430.write('SOUR:CURR:MODE FIX')  # SOURce:CURRent:MODE FIXed
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to Keithley 6430!')

# GMH
port = 4  # input('\nEnter GMH-probe COM-port number: ')
gmh530 = gmh.GMHSensor(port)
print(f'gmh530 test-read: {gmh530.measure("T")}')


"""
-------------------------------
Measurement Section starts here:
-------------------------------
"""

while True:  # 1 loop for each I-setting or test
    # Gather info for this test
    high_i_method = None
    suffix = ''
    i_set = float(input(f'\nEnter 6430 current source setting: '))
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
    t = dt.datetime.now()
    t_str = t.strftime('%d/%m/%Y %H:%M:%S')
    print(f'Timestamp: {t_str}\n')

    # set up 3458:
    if high_i_method:  # >= 100 uA
        suffix = 'HI'
        dvm.write('DCI 0.01; NPLC 20; AZERO ON')  # Set DVM to high range, initially, for safety

        print(input(f'Ensure 6430 output is connected to I-meter input. Press ENTER when ready.'))

        i_readings = measure(i_set)  # 3458a current readings dictionary

        # ************************** Calculations *****************************
        corrn452 = dvm452_I_corrections[abs(i_set)]  # IS CORRECTION POLARITY-DEPENDENT?
        I_drift = GTC.ta.estimate(i_readings[0])  # Zero-drift at mid-point
        Ip = (GTC.ta.estimate(i_readings[1]) - I_drift) * corrn452  # Drift- and gain-corrected
        In = (GTC.ta.estimate(i_readings[-1]) - I_drift) * corrn452  # Drift- and gain-corrected
        I_off = (Ip + In) / 2  # Offset in Rs-loaded voltage
        I_av = (Ip - In) / 2 - I_off
        src_corrn = I_av / i_set

        # Calculations & write results
        test_key = f'K6430_{i_set:g}_{suffix}'
        result = {test_key: {'timestamp': t_str, 'data': i_readings, 'correction': src_corrn}
                  }

    else:  # <= 100 uA
        suffix = 'LO'
        dvm.write(f'DCI v_rng; NPLC 20; AZERO ON')  # Set DVM to high range, initially, for safety

        print(input(f'Connect 6430 output to [Rs in parallel to dvm]. Press ENTER when ready.'))
        print('pretending to do something useful')
        v_readings = []

        R_name = input(f'\nSelect shunt resistor - ENSURE IT IS NOT SHORTED!\n{RESISTORS.keys()}: ')
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
        delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds / 86400 + delta_t.microseconds / 8.64e10, 0.1, 8,
                                 'delta_t_days')

        v_rng = i_set*Rs

        # ************************** Calculations *****************************
        src_corrn = 1

        result = {'I_set': i_set, 'high-I-method': high_i_method, 'timestamp': t_str,
                  'data': v_readings, 'correction': src_corrn}

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
