"""
Manage multiple session.TelecortexSession objects in different ways.

TODO: Managers have access to conf object.
"""


import logging
import multiprocessing as mp
import queue
import asyncio
import serial_asyncio
import functools
import itertools
import sys
import time
from collections import OrderedDict

import serial

from context import telecortex
from telecortex.ser import DEFAULT_BAUD, DEFAULT_TIMEOUT
from telecortex.session import (TelecortexSerialProtocol, TelecortexSession,
                                ThreadedTelecortexSession,
                                VirtualTelecortexSession)


# TODO: rename TelecortexBaseManager
class TeleCortexBaseManager(object):
    """
    Manage multiple abstract TelecortexSession objects.
    """
    session_class = TelecortexSession
    serial_class = serial.Serial

    def __init__(self, servers, **kwargs):
        self.servers = servers
        self.known_cids = OrderedDict()
        self.__class__.relinquish_time = kwargs.pop('manager_relinquish', 0.001)
        self.session_kwargs = kwargs

    @classmethod
    def open_sesh(cls, serial_kwargs, session_kwargs):
        """
        Open a serial connection and create a session object.
        """
        ser = cls.serial_class(**serial_kwargs)
        sesh = cls.session_class(ser, **session_kwargs)
        return sesh

    def get_serial_conf(self, server_info):
        """
        Determine the arguments to give to serial.Serial from server_info.

        May have to make connections to devices in order to determine CID if
        device file is not given.
        """
        response = {
            'baudrate': server_info.get('baud', DEFAULT_BAUD),
            'timeout': server_info.get('timeout', DEFAULT_TIMEOUT)
        }
        if 'file' in server_info:
            response['port'] = server_info['file']
            return response

        dev_kwargs = {}
        for key in ['vid', 'pid', 'ser', 'dev']:
            if IGNORE_SERIAL_NO and key in ['ser']:
                continue
            if IGNORE_VID_PID and key in ['vid', 'pid']:
                continue
            if key in server_info:
                dev_kwargs[key] = server_info[key]

        ports = query_serial_dev(**dev_kwargs)

        if 'cid' in server_info:
            ports_matching_cid = []

            for port in ports:
                cid = None
                if port in self.known_cids:
                    cid = self.known_cids[port]
                    if cid != server_info.get('cid'):
                        continue
                else:
                    serial_kwargs = response.copy()
                    serial_kwargs['port'] = port
                    sesh = self.open_sesh(serial_kwargs, self.session_kwargs)
                    sesh.reset_board()
                    if server_info.get('cid') is not None:
                        sesh_cid = int(sesh.get_cid())
                        self.known_cids[port] = sesh_cid
                        if sesh_cid != server_info.get('cid'):
                            sesh.close()
                            continue
                ports_matching_cid.append(port)
            ports = ports_matching_cid

        if len(ports) > 1:
            logging.warning(
                "ambiguous server info matches multiple ports: %s | %s" % (
                    server_info, ports
                )
            )

        if not ports:
            logging.critical(
                "target device not found for server: %s" % server_info)
            return {}
        response['port'] = ports[0]

        return response


    @property
    def any_alive(self):
        raise NotImplementedError()

    def all_idle(self):
        raise NotImplementedError()

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        raise NotImplementedError()

# TODO: rename TelecortexSyncManager, as in opposite of async
class TelecortexSessionManager(TeleCortexBaseManager):
    """
    Manage TelecortexSession objects in a single thread.
    """
    def __init__(self, servers, **kwargs):
        super(TelecortexSessionManager, self).__init__(servers, **kwargs)
        self.sessions = OrderedDict()
        self.refresh_connections()

    def refresh_connections(self):
        """
        Use information from `self.servers`, ensure all sessions are connected.
        """
        for server_id, server_info in self.servers.items():
            logging.info(
                "looking for server_id %d with info: %s" %
                (server_id, server_info)
            )
            if server_id in self.sessions:
                if self.sessions[server_id]:
                    # we're fine
                    continue
                if not self.sessions[server_id]:
                    # session is dead, kill it
                    self.sessions[server_id].close()
                    del self.sessions[server_id]

            if self.sessions.get(server_id) is not None:
                continue

            # if session does not exist, create a new one
            serial_conf = self.get_serial_conf(server_info)

            if serial_conf:
                sesh = self.open_sesh(serial_conf, self.session_kwargs)
                sesh.reset_board()
                logging.warning("added session for server: %s" % server_info)
                self.sessions[server_id] = sesh

    def close(self):
        for server_id, session in self.sessions.items():
            session.close()
        self.sessions = OrderedDict()

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        self.sessions[server_id].chunk_payload_with_linenum(cmd, args, payload)

    @property
    def any_alive(self):
        # TODO: implement this
        return True

    def wait_for_workers_idle(self):
        # TODO: implement this
        pass

    def __enter__(self, *args, **kwargs):
        # TODO: this
        pass

    def __exit__(self, *args, **kwargs):
        self.close()


