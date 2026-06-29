"""Shared pytest fixtures for JobPilot tests."""

import socket
from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Prevent tests from opening real network connections."""

    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(address: object) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        return host in {"127.0.0.1", "::1", "localhost"}

    def guarded_create_connection(
        address: object,
        *args: object,
        **kwargs: object,
    ) -> socket.socket:
        if is_loopback(address):
            return original_create_connection(address, *args, **kwargs)
        raise AssertionError("Real network access is not allowed during tests.")

    def guarded_connect(self: socket.socket, address: object) -> None:
        if is_loopback(address):
            return original_connect(self, address)
        raise AssertionError("Real network access is not allowed during tests.")

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        if is_loopback(address):
            return original_connect_ex(self, address)
        raise AssertionError("Real network access is not allowed during tests.")

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
