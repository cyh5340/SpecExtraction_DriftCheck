def greet(name):
    return f"Hi, {name}."


def normalize_email(email):
    return email.strip()


def parse_bool(value):
    """Return True for "yes", "true" or "1" (case-insensitive), otherwise False."""
    return value in ("yes", "true", "1")
