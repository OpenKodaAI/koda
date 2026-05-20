"""Tests for the channel abstraction types (dataclasses)."""

import dataclasses

from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage


class TestChannelIdentity:
    def test_construction_with_all_fields(self):
        identity = ChannelIdentity(
            channel_type="telegram",
            channel_id="12345",
            user_id="67890",
            user_display_name="Alice",
            is_group=True,
        )
        assert identity.channel_type == "telegram"
        assert identity.channel_id == "12345"
        assert identity.user_id == "67890"
        assert identity.user_display_name == "Alice"
        assert identity.is_group is True

    def test_is_group_defaults_to_false(self):
        identity = ChannelIdentity(
            channel_type="discord",
            channel_id="chan-1",
            user_id="usr-1",
            user_display_name="Bob",
        )
        assert identity.is_group is False

    def test_frozen_raises_on_attribute_set(self):
        identity = ChannelIdentity(
            channel_type="slack",
            channel_id="C01",
            user_id="U01",
            user_display_name="Carol",
        )
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            identity.channel_type = "whatsapp"  # type: ignore[misc]

    def test_equality(self):
        a = ChannelIdentity("telegram", "1", "2", "X")
        b = ChannelIdentity("telegram", "1", "2", "X")
        assert a == b

    def test_inequality_different_channel(self):
        a = ChannelIdentity("telegram", "1", "2", "X")
        b = ChannelIdentity("discord", "1", "2", "X")
        assert a != b

    def test_usable_as_dict_key(self):
        """Frozen dataclasses are hashable by default, so ChannelIdentity works as a dict key."""
        identity = ChannelIdentity("telegram", "1", "2", "X")
        d = {identity: "value"}
        assert d[identity] == "value"


class TestIncomingMessage:
    def test_construction_with_required_fields(self):
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        msg = IncomingMessage(
            id="msg-1",
            channel=channel,
            text="hello",
            timestamp=1700000000.0,
        )
        assert msg.id == "msg-1"
        assert msg.channel is channel
        assert msg.text == "hello"
        assert msg.timestamp == 1700000000.0

    def test_default_lists_are_empty(self):
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        msg = IncomingMessage(id="1", channel=channel, text="hi", timestamp=0.0)
        assert msg.image_paths == []
        assert msg.document_paths == []

    def test_default_optional_fields_are_none(self):
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        msg = IncomingMessage(id="1", channel=channel, text="hi", timestamp=0.0)
        assert msg.reply_to_id is None
        assert msg.audio_path is None
        assert msg.raw_platform_data is None

    def test_frozen_raises_on_attribute_set(self):
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        msg = IncomingMessage(id="1", channel=channel, text="hi", timestamp=0.0)
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            msg.text = "changed"  # type: ignore[misc]

    def test_construction_with_all_optional_fields(self):
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        msg = IncomingMessage(
            id="msg-2",
            channel=channel,
            text="look at this",
            timestamp=1700000001.0,
            reply_to_id="msg-1",
            image_paths=["/tmp/img.png"],
            document_paths=["/tmp/doc.pdf"],
            audio_path="/tmp/voice.ogg",
            raw_platform_data={"extra": True},
        )
        assert msg.reply_to_id == "msg-1"
        assert msg.image_paths == ["/tmp/img.png"]
        assert msg.document_paths == ["/tmp/doc.pdf"]
        assert msg.audio_path == "/tmp/voice.ogg"
        assert msg.raw_platform_data == {"extra": True}

    def test_default_list_instances_are_independent(self):
        """Each IncomingMessage gets its own list instance, not a shared mutable default."""
        channel = ChannelIdentity("telegram", "1", "2", "Alice")
        a = IncomingMessage(id="1", channel=channel, text="a", timestamp=0.0)
        b = IncomingMessage(id="2", channel=channel, text="b", timestamp=0.0)
        assert a.image_paths is not b.image_paths
        assert a.document_paths is not b.document_paths


class TestOutgoingMessage:
    def test_construction_with_text_only(self):
        msg = OutgoingMessage(text="hello")
        assert msg.text == "hello"

    def test_default_parse_mode_is_html(self):
        msg = OutgoingMessage(text="hi")
        assert msg.parse_mode == "html"

    def test_default_paths_are_none(self):
        msg = OutgoingMessage(text="hi")
        assert msg.voice_path is None
        assert msg.document_path is None
        assert msg.document_filename is None
        assert msg.image_path is None

    def test_is_mutable(self):
        """OutgoingMessage is NOT frozen, so attributes can be reassigned."""
        msg = OutgoingMessage(text="original")
        msg.text = "updated"
        assert msg.text == "updated"
        msg.parse_mode = "markdown"
        assert msg.parse_mode == "markdown"

    def test_construction_with_all_fields(self):
        msg = OutgoingMessage(
            text="here is a file",
            parse_mode="markdown",
            voice_path="/tmp/voice.ogg",
            document_path="/tmp/doc.pdf",
            document_filename="report.pdf",
            image_path="/tmp/img.png",
        )
        assert msg.text == "here is a file"
        assert msg.parse_mode == "markdown"
        assert msg.voice_path == "/tmp/voice.ogg"
        assert msg.document_path == "/tmp/doc.pdf"
        assert msg.document_filename == "report.pdf"
        assert msg.image_path == "/tmp/img.png"
