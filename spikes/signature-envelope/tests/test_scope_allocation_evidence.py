from __future__ import annotations

import copy
import json

import pytest

from scope_allocation_evidence import EVIDENCE, validate


def test_live_evidence_is_bound_to_current_sources() -> None:
    validate(json.loads(EVIDENCE.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(production_authorization=True),
        lambda value: value.update(outage_failed_closed=False),
        lambda value: value.update(five_member_row_counts=[1, 1, 1, 0, 1]),
        lambda value: value.update(live_test_result="13 passed, 1 skipped in 2.5s"),
        lambda value: value.update(migration_sha256="0" * 64),
        lambda value: value.update(limitations=[]),
        lambda value: value["source_sha256"].update({"scope_allocation.py": "0" * 64}),
    ],
)
def test_live_evidence_mutations_fail_closed(mutate) -> None:
    evidence = copy.deepcopy(json.loads(EVIDENCE.read_text(encoding="utf-8")))
    mutate(evidence)
    with pytest.raises(ValueError):
        validate(evidence)
