"""Test doubles that sit at the edges of the runtime.

``tests.fakes.provider`` replaces a provider adapter (the entry that
``koda.services.llm_runner`` dispatches to) with a scripted runner, and
``tests.fakes.telegram`` replaces the Telegram bot, application and update.
Everything between those edges, from the queue through provider fallback,
the agent tool loop, persistence and response delivery, stays real.
"""
