"""File operation command handlers: /write, /edit, /rm, /mkdir, /cat."""

from telegram import Update
from telegram.ext import ContextTypes

from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.files import NO_WORK_DIR_MESSAGE, file_command_path, file_command_work_dir, resolve_work_path
from koda.utils.messaging import send_long_message


@authorized
@with_approval("write")
async def cmd_write(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Write content to a file: /write <path> <content>."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /write <path> <content>")
        return

    path_arg = file_command_path("write", args)
    content = " ".join(args[1:])
    work_dir = file_command_work_dir(context.user_data)
    if work_dir is None:
        await update.message.reply_text(NO_WORK_DIR_MESSAGE)
        return

    from koda.utils.files import safe_write

    result = safe_write(path_arg, content, work_dir)
    await update.message.reply_text(result)


@authorized
@with_approval("edit")
async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Append content to a file: /edit <path> <content>."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /edit <path> <content to append>")
        return

    path_arg = file_command_path("edit", args)
    content = " ".join(args[1:])
    work_dir = file_command_work_dir(context.user_data)
    if work_dir is None:
        await update.message.reply_text(NO_WORK_DIR_MESSAGE)
        return

    resolution = resolve_work_path(path_arg, work_dir, deny_sensitive_dirs=False)
    if resolution.path is None:
        await update.message.reply_text(resolution.error or "Access denied.")
        return
    target = resolution.path

    if not target.exists():
        await update.message.reply_text(f"File not found: {path_arg}")
        return

    try:
        with open(target, "a") as f:
            f.write(content + "\n")
        await update.message.reply_text(f"Appended to: {path_arg}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@authorized
@with_approval("rm")
async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a file: /rm <path>."""
    path_arg = file_command_path("rm", context.args)
    if not path_arg:
        await update.message.reply_text("Usage: /rm <path>")
        return

    work_dir = file_command_work_dir(context.user_data)
    if work_dir is None:
        await update.message.reply_text(NO_WORK_DIR_MESSAGE)
        return

    from koda.utils.files import safe_delete

    result = safe_delete(path_arg, work_dir)
    await update.message.reply_text(result)


@authorized
@with_approval("mkdir")
async def cmd_mkdir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a directory: /mkdir <path>."""
    path_arg = file_command_path("mkdir", context.args)
    if not path_arg:
        await update.message.reply_text("Usage: /mkdir <path>")
        return

    work_dir = file_command_work_dir(context.user_data)
    if work_dir is None:
        await update.message.reply_text(NO_WORK_DIR_MESSAGE)
        return
    resolution = resolve_work_path(path_arg, work_dir, deny_sensitive_dirs=False)
    if resolution.path is None:
        await update.message.reply_text(resolution.error or "Access denied.")
        return
    target = resolution.path

    if target.exists():
        await update.message.reply_text(f"Already exists: {path_arg}")
        return

    try:
        target.mkdir(parents=True, exist_ok=True)
        await update.message.reply_text(f"Created directory: {path_arg}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@authorized
@with_approval("cat")
async def cmd_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Read and display file contents: /cat <path>."""
    path_arg = file_command_path("cat", context.args)
    if not path_arg:
        await update.message.reply_text("Usage: /cat <path>")
        return

    work_dir = file_command_work_dir(context.user_data)
    if work_dir is None:
        await update.message.reply_text(NO_WORK_DIR_MESSAGE)
        return

    from koda.utils.files import safe_read

    result = safe_read(path_arg, work_dir)
    await send_long_message(update, f"```\n{result}\n```")
