"""
Request utilities — client IP extraction and public-IP detection.
"""

import ipaddress
from typing import Optional

from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract the real client IP address.

    Prefers the first entry of the X-Forwarded-For header (set by reverse
    proxies / load balancers) and falls back to the direct peer address.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return None


def is_public_ip(ip: Optional[str]) -> bool:
    """Return True when the IP is a routable public address (not private/local)."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )
