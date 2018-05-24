import argparse
import logging
import os
import re
from pprint import pformat, pprint

import coloredlogs
from telecortex.mapping import MAPS_DOME, MAPS_DOME_SIMPLIFIED, MAPS_GOGGLE
from telecortex.mapping import PANELS_DOME_SIMPLIFIED, PANELS_DOME_MAPPED_OVERHEAD, PANELS_GOGGLE
from telecortex.session import SERVERS_DOME, SERVERS_SINGLE


class TeleCortexConfig(object):
    def __init__(self, name, description, default_config='dome'):
        self.name = name

        self.parser = argparse.ArgumentParser(description=description)
        self.parser.add_argument('--verbose', '-v', action='count', default=1)
        self.parser.add_argument('--verbosity', action='store', dest='verbose', type=int)
        self.parser.add_argument('--quiet', '-q', action='store_const', const=0, dest='verbose')
        self.parser.add_argument('--enable-log', default=True)
        self.parser.add_argument('--disable-log', action='store_false', dest='enable_log')
        self.parser.add_argument(
            '--config',
            choices=['dome', 'dome_simplified', 'single', 'goggles'],
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
            'dome': SERVERS_DOME,
            'dome_simplified': SERVERS_DOME,
            'single': SERVERS_SINGLE,
            'goggles': SERVERS_SINGLE,
        }.get(self.args.config, SERVERS_SINGLE)

        self.maps = {
            'dome': MAPS_DOME,
            'dome_simplified': MAPS_DOME_SIMPLIFIED,
            'single': MAPS_DOME_SIMPLIFIED,
            'goggles': MAPS_GOGGLE,
        }.get(self.args.config, MAPS_DOME_SIMPLIFIED)

        self.panels = {
            'dome': PANELS_DOME_MAPPED_OVERHEAD,
            'dome_simplified': PANELS_DOME_SIMPLIFIED,
            'single': PANELS_DOME_SIMPLIFIED,
            'goggles': PANELS_GOGGLE
        }.get(self.args.config, PANELS_DOME_SIMPLIFIED)

        logging.debug("conf.servers:\n%s" % pformat(self.servers))
        logging.debug("conf.maps:\n%s" % pformat(self.maps))
        logging.debug("conf.panels:\n%s" % pformat(self.panels))

    def setup_logger(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(logging.DEBUG)
        if self.args.enable_log:
            self.logger.addHandler(self.file_handler)
        self.stream_handler = logging.StreamHandler()
        self.stream_handler.setLevel(self.log_level)
        if os.name != 'nt':
            self.stream_handler.setFormatter(coloredlogs.ColoredFormatter())
        self.stream_handler.addFilter(coloredlogs.HostNameFilter())
        self.stream_handler.addFilter(coloredlogs.ProgramNameFilter())
        self.logger.addHandler(self.stream_handler)
