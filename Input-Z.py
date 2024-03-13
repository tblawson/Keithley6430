# -*- coding: utf-8 -*
"""
General-purpose input-Z measurement routine for 3458A DVMs.

RESISTORS data: All uncertainties are expressed in the quantity units.
u(t0) is in [days]; tau is in [days^-1].
"""
import GTC
import pyvisa as visa
import csv
import datetime as dt
import time
# import gmhstuff-tblawson as GMH


# throwaway = dt.datetime.strptime('20110101', '%Y%m%d')  # known bug fix
# t_dt = dt.datetime.strptime(s, '%d/%m/%Y %H:%M:%S')
# t_tup = dt.datetime.timetuple(t_dt)
# t_av += time.mktime(t_tup)  # (accumulate data for average)
# t_av /= n  # av. time as float (seconds from epoch)
# t_av_fl = dt.datetime.fromtimestamp(t_av)
# return t_av_fl.strftime('%d/%m/%Y %H:%M:%S')  # av. time as string

RESISTORS = {'G493': {'R0': GTC.ureal(100000.255, 0.145, 125, 'G493_R0'),
                      'alpha': GTC.ureal(-9.6e-7, 6.1e-7, 74, 'G493_alpha'),
                      'T0': GTC.ureal(20.476, 0.035, 75, 'G494_T0'),
                      'gamma': GTC.ureal(1.53e-8, 6.9e-9, 73, 'G493_gamma'),
                      'V0': GTC.ureal(20.26, 2.97, 75, 'G493_V0'),
                      'tau': GTC.ureal(4.18e-9, 2.8e-10, 74, 'G493_tau'),
                      't0': '25/05/2019 16:26:30'},
             'Al969': {'R0': GTC.ureal(1000001.50, 2.43, 91, 'Al969_R0'),
                       'alpha': GTC.ureal(-1.6e-6, 4.2e-7, 129, 'Al969_alpha'),
                       'T0': GTC.ureal(20.580, 0.028, 130, 'Al969_T0'),
                       'gamma': GTC.ureal(5.09e-9, 3.0e-9, 128, 'Al969_gamma'),
                       'V0': GTC.ureal(44.1, 3.8, 130, 'Al969_V0'),
                       'tau': GTC.ureal(-6.6e-11, 2.6e-10, 129, 'Al969_tau'),
                       't0': '04/11/2020 17:45:37'},
             'C9736': {'R0': GTC.ureal(10001381, 60, 128, 'C9736_R0'),
                       'alpha': GTC.ureal(-3.06e-6, 7.9e-7, 79, 'C9736_alpha'),
                       'T0': GTC.ureal(20.546, 0.017, 80, 'C9736_T0'),
                       'gamma': GTC.ureal(9.21e-9, 2.7e-9, 79, 'C9736_gamma'),
                       'V0': GTC.ureal(46.7, 4.8, 80, 'C9736_V0'),
                       'tau': GTC.ureal(4.3e-10, 2.3e-10, 79, 'C9736_tau'),
                       't0': '31/10/2020 09:54:00'},
             'C9620': {'R0': GTC.ureal(99998713, 856, 64, 'C9620_R0'),
                       'alpha': GTC.ureal(7.9e-6, 1.4e-6, 56, 'C9620_alpha'),
                       'T0': GTC.ureal(20.656, 0.025, 57, 'C9620_T0'),
                       'gamma': GTC.ureal(4.0e-9, 6.1e-9, 56, 'C9620_gamma'),
                       'V0': GTC.ureal(48.8, 5.9, 57, 'C9620_V0'),
                       'tau': GTC.ureal(7.2e-10, 7.1e-10, 56, 'C9620_tau'),
                       't0': '07/09/2020 08:50:44'},
             'G003': {},  #
             'C1G': {},
             'C10G': {},
             'C100G': {},
             'C1T': {},
             }

# GPIB connection and dvm initialisation
RM = visa.ResourceManager()
addr = input('Enter dvm GPIB address: ')
try:
    dvm = RM.open_resource(f'GPIB0::{addr}::INSTR')
    dvm.read_termination = '\r\n'
    dvm.write_termination = '\r\n'
    dvm.timeout = 2000
    rply = dvm.query('IDN?')
    print(f'DVM at GPIB addr {addr} response: {rply}')
    dvm.write('DCV 0; NPLC 20; AZERO ON')  # DCV 100 mV range; Sample every 0.4 s; Autozero
except:
    print('ERROR - Failed to setup visa connection!')

# GMH probe setup
# gmh530 = GMH.GMHSensor(4)
# gmh530.open_port()
# T = gmh530.measure('T')[0]

# Test setup
R_name = input(f'Select resistor connected across DVM output\n{RESISTORS.keys()}: ')
for item in RESISTORS[R_name]:
    print(f'{item} = {RESISTORS[R_name][item]}')
R0 = RESISTORS[R_name]['R0']
alpha = RESISTORS[R_name]['alpha']
T0 = RESISTORS[R_name]['T0']
gamma = RESISTORS[R_name]['gamma']
V0 = RESISTORS[R_name]['V0']
tau = RESISTORS[R_name]['tau']
t0 = RESISTORS[R_name]['t0']
t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')

# Ib measurement and data acquisition
# T = GTC.ureal(float(gmh530.measure('T')[0]), 0.05, 8, 'T')  # Resistor temp with type-B uncert.
T = GTC.ureal(float(input('R temperature: ')), 0.05, 8, 'T')  # Resistor temp with type-B uncert.

t = dt.datetime.now()
delta_t = t - t0_dt  # datetime.timedelta object
delta_t_days = GTC.ureal(delta_t.days + delta_t.seconds/86400 + delta_t.microseconds/8.64e10, 0.1, 8, 'delta_t_days')

Vbias = []
dvm.write('LFREQ LINE')
time.sleep(1)
dvm.write('AZERO ONCE')
time.sleep(1)
for n in range(20):
    reading = dvm.read()  # dvm.query('READ?')
    print(reading)
    Vbias.append(reading)
dvm.write('AZERO ON')
V = GTC.ta.estimate(Vbias)

with open('Ibias_data.csv', 'w', newline='') as csvfile:
    datawriter = csv.writer(csvfile, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    datawriter.writerow(Vbias)

# Ib calculation
R = R0*(1 + alpha*(T-T0) + gamma*(V-V0) + tau*delta_t_days)
print(R)
Ib = GTC.ta.estimate(Vbias)/R
print(Ib)
