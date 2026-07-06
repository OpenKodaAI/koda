from __future__ import annotations

from unittest.mock import patch

from koda.memory.quality import apply_memory_utility_feedback


def test_apply_memory_utility_feedback_updates_selected_memory_scores() -> None:
    with (
        patch(
            "koda.memory.napkin.get_memory_recall_audits",
            return_value=[
                {
                    "selected": [
                        {"memory_id": 10},
                        {"memory_id": 11},
                        {"memory_id": 10},
                    ]
                }
            ],
        ) as mock_audits,
        patch("koda.memory.napkin.adjust_memory_quality_scores", return_value=2) as mock_adjust,
        patch("koda.memory.quality.record_memory_quality_counter") as mock_counter,
    ):
        updated = apply_memory_utility_feedback(agent_id="AGENT_A", user_id=42, task_id=77, outcome="useful")

    assert updated == 2
    mock_audits.assert_called_once_with(42, agent_id="agent_a", task_id=77, limit=3)
    mock_adjust.assert_called_once_with([10, 11], delta=0.03, agent_id="agent_a")
    mock_counter.assert_called_once_with("AGENT_A", "utility_quality_update", "useful", delta=2)
