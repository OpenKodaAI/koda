from koda.services.response_markup import build_response_markup


def test_build_response_markup_includes_feedback_actions_for_task_outputs():
    markup = build_response_markup(42)

    rows = markup.inline_keyboard
    assert rows[0][0].callback_data == "bookmark:save"
    assert rows[1][0].callback_data == "feedback:approved:42"
    assert rows[1][1].callback_data == "feedback:corrected:42"
    assert rows[2][0].callback_data == "feedback:failed:42"
    assert rows[2][1].callback_data == "feedback:risky:42"
    assert rows[3][0].callback_data == "feedback:promote:42"


def test_build_response_markup_omits_feedback_actions_without_task_context():
    markup = build_response_markup(None)

    rows = markup.inline_keyboard
    assert len(rows) == 1
    assert rows[0][0].callback_data == "bookmark:save"
