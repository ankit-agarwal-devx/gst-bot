"""Fake tax-model upstream. Behaviour is defined by FAILURE_CONTRACT.md."""
from fake_taxmodel.clock import RealClock, VirtualClock
from fake_taxmodel.engine import FakeTaxModel, KeyConfig, Reply, Ticket
from fake_taxmodel.roll import PROFILES, roll

__all__ = [
    "FakeTaxModel", "KeyConfig", "Reply", "Ticket",
    "RealClock", "VirtualClock", "PROFILES", "roll",
]
