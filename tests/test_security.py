import socket
import pytest
from app.security import UnsafeURL, SafeFetcher, clean_text, normalize, validate_public_url


def fake_resolver(ip):
    return lambda host, port, proto=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.mark.parametrize("url", ["http://example.com", "ftp://x.com", "https://user:pw@example.com",
                                 "https://example.com:8443", "file:///etc/passwd"])
def test_rejects_bad_urls(url):
    with pytest.raises(UnsafeURL):
        validate_public_url(url, fake_resolver("93.184.216.34"))


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"])
def test_rejects_private_ips(ip):
    with pytest.raises(UnsafeURL):
        validate_public_url("https://evil.example", fake_resolver(ip))


def test_accepts_public():
    assert validate_public_url("https://example.com/menu", fake_resolver("93.184.216.34"))


def test_fetcher_returns_none_for_private():
    f = SafeFetcher(resolver=fake_resolver("10.1.2.3"))
    assert f.get("https://internal.example") is None


def test_clean_and_normalize():
    assert clean_text("  hi\x00 there\n\n you  ", 8) == "hi there"
    assert normalize("It\u2019s  Gluten-FREE") == "it's gluten-free"
