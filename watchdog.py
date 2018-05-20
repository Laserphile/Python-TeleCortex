import subprocess
import sys


def watchdog(args, exception_str):
    """
    creates a subprocess using args, monitors output for exception_str (case insensitive), and restarts if found
    """
    restarts = 0
    while 1:
        print("creating process with args: %s" % args)
        print("restart number %d" % restarts )
        proc = subprocess.Popen(
            args=args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        while proc.returncode is None:
            stdout_data, _ = proc.communicate()
            sys.stdout.write(stdout_data)
            if stdout_data.upper().contains(exception_str.upper()):
                print("restarting process")
                proc.kill()
        restarts += 1


def main():
    if len(sys.argv) < 2:
        print('usage: %s script_name [script_arguments]')
    args = ['python'] + sys.argv[1:]
    watchdog(args, 'Exception')


if __name__ == '__main__':
    main()
