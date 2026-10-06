"""
TCP stream reader that buffers data and yields complete frames.

TCP delivers a byte stream; one recv() call may produce a partial header,
a partial payload, or multiple frames concatenated. This class hides that
complexity from the rest of the server.
"""

import socket
from bhtp.protocol import HEADER_SIZE, MAX_PAYLOAD, decode_frame_header


class FrameReader:
    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._buf = bytearray()

    def _recv_at_least(self, n: int) -> bool:
        """Pull bytes from the socket until the buffer holds at least n bytes.
        Returns False if the connection was closed before n bytes arrived."""
        while len(self._buf) < n:
            chunk = self._sock.recv(4096)
            if not chunk:
                return False
            self._buf += chunk
        return True

    def read_frame(self) -> tuple[int, int, int, bytes] | None:
        """
        Block until one complete frame is available.

        Returns (frame_type, flags, stream_id, payload) or None on EOF.
        Raises ValueError if payload_len > MAX_PAYLOAD.
        """
        if not self._recv_at_least(HEADER_SIZE):
            return None

        raw_hdr = bytes(self._buf[:HEADER_SIZE])
        payload_len, ftype, flags, stream_id = decode_frame_header(raw_hdr)

        if payload_len > MAX_PAYLOAD:
            raise ValueError(
                f"frame payload length {payload_len} exceeds limit {MAX_PAYLOAD}"
            )

        total = HEADER_SIZE + payload_len
        if not self._recv_at_least(total):
            return None

        payload = bytes(self._buf[HEADER_SIZE:total])
        del self._buf[:total]
        return ftype, flags, stream_id, payload
