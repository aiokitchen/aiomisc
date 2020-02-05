#!/usr/bin/env python3.7

import logging
import os
from multiprocessing.pool import ThreadPool
import argparse
from pathlib import Path
from subprocess import check_call


PLANTUML_JAR = Path(os.environ["PLANTUML_JAR"])
assert PLANTUML_JAR.is_file()

parser = argparse.ArgumentParser()
parser.add_argument(
    "-s",
    "--source",
    help="Source directory with plantuml files",
    required=True,
    type=Path,
)

FORMAT_EXTENSION_MAPPING = tuple(sorted({"txt", "utxt", "png", "svg"}))

parser.add_argument(
    "-f",
    "--format",
    action="append",
    metavar="FORMAT",
    choices=FORMAT_EXTENSION_MAPPING,
    default=["svg"],
)

parser.add_argument("-w", "--workers", type=int, default=8)

parser.add_argument("--pattern", default="*.puml")


def main():
    logging.basicConfig(level=logging.INFO)
    arguments = parser.parse_args()
    pool = ThreadPool(arguments.workers)
    files = list(map(str, arguments.source.rglob(arguments.pattern)))

    def convert(fmt):
        cmd = [
            "/usr/bin/java",
            "-jar",
            str(PLANTUML_JAR),
            "-t{}".format(fmt),
            "-overwrite",
            *files,
        ]
        logging.info(" ".join(cmd))
        check_call(cmd)

    for _ in pool.imap(convert, arguments.format):
        pass


if __name__ == "__main__":
    main()
