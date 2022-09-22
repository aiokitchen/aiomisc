import asyncio
from asyncio import (
    CancelledError, Future, Task, create_task, wait, AbstractEventLoop,
)
from contextlib import suppress
from itertools import filterfalse
from time import monotonic
from typing import (
    Any, Coroutine, Iterable, List, Optional, Sequence, Tuple, Union,
)


ToC = Union[Task, Coroutine]
dummy = object()


async def gather(
        *tocs: Optional[ToC],
        loop: Optional[AbstractEventLoop] = None,
        return_exceptions: bool = False,
) -> list:
    """
    Same as `asyncio.gather`, but allows to pass Nones untouched.
    :param tocs: list of tasks/coroutines/Nones.
    Nones are skipped and returned as is.
    :param loop:
    :param return_exceptions: whether to return exceptions
    :returns: list of task/coroutine return values
    """
    ret = [dummy if tfc else None for tfc in tocs]
    res = await asyncio.gather(
        *filter(None, tocs), loop=loop, return_exceptions=return_exceptions,
    )
    for i, val in enumerate(ret):
        if val is not None:
            ret[i] = res.pop(0)
    return ret


async def gather_shackled(
        *tocs: Optional[ToC],
        wait_cancelled: bool = False,
) -> list:
    """
    Gather tasks dependently. If any of them is failed, then, other tasks
    are cancelled and the original exception is raised.
    :param tocs: list of tasks/coroutines/Nones.
    Nones are skipped and returned as is.
    :param wait_cancelled: whether to wait until all the other tasks are
    cancelled upon any fail or external cancellation.
    :returns: list of results (values or exceptions)
    """
    return await gather_graceful(
        primary=tocs, secondary=None, wait_cancelled=wait_cancelled,
    )


async def gather_independent(
        *tocs: Optional[ToC],
        wait_cancelled: bool = False,
) -> list:
    """
    Gather tasks independently. If any of them is failed, then, other tasks
    are NOT cancelled and processed as is. Any raised exceptions are returned.
    :param tocs: list of tasks/coroutines/Nones.
    Nones are skipped and returned as is.
    :param wait_cancelled: whether to wait until all the other tasks are
    cancelled upon primary fail or external cancellation.
    :returns: list of results (values or exceptions)
    """
    return await gather_graceful(
        primary=None, secondary=tocs, wait_cancelled=wait_cancelled,
    )


async def gather_graceful(
        primary: Optional[Sequence[Optional[ToC]]] = None, *,
        secondary: Sequence[Optional[ToC]] = None,
        wait_cancelled: bool = False,
) -> Union[list, Tuple[list, list]]:
    """
    Gather tasks in two groups - primary and secondary. If any primary
    is somehow failed, then, other tasks are cancelled. If secondary is failed,
    then, nothing else is done. If any primary is failed, then, will raise the
    first exception. Returns two lists of results, one for the primary tasks
    (only values) and the other for the secondary tasks (values or exceptions).
    :param primary: list of tasks/coroutines/Nones.
    Nones are skipped and returned as is.
    :param secondary: list of tasks/coroutines/Nones.
    Nones are skipped and returned as is.
    :param wait_cancelled: whether to wait until all the other tasks are
    cancelled upon primary fail or external cancellation.
    :returns: either primary results or secondary results or both
    :raises ValueError: if both primary and secondary are None
    """
    if primary is None and secondary is None:
        raise ValueError("Either primary or secondary must not be None")

    tasks_primary = [
        create_task(toc) if isinstance(toc, Coroutine) else toc
        for toc in primary or []
    ]
    tasks_secondary = [
        create_task(toc) if isinstance(toc, Coroutine) else toc
        for toc in secondary or []
    ]

    await wait_graceful(
        filter(None, tasks_primary),
        filter(None, tasks_secondary),
        wait_cancelled=wait_cancelled,
    )

    ret_primary = []
    ret_secondary = []
    if tasks_primary:
        ret_primary = await _gather_primary(tasks_primary)
    if tasks_secondary:
        ret_secondary = await _gather_secondary(tasks_secondary)

    if primary is None and secondary is not None:
        return ret_secondary

    if primary is not None and secondary is None:
        return ret_primary

    return ret_primary, ret_secondary


