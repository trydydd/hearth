"""
auth.py — Password verification helper for the Hearth admin backend.

Uses PAM (``python3-pam`` system package) to verify system account passwords.
PAM is the correct and only supported method; the ``crypt``/``spwd`` modules
were removed in Python 3.13 (PEP 594) and are therefore unavailable on
Raspberry Pi OS Trixie (Debian 13).
"""

from __future__ import annotations


def verify_password(username: str, password: str) -> bool:
    """Return ``True`` if *password* is correct for system account *username*.

    Requires the ``python3-pam`` system package, which is installed by the
    Hearth common Ansible role.  Returns ``False`` when PAM is not available
    (e.g. CI / development environments without the system package) so that
    callers can stub / mock this function in tests.
    """
    try:
        import pam  # python3-pam

        return pam.pam().authenticate(username, password)
    except ImportError:
        pass

    return False
