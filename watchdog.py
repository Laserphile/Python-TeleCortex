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
import errno
import sys
import signal
import time
import tty
import termios

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

def pid_exists(pid):
    """Check whether pid exists in the current process table.
    UNIX only.
    """
    if pid < 0:
        return False
    if pid == 0:
        # According to "man 2 kill" PID 0 refers to every process
        # in the process group of the calling process.
        # On certain systems 0 is a valid PID but we have no way
        # to know that in a portable fashion.
        raise ValueError('invalid PID 0')
    try:
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # ESRCH == No such process
            return False
        elif err.errno == errno.EPERM:
            # EPERM clearly means there's a process to deny access to
            return True
        else:
            # According to "man 2 kill" possible error values are
            # (EINVAL, EPERM, ESRCH)
            raise
    else:
        return True

def actually_kill_proc(proc):
    if pid_exists(proc.pid):
        watchdog_print("terminating")
        watchdog_print("my_pid: %s, my_pgid: %s, my_ppid: %s, proc_pid: %s proc_pgid: %s" % (
            os.getpid(), os.getpgid(os.getpid()), os.getppid(),
            proc.pid, os.getpgid(proc.pid)
        ))
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    else:
        raise UserWarning("tried to terminate process that is already dead")

def check_out_for_exceptions(out, exceptions):
    for exc in exceptions:
        if exc.upper() in out.upper():
            watchdog_print("found %s in output" % exc)
            return True

def watchdog(args, exceptions, timeout=3600):
    """
    creates a subprocess using args, monitors output for exceptions (case insensitive), and restarts if found
    """
    watchdog_print("press ctrl-c to kill process, r<enter> to restart")

    restarts = 0
    while 1:
        watchdog_print("creating process with args: %s" % args)

        pty_master, pty_slave = pty.openpty()
        aux_master, aux_slave = pty.openpty()

        # probably not necessary?
        # tty.setraw(pty_master)
        tty.setraw(pty_slave)
        # tty.setraw(aux_master)
        tty.setraw(aux_slave)

        stdin_orig_settings = termios.tcgetattr(sys.stdin)

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

        set_nonblocking(aux_master)
        set_nonblocking(pty_master)

        time.sleep(0.1)

        start = time.clock()
        last_cycle = False

        try:
            while proc.returncode is None and (time.clock() - start < timeout):
                # watchdog_print("start of loop")
                try:
                    set_nonblocking(sys.stdin)
                    stdin_text = text_type(os.read(sys.stdin.fileno(), BUFFSIZE), ENCODING)
                    set_blocking(sys.stdin)
                except (IOError, OSError):
                    stdin_text = None
                except Exception as exc:
                    watchdog_print("! READ STDIN FAILED: %s %s, " % (type(exc), exc))
                    raise exc
                if stdin_text is not None and len(stdin_text) > 0:
                    stdin_binary = binary_type(stdin_text, ENCODING)
                    print("SEND STDIN %s" % (repr(stdin_binary)))
                    if binary_type('\x03', ENCODING) in stdin_binary: # ctrl-c
                        watchdog_print("raising KeyboardInterrupt")
                        raise KeyboardInterrupt("received '\\x03' from stdin")

                    elif binary_type('r', ENCODING) in stdin_binary: # ctrl-d
                        watchdog_print("received r from stdin, restarting")
                        proc.terminate()
                    else:
                        os.write(pty_master, stdin_binary)

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

                    if check_out_for_exceptions(stdout_text, exceptions):
                        actually_kill_proc(proc)
                        break

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

                    if check_out_for_exceptions(stderr_text, exceptions):
                        actually_kill_proc(proc)
                        break
                # watchdog_print("end of loop")
                time.sleep(0.01)
                sys.stdout.flush()
                proc.poll()

        except KeyboardInterrupt:
            last_cycle = True
        except Exception as exc:
            watchdog_print("there was an exception in the main loop: %s %s" % (
                type(exc), exc
            ))
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, stdin_orig_settings)
            watchdog_print("outside of loop, proc.returncode is %s" % proc.returncode)
            if proc.returncode is None:
                actually_kill_proc(proc)
            end = time.clock()
            if(end - start < 0.1 and restarts > 1):
                watchdog_print("subprocess terminated immediately after multiple restarts, waiting")
                time.sleep(1)

        if last_cycle:
            break

        restarts += 1
        watchdog_print("restart number %d" % restarts )


def main():
    if len(sys.argv) < 2:
        print('usage: %s script_name [script_arguments]' % sys.argv[0])
    args = ['python'] + sys.argv[1:]
    watchdog(args, ['Exception', 'Traceback (most recent call last)'])


if __name__ == '__main__':
    main()
