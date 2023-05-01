import logging
import os
from types import MappingProxyType
from typing import Callable, Mapping


def setup_plugins() -> Mapping[str, Callable]:
    if os.getenv("AIOMISC_NO_PLUGINS"):
        return MappingProxyType({})

    import pkg_resources

    plugins = {}

    for entry_point in pkg_resources.iter_entry_points("aiomisc.plugins"):
        plugins[entry_point.name] = entry_point.load()

    for entry_point in pkg_resources.iter_entry_points("aiomisc"):
        plugins[entry_point.name] = entry_point.load()

    logger = logging.getLogger(__name__)
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
