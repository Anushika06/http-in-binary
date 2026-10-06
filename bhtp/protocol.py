"""
BHTP/1 protocol constants and frame codec.

Wire format (12-byte fixed header):
  Bytes 0-3 : Payload Length (u32, big-endian)
  Byte  4   : Frame Type (u8)
  Byte  5   : Flags (u8)
  Bytes 6-7 : Reserved (u16, always 0x0000 on send, ignored on receive)
  Bytes 8-11: Stream ID (u32, big-endian)
  Bytes 12+ : Payload (variable, 0–16384 bytes)
"""

import struct

HEADER_SIZE = 12
MAX_PAYLOAD = 16384

# Frame types
TYPE_REQUEST  = 0x01
TYPE_RESPONSE = 0x02
TYPE_DATA     = 0x03
TYPE_ERROR    = 0x04

# Flags
FLAG_END_STREAM = 0x01

# Method codes
METHOD_GET = 0x01

# Status codes
STATUS_OK          = 200
STATUS_BAD_REQUEST = 400
STATUS_NOT_FOUND   = 404

_HEADER_STRUCT = struct.Struct(">IBBHI")  # length u32, type u8, flags u8, reserved u16, stream_id u32


def encode_frame_header(payload_len: int, ftype: int, flags: int, stream_id: int) -> bytes:
    return _HEADER_STRUCT.pack(payload_len, ftype, flags, 0, stream_id)


def decode_frame_header(raw: bytes) -> tuple[int, int, int, int]:
    """Returns (payload_len, frame_type, flags, stream_id)."""
    payload_len, ftype, flags, reserved, stream_id = _HEADER_STRUCT.unpack(raw)
    return payload_len, ftype, flags, stream_id


HEADER_TABLE = {
    1: "content-type",
    2: "content-length",
    3: "server",
    4: "date",
    5: "connection",
    6: "content-encoding",
    7: "cache-control",
    8: "last-modified",
}
HEADER_IDS = {name: hid for hid, name in HEADER_TABLE.items()}

def encode_headers(headers: list[tuple[str, str]]) -> bytes:
    buf = bytearray()
    for name, value in headers:
        name_lower = name.lower()
        hid = HEADER_IDS.get(name_lower)
        vb = value.encode("utf-8")
        if hid is not None:
            buf += struct.pack(">BH", hid, len(vb)) + vb
        else:
            nb = name_lower.encode("ascii")
            buf += struct.pack(">BH", 0, len(nb)) + nb
            buf += struct.pack(">H", len(vb)) + vb
    return bytes(buf)


def decode_headers(data: bytes, count: int) -> tuple[list[tuple[str, str]], int]:
    """
    Decode `count` headers from `data`.
    Returns (headers list, bytes consumed).
    Raises ValueError on malformed input.
    """
    headers = []
    offset = 0
    for _ in range(count):
        if offset + 1 > len(data):
            raise ValueError("header truncated at ID")
        hid = data[offset]
        offset += 1
        
        if hid == 0:
            if offset + 2 > len(data):
                raise ValueError("header name length truncated")
            name_len = struct.unpack_from(">H", data, offset)[0]
            offset += 2
            if not 1 <= name_len <= 255:
                raise ValueError("custom name length outside 1-255")
            if offset + name_len > len(data):
                raise ValueError("header name truncated")
            name = data[offset:offset + name_len].decode("ascii", errors="replace")
            offset += name_len
        else:
            name = HEADER_TABLE.get(hid, f"unknown-{hid}")
            
        if offset + 2 > len(data):
            raise ValueError("header value-len truncated")
        val_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        if offset + val_len > len(data):
            raise ValueError("header value truncated")
        value = data[offset:offset + val_len].decode("utf-8", errors="replace")
        offset += val_len
        headers.append((name, value))
    return headers, offset


def encode_request(path: str, headers: list[tuple[str, str]], stream_id: int) -> bytes:
    path_bytes = path.encode("utf-8")
    hdr_bytes = encode_headers(headers)
    payload = (
        struct.pack(">BH", METHOD_GET, len(path_bytes))
        + path_bytes
        + struct.pack(">B", len(headers))
        + hdr_bytes
    )
    frame_hdr = encode_frame_header(len(payload), TYPE_REQUEST, 0, stream_id)
    return frame_hdr + payload


def encode_response(status: int, headers: list[tuple[str, str]], stream_id: int,
                    end_stream: bool = True) -> bytes:
    hdr_bytes = encode_headers(headers)
    payload = (
        struct.pack(">HB", status, len(headers))
        + hdr_bytes
    )
    flags = FLAG_END_STREAM if end_stream else 0
    frame_hdr = encode_frame_header(len(payload), TYPE_RESPONSE, flags, stream_id)
    return frame_hdr + payload


def encode_data(body_chunk: bytes, stream_id: int, end_stream: bool) -> bytes:
    flags = FLAG_END_STREAM if end_stream else 0
    frame_hdr = encode_frame_header(len(body_chunk), TYPE_DATA, flags, stream_id)
    return frame_hdr + body_chunk


def encode_error(code: int, message: str) -> bytes:
    msg_bytes = message.encode("utf-8")
    payload = struct.pack(">HH", code, len(msg_bytes)) + msg_bytes
    frame_hdr = encode_frame_header(len(payload), TYPE_ERROR, 0, 0)
    return frame_hdr + payload


def parse_request_payload(payload: bytes) -> tuple[int, str, list[tuple[str, str]]]:
    """
    Returns (method, path, headers).
    Raises ValueError on malformed input.
    """
    if len(payload) < 3:
        raise ValueError("request payload too short")
    method = payload[0]
    path_len = struct.unpack_from(">H", payload, 1)[0]
    offset = 3
    if path_len == 0:
        raise ValueError("path length is zero")
    if offset + path_len > len(payload):
        raise ValueError("path truncated")
    path = payload[offset:offset + path_len].decode("utf-8", errors="strict")
    offset += path_len
    if not path.startswith("/"):
        raise ValueError("path does not begin with '/'")
    if offset + 1 > len(payload):
        raise ValueError("header count missing")
    hdr_count = payload[offset]
    offset += 1
    if hdr_count > 31:
        raise ValueError(f"header count {hdr_count} exceeds limit 31")
    headers, _ = decode_headers(payload[offset:], hdr_count)
    return method, path, headers
