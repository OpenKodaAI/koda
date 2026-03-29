"""Text, photo, document, and audio message handlers."""

from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from koda.config import LINK_ANALYSIS_ENABLED
from koda.logging_config import get_logger
from koda.services.artifact_ingestion import build_local_artifact_bundle
from koda.services.chat_settings import maybe_apply_agent_local_settings_from_chat
from koda.services.queue_manager import enqueue
from koda.utils.audio import build_audio_prompt, download_audio, download_voice, transcribe_audio
from koda.utils.command_helpers import authorized_with_rate_limit
from koda.utils.documents import build_document_prompt, download_document, is_supported_document
from koda.utils.images import build_image_prompt, cleanup_previous_images, download_photos, track_images
from koda.utils.reply import extract_reply_context

log = get_logger(__name__)


@authorized_with_rate_limit
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query_text = update.message.text
    if not query_text:
        return

    settings_reply = maybe_apply_agent_local_settings_from_chat(query_text, context.user_data)
    if settings_reply:
        await update.message.reply_text(settings_reply, parse_mode=ParseMode.HTML)
        return

    # Reply context
    reply_ctx = extract_reply_context(update.message)
    if reply_ctx:
        query_text = f"Previous response:\n{reply_ctx}\n\nNew question:\n{query_text}"

    # Cleanup previous images
    cleanup_previous_images(context.user_data)

    # Link analysis interception
    if LINK_ANALYSIS_ENABLED:
        from koda.utils.url_detector import extract_urls, is_link_message

        if is_link_message(update.message.text):  # Use original text, not reply-augmented
            urls = extract_urls(update.message.text)
            if urls:
                from koda.services.link_analyzer import (
                    build_link_keyboard,
                    fetch_link_metadata,
                    meta_to_dict,
                )
                from koda.utils.url_detector import url_hash

                url = urls[0]
                meta = await fetch_link_metadata(url)
                link_meta = context.user_data.setdefault("_link_meta", {})
                link_meta[url_hash(url)] = meta_to_dict(meta)
                # Limit stored metadata to prevent unbounded growth
                if len(link_meta) > 20:
                    oldest = list(link_meta.keys())[: len(link_meta) - 20]
                    for k in oldest:
                        del link_meta[k]
                keyboard = build_link_keyboard(meta)
                await update.message.reply_text(
                    meta.summary_text(),
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return  # Don't enqueue to provider execution — wait for button press

    user_id = update.effective_user.id
    await enqueue(user_id, update, context, query_text)


@authorized_with_rate_limit
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo and image document messages."""
    user_id = update.effective_user.id

    image_paths = await download_photos(update)
    if not image_paths:
        await update.message.reply_text("Could not download the image. Please try again.")
        return

    # Track images as in-flight before enqueuing
    track_images(image_paths)

    caption = update.message.caption
    query_text = build_image_prompt(caption, image_paths)

    reply_ctx = extract_reply_context(update.message)
    if reply_ctx:
        query_text = f"Previous response:\n{reply_ctx}\n\nNew question:\n{query_text}"

    # Cleanup previous images
    cleanup_previous_images(context.user_data)

    artifact_bundle = build_local_artifact_bundle(image_paths, source="telegram_photo")
    await enqueue(user_id, update, context, query_text, image_paths, artifact_bundle)


@authorized_with_rate_limit
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle non-image document messages (PDF, DOCX, TXT, etc.)."""
    user_id = update.effective_user.id

    doc = update.message.document
    if not doc or not is_supported_document(doc.mime_type):
        await update.message.reply_text(
            "Unsupported document type. Supported: PDF, DOCX, XLSX, TXT, CSV, TSV, JSON, HTML, MD, PY, YAML, XML."
        )
        return

    doc_path, doc_name = await download_document(update)
    if not doc_path:
        await update.message.reply_text("Could not download the document. Please try again.")
        return

    # Track document like images for cleanup
    track_images([doc_path])

    caption = update.message.caption
    query_text = build_document_prompt(caption, doc_path, doc_name or "document")

    reply_ctx = extract_reply_context(update.message)
    if reply_ctx:
        query_text = f"Previous response:\n{reply_ctx}\n\nNew question:\n{query_text}"

    cleanup_previous_images(context.user_data)
    artifact_bundle = build_local_artifact_bundle(
        [doc_path],
        source="telegram_document",
        mime_types={doc_path: doc.mime_type or ""},
    )
    await enqueue(user_id, update, context, query_text, [doc_path], artifact_bundle)


async def _handle_audio_common(update: Update, context: ContextTypes.DEFAULT_TYPE, audio_path: str) -> None:
    """Common logic for voice and audio handlers: transcribe and enqueue."""
    user_id = update.effective_user.id
    caption = update.message.caption

    transcription = await transcribe_audio(
        audio_path,
        provider=str(context.user_data.get("transcription_provider") or "").strip().lower() or None,
        model=str(context.user_data.get("transcription_model") or "").strip() or None,
    )

    # Cleanup the downloaded audio file
    Path(audio_path).unlink(missing_ok=True)

    if not transcription:
        await update.message.reply_text("Não foi possível transcrever o áudio. Tente novamente ou envie como texto.")
        return

    query_text = build_audio_prompt(transcription, caption)

    reply_ctx = extract_reply_context(update.message)
    if reply_ctx:
        query_text = f"Previous response:\n{reply_ctx}\n\nNew question:\n{query_text}"

    cleanup_previous_images(context.user_data)
    await enqueue(user_id, update, context, query_text)


@authorized_with_rate_limit
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages."""
    audio_path = await download_voice(update)
    if not audio_path:
        await update.message.reply_text("Could not download the voice message. Please try again.")
        return

    await _handle_audio_common(update, context, audio_path)


@authorized_with_rate_limit
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle audio file messages."""
    audio_path = await download_audio(update)
    if not audio_path:
        await update.message.reply_text("Could not download the audio file. Please try again.")
        return

    await _handle_audio_common(update, context, audio_path)
