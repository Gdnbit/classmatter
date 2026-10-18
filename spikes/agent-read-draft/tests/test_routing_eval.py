from __future__ import annotations

import hashlib

from routing_eval import CORPUS_PATH, build_corpus


def test_routing_corpus_is_320_unique_synthetic_cases():
    cases = build_corpus()
    assert len(cases) == 320
    assert len({case["case_id"] for case in cases}) == 320
    assert {case["provenance"] for case in cases} == {"synthetic-template-v1"}


def test_tracked_routing_corpus_has_expected_hash():
    assert hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest() == (
        "36de45766afc04f748c01c184ceeb6438fa5507132692180c3f950e0187490d5"
    )
