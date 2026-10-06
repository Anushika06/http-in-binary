# BHTP/1 — Binary Hypertext Transfer Protocol, Version 1
### Wire Protocol Specification — Revision 1.0

---

## 1. Overview

BHTP/1 is a binary, request–response application protocol carried over a persistent TCP connection. Every unit of data is a **frame**. A client sends REQUEST frames; a server replies with RESPONSE frames. The body of large responses is sent in one or more DATA frames. Connections stay open; the same TCP stream carries multiple sequential exchanges.

This document is the complete specification. A stranger should be able to write a compatible client or server from it alone.

---

## 2. Conventions

- All multi-byte integers are **big-endian** (network byte order).
- `u8`, `u16`, `u32` denote unsigned integers of 1, 2, and 4 bytes.
- Field sizes are justified in §3.1.

---

## 3. Frame Structure

Every frame begins with a **fixed 8-byte header**, followed by a variable-length payload whose size is given by the header.

```
 0               1               2               3
 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Payload Length (u32)                    |  bytes 0-3
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Frame Type   |    Flags      |         Stream ID (u16)       |  bytes 4-7
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Payload (variable)                      |
:                                                                :
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 3.1 Header Fields

| Field          | Size  | Justification |
|----------------|-------|---------------|
| Payload Length | u32   | Allows payloads up to 4 GiB; a receiver enforces the 64 KiB cap (3.2) independently of this range, leaving headroom for future versions. |
| Frame Type     | u8    | 256 distinct frame types; only 4 are defined in v1, leaving 252 for future extension. |
| Flags          | u8    | 8 per-frame-type bits; only END_STREAM (0x01) is defined in v1. |
| Stream ID      | u16   | 65535 concurrent logical streams; v1 uses only stream 0 (sequential), reserving the rest for a future multiplexed version. |

### 3.2 Size Limits

| Quantity               | Maximum   |
|------------------------|-----------|
| Payload Length         | 65535 bytes (64 KiB - 1) |
| Single header name     | 255 bytes |
| Single header value    | 1023 bytes |
| Header count per frame | 31 |

A receiver that reads a Payload Length exceeding 65535 MUST close the connection immediately without sending a reply.

---

## 4. Frame Types

| Name     | Value  | Direction        | Description |
|----------|--------|-----------------|-------------|
| REQUEST  | 0x01   | client to server | A complete request (method, path, headers). |
| RESPONSE | 0x02   | server to client | Status line plus response headers, and optionally the body when END_STREAM is set. |
| DATA     | 0x03   | server to client | A chunk of the response body (when body does not fit in one RESPONSE frame). |
| ERROR    | 0x04   | server to client | A fatal protocol-level error; the sender closes the connection after this frame. |

A receiver that encounters an unknown frame type MUST read and discard exactly Payload Length bytes, then resume reading the next frame. It MUST NOT close the connection solely because of an unrecognised type.

---

## 5. Flags

| Bit | Name        | Value  | Applies to   | Meaning |
|-----|-------------|--------|--------------|---------|
| 0   | END_STREAM  | 0x01   | RESPONSE, DATA | This frame carries the last byte of the response body. No DATA frames follow. |

All other flag bits are reserved and MUST be sent as zero. A receiver MUST ignore unknown flag bits.

---

## 6. Header Encoding

BHTP/1 uses a compact binary representation instead of text. Headers in a REQUEST or RESPONSE payload are encoded as follows.

```
+--------+-------------------+--------+-------------------+
|  Name  |   Name Bytes      | Value  |   Value Bytes     |
| Len u8 |  (1-255 bytes)    |Len u16 |  (0-1023 bytes)   |
+--------+-------------------+--------+-------------------+
```

- Name Len (u8): length of the header name in bytes. MUST be >= 1.
- Name: UTF-8 bytes, lowercase, no surrounding whitespace.
- Value Len (u16): length of the header value in bytes. MAY be 0.
- Value: UTF-8 bytes, no surrounding whitespace.

Multiple headers appear back to back. The header block ends when Header Count encoded headers have been consumed.

---

## 7. REQUEST Frame Payload

```
 Byte  0      : Method   (u8)  — see 7.1
 Bytes 1-2    : Path Length (u16) — number of bytes in the URI path
 Bytes 3+     : Path bytes (UTF-8, starts with '/', no query string for v1)
 After path   : Header Count (u8) — 0-31
 After count  : Header block (Header Count encoded headers per 6)
```

The REQUEST frame has no body; only the path and headers are carried.

### 7.1 Method Codes

| Method  | Code   |
|---------|--------|
| GET     | 0x01   |

Codes 0x00, 0x02-0xFF are reserved.

---

## 8. RESPONSE Frame Payload

```
 Bytes 0-1    : Status Code (u16)   — see 8.1
 Byte  2      : Header Count (u8)   — 0-31
 After count  : Header block (Header Count encoded headers per 6)
 After headers: Body bytes (remainder of payload, present only when
                END_STREAM is set; MAY be empty)
```

When END_STREAM is not set, no body bytes appear in the RESPONSE frame. The body is delivered in subsequent DATA frames.

### 8.1 Status Codes

BHTP/1 uses a subset of standard HTTP status codes as u16:

| Code  | Meaning |
|-------|---------|
| 200   | OK |
| 400   | Bad Request (malformed frame or invalid path) |
| 404   | Not Found |

---

## 9. DATA Frame Payload

DATA frame payload = opaque body bytes (up to 65535 bytes per frame)

DATA frames carry only body bytes. Headers are not repeated. The END_STREAM flag on the last DATA frame signals end of body.

---

## 10. ERROR Frame Payload

```
 Bytes 0-1   : Error Code (u16)
 Bytes 2-3   : Message Length (u16)
 After length: Message bytes (UTF-8, human-readable description)
```

The sender MUST close the connection after sending an ERROR frame. The receiver MUST close the connection on receipt.

---

## 11. Request-Response Sequence

```
Client                             Server
  |  --- REQUEST (stream 0) --->     |
  |                                  |
  |  <-- RESPONSE (END_STREAM) --    |   (body fits in one frame)
  |                                  |
  |  --- REQUEST (stream 0) --->     |
  |                                  |
  |  <-- RESPONSE ---------------    |   (body too large)
  |  <-- DATA -------------------    |
  |  <-- DATA (END_STREAM) ------    |
  |                                  |
  +-- (next request, same connection)
```

Requests are strictly sequential in v1. The client MUST NOT send a second REQUEST until END_STREAM has been received.

---

## 12. Malformed Frame Behaviour

A frame is malformed if:
- Payload Length exceeds 65535.
- A REQUEST frame carries Method code 0x00 or 0x02-0xFF.
- A REQUEST frame's Path Length is 0 or the path does not begin with '/'.
- A header Name Len is 0.
- The encoded headers overflow the remaining payload bytes.

On a malformed REQUEST, the server MUST reply with status 400 (END_STREAM set) and then keep the connection open for the next frame. The connection is closed only when the payload length limit is violated.

---

## 13. Connection and Persistence

- The TCP connection is persistent. The server keeps it open after each exchange.
- Either peer may close the connection by closing the TCP socket.
- Stream ID 0x0000 is the only valid stream ID in v1. A frame with any other Stream ID MUST be silently skipped by its length.
