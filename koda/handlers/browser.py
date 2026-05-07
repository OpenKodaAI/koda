"""Browser automation command handlers: /browse, /click, /type, /screenshot, /js."""

import io

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import BROWSER_FEATURES_ENABLED
from koda.services.browser_manager import browser_manager
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


async def _check_browser() -> str | None:
    """Check if browser is available. Returns error message or None."""
    if not BROWSER_FEATURES_ENABLED:
        return "Browser automation is disabled."
    if not await browser_manager.ensure_started():
        return "Browser is not running. It may not be installed or failed to start."
    return None


@authorized
@with_approval("browse")
async def cmd_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Navigate to a URL."""
    error = await _check_browser()
    if error:
        await update.message.reply_text(error)
        return

    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /browse <url>")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    user_id = update.effective_user.id
    result = await browser_manager.navigate(user_id, url)
    await update.message.reply_text(result)


@authorized
@with_approval("click")
async def cmd_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Click an element by CSS selector."""
    error = await _check_browser()
    if error:
        await update.message.reply_text(error)
        return

    selector = " ".join(context.args) if context.args else ""
    if not selector:
        await update.message.reply_text("Usage: /click <css-selector>")
        return

    user_id = update.effective_user.id
    result = await browser_manager.click(user_id, selector)
    await update.message.reply_text(result)


@authorized
@with_approval("type")
async def cmd_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Type text into an element: /type <selector> <text>."""
    error = await _check_browser()
    if error:
        await update.message.reply_text(error)
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /type <css-selector> <text>")
        return

    selector = args[0]
    text = " ".join(args[1:])

    user_id = update.effective_user.id
    result = await browser_manager.type_text(user_id, selector, text)
    await update.message.reply_text(result)


@authorized
@with_approval("screenshot")
async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Take a screenshot of the current page."""
    error = await _check_browser()
    if error:
        await update.message.reply_text(error)
        return

    user_id = update.effective_user.id
    png_bytes = await browser_manager.screenshot(user_id)
    if png_bytes:
        await update.message.reply_photo(photo=io.BytesIO(png_bytes), caption="Screenshot")
    else:
        await update.message.reply_text("Failed to take screenshot. Navigate to a page first with /browse.")


@authorized
@with_approval("js")
async def cmd_js(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute JavaScript in the browser page."""
    error = await _check_browser()
    if error:
        await update.message.reply_text(error)
        return

    script = " ".join(context.args) if context.args else ""
    if not script:
        await update.message.reply_text("Usage: /js <javascript code>")
        return

    user_id = update.effective_user.id
    result = await browser_manager.run_js(user_id, script)
    await send_long_message(update, f"```\n{result}\n```")
