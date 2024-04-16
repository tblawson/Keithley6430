import pyvisa as visa


RM = visa.ResourceManager()
K6430 = RM.open_resource(f'GPIB1::20::INSTR')
K6430.read_termination = '\n'
K6430.write_termination = '\n'
K6430.timeout = 2000
rply = K6430.query('*IDN?')

while True:
    cmd = input('command string: ')
    if cmd == '':
        break
    K6430.write(cmd)
