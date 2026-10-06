"""
bserve — BHTP/1 file server

Usage: python bserve.py <docroot> <port>
"""

import os
import socket
import threading
import mimetypes
import sys

from bhtp.protocol import (
    TYPE_REQUEST, TYPE_RESPONSE, TYPE_DATA, TYPE_ERROR,
    ERR_PROTOCOL,
    METHOD_GET, FLAG_END_STREAM,
    STATUS_OK, STATUS_BAD_REQUEST, STATUS_NOT_FOUND, STATUS_INTERNAL_ERROR,
    MAX_PAYLOAD,
    encode_response, encode_data, encode_error,
    parse_request_payload,
)
from bhtp.reader import FrameReader

# Body chunks are capped at MAX_PAYLOAD to respect the per-frame size limit.
_CHUNK_SIZE = MAX_PAYLOAD


def _safe_path(docroot: str, request_path: str) -> str | None:
    """
    Resolve request_path under docroot and return the absolute filesystem path,
    or None if the result escapes the docroot (path-traversal guard).
    """
    # Strip leading slash; os.path.join ignores docroot if path is absolute.
    rel = request_path.lstrip("/")
    try:
        candidate = os.path.realpath(os.path.join(docroot, rel))
    except ValueError:
        # os.path.realpath raises ValueError on paths containing NUL bytes.
        return None
    root = os.path.realpath(docroot)
    if not candidate.startswith(root + os.sep) and candidate != root:
        return None
    return candidate


def _send_all(sock: socket.socket, data: bytes) -> None:
    """Write all bytes, retrying on short sends (handles EINTR and partial writes)."""
    mv = memoryview(data)
    sent = 0
    while sent < len(data):
        n = sock.send(mv[sent:])
        if n == 0:
            raise ConnectionError("socket closed during send")
        sent += n


def _serve_file(sock: socket.socket, filepath: str, stream_id: int) -> None:
    try:
        size = os.path.getsize(filepath)
        f = open(filepath, "rb")
    except OSError:
        _send_all(sock, encode_response(STATUS_INTERNAL_ERROR, [], stream_id, end_stream=True))
        return

    mime, _ = mimetypes.guess_type(filepath)
    if mime is None:
        mime = "application/octet-stream"

    resp_headers = [
        ("content-type", mime),
        ("content-length", str(size)),
    ]

    with f:
        first_chunk = f.read(_CHUNK_SIZE)
        remaining = size - len(first_chunk)

        if remaining == 0:
            # Entire body fits in the first DATA frame, or it's empty.
            _send_all(sock, encode_response(STATUS_OK, resp_headers, stream_id, end_stream=False))
            _send_all(sock, encode_data(first_chunk, stream_id, end_stream=True))
            return

        # Body spans multiple frames: send RESPONSE (no body), then DATA frames.
        _send_all(sock, encode_response(STATUS_OK, resp_headers, stream_id, end_stream=False))
        _send_all(sock, encode_data(first_chunk, stream_id, end_stream=(remaining == 0)))

        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            remaining -= len(chunk)
            _send_all(sock, encode_data(chunk, stream_id, end_stream=(remaining <= 0)))


_CONTINUE = 0
_CLOSE    = 1


def _handle_request(sock: socket.socket, docroot: str,
                    ftype: int, flags: int, stream_id: int, payload: bytes) -> int:
    """Handle one frame. Returns _CLOSE if the connection must be shut down."""
    if ftype == TYPE_ERROR:
        # Peer signalled a fatal error; close without replying.
        return _CLOSE

    if ftype != TYPE_REQUEST:
        # Unknown frame type — already consumed by length in read_frame(); skip.
        return _CONTINUE

    if stream_id == 0:
        # REQUEST on stream 0 violates the protocol (SPEC §2.4).
        _send_all(sock, encode_error(ERR_PROTOCOL, "REQUEST on stream 0"))
        return _CLOSE

    try:
        method, path, _ = parse_request_payload(payload)
    except ValueError:
        _send_all(sock, encode_response(STATUS_BAD_REQUEST, [], stream_id, end_stream=True))
        return _CONTINUE

    if method != METHOD_GET:
        _send_all(sock, encode_response(STATUS_BAD_REQUEST, [], stream_id, end_stream=True))
        return _CONTINUE

    filepath = _safe_path(docroot, path)
    if filepath is None or not os.path.isfile(filepath):
        _send_all(sock, encode_response(STATUS_NOT_FOUND, [], stream_id, end_stream=True))
        return _CONTINUE

    _serve_file(sock, filepath, stream_id)
    return _CONTINUE


def _handle_connection(sock: socket.socket, addr: tuple, docroot: str) -> None:
    print(f"[+] connection from {addr[0]}:{addr[1]}", flush=True)
    reader = FrameReader(sock)
    try:
        while True:
            try:
                frame = reader.read_frame()
            except ValueError as e:
                # Payload length exceeded limit; cannot recover frame boundary.
                _send_all(sock, encode_error(ERR_PROTOCOL, str(e)))
                break

            if frame is None:
                break  # clean EOF

            ftype, flags, stream_id, payload = frame
            if _handle_request(sock, docroot, ftype, flags, stream_id, payload) == _CLOSE:
                break

    except (ConnectionError, BrokenPipeError, OSError):
        pass
    finally:
        sock.close()
        print(f"[-] connection closed {addr[0]}:{addr[1]}", flush=True)


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: bserve <docroot> <port>", file=sys.stderr)
        sys.exit(1)

    docroot = os.path.realpath(sys.argv[1])
    if not os.path.isdir(docroot):
        print(f"error: {docroot!r} is not a directory", file=sys.stderr)
        sys.exit(1)

    port = int(sys.argv[2])

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", port))
    srv.listen(64)
    print(f"bserve listening on port {port}, root={docroot}", flush=True)

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=_handle_connection, args=(conn, addr, docroot), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nbserve stopped")


if __name__ == "__main__":
    main()
