import hashlib

import pytest

from class_os.domain.record_note import RecordNoteCandidate


def test_note_candidate_is_only_a_verbatim_current_message_span_not_a_fact():
    message = "请记录：🌱小甲今天带回合成材料。请稍后核对。"
    quote = "🌱小甲今天带回合成材料。"
    candidate = RecordNoteCandidate.from_message(message, quote)
    payload = candidate.canonical()
    assert payload == {"schema_version": "class-os.record-note-candidate.v1", "status": "unverified-user-note",
                       "note_quote": quote, "source_start": message.index(quote),
                       "source_end": message.index(quote) + len(quote),
                       "source_hash": hashlib.sha256(message.encode("utf-8")).hexdigest()}
    assert not any(field in payload for field in ("student_id", "occurred_at", "kind", "fact_text", "command"))


@pytest.mark.parametrize("quote", ["", "合成编造的学生结论", "x" * 1001, "\u200b", None])
def test_blank_invented_oversized_or_hidden_note_is_not_a_candidate(quote):
    with pytest.raises(ValueError):
        RecordNoteCandidate.from_message("合成本轮原文", quote)


def test_old_history_is_not_the_source_and_source_hash_is_for_this_whole_message():
    first = RecordNoteCandidate.from_message("第一轮：合成原文", "合成原文")
    second = RecordNoteCandidate.from_message("第二轮：合成原文", "合成原文")
    assert first.source_hash != second.source_hash
    with pytest.raises(ValueError):
        RecordNoteCandidate.from_message("第二轮只有这个", "第一轮原文")


@pytest.mark.parametrize("start,end,digest", [(True, 1, "a" * 64), (-1, 0, "a" * 64),
                                            (0, 2, "a" * 64), (0, 1, "A" * 64)])
def test_source_fields_are_closed_coherent_values_not_arbitrary_metadata(start, end, digest):
    with pytest.raises(ValueError):
        RecordNoteCandidate("x", start, end, digest)


def test_overlong_quote_is_rejected_even_when_it_is_in_the_current_message():
    with pytest.raises(ValueError):
        RecordNoteCandidate.from_message("x" * 1001, "x" * 1001)
