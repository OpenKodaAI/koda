"""Tests for deterministic runtime task classification."""

from koda.services.runtime.classifier import classify_task


def test_classify_heavy_browser_work():
    classification = classify_task("Open a browser, run playwright tests, install dependencies, and validate the app")

    assert classification.classification == "heavy"
    assert classification.environment_kind == "dev_worktree_browser"
    assert classification.isolation == "worktree"


def test_classify_light_default():
    classification = classify_task("Explique o código e responda a dúvida")

    assert classification.classification == "light"
    assert classification.environment_kind == "dev_worktree"
    assert classification.duration == "short"
