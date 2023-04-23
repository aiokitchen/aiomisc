import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

from aiomisc_log import LogFormat, LogLevel, basic_config

from . import plugins


executable = Path(sys.executable)
module_name = "aiomisc.plugins"
parser = ArgumentParser(prog=f"{executable.name} -m {module_name}")
parser.add_argument(
    "-q", "-s", "--quiet", "--silent", action="store_true",
    help="Disable logs and just output plugin-list, alias for "
         "--log-level=critical",
)

parser.add_argument(
    "-n", "--no-output", action="store_true",
    help="Disable output plugin-list to the stdout",
)

parser.add_argument(
    "-l", "--log-level", choices=LogLevel.choices(),
    default=LogLevel.default(), help="Logging level",
)

parser.add_argument(
    "-F", "--log-format", choices=LogFormat.choices(),
    default=LogFormat.default(), help="Logging format",
)


def main() -> None:
    arguments = parser.parse_args()

    if arguments.quiet:
        arguments.log_level = LogLevel.critical.name

    basic_config(log_format=arguments.log_format, level=arguments.log_level)
    logging.info("Available %s plugins.", len(plugins))

    for name, plugin in sorted(plugins.items()):
        logging.info("%r - %s", name, getattr(plugin, "__doc__", ""))

        if not arguments.no_output:
            print(name)


if __name__ == "__main__":
    main()
