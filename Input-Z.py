# -*- coding: utf-8 -*
"""
General-purpose input-Z measurement routine for 3458A DVMs.

RESISTORS data: All uncertainties are expressed in the quantity units.
u(t0) is in [days]; tau is in [days^-1].
"""
import GTC
import pyvisa as visa
import json
import datetime as dt
import time
import gmhstuff as gmh


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
RESULTS = {}

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

while True:
    # Test setup
    R_name = input(f'\nSelect resistor connected across DVM output (or Enter to break loop)\n{RESISTORS.keys()}: ')
    if R_name == '':
        break
    R0 = RESISTORS[R_name]['R0']
    alpha = RESISTORS[R_name]['alpha']
    T0 = RESISTORS[R_name]['T0']
    gamma = RESISTORS[R_name]['gamma']
    V0 = RESISTORS[R_name]['V0']
    tau = RESISTORS[R_name]['tau']
    t0 = RESISTORS[R_name]['t0']
    t0_dt = dt.datetime.strptime(t0, '%d/%m/%Y %H:%M:%S')

    """
    -------------------------------
    Measurement Section starts here:
    -------------------------------
    """
    # Grab a temperature reading
    T = GTC.ureal(float(gmh530.measure('T')[0]), 0.05, 8, 'T')  # Resistor temp with type-B uncert.
    t = dt.datetime.now()
    t_str = t.strftime('%d/%m/%Y %H:%M:%S')
    # print(f'Timestamp: {t_str}')
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
        Vbias.append(float(reading))
    dvm.write('AZERO ON')
    V = GTC.ta.estimate(Vbias)

# with open('Ibias_data.csv', 'a', newline='') as csvfile:
#     datawriter = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
#     datawriter.writerow(Vbias)

    # Ib calculation
    R = R0*(1 + alpha*(T-T0) + gamma*(V-V0) + tau*delta_t_days)
    print(f'\nTest resistor (corrected) = {R:1.3e}')
    Ib_approx = V / R
    print(f'Input bias I = {Ib_approx:1.3e}')

    # Compile results dict
    Ib_result = {R_name: {'T': T, 'V': V, 't': t,
                          'R': R,  # 'R': {'val': R.x, 'unc': R.u, 'df': R.df},
                          'Ib_approx': Ib_approx  # 'Ib': {'val': Ib_approx.x, 'unc': Ib_approx.u, 'df': Ib_approx.df}
                          }
                }
    RESULTS.update(Ib_result)
# End of measurement loop for this resistor

# Do full calculation
inv_R = []
inv_V = []
for nom_R in RESULTS:
    inv_R.append(1/(RESULTS[nom_R]['R']))  # inv_R.append(1/nom_R['R'])
    inv_V.append(1/(RESULTS[nom_R]['V']))
inv_R_vals = [r.x for r in inv_R]
inv_R_uncs = [r.u for r in inv_R]
inv_V_vals = [v.x for v in inv_V]
inv_V_uncs = [v.u for v in inv_V]
c, m = GTC.ta.line_fit_wtls(inv_R_vals, inv_V_vals, inv_R_uncs, inv_V_uncs).a_b
Ib = 1/m
Rin = m/c
RESULTS.update({'Ib': Ib, 'Rin': Rin})
print(f'Final calculated values:\nIb = {Ib}\nRin = {Rin}')

json_str = json.dumps(RESULTS, indent=4)
with open('results.json', 'w') as json_file:
    json.dump(json_str, file)
