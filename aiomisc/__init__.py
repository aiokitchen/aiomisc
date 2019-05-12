import logging
import pkg_resources

from . import io
from . import log

from .backoff import asyncbackoff
from .context import Context, get_context
from .entrypoint import entrypoint
from .iterator_wrapper import IteratorWrapper
from .periodic import PeriodicCallback
from .service import Service
from .signal import Signal, receiver
from .thread_pool import threaded, threaded_iterable, ThreadPoolExecutor
from .timeout import timeout

from .utils import (
    bind_socket, chunk_list, new_event_loop, select, SelectResult, shield
)


plugins = {
    entry_point.name: entry_point.load()
    for entry_point
    in pkg_resources.iter_entry_points('aiomisc.plugins')
}


def setup_plugins():
    logger = logging.getLogger(__name__)
    for name, plugin in plugins.items():
        try:
            logger.debug("Trying to load %r %r", name, plugin)
            plugin.setup()
        except:  # noqa
            logger.exception('Error on %s aiomisc plugin setup', name)
            raise


setup_plugins()


__all__ = (
    'asyncbackoff', 'Context', 'get_context', 'plugins',
    'entrypoint', 'io', 'IteratorWrapper', 'log', 'PeriodicCallback',
    'Service', 'threaded', 'threaded_iterable', 'ThreadPoolExecutor',
    'timeout', 'bind_socket', 'chunk_list', 'new_event_loop', 'select',
    'SelectResult', 'shield', 'Signal', 'receiver',
)
