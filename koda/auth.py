"""Authentication and authorization."""

from telegram import Update

from koda.config import ALLOWED_USER_IDS


def auth_check(update: Update) -> bool:
    """Return True if user is allowed."""
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USER_IDS)


async def reject_unauthorized(update: Update) -> None:
    """Send access denied message."""
    from koda.services.audit import emit_security

    user_id = update.effective_user.id if update.effective_user else None
    emit_security("security.auth_failure", user_id=user_id)

    if update.message:
        await update.message.reply_text("Access denied.")
    elif update.callback_query:
        await update.callback_query.answer("Access denied.", show_alert=True)
