"""ship tests run inside a gate (which holds the machine-wide gate slot), so they never take the real lock:
`KB_GATE_SLOT_HELD` makes `gate_slot` a no-op. The slot's own tests (test_gate_slot.py) clear it."""
import pytest

from kb_distillery.git import gate_slot


@pytest.fixture(autouse=True)
def _no_real_gate_slot(monkeypatch):
    monkeypatch.setenv(gate_slot.HELD_ENV, "1")
