"""Unit-тесты IP-allowlist парсинга CIDR (Sprint 4.5-A, extended 4.5-H)."""

from __future__ import annotations

import ipaddress

import pytest

from pipirik_wars.admin_web.auth.ip_allowlist import (
    extract_client_ip_from_xff,
    is_private_ip,
    parse_cidr_list,
)


class TestParseCidrList:
    def test_wildcard_returns_empty(self) -> None:
        assert parse_cidr_list("*") == []

    def test_empty_string_returns_empty(self) -> None:
        assert parse_cidr_list("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert parse_cidr_list("   ") == []

    def test_single_cidr(self) -> None:
        result = parse_cidr_list("10.0.0.0/24")
        assert len(result) == 1
        assert result[0] == ipaddress.ip_network("10.0.0.0/24")

    def test_multiple_cidrs(self) -> None:
        result = parse_cidr_list("10.0.0.0/24, 192.168.1.0/28, 172.16.0.0/12")
        assert len(result) == 3

    def test_ipv6_cidr(self) -> None:
        result = parse_cidr_list("::1/128")
        assert len(result) == 1
        assert result[0] == ipaddress.ip_network("::1/128")

    def test_strips_whitespace(self) -> None:
        result = parse_cidr_list("  10.0.0.0/24 , 192.168.0.0/16  ")
        assert len(result) == 2

    def test_ignores_empty_entries(self) -> None:
        result = parse_cidr_list("10.0.0.0/24,,192.168.0.0/16")
        assert len(result) == 2

    def test_single_host(self) -> None:
        result = parse_cidr_list("192.168.1.1/32")
        assert len(result) == 1
        addr = ipaddress.ip_address("192.168.1.1")
        assert addr in result[0]

    def test_invalid_cidr_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_cidr_list("not-a-cidr")

    def test_ip_in_network(self) -> None:
        result = parse_cidr_list("10.0.0.0/8")
        addr = ipaddress.ip_address("10.1.2.3")
        assert addr in result[0]

    def test_ip_not_in_network(self) -> None:
        result = parse_cidr_list("10.0.0.0/8")
        addr = ipaddress.ip_address("11.0.0.1")
        assert addr not in result[0]


class TestIsPrivateIp:
    @pytest.mark.parametrize(
        "ip_str",
        [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.1",
            "::1",
        ],
    )
    def test_private_ips(self, ip_str: str) -> None:
        assert is_private_ip(ipaddress.ip_address(ip_str)) is True

    @pytest.mark.parametrize(
        "ip_str",
        [
            "8.8.8.8",
            "1.1.1.1",
            "203.0.113.1",
            "2001:db8::1",
        ],
    )
    def test_public_ips(self, ip_str: str) -> None:
        assert is_private_ip(ipaddress.ip_address(ip_str)) is False


class TestExtractClientIpFromXff:
    def test_single_ip(self) -> None:
        assert extract_client_ip_from_xff("1.2.3.4") == "1.2.3.4"

    def test_chain_rightmost_public(self) -> None:
        assert extract_client_ip_from_xff("1.2.3.4, 10.0.0.1") == "1.2.3.4"

    def test_chain_skips_private_proxies(self) -> None:
        result = extract_client_ip_from_xff("8.8.8.8, 10.0.0.1, 192.168.1.1")
        assert result == "8.8.8.8"

    def test_all_private_returns_leftmost(self) -> None:
        result = extract_client_ip_from_xff("10.0.0.1, 192.168.1.1")
        assert result == "10.0.0.1"

    def test_empty_returns_empty(self) -> None:
        assert extract_client_ip_from_xff("") == ""

    def test_spoofed_xff_with_private_proxy(self) -> None:
        result = extract_client_ip_from_xff("spoofed, 5.6.7.8, 10.0.0.1")
        assert result == "5.6.7.8"

    def test_trusted_proxies_explicit(self) -> None:
        trusted = frozenset({ipaddress.ip_network("10.0.0.0/8")})
        result = extract_client_ip_from_xff(
            "1.1.1.1, 10.0.0.5",
            trusted_proxies=trusted,
        )
        assert result == "1.1.1.1"

    def test_trusted_proxies_not_matching(self) -> None:
        trusted = frozenset({ipaddress.ip_network("10.0.0.0/8")})
        result = extract_client_ip_from_xff(
            "1.1.1.1, 5.5.5.5",
            trusted_proxies=trusted,
        )
        assert result == "5.5.5.5"

    def test_invalid_ip_in_chain_returned_as_is(self) -> None:
        result = extract_client_ip_from_xff("1.2.3.4, not-an-ip")
        assert result == "not-an-ip"

    def test_multiple_proxies_in_chain(self) -> None:
        result = extract_client_ip_from_xff("203.0.113.50, 10.0.0.1, 10.0.0.2, 192.168.1.1")
        assert result == "203.0.113.50"

    def test_ipv6_loopback_in_chain(self) -> None:
        result = extract_client_ip_from_xff("2001:db8::1, ::1")
        assert result == "2001:db8::1"
