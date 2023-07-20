import logging
import os
from itertools import chain
from types import MappingProxyType
from typing import Callable, Mapping

from aiomisc.compat import entry_pont_iterator


def setup_plugins() -> Mapping[str, Callable]:
    if os.getenv("AIOMISC_NO_PLUGINS"):
        return MappingProxyType({})

    plugins = {}
    logger = logging.getLogger(__name__)

    for entry_point in chain(
        entry_pont_iterator("aiomisc.plugins"),
        entry_pont_iterator("aiomisc"),
    ):
        try:
            plugins[entry_point.name] = entry_point.load()
        except:  # noqa
            logger.exception(
                "Failed to load entrypoint %r", entry_point,
            )

    for name, plugin in plugins.items():
        try:
            logger.debug("Trying to load %r %r", name, plugin)
            plugin.setup()
        except:  # noqa
            logger.exception("Error on %s aiomisc plugin setup", name)
            raise

    return MappingProxyType(plugins)


plugins: Mapping[str, Callable] = setup_plugins()


__all__ = ("plugins",)
