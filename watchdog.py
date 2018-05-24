"""
Run a given script and check STDOUT and STDERR for strings that indicate that it has failed.
Restart the script periodically.
Rerout stdin/stdout/stderr from watchdog process to child process

Usage:

    python watchdog.py <your script>

To get a list of poc scripts and what they do, check out poc/__init__.py
"""

import fcntl
import os
import pty
import subprocess
import sys
import signal
import time
import tty

from six import text_type, binary_type

ENCODING = 'latin-1'
BUFFSIZE = 2048

def watchdog_print(thing):
    print("[watchdog] %s" % text_type(thing))

def set_nonblocking(file_obj):
    flags = fcntl.fcntl(file_obj, fcntl.F_GETFL)
    # print("flags before on %s are %s" % (file_obj, flags))
    flags = flags | os.O_NONBLOCK
    # print("flags after on %s are %s" % (file_obj, flags))
    fcntl.fcntl(file_obj, fcntl.F_SETFL, flags)

def set_blocking(file_obj):
    flags = fcntl.fcntl(file_obj, fcntl.F_GETFL)
    # print("flags before on %s are %s" % (file_obj, flags))
    flags = flags & ~os.O_NONBLOCK
    # print("flags after on %s are %s" % (file_obj, flags))
    fcntl.fcntl(file_obj, fcntl.F_SETFL, flags)

def actually_kill_proc(proc):
    watchdog_print("my_pid: %s, my_pgid: %s, my_ppid: %s, proc_pid: %s proc_pgid: %s" % (
        os.getpid(), os.getpgid(os.getpid()), os.getppid(),
        proc.pid, os.getpgid(proc.pid)
    ))
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

def watchdog(args, exception_str, timeout=3600):
    """
    creates a subprocess using args, monitors output for exception_str (case insensitive), and restarts if found
    """
    watchdog_print("press ctrl-c to kill process, ctrl-d to restart")

    restarts = 0
    while 1:
        watchdog_print("creating process with args: %s" % args)

        pty_master, pty_slave = pty.openpty()
        aux_master, aux_slave = pty.openpty()

        # probably not necessary?
        tty.setraw(pty_master)
        tty.setraw(pty_slave)
        tty.setraw(aux_master)
        tty.setraw(aux_slave)

        set_blocking(pty_slave)
        set_blocking(aux_slave)

        proc = subprocess.Popen(
            args=args,
            stdin=pty_slave,
            stdout=pty_slave,
            stderr=aux_slave,
            close_fds=True,
            preexec_fn=os.setsid,
        )

        set_nonblocking(sys.stdin)
        set_nonblocking(aux_master)

        time.sleep(0.1)

        start = time.clock()

        try:
            while proc.returncode is None and (time.clock() - start < timeout):
                # watchdog_print("start of loop")
                try:
                    set_nonblocking(pty_master)
                    stdin_text = text_type(os.read(sys.stdin.fileno(), BUFFSIZE), ENCODING)
                    set_blocking(pty_master)
                except (IOError, OSError):
                    stdin_text = None
                except Exception as exc:
                    watchdog_print("! READ STDIN FAILED: %s %s, " % (type(exc), exc))
                    raise exc
                if stdin_text is not None:
                    print("SEND STDIN %s" % (repr(stdin_text)))
                    if '\x03' in stdin_text: # ctrl-c
                        watchdog_print("raising KeyboardInterrupt")
                        raise KeyboardInterrupt("received '\\x03' from stdin")

                    if '\x04' in stdin_text: # ctrl-d
                        watchdog_print("received \\x04 from stdin, restarting")
                        proc.terminate()
                    os.write(pty_master, binary_type(stdin_text, ENCODING))

                try:
                    stdout_text = text_type(os.read(pty_master, BUFFSIZE), ENCODING)
                except (IOError, OSError):
                    stdout_text = None
                except Exception as exc:
                    watchdog_print("! READ STDOUT FAILED: %s %s, " % (type(exc), exc))
                    raise exc
                if stdout_text is not None:
                    # watchdog_print("RECV STDOUT %s" % (repr(stdout_text)))
                    # print(binary_type(stdout_text, ENCODING))
                    os.write(sys.stdout.fileno(), binary_type(stdout_text, ENCODING))

                    if exception_str.upper() in stdout_text.upper():
                        watchdog_print("restarting process")
                        proc.terminate()

                try:
                    stderr_text = text_type(os.read(aux_master, BUFFSIZE), ENCODING)
                except (IOError, OSError):
                    stderr_text = None
                except Exception as exc:
                    watchdog_print("! READ STDERR FAILED: %s %s, " % (type(exc), exc))
                    raise exc
                if stderr_text is not None:
                    # watchdog_print("RECV STDERR %s" % (repr(stderr_text)))
                    # print(binary_type(stderr_text, ENCODING))
                    os.write(sys.stdout.fileno(), binary_type(stderr_text, ENCODING))

                    if exception_str.upper() in stderr_text.upper():
                        watchdog_print("restarting process")
                        proc.terminate()
                # watchdog_print("end of loop")
                time.sleep(0.01)
                sys.stdout.flush()
                proc.poll()

        except Exception as exc:
            watchdog_print("there was an exception in the main loop: %s %s" % (
                type(exc), exc
            ))
        finally:
            watchdog_print("outside of loop, proc.returncode is %s" % proc.returncode)
            if proc.returncode is None:
                watchdog_print("terminating")
                proc.terminate()

        restarts += 1
        watchdog_print("restart number %d" % restarts )


def main():
    if len(sys.argv) < 2:
        print('usage: %s script_name [script_arguments]' % sys.argv[0])
    args = ['python'] + sys.argv[1:]
    watchdog(args, 'Exception')


if __name__ == '__main__':
    main()
