"""SSRF protection for user-supplied webhook URLs (PRD §9, Rayonne pattern).

Outbound notification targets must be public https endpoints: every address
the hostname resolves to has to be globally routable — no loopback, RFC1918,
link-local (cloud metadata!), or otherwise reserved space.
"""

import ipaddress
import socket
from urllib.parse import urlsplit


def validate_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValueError("webhook URLs must use https")
    host = parts.hostname
    if not host:
        raise ValueError("webhook URL has no host")
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"webhook host does not resolve: {host!r}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError("webhook host resolves to a non-public address")
