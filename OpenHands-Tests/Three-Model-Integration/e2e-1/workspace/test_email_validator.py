from email_validator import is_valid_email

def test_valid_emails():
    assert is_valid_email('user@example.com') is True
    assert is_valid_email('first.last+tag@sub.domain.org') is True

def test_invalid_emails():
    assert is_valid_email('plainaddress') is False
    assert is_valid_email('@missingusername.com') is False
    assert is_valid_email('user@.com') is False
    assert is_valid_email('') is False
