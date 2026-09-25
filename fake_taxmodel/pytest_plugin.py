"""pytest fixtures for the fake. Enable with `pytest_plugins = ["fake_taxmodel.pytest_plugin"]`.

`fake_taxmodel` routes all httpx traffic for http://taxmodel.test to an in-process
fake and swaps time.sleep / time.monotonic / time.time for a virtual clock.
Code under test must call those through the `time` module (not `from time import
sleep`), and must not use datetime for deadlines, or real time will pass.
"""
import time

import pytest

from fake_taxmodel.clock import VirtualClock
from fake_taxmodel.engine import FakeTaxModel
from fake_taxmodel.transport import FakeTransport, install


@pytest.fixture
def virtual_clock(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    monkeypatch.setattr(time, "time", clock.time)
    return clock


@pytest.fixture
def fake_taxmodel(monkeypatch, virtual_clock):
    engine = FakeTaxModel.with_defaults(clock=virtual_clock)
    install(monkeypatch, FakeTransport(engine))
    yield engine
    if engine.violations:
        pytest.fail("fake tax-model saw contract violations:\n  " + "\n  ".join(engine.violations),
                    pytrace=False)
