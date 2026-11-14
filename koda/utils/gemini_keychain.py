"""Gemini CLI's encrypted file keychain, from which disconnecting the provider removes the sign-ins.

Where no OS keychain works, as in Docker, the pinned Gemini CLI (``packages/provider-clis``,
0.68.0, ``FileKeychain``) keeps its keychain in one file, ``koda.config.GEMINI_CLI_FILE_KEYCHAIN``
under HOME. The file holds a JSON object (service -> account -> secret) encrypted with
AES-256-GCM and written as ``<iv>:<auth tag>:<ciphertext>`` in hex. Its key is
``scrypt("gemini-cli-oauth", "<host name>-<user name>-gemini-cli")``, 32 bytes with Node's
defaults (N=16384, r=8, p=1), so whoever reads the file on that host can decrypt it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pwd
import secrets
import socket
from collections.abc import Iterable
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_PASSWORD = b"gemini-cli-oauth"
_IV_BYTES = 12
_IV_SIZES = (12, 16)
_TAG_BYTES = 16

Keychain = dict[str, dict[str, str]]
"""A decrypted keychain: service -> account -> secret."""


def keychain_key(hostname: str, username: str) -> bytes:
    """Return the key the CLI derives for ``hostname`` and ``username`` (``FileKeychain.deriveEncryptionKey``)."""
    salt = f"{hostname}-{username}-gemini-cli".encode()
    return hashlib.scrypt(_KEY_PASSWORD, salt=salt, n=16384, r=8, p=1, dklen=32)


def current_identity() -> tuple[str, str] | None:
    """Return the host and user names the CLI derives the key from in this process, or None.

    Node's ``os.hostname()`` and ``os.userInfo().username``, which the CLI reads, are
    ``gethostname`` and the password entry of the effective user, as these are. A user with
    no password entry has no key: the CLI cannot open its keychain either.
    """
    try:
        return socket.gethostname(), pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        return None


def decrypt_keychain(data: str, key: bytes) -> Keychain:
    """Return the entries of the keychain text ``data``, as ``FileKeychain.decrypt`` reads it.

    Raises ValueError when ``data`` is not a keychain or ``key`` does not open it.
    """
    parts = data.strip().split(":")
    if len(parts) != 3:
        raise ValueError("not a Gemini CLI file keychain")
    iv, tag, encrypted = (bytes.fromhex(part) for part in parts)
    if len(iv) not in _IV_SIZES or len(tag) != _TAG_BYTES:
        raise ValueError("not a Gemini CLI file keychain")
    try:
        plain = AESGCM(key).decrypt(iv, encrypted + tag, None)
    except InvalidTag as exc:
        raise ValueError("the key of this host and user does not open the keychain") from exc
    entries = json.loads(plain.decode("utf-8"))
    if not isinstance(entries, dict) or not all(isinstance(accounts, dict) for accounts in entries.values()):
        raise ValueError("not a Gemini CLI file keychain")
    return entries


def encrypt_keychain(entries: Keychain, key: bytes) -> str:
    """Return ``entries`` encrypted as ``FileKeychain.encrypt`` writes them: a fresh 12-byte IV, a 16-byte tag."""
    iv = secrets.token_bytes(_IV_BYTES)
    sealed = AESGCM(key).encrypt(iv, json.dumps(entries, indent=2, ensure_ascii=False).encode("utf-8"), None)
    return f"{iv.hex()}:{sealed[-_TAG_BYTES:].hex()}:{sealed[:-_TAG_BYTES].hex()}"


def remove_keychain_services(path: Path, services: Iterable[str]) -> bool:
    """Remove ``services``, with every entry in them, from the file keychain at ``path``; return whether it changed.

    It does what the CLI's own ``FileKeychain.deletePassword`` does for each entry: what is
    left is encrypted again under the same key with mode 0600, and a file left with no
    service is deleted. The new content goes to a temp copy beside the file
    (``<name>.tmp.<hex>``, which the file layer refuses as a copy of the keychain), which is
    then renamed over it, so a Koda killed mid-write leaves the old keychain, never a
    truncated one that the CLI would refuse to open, losing the extensions' secrets in it.
    A missing file, one that the key of this host and user does not open, and one that
    holds none of ``services`` are left as they are.
    """
    identity = current_identity()
    if identity is None:
        return False
    target = Path(os.path.realpath(path))
    try:
        data = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    key = keychain_key(*identity)
    try:
        entries = decrypt_keychain(data, key)
    except ValueError:
        return False
    removed = [service for service in dict.fromkeys(services) if service in entries]
    if not removed:
        return False
    for service in removed:
        del entries[service]
    if not entries:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            return False
        return True
    temp = target.with_name(f"{target.name}.tmp.{secrets.token_hex(4)}")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encrypt_keychain(entries, key))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink()
        return False
    return True
