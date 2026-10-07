import ipaddress
import socket
import sys
from urllib.parse import urlsplit


LOCAL_HOSTS = {
    "ai-provider",
    "localhost",
    "host.docker.internal",
}
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".example")


def is_public_provider_url(raw_url: str) -> bool:
    try:
        url = urlsplit(raw_url.strip())
        host = (url.hostname or "").rstrip(".").lower()
        if (
            url.scheme != "https"
            or not host
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or host in LOCAL_HOSTS
            or host.endswith(LOCAL_SUFFIXES)
        ):
            return False

        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            port = url.port or 443
            addresses = [
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            ]
        return bool(addresses) and all(address.is_global for address in addresses)
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if is_public_provider_url(sys.stdin.read()) else 1)
