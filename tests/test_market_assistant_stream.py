import pytest

from app.tools.market_assistant_stream import AnswerTextStreamExtractor


def test_extractor_returns_incremental_chunks_in_order():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{"answer_') == ""
    assert extractor.feed('text":"现在') == "现在"
    assert extractor.feed("市场\\n正在") == "市场\n正在"
    assert extractor.feed('变化","sections":') == "变化"
    extractor.finish()


def test_extractor_decodes_json_string_escapes():
    extractor = AnswerTextStreamExtractor()
    assert (
        extractor.feed('{"answer_text":"he said \\"hi\\"\\\\bye\\nnext\\ttab\\u4e2d"}')
        == 'he said "hi"\\bye\nnext\ttab中'
    )
    extractor.finish()


def test_extractor_holds_escape_split_across_deltas():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{"answer_text":"\\u4e') == ""
    assert extractor.feed('2d"}') == "中"
    extractor.finish()


def test_extractor_holds_simple_escape_split_across_deltas():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{"answer_text":"line\\') == "line"
    assert extractor.feed('nnext"}') == "\nnext"
    extractor.finish()


def test_extractor_ignores_nested_answer_text_key():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed(
        '{"nested":{"answer_text":"nested"},"answer_text":"top"}'
    ) == ("top")
    extractor.finish()


def test_extractor_does_not_emit_other_field_values():
    extractor = AnswerTextStreamExtractor()
    assert (
        extractor.feed('{"answer_text":"visible","reasoning":"secret","sections":[]}')
        == "visible"
    )
    extractor.finish()


def test_extractor_tolerates_whitespace_between_tokens():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{ "answer_text" : "  hi  " }') == "  hi  "
    extractor.finish()


def test_extractor_ignores_content_after_answer_text_string():
    extractor = AnswerTextStreamExtractor()
    assert (
        extractor.feed(
            '{"answer_text":"done","sections":[{"kind":"decision","claims":[]}]}'
        )
        == "done"
    )
    extractor.finish()


def test_extractor_feed_empty_returns_empty_string():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed("") == ""
    assert extractor.feed("") == ""


def test_extractor_rejects_non_string_delta():
    extractor = AnswerTextStreamExtractor()
    with pytest.raises(ValueError, match="answer text delta is required"):
        extractor.feed(None)


def test_finish_on_never_fed_extractor_raises_missing():
    extractor = AnswerTextStreamExtractor()
    with pytest.raises(ValueError, match="answer_text missing"):
        extractor.finish()


def test_finish_raises_when_answer_text_missing():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"sections":[]}')
    with pytest.raises(ValueError, match="answer_text missing"):
        extractor.finish()


def test_finish_raises_when_answer_text_string_incomplete():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"still streaming')
    with pytest.raises(ValueError, match="answer_text string incomplete"):
        extractor.finish()


def test_finish_raises_on_invalid_escape():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"a\\xb"}')
    with pytest.raises(ValueError, match="invalid escape"):
        extractor.finish()


def test_finish_raises_on_invalid_unicode_escape():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"\\u12xy"}')
    with pytest.raises(ValueError, match="invalid escape"):
        extractor.finish()


def test_finish_raises_on_duplicate_top_level_answer_text():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"first","answer_text":"second"}')
    with pytest.raises(ValueError, match="duplicate top-level answer_text"):
        extractor.finish()


def test_extractor_combines_surrogate_pair_escape():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{"answer_text":"\\ud83d\\ude3a"}') == "😺"
    extractor.finish()


def test_extractor_combines_surrogate_pair_split_across_deltas():
    extractor = AnswerTextStreamExtractor()
    assert extractor.feed('{"answer_text":"\\ud83d') == ""
    assert extractor.feed('\\ude3a"}') == "😺"
    extractor.finish()


def test_finish_raises_on_lone_high_surrogate_escape():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"\\ud83d"}')
    with pytest.raises(ValueError, match="invalid escape"):
        extractor.finish()


def test_finish_raises_on_lone_low_surrogate_escape():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"\\ude3a"}')
    with pytest.raises(ValueError, match="invalid escape"):
        extractor.finish()


def test_finish_raises_on_high_surrogate_followed_by_non_low_escape():
    extractor = AnswerTextStreamExtractor()
    extractor.feed('{"answer_text":"\\ud83d\\u0041"}')
    with pytest.raises(ValueError, match="invalid escape"):
        extractor.finish()
