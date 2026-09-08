"""URL normalization and parsing utilities.

This module provides two public functions:

* :func:`normalize_url` - canonicalize a URL by lowercasing the scheme/host,
  removing default ports, alphabetically sorting query parameters, dropping
  empty query parameters, and trimming trailing slashes from the path.
* :func:`parse_url` - decompose a URL into its individual components.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Default ports associated with common schemes. When a URL uses one of these
# ports explicitly it is redundant and gets removed during normalization.
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """Return a canonicalized version of ``url``.

    The following transformations are applied:

    * The scheme and host are lowercased.
    * Default ports (80 for ``http``, 443 for ``https``) are removed.
    * Query parameters are sorted alphabetically by key.
    * Empty query parameters (those with no value) are dropped.
    * A trailing slash is removed from the path unless the path is the root
      ``/``.

    Args:
        url: The URL to normalize.

    Returns:
        The normalized URL.
    """
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    try:
        port = parts.port
    except ValueError:
        port = None

    # Drop the default port when it matches the scheme's default.
    if port is not None and port == _DEFAULT_PORTS.get(scheme):
        port = None

    # Trim a trailing slash, but keep the root path ("/") intact.
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Sort query parameters by key and drop empty ones.
    params = parse_qsl(parts.query, keep_blank_values=True)
    params = [(name, value) for name, value in params if name and value != ""]
    params.sort(key=lambda item: item[0])
    query = urlencode(params)

    # Rebuild the network location component.
    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"

    return urlunsplit((scheme, netloc, path, query, parts.fragment))


def parse_url(url: str) -> dict:
    """Decompose ``url`` into its individual components.

    Args:
        url: The URL to parse.

    Returns:
        A dictionary with the keys ``scheme``, ``host``, ``port`` (an ``int``
        or ``None``), ``path``, and ``query_params`` (a mapping of parameter
        name to value).
    """
    parts = urlsplit(url)

    try:
        port = parts.port
    except ValueError:
        port = None

    params = parse_qsl(parts.query, keep_blank_values=True)
    query_params = {name: value for name, value in params}

    return {
        "scheme": parts.scheme,
        "host": parts.hostname,
        "port": port,
        "path": parts.path,
        "query_params": query_params,
    }
