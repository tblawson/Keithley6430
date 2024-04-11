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
# sn = input('\nEnter last 3 digits of 3458A serial number: ')
# results_filename = os.path.join(folder, f'HP3458A-{sn}_Rin.json')
# ib_Rin_filename = os.path.join(folder, f'HP3458A-{sn}_Ib_Rin.json')

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
    print(f'DVM response (addr{addr_dvm}): {rply}')
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to dvm!')

addr_K6430 = 20  # input('\nEnter Keithley GPIB address: ')
# cmd = input('Keithley cmd: ')
try:
    K6430 = RM.open_resource(f'GPIB1::{addr_K6430}::INSTR')
    K6430.read_termination = '\n'
    K6430.write_termination = '\n'
    K6430.timeout = 2000
    rply = K6430.query('*IDN?')
    print(f'Keithley 6430 response (addr{addr_K6430}): {rply}')
except visa.VisaIOError:
    print('ERROR - Failed to setup visa connection to Keithley 6430!')


# dvm.write('DCV 100; NPLC 20; AZERO ON')  # Set DVM to high range, initially, for safety
