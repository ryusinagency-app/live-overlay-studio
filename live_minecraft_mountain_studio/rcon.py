from __future__ import annotations

import socket
import struct


class RconError(RuntimeError):
    pass


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 4.0):
        self.host = host
        self.port = int(port)
        self.password = password
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.request_id = 0

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        request_id, _, _ = self._request(3, self.password)
        if request_id == -1:
            raise RconError("RCON認証に失敗しました")
        return self

    def __exit__(self, *_):
        if self.sock:
            self.sock.close()
        self.sock = None

    def command(self, command: str) -> str:
        _, _, body = self._request(2, command)
        return body

    def _request(self, packet_type: int, body: str):
        if not self.sock:
            raise RconError("RCONへ接続されていません")
        self.request_id += 1
        payload = struct.pack("<ii", self.request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        length_bytes = self._recv_exact(4)
        length = struct.unpack("<i", length_bytes)[0]
        if length < 10 or length > 10_000_000:
            raise RconError("RCONから不正な応答を受信しました")
        response = self._recv_exact(length)
        request_id, response_type = struct.unpack("<ii", response[:8])
        return request_id, response_type, response[8:-2].decode("utf-8", "replace")

    def _recv_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            part = self.sock.recv(length - len(chunks)) if self.sock else b""
            if not part:
                raise RconError("RCON接続が切断されました")
            chunks.extend(part)
        return bytes(chunks)