class TelecortexVirtualManagerMixin(object):
    """
    Don't actually create any connections
    """
    serial_class = dict
    session_class = VirtualTelecortexSession

    def get_serial_conf(self, server_info):
        return {
            'port': server_info.get('file', "VIRTUAL"),
            'baudrate': server_info.get('baud', DEFAULT_BAUD),
            'timeout': server_info.get('timeout', DEFAULT_TIMEOUT)
        }


class TelecortexVirtualManager(
    TelecortexSessionManager, TelecortexVirtualManagerMixin
):
    serial_class = TelecortexVirtualManagerMixin.serial_class
    session_class = TelecortexVirtualManagerMixin.session_class
    get_serial_conf = TelecortexVirtualManagerMixin.get_serial_conf


class TelecortexThreadManager(TeleCortexBaseManager):
    """
    Manage TelecortexSession objects in multiple sessions.
    """
    session_class = ThreadedTelecortexSession

    queue_length = 10

    def __init__(self, servers, **kwargs):
        super(TelecortexThreadManager, self).__init__(servers, **kwargs)
        # A tuple of (queue, proc) for each server_id
        # TODO: split into sesh_workers and cmd_queues
        self.sessions = OrderedDict()
        self.refresh_connections()

    @classmethod
    def relinquish(cls):
        time.sleep(cls.relinquish_time)

    @classmethod
    def controller_thread(cls, serial_conf, queue_, session_kwargs):
        # setup serial device

        sesh = cls.open_sesh(serial_conf, session_kwargs)
        sesh.reset_board()
        sesh.get_cid()
        # listen for commands
        while sesh:
            try:
                cmd, args, payload = queue_.get_nowait()
            except queue.Empty as exc:
                logging.info("Queue Empty: %s | %s" % (sesh.cid, exc))
                # TODO: relinquish control to other sessions
                cls.relinquish()
                continue
            except Exception as exc:
                logging.error(exc)
                continue
            # logging.debug("received: %s" % str((cmd, args, payload)))
            sesh.chunk_payload_with_linenum(cmd, args, payload)
            while not sesh.ready:
                logging.debug("sesh not ready: %s" % sesh.cid)
                # TODO: relinquish control here
                cls.relinquish()

    def refresh_connections(self, server_ids=None):
        if server_ids is None:
            server_ids = self.servers.keys()

        assert sys.version_info > (3, 0), (
            "multiprocessing only works properly on python 3")
        ctx = mp.get_context('fork')

        for server_id in server_ids:
            queue, old_proc = self.sessions.get(server_id, (None, None))
            if old_proc is not None:
                old_proc.terminate()

            server_info = self.servers.get(server_id, {})
            serial_conf = self.get_serial_conf(server_info)

            if serial_conf:
                if queue is None:
                    queue = mp.Queue(self.queue_length)

                proc = ctx.Process(
                    target=self.controller_thread,
                    args=(serial_conf, queue, self.session_kwargs),
                    name="controller_%s" % server_id
                )
                proc.start()
                self.sessions[server_id] = (queue, proc)

    @property
    def any_alive(self):
        return any([self.sessions.get(server_id, (None, None))[1]
                    for server_id in self.servers.keys()])

    def session_active(self, server_id):
        return self.sessions.get(server_id)

    @property
    def all_idle(self):
        return all([queue.empty() for (queue, proc) in self.sessions.values()])

    def wait_for_workers_idle(self):
        while not self.all_idle:
            logging.debug("waiting on queue idle")
            self.relinquish()

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        loops = 0

        while True:
            loops += 1
            if loops > 1000:
                raise UserWarning(
                    "too many retries: %s, %s" % (
                        loops, map(str, [server_id, cmd, args, payload])
                    )
                )
            try:
                self.sessions[server_id][0].put(
                    (cmd, args, payload),
                    timeout=0
                )
            except queue.Full as exc:
                logging.debug("Queue Full: %d | %s" % (server_id, exc))
                # TODO: relinquish control to other sessions
                self.relinquish()
            except OSError as exc:
                logging.error("OSError: %s" % exc)
                self.refresh_connections([server_id])
                continue
            except Exception as exc:
                raise UserWarning("unhandled exception: %s" % str(exc))
            break


