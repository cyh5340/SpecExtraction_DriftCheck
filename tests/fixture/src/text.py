def greet(name):
    return f"Hello, {name}!"


def normalize_email(email):
    return email.strip().lower()


def parse_bool(value):
    """Return True for "yes", "true" or "1" (case-insensitive), otherwise False."""
    return value.lower() in ("yes", "true", "1")
