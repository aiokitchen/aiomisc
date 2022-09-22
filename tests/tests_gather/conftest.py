from asyncio import CancelledError, sleep


async def ok(delay=0):
    await sleep(delay)
    return 123


async def fail(delay=0):
    await sleep(delay)
    raise ValueError


async def cancel(delay=0):
    await sleep(delay)
    raise CancelledError
