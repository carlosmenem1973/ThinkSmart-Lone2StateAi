"""Legacy bootstrap hook retained for compatibility.

Cognito is the sole identity provider. Administrator membership must be managed
through Cognito groups; this module intentionally does not create local passwords.
"""
def ensure_bootstrap_admin() -> None:
    return None
