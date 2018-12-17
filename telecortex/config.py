import argparse
import logging
import os
import re
from builtins import super
from pprint import pformat, pprint

import coloredlogs
from telecortex.mapping import (MAPS_DOME_DJ, MAPS_DOME_OVERHEAD,
                                MAPS_DOME_SIMPLIFIED, MAPS_DOME_TRIFORCE,
                                MAPS_GOGGLE, MAPS_TRIFORCE, PANELS_DOME_DJ,
                                PANELS_DOME_OVERHEAD, PANELS_DOME_SIMPLIFIED,
                                PANELS_DOME_TRIFORCE, PANELS_GOGGLE,
                                PANELS_TRIFORCE)
from telecortex.session import (SERVERS_DOME, SERVERS_SINGLE,
                                TelecortexSession, TelecortexSessionManager,
                                TelecortexThreadManager,
                                TelecortexVirtualManager,
                                TeleCortexVirtualThreadManager,
                                VirtualTelecortexSession)


class TeleCortexConfig(object):
    def __init__(self, name, description, default_config='dome'):
        self.name = name

        self.parser = argparse.ArgumentParser(description=description)
        self.parser.add_argument('--verbose', '-v', action='count', default=1)
        self.parser.add_argument('--verbosity', action='store',
                                 dest='verbose', type=int)
        self.parser.add_argument('--quiet', '-q', action='store_const',
                                 const=0, dest='verbose')
        self.parser.add_argument('--enable-log-file', default=False)
        self.parser.add_argument('--max-ack-queue', default=5, type=int)
        self.parser.add_argument('--do-crc', default=True)
        self.parser.add_argument('--skip-crc', action='store_false',
                                 dest='do_crc')
        self.parser.add_argument('--virtual', action='store_true')
        self.parser.add_argument('--ignore-acks', action='store_true',
                                 default=False)
        self.parser.add_argument('--chunk-size', default=230, type=int)
        self.parser.add_argument('--ser-buf-size', default=(230 * 1.2),
                                 type=int)

        # self.parser.add_argument('--disable-log-file', action='store_false',
        #                          dest='enable_log_file')
        self.parser.add_argument(
            '--config',
            choices=[
                'dome', 'dome_simplified', 'dome_overhead', 'single',
                'goggles', 'triforce'
            ],
            default=default_config
        )
        self.args = argparse.Namespace()

    @property
    def handle(self):
        handle = self.name.lower()
        handle, _ = re.subn('\W', '_', handle)
        return handle

    @property
    def log_file(self):
        return ".%s.log" % self.handle

    @property
    def quiet(self):
        if hasattr(self.args, 'verbose') and self.args.verbose is not None:
            return self.args.verbose == 0
        return False

    @property
    def log_level(self):
        if hasattr(self.args, 'verbose') and self.args.verbose is not None:
            return 50 - 10 * self.args.verbose
        return 40

    def parse_args(self, *args, **kwargs):
        self.args = self.parser.parse_args(*args, **kwargs)
        self.process_args()

    def process_args(self):
        self.setup_logger()

        self.servers = {
            'dome_overhead': SERVERS_DOME,
            'dome_dj': SERVERS_DOME,
            'dome_simplified': SERVERS_DOME,
            'dome_triforce': SERVERS_SINGLE,
            'triforce': SERVERS_SINGLE,
            'single': SERVERS_SINGLE,
            'goggles': SERVERS_SINGLE,
        }.get(self.args.config, SERVERS_SINGLE)

        self.maps = {
            'dome_overhead': MAPS_DOME_OVERHEAD,
            'dome_dj': MAPS_DOME_DJ,
            'dome_simplified': MAPS_DOME_SIMPLIFIED,
            'dome_triforce': MAPS_DOME_TRIFORCE,
            'triforce': MAPS_TRIFORCE,
            'single': MAPS_DOME_SIMPLIFIED,
            'goggles': MAPS_GOGGLE,
        }.get(self.args.config, MAPS_DOME_SIMPLIFIED)

        self.panels = {
            'dome_overhead': PANELS_DOME_OVERHEAD,
            'dome_dj': PANELS_DOME_DJ,
            'dome_simplified': PANELS_DOME_SIMPLIFIED,
            'dome_triforce': PANELS_DOME_TRIFORCE,
            'triforce': PANELS_TRIFORCE,
            'single': PANELS_DOME_SIMPLIFIED,
            'goggles': PANELS_GOGGLE
        }.get(self.args.config, PANELS_DOME_SIMPLIFIED)

        logging.debug("conf.servers:\n%s" % pformat(self.servers))
        logging.debug("conf.maps:\n%s" % pformat(self.maps))
        logging.debug("conf.panels:\n%s" % pformat(self.panels))
        logging.debug("conf.args:\n%s" % pformat(vars(self.args)))

    def setup_logger(self):
        self.logger = logging.getLogger()
        if self.quiet:
            self.logger.setLevel(logging.CRITICAL)
        else:
            self.logger.setLevel(logging.DEBUG)
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(logging.DEBUG)
        if self.args.enable_log_file:
            self.logger.addHandler(self.file_handler)
        self.stream_handler = logging.StreamHandler()
        self.stream_handler.setLevel(self.log_level)
        if os.name != 'nt':
            self.stream_handler.setFormatter(coloredlogs.ColoredFormatter())
        self.stream_handler.addFilter(coloredlogs.HostNameFilter())
        self.stream_handler.addFilter(coloredlogs.ProgramNameFilter())
        self.logger.addHandler(self.stream_handler)

    @property
    def session_kwargs(self):
        return {
            'max_ack_queue': self.args.max_ack_queue,
            'do_crc': self.args.do_crc,
            'ignore_acks': self.args.ignore_acks,
            'chunk_size': self.args.chunk_size,
            'ser_buf_size': self.args.ser_buf_size
        }


class TeleCortexSessionConfig(TeleCortexConfig):
    """
    Config for a single session
    """

    @property
    def session_class(self):
        return VirtualTelecortexSession if self.args.virtual \
            else TelecortexSession

    def setup_session(self, ser):
        sesh = self.session_class(ser, **self.session_kwargs)
        sesh.reset_board()
        return sesh


class TeleCortexManagerConfig(TeleCortexConfig):
    """
    Config for multiple managed sessions
    """

    real_manager_class = TelecortexSessionManager
    virtual_manager_class = TelecortexVirtualManager

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def manager_class(self):
        return self.virtual_manager_class if self.args.virtual \
            else self.real_manager_class

    def setup_manager(self):
        return self.manager_class(self.servers, **self.session_kwargs)

class TeleCortexThreadManagerConfig(TeleCortexManagerConfig):
    real_manager_class = TelecortexThreadManager
    virtual_manager_class = TeleCortexVirtualThreadManager
