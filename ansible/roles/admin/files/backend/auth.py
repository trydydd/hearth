"""
auth.py — Password verification helper for the CafeBox admin backend.

Tries PAM first (requires the ``python3-pam`` system package).  Falls back
to ``spwd`` / ``crypt`` for environments where PAM is not available (e.g.
CI, development containers).
"""

from __future__ import annotations


def verify_password(username: str, password: str) -> bool:
    """Return ``True`` if *password* is correct for system account *username*.

    PAM is tried first.  If the ``pam`` module is not installed the function
    falls back to reading ``/etc/shadow`` directly, which requires the process
    to run as root or as a member of the ``shadow`` group.

    Returns ``False`` if neither method is available (e.g. pure unit-test
    environment) so that callers can stub / mock this function in tests.
    """
    try:
        import pam  # python3-pam

        return pam.pam().authenticate(username, password)
    except ImportError:
        pass

    try:
        import crypt  # noqa: PLC0415  (deprecated in 3.13 but still available)
        import spwd  # noqa: PLC0415  (Unix only)

        entry = spwd.getspnam(username)
        return crypt.crypt(password, entry.sp_pwd) == entry.sp_pwd
    except (ImportError, KeyError, PermissionError):
        pass

    return False
