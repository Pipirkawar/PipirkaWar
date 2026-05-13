"""Unit-тесты IP-allowlist парсинга CIDR (Sprint 4.5-A)."""

from __future__ import annotations

import ipaddress

import pytest

from pipirik_wars.admin_web.auth.ip_allowlist import parse_cidr_list


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
