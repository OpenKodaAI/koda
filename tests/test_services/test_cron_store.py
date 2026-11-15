"""Cron wrapper limits."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from koda.services import cron_store


def test_cron_cap_counts_the_users_jobs_on_this_agent_and_says_so() -> None:
    # list_jobs returns the user's jobs on this agent only, so the cap is per user and per agent.
    jobs_on_this_agent = [{"id": index, "job_type": "shell_command", "status": "active"} for index in range(10)]
    with (
        patch.object(cron_store, "list_jobs", return_value=jobs_on_this_agent) as list_jobs,
        patch.object(cron_store, "create_shell_command_job") as create_job,
        pytest.raises(ValueError, match=r"^Maximum of 10 cron jobs per user on this agent reached\.$"),
    ):
        cron_store.create_cron_job(user_id=111, chat_id=222, cron_expression="0 * * * *", command="ls")

    list_jobs.assert_called_once_with(111)
    create_job.assert_not_called()
