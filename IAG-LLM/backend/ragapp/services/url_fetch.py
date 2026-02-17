from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


class UrlFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedUrl:
    final_url: str
    status_code: int
    content_type: str
    content_bytes: bytes
    title: str
    text: str


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return bool(ip.is_global)


def _resolve_host_ips(host: str, port: int) -> list[str]:
    ips: set[str] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP):
        if family == socket.AF_INET:
            ips.add(sockaddr[0])
        elif family == socket.AF_INET6:
            ips.add(sockaddr[0])
    return sorted(ips)


def _assert_public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UrlFetchError("URL inválida: só é permitido http/https")
    if not parts.netloc:
        raise UrlFetchError("URL inválida: falta host")
    if parts.username or parts.password:
        raise UrlFetchError("URL inválida: credenciais na URL não são permitidas")
    host = parts.hostname or ""
    if host.lower() in {"localhost"}:
        raise UrlFetchError("URL inválida: host não permitido")
    port = int(parts.port or (443 if parts.scheme == "https" else 80))
    ips = _resolve_host_ips(host, port)
    if not ips:
        raise UrlFetchError("URL inválida: não foi possível resolver DNS")
    if not all(_is_public_ip(ip) for ip in ips):
        raise UrlFetchError("URL inválida: IP privado/loopback/link-local não permitido")
    normalized = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            parts.query,
            "",
        )
    )
    return normalized


def _read_limited_bytes(
    r: requests.Response, *, max_bytes: int, chunk_size: int = 64 * 1024
) -> bytes:
    out = bytearray()
    for chunk in r.iter_content(chunk_size=chunk_size):
        if not chunk:
            continue
        out.extend(chunk)
        if len(out) > max_bytes:
            raise UrlFetchError("Download excede o limite de bytes")
    return bytes(out)


def fetch_url_text(url: str) -> FetchedUrl:
    timeout_s = int(os.environ.get("IAC_FETCH_TIMEOUT_S", "20"))
    max_bytes = int(os.environ.get("IAC_FETCH_MAX_BYTES", str(5_000_000)))
    max_redirects = int(os.environ.get("IAC_FETCH_MAX_REDIRECTS", "3"))

    current = _assert_public_url(url)
    session = requests.Session()
    for _ in range(max_redirects + 1):
        parts = urlsplit(current)
        port = int(parts.port or (443 if parts.scheme == "https" else 80))
        ips = _resolve_host_ips(parts.hostname or "", port)
        if not ips or not all(_is_public_ip(ip) for ip in ips):
            raise UrlFetchError("Redirecionamento para host/IP não permitido")

        r = session.get(
            current,
            stream=True,
            allow_redirects=False,
            timeout=(min(5, timeout_s), timeout_s),
            headers={"User-Agent": "iac-web/0.1 (+local)"},
        )

        if 300 <= r.status_code < 400 and r.headers.get("Location"):
            current = _assert_public_url(urljoin(current, r.headers["Location"]))
            continue

        content_type = (r.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        b = _read_limited_bytes(r, max_bytes=max_bytes)

        # HTML -> text
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(b, "html.parser")
        title = (soup.title.string if soup.title and soup.title.string else "").strip()
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return FetchedUrl(
            final_url=current,
            status_code=r.status_code,
            content_type=content_type,
            content_bytes=b,
            title=title,
            text=text,
        )

    raise UrlFetchError("Demasiados redirecionamentos")

