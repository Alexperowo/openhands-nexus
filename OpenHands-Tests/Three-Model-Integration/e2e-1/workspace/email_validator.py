import re

def is_valid_email(email: str) -> bool:
    if not isinstance(email, str) or not email.strip():
        return False
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return bool(re.match(pattern, email.strip()))