async def _gather_primary(tasks: Sequence[Optional[Task]]):
    return [await task if task else None for task in tasks]


async def _gather_secondary(tasks: Sequence[Optional[Task]]):
    ret: List[Optional[Any]] = []
    for task in tasks:
        if task is None:
            ret.append(None)
            continue
        try:
            ret.append(await task)
        except CancelledError as e:
            # Check whether cancelled internally
            if task.cancelled():
                ret.append(e)
                continue
            raise
        except Exception as e:
            ret.append(e)
    return ret


async def wait_graceful(
        primary: Optional[Iterable[Task]] = None,
        secondary: Optional[Iterable[Task]] = None,
        *,
        wait_cancelled: bool = False,
):
    """
    Waits for the tasks in two groups - primary and secondary. If any primary
    is somehow failed, then, other tasks are cancelled. If secondary is failed,
    then, nothing else is done. If any primary is failed, then, will raise the
    first exception.
    :param primary: optional iterable of primary tasks.
    :param secondary: optional iterable of secondary tasks.
    :param wait_cancelled: whether to wait until all the other tasks are
    cancelled upon primary fail or external cancellation.
    """
    await _wait_graceful(
        primary or [],
        secondary or [],
        wait_cancelled=wait_cancelled,
    )


async def _wait_graceful(
        primary: Iterable[Task],
        secondary: Iterable[Task],
        *,
        wait_cancelled: bool = False,
):
    primary, secondary = set(primary), set(secondary)
    to_cancel = set()
    failed_primary_task = None
    try:
        # If any primary tasks
        if primary:
            # Wait for primary tasks first
            done, pending = await wait_first_cancelled_or_exception(primary)
            # If any failed, cancel pending primary and all secondary task
            failed_primary_task = _first_cancelled_or_exception(*done)
            if failed_primary_task:
                to_cancel.update(pending | secondary)
        # If no primary task failed, wait for secondary tasks
        if not failed_primary_task and secondary:
            await wait(secondary)
    except CancelledError:
        # If was cancelled externally, cancel all tasks
        to_cancel.update(primary | secondary)

    # Keep only pending tasks
    to_cancel = set(filterfalse(Future.done, to_cancel))

    # Cancel tasks
    for task in to_cancel:
        task.cancel()

    # Wait for cancelled tasks to complete suppressing external cancellation
    if wait_cancelled and to_cancel:
        with suppress(CancelledError):
            await wait(to_cancel)

    # If some primary task failed or cancelled internally, raise exception
    if failed_primary_task:
        return failed_primary_task.result()
    # If was cancelled externally
    if to_cancel:
        raise CancelledError


def _first_cancelled_or_exception(*fs: Future):
    for fut in fs:
        if fut.cancelled() or fut.exception():
            return fut


async def wait_first_cancelled_or_exception(
        fs: Iterable[Future], *,
        loop: Optional[AbstractEventLoop] = None,
        timeout: float = None,
):
    """
    Waits for the futures until any of them is cancelled or raises an exception
    :param Iterable[Future] fs: iterable of future objects to wait for
    :param loop:
    :param float timeout: wait timeout, same as for `asyncio.wait`
    """
    t = monotonic()
    done = set()
    pending = set(fs)
    left = timeout
    while pending and (left is None or left > 0):
        if left is not None and timeout is not None:
            left = timeout - (monotonic() - t)
        d, p = await wait(
            pending, timeout=left,
            return_when=asyncio.FIRST_COMPLETED,
            loop=loop,
        )
        done.update(d)
        pending = p
        if _first_cancelled_or_exception(*d):
            break
    return done, pending
