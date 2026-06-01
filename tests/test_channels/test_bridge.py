"""Tests for the MessageBridge implementations."""

from unittest.mock import AsyncMock, MagicMock

from koda.channels.bridge import AdapterMessageBridge, TelegramMessageBridge
from koda.channels.types import ChannelIdentity, OutgoingMessage


class TestTelegramMessageBridge:
    async def test_send_text_delegates_to_bot(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot)

        await bridge.send_text(chat_id=123, text="hello", parse_mode="html")

        bot.send_message.assert_awaited_once_with(chat_id=123, text="hello", parse_mode="html")

    async def test_send_text_returns_bot_result(self):
        bot = AsyncMock()
        bot.send_message.return_value = "sent-msg-obj"
        bridge = TelegramMessageBridge(bot=bot)

        result = await bridge.send_text(chat_id=123, text="hello")
        assert result == "sent-msg-obj"

    async def test_reply_text_delegates_to_message(self):
        bot = AsyncMock()
        message = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot, message=message)

        await bridge.reply_text("world", parse_mode="html")

        message.reply_text.assert_awaited_once_with("world", parse_mode="html")

    async def test_reply_text_with_no_message_returns_none(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot, message=None)

        result = await bridge.reply_text("hello")
        assert result is None

    async def test_reply_text_with_no_message_does_not_crash(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot, message=None)

        # Should not raise
        await bridge.reply_text("hello")

    async def test_send_typing_delegates_to_bot(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot)

        await bridge.send_typing(chat_id=456)

        bot.send_chat_action.assert_awaited_once()
        call_kwargs = bot.send_chat_action.call_args
        assert call_kwargs.kwargs["chat_id"] == 456

    async def test_send_voice_delegates_to_bot(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot)

        await bridge.send_voice(chat_id=123, voice="/tmp/voice.ogg", caption="audio")

        bot.send_voice.assert_awaited_once_with(chat_id=123, voice="/tmp/voice.ogg", caption="audio")

    async def test_send_document_delegates_to_bot(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot)

        await bridge.send_document(chat_id=123, document="/tmp/doc.pdf", filename="report.pdf", caption="doc")

        bot.send_document.assert_awaited_once_with(
            chat_id=123, document="/tmp/doc.pdf", filename="report.pdf", caption="doc"
        )

    async def test_send_photo_delegates_to_bot(self):
        bot = AsyncMock()
        bridge = TelegramMessageBridge(bot=bot)

        await bridge.send_photo(chat_id=123, photo="/tmp/img.png", caption="pic")

        bot.send_photo.assert_awaited_once_with(chat_id=123, photo="/tmp/img.png", caption="pic")


class TestAdapterMessageBridge:
    def _make_bridge(self):
        adapter = AsyncMock()
        adapter.send_text = AsyncMock(return_value="adapter-msg-id")
        adapter.send_typing = AsyncMock()
        adapter.send_voice = AsyncMock()
        adapter.send_document = AsyncMock()
        adapter.send_image = AsyncMock()
        channel = ChannelIdentity(
            channel_type="whatsapp",
            channel_id="wa-chat-1",
            user_id="wa-user-1",
            user_display_name="Dave",
        )
        bridge = AdapterMessageBridge(adapter=adapter, channel=channel)
        return bridge, adapter, channel

    async def test_send_text_creates_outgoing_and_delegates(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.send_text(chat_id="wa-chat-1", text="hello")

        adapter.send_text.assert_awaited_once()
        call_args = adapter.send_text.call_args
        assert call_args.args[0] is channel
        outgoing = call_args.args[1]
        assert isinstance(outgoing, OutgoingMessage)
        assert outgoing.text == "hello"
        assert outgoing.parse_mode == "html"

    async def test_send_text_respects_parse_mode_kwarg(self):
        bridge, adapter, _channel = self._make_bridge()

        await bridge.send_text(chat_id="x", text="hello", parse_mode="markdown")

        outgoing = adapter.send_text.call_args.args[1]
        assert outgoing.parse_mode == "markdown"

    async def test_reply_text_routes_through_send_text(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.reply_text("reply content")

        adapter.send_text.assert_awaited_once()
        call_args = adapter.send_text.call_args
        outgoing = call_args.args[1]
        assert outgoing.text == "reply content"

    async def test_send_typing_delegates_to_adapter(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.send_typing(chat_id="wa-chat-1")

        adapter.send_typing.assert_awaited_once_with(channel)

    async def test_send_voice_delegates_to_adapter(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.send_voice(chat_id="x", voice="/tmp/voice.ogg", caption="audio")

        adapter.send_voice.assert_awaited_once_with(channel, "/tmp/voice.ogg", "audio")

    async def test_send_document_delegates_to_adapter(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.send_document(chat_id="x", document="/tmp/doc.pdf", filename="report.pdf", caption="doc")

        adapter.send_document.assert_awaited_once_with(channel, "/tmp/doc.pdf", "report.pdf", "doc")

    async def test_send_photo_delegates_to_adapter_send_image(self):
        bridge, adapter, channel = self._make_bridge()

        await bridge.send_photo(chat_id="x", photo="/tmp/img.png", caption="pic")

        adapter.send_image.assert_awaited_once_with(channel, "/tmp/img.png", "pic")

    async def test_send_voice_converts_non_string_to_string(self):
        bridge, adapter, channel = self._make_bridge()
        file_obj = MagicMock()
        file_obj.__str__ = lambda self: "/tmp/converted.ogg"

        await bridge.send_voice(chat_id="x", voice=file_obj, caption="")

        adapter.send_voice.assert_awaited_once_with(channel, "/tmp/converted.ogg", "")

    async def test_send_document_converts_non_string_to_string(self):
        bridge, adapter, channel = self._make_bridge()
        file_obj = MagicMock()
        file_obj.__str__ = lambda self: "/tmp/converted.pdf"

        await bridge.send_document(
            chat_id="x",
            document=file_obj,
            filename="f.pdf",
            caption="",
        )

        adapter.send_document.assert_awaited_once_with(
            channel,
            "/tmp/converted.pdf",
            "f.pdf",
            "",
        )

    async def test_send_photo_converts_non_string_to_string(self):
        bridge, adapter, channel = self._make_bridge()
        file_obj = MagicMock()
        file_obj.__str__ = lambda self: "/tmp/converted.png"

        await bridge.send_photo(chat_id="x", photo=file_obj, caption="")

        adapter.send_image.assert_awaited_once_with(channel, "/tmp/converted.png", "")
