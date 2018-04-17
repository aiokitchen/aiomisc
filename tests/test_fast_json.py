import base64
import json
from datetime import datetime

import pytest
from tempfile import TemporaryFile


CASES = [
    ({}, '{}'),
    ([], '[]'),
    ([1, 2, 3], '[1, 2, 3]'),
    ('foo/bar', '"foo/bar"'),
]


def test_dumps_unknown_object():
    class Test:
        def __init__(self, **kwargs):
            self.kw = kwargs

        def __str__(self):
            return str(self.kw)

    obj = Test(foo=1, bar=2)
    assert json.dumps(obj) == json.dumps(str(obj))


def test_dumps_bytes():
    data = b'\x00\x01'
    assert json.dumps(data) == json.dumps(base64.b64encode(data).decode())


def test_dumps_date():
    data = datetime.now()
    assert json.dumps(data) == json.dumps(data.isoformat())


@pytest.mark.parametrize("obj,json_string", CASES)
def test_dumps(obj, json_string):
    assert json.dumps(obj) == json_string


@pytest.mark.parametrize("obj,json_string", CASES)
def test_loads(obj, json_string):
    assert obj == json.loads(json_string)


@pytest.mark.parametrize("obj,json_string", CASES)
def test_dump(obj, json_string):
    with TemporaryFile('w+') as f:
        f.seek(0)
        json.dump(obj, f)
        f.seek(0)

        assert f.read() == json_string


@pytest.mark.parametrize("obj,json_string", CASES)
def test_load(obj, json_string):
    with TemporaryFile('w+') as f:
        f.seek(0)
        f.write(json_string)
        f.seek(0)

        assert json.load(f) == obj
