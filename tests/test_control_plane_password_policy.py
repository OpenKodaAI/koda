"""Table-driven tests for the operator password policy."""

from __future__ import annotations

import pytest

from koda.control_plane.password_policy import PasswordPolicyError, validate_password


@pytest.mark.parametrize(
    "password",
    [
        "CorrectHorseBattery!9",
        "RiverBend$Quiet17!",
        "tr0ub4dor&3*Opus",
        "SailorMoon$Moonbeam2026",
    ],
)
def test_strong_passwords_accepted(password: str) -> None:
    validate_password(password, min_length=12, username="owner", email="owner@example.com")


@pytest.mark.parametrize(
    "password,error_code",
    [
        ("short1!", "password_too_short"),
        ("a" * 300, "password_too_long"),
        ("alllowercaseonly", "password_weak_composition"),  # only one class
        ("ALLUPPERONLY12XX", "password_weak_composition"),  # two classes (upper, digit)
        ("OnlyLettersNoOthers", "password_weak_composition"),  # upper+lower, < 3 classes
        ("password1234!", "password_too_common"),
        ("Welcome2025!", "password_too_common"),
        ("OwnerOwner!12a", "password_contains_identifier"),  # contains "owner"
        ("aaaa1A!aaaaaaaaaaaa", "password_low_entropy"),
    ],
)
def test_weak_passwords_rejected(password: str, error_code: str) -> None:
    with pytest.raises(PasswordPolicyError) as info:
        validate_password(password, min_length=12, username="owner", email="owner@example.com")
    assert info.value.code == error_code


def test_missing_password_rejected() -> None:
    with pytest.raises(PasswordPolicyError) as info:
        validate_password("", min_length=12, username="owner", email="owner@example.com")
    assert info.value.code == "password_too_short"
