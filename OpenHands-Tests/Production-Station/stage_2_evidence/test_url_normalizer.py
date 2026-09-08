"""Test suite for the url_normalizer module."""

import pytest

from url_normalizer import normalize_url, parse_url


def test_normalize_url_lowercases_scheme_and_host():
    """Scheme and host must be lowercased."""
    assert normalize_url("HTTP://Example.COM/path") == "http://example.com/path"


def test_normalize_url_removes_default_ports():
    """Default ports (80 for http, 443 for https) are removed."""
    assert normalize_url("http://example.com:80/path") == "http://example.com/path"
    assert normalize_url("https://example.com:443/path") == "https://example.com/path"


def test_normalize_url_preserves_non_default_ports():
    """Non-default ports must be kept untouched."""
    assert normalize_url("http://example.com:8080/path") == "http://example.com:8080/path"
    assert normalize_url("https://example.com:8443/path") == "https://example.com:8443/path"


def test_normalize_url_sorts_query_params_and_drops_empty():
    """Query parameters are sorted by key and empty ones dropped."""
    assert normalize_url("http://example.com/path?b=2&a=1") == "http://example.com/path?a=1&b=2"
    assert normalize_url("http://example.com/path?a=1&b=&c=3") == "http://example.com/path?a=1&c=3"
    assert normalize_url("http://example.com/path?empty=") == "http://example.com/path"


def test_normalize_url_handles_trailing_slash():
    """Trailing slashes are removed except for the root path."""
    assert normalize_url("http://example.com/path/to/") == "http://example.com/path/to"
    assert normalize_url("http://example.com/") == "http://example.com/"


def test_parse_url_full():
    """parse_url returns the expected component dictionary."""
    result = parse_url("https://Example.COM:8080/path/to?b=2&a=1")
    assert result == {
        "scheme": "https",
        "host": "example.com",
        "port": 8080,
        "path": "/path/to",
        "query_params": {"b": "2", "a": "1"},
    }


def test_parse_url_without_port():
    """port is None when no port is present in the URL."""
    result = parse_url("http://example.com/path")
    assert result["port"] is None
    assert result["scheme"] == "http"
    assert result["host"] == "example.com"
    assert result["path"] == "/path"
    assert result["query_params"] == {}


def test_parse_url_keeps_empty_query_params():
    """parse_url preserves every parameter, including empty values.

    Dropping empty parameters is the responsibility of normalize_url;
    parse_url simply reports the parameters present in the URL.
    """
    result = parse_url("http://example.com/path?a=1&b=&c=3")
    assert result["query_params"] == {"a": "1", "b": "", "c": "3"}


def test_normalize_then_parse_roundtrip():
    """Normalizing then parsing produces a clean, canonical result."""
    normalized = normalize_url("http://EXAMPLE.com:80/Path/?b=2&a=1&empty=")
    result = parse_url(normalized)
    assert result == {
        "scheme": "http",
        "host": "example.com",
        "port": None,
        "path": "/Path",
        "query_params": {"a": "1", "b": "2"},
    }
