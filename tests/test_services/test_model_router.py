"""Tests for multi-model routing."""

from koda.services.model_router import (
    MODEL_CODEX_MEDIUM,
    MODEL_CODEX_SMALL,
    MODEL_HAIKU,
    MODEL_OPUS,
    MODEL_SONNET,
    estimate_complexity,
)


class TestEstimateComplexity:
    def test_simple_greeting(self):
        model = estimate_complexity("hi")
        assert model == MODEL_HAIKU

    def test_simple_question(self):
        model = estimate_complexity("what is Python?")
        assert model == MODEL_HAIKU

    def test_medium_query(self):
        model = estimate_complexity("How do I read a file in Python and process its contents?")
        assert model in (MODEL_HAIKU, MODEL_SONNET)

    def test_complex_query_with_code(self):
        query = """
        Please refactor this complex function:
        ```python
        def process(data):
            import json
            class Handler:
                def handle(self):
                    pass
            return Handler()
        ```
        """
        model = estimate_complexity(query)
        assert model in (MODEL_SONNET, MODEL_OPUS)

    def test_complex_keywords_boost(self):
        model = estimate_complexity("Refactor the authentication system and optimize the database queries")
        assert model in (MODEL_SONNET, MODEL_OPUS)

    def test_long_query_boosts(self):
        model = estimate_complexity("x " * 2000)
        assert model in (MODEL_SONNET, MODEL_OPUS)

    def test_images_at_least_sonnet(self):
        model = estimate_complexity("hi", has_images=True)
        assert model in (MODEL_SONNET, MODEL_OPUS)

    def test_code_presence_boosts(self):
        model = estimate_complexity("def foo():\n    import os\n    class Bar:\n        pass")
        assert model != MODEL_HAIKU

    def test_tool_query_jira_tasks(self):
        model = estimate_complexity("show my Jira tasks in progress")
        assert model == MODEL_HAIKU

    def test_tool_query_portuguese(self):
        model = estimate_complexity("quais tarefas estão em progresso?")
        assert model == MODEL_HAIKU

    def test_tool_query_with_complex_keyword_not_downgraded(self):
        model = estimate_complexity("analyze and refactor the Jira issues")
        assert model != MODEL_HAIKU

    def test_codex_provider_routes_to_codex_models(self):
        model = estimate_complexity("show my Jira tasks in progress", provider="codex")
        assert model == MODEL_CODEX_SMALL

    def test_codex_images_need_at_least_medium(self):
        model = estimate_complexity("hi", provider="codex", has_images=True)
        assert model in (MODEL_CODEX_MEDIUM,)
