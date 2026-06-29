"""Authentication and authorization."""

from telegram import Update

from koda.config import ADMIN_USER_IDS, AGENT_ID, ALLOWED_USER_IDS


def auth_check(update: Update) -> bool:
    """Return True if user is allowed. Empty ALLOWED_USER_IDS denies all access."""
    user = update.effective_user
    if not user:
        return False
    try:
        from koda.channels.gateway import evaluate_telegram_update

        decision = evaluate_telegram_update(
            update,
            agent_id=AGENT_ID,
            legacy_allowed_user_ids=ALLOWED_USER_IDS,
        )
        if decision is not None:
            return decision.allowed
    except Exception:
        # Auth must remain fail-closed if the gateway cannot evaluate safely.
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
    message = "Access denied."
    try:
        from koda.channels.gateway import denial_message_for_decision, last_decision_for_update

        message = denial_message_for_decision(last_decision_for_update(update))
    except Exception:
        pass

    if update.message:
        await update.message.reply_text(message)
    elif update.callback_query:
        await update.callback_query.answer(message, show_alert=True)
