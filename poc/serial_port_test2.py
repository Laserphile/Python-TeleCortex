from serial_port_test import SERVERS, SerialPortManager


def main():
    with SerialPortManager(SERVERS) as spm:
        pass

if __name__ == '__main__':
    main()
