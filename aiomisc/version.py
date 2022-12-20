import pkg_resources


__version__ = pkg_resources.get_distribution("aiomisc").version
version_info = tuple(map(int, __version__.split(".")))
