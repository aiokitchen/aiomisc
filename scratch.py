import logging
from typing import Any

import aiomisc

from time import sleep


class SuicideService(aiomisc.service.RespawningProcessService):
    @classmethod
    def in_process(cls) -> Any:
        sleep(1)
        logging.warning("Goodbye mad world")
        exit(42)


if __name__ == '__main__':
    with aiomisc.entrypoint(SuicideService()) as loop:
        loop.run_forever()
