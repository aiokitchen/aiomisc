from aiomisc.counters import Statistic, get_statistics


class StatSimple(Statistic):
    test_prop: int
    foo: int
    bar: float


class StatChild(StatSimple):
    baz: int


def test_get_statistics():
    assert list(get_statistics(StatSimple, StatChild)) == []

    simple = StatSimple()

    assert list(get_statistics(StatSimple, StatChild))

    simple.test_prop += 1

    for klass, name, metric, value in get_statistics(StatSimple, StatChild):
        if metric != "test_prop":
            continue

        assert value == 1

    # decref all
    del simple, klass, metric, value

    assert list(get_statistics(StatSimple, StatChild)) == []


def test_inheritance():
    stat = StatChild()

    assert stat.test_prop == 0
    assert stat.foo == 0
    assert stat.bar == 0.0
    assert stat.baz == 0