class TeleCortexVirtualThreadManager(
    TelecortexThreadManager, TelecortexVirtualManagerMixin
):
    serial_class = TelecortexVirtualManagerMixin.serial_class
    session_class = TelecortexVirtualManagerMixin.session_class
    get_serial_conf = TelecortexVirtualManagerMixin.get_serial_conf


class TeleCortexCacheManager(TeleCortexBaseManager):
    def __init__(self, servers, cache_file):
        super(TeleCortexCacheManager, self).__init__(servers)
        self.cache_file = cache_file
        with open(self.cache_file, 'w') as cache:
            cache.write('')

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        with open(self.cache_file, 'a') as cache:
            pass
            # TODO: fix this
            # print(
            #     "%s: %s" % (
            #         server_id,
            #         ", ".join(map(str, [
            #             cmd, json.dumps(args), payload
            #         ]))
            #     ), file=cache
            # )

    @property
    def any_alive(self):
        return True

    def all_idle(self):
        return True

    def session_active(self, server_id):
        return True


class TelecortexAsyncManager(TeleCortexBaseManager):
    """
    Manages TelecortexSerialProtocol objects in an async loop.
    """
    protocol_class = TelecortexSerialProtocol

    def __init__(self, conf, graphics, **kwargs):
        self.queue_len = kwargs.pop('queue_len', 10)
        self.conf = conf
        self.graphics = graphics
        super(TelecortexAsyncManager, self).__init__(conf.servers, **kwargs)
        # asyncio.Queues for sending commands to each server.
        self.cmd_queues = OrderedDict()
        # asyncio coroutines controlling each serial device
        # TODO: rename sesh_workers
        self.sessions = OrderedDict()
        # asyncio coroutine sending graphics to each serial coroutine
        self.gfx_coroutine = None
        self.loop = asyncio.get_event_loop()
        self.loop.set_debug(True)
        self.refresh_connections()

    @classmethod
    def open_sesh(cls, serial_kwargs, session_kwargs):
        """
        @overrides TeleCortexBaseManager.open_sesh.
        """
        return

    def refresh_connections(self, server_ids=None):
        if server_ids is None:
            server_ids = self.servers.keys()
        else:
            raise UserWarning("individual server refresh not supported")

        assert sys.version_info > (3, 7), (
            "async only works properly on python 3.7")

        for server_id, server_info in self.servers.items():
            if server_id not in self.cmd_queues:
                self.cmd_queues[server_id] = asyncio.Queue(self.queue_len)

            if server_id in self.sessions:
                self.sessions[server_id].cancel()
            serial_kwargs = self.get_serial_conf(server_info)
            serial_url = serial_kwargs.pop('port')
            coro = serial_asyncio.create_serial_connection(
                self.loop,
                functools.partial(
                    self.protocol_class,
                    self.cmd_queues[server_id],
                    **self.session_kwargs
                ),
                serial_url,
                **serial_kwargs
            )
            self.sessions[server_id] = coro

        if self.gfx_coroutine is None:
            self.gfx_coroutine = self.graphics(self, self.conf)

        self.loop.run_until_complete(asyncio.gather(
            self.gfx_coroutine,
            *self.sessions.values()
        ))

    @property
    def all_idle(self):
        return all([queue.empty() for queue in self.cmd_queues.values()])

    @property
    def any_alive(self):
        # TODO: implement this
        return True

    async def relinquish_async(self):
        await asyncio.sleep(self.relinquish_time)

    async def wait_for_workers_idle_async(self):
        while not self.all_idle:
            logging.debug("waiting on queue idle")
            await self.relinquish_async()

    async def chunk_payload_with_linenum_async(
        self, server_id, cmd, args, payload
    ):
        await self.cmd_queues[server_id].put(
            (cmd, args, payload)
        )
