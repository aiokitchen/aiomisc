import subprocess
import sys
from textwrap import dedent

import pytest

from tests import unix_only


@unix_only
@pytest.mark.parametrize("loop_owner", [False, True])
@pytest.mark.parametrize("shutdown_timeout", [False, True])
def test_sigterm_shutdown(loop_owner, shutdown_timeout):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            dedent("""
                import asyncio
                import os
                import signal
                import sys

                import aiomisc

                loop_owner = sys.argv[1] == "True"
                shutdown_timeout = sys.argv[2] == "True"

                class SlowStop(aiomisc.Service):
                    async def start(self):
                        pass

                    async def stop(self, exception=None):
                        print("stop: begin", flush=True)
                        try:
                            if shutdown_timeout:
                                await asyncio.Event().wait()
                            else:
                                await asyncio.sleep(0.1)
                        except asyncio.CancelledError:
                            print("stop: cancelled", flush=True)
                            raise
                        print("stop: done", flush=True)

                def send_signal(loop):
                    loop.call_soon(os.kill, os.getpid(), signal.SIGTERM)

                async def main():
                    async with aiomisc.entrypoint(SlowStop(), **options) as ep:
                        send_signal(asyncio.get_running_loop())
                        await ep.closing()
                        print("closing: returned", flush=True)
                    await asyncio.sleep(0.01)
                    print("main: done", flush=True)

                options = dict(
                    log_config=False,
                    shutdown_timeout=0.05 if shutdown_timeout else 5,
                )
                if loop_owner:
                    with aiomisc.entrypoint(SlowStop(), **options) as loop:
                        send_signal(loop)
                        loop.run_forever()
                    print("main: done", flush=True)
                else:
                    asyncio.run(main())
                """),
            str(loop_owner),
            str(shutdown_timeout),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == (70 if shutdown_timeout else 0), result.stderr
    assert result.stdout.count("stop: begin") == 1
    if shutdown_timeout:
        assert "stop: cancelled" in result.stdout
        assert "stop: done" not in result.stdout
        assert "Shutdown did not happen in 0.05 seconds" in result.stderr
    else:
        assert "stop: done" in result.stdout
        assert "stop: cancelled" not in result.stdout
        assert "main: done" in result.stdout
        assert "Shutdown did not happen" not in result.stderr
