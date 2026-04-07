"""Authentication and authorization."""

from telegram import Update

from koda.config import ADMIN_USER_IDS, ALLOWED_USER_IDS


def auth_check(update: Update) -> bool:
    """Return True if user is allowed. Empty ALLOWED_USER_IDS denies all access."""
    user = update.effective_user
    if not user:
        return False
    if not ALLOWED_USER_IDS:
        return False
    return user.id in ALLOWED_USER_IDS


def is_admin(user_id: int) -> bool:
    """Return True if *user_id* belongs to an admin."""
    return user_id in ADMIN_USER_IDS


async def reject_unauthorized(update: Update) -> None:
    """Send access denied message."""
    from koda.services.audit import emit_security

    user_id = update.effective_user.id if update.effective_user else None
    emit_security("security.auth_failure", user_id=user_id)

    if update.message:
        await update.message.reply_text("Access denied.")
    elif update.callback_query:
        await update.callback_query.answer("Access denied.", show_alert=True)
