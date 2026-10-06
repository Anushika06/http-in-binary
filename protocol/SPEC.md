# BHTTP/1 — Binary HTTP Protocol Specification

**Version:** 1  
**Transport:** TCP (stream, persistent connections)  
**Byte order:** big-endian throughout

---

## 1. Overview

BHTTP/1 is a binary, frame-based request/response protocol carried over a single persistent TCP connection. Multiple sequential request/response exchanges share one connection using monotonically increasing stream IDs.

---

## 2. Frame Header (12 bytes, fixed)

Every frame begins with a 12-byte header followed immediately by the payload.

```
Offset  Size   Type    Field
------  -----  ------  ----------------------------------------
0       4      u32     Payload Length   (0 – 16384)
4       1      u8      Frame Type
5       1      u8      Flags
6       2      u16     Reserved         (send as 0x0000; ignore on receive)
8       4      u32     Stream ID
```

The payload begins at byte 12 and is exactly `Payload Length` bytes long.

### 2.1 Payload Length

Maximum payload per frame: **16 384 bytes**. A frame with `Payload Length > 16384` is a fatal protocol error; the receiver closes the connection after sending an ERROR frame.

### 2.2 Frame Types

| Value | Name     | Direction        |
|-------|----------|------------------|
| 0x01  | REQUEST  | client → server  |
| 0x02  | RESPONSE | server → client  |
| 0x03  | DATA     | server → client  |
| 0x04  | ERROR    | either direction |

Any other type value is **unknown**. Unknown frames are skipped by consuming exactly `Payload Length` bytes and then reading the next frame; no error is sent.

### 2.3 Flags

| Bit | Mask | Name       | Applies to              |
|-----|------|------------|-------------------------|
| 0   | 0x01 | END_STREAM | REQUEST, RESPONSE, DATA |

All other flag bits are reserved; receivers ignore them.

`END_STREAM` on a frame signals that the sender has finished sending on that stream. A body-less response (e.g., 404) sets `END_STREAM` on the RESPONSE frame. A file response sets `END_STREAM` on the final DATA frame.

### 2.4 Stream IDs

- The client assigns a new stream ID per request, starting at **1** and incrementing by 1.
- The server echoes the same stream ID on every RESPONSE and DATA frame that belongs to that request.
- ERROR frames use stream ID **0**.
- RESPONSE or DATA on stream 0 is a protocol error.

---

## 3. REQUEST Frame

Sent by the client. Always carries `END_STREAM` (flag `0x01`).

```
Frame Header (12 bytes)
  Payload Length  = length of payload below
  Frame Type      = 0x01
  Flags           = 0x01  (END_STREAM)
  Reserved        = 0x0000
  Stream ID       = <client-assigned, >= 1>

Payload
  1 byte   Method      (0x01 = GET)
  2 bytes  Path Length (u16, number of UTF-8 bytes in path)
  N bytes  Path        (UTF-8, must begin with '/')
  1 byte   Header Count (0-31)
  [Header Count x encoded header]
```

See §6 for header encoding.

---

## 4. RESPONSE Frame

Sent by the server. Contains status code and response headers only — **never** body bytes.

```
Frame Header (12 bytes)
  Payload Length  = length of payload below
  Frame Type      = 0x02
  Flags           = 0x01 (END_STREAM) if no DATA frames follow, else 0x00
  Reserved        = 0x0000
  Stream ID       = <mirrors the request's stream ID>

Payload
  2 bytes  Status Code  (u16; e.g., 0x00C8 = 200, 0x0190 = 400, 0x0194 = 404)
  1 byte   Header Count (number of headers that follow)
  [Header Count x encoded header]
```

---

## 5. DATA Frame

Carries a chunk of the response body. One or more DATA frames follow the RESPONSE frame when the body is non-empty. The final DATA frame sets `END_STREAM`.

```
Frame Header (12 bytes)
  Payload Length  = number of body bytes in this frame (0-16384)
  Frame Type      = 0x03
  Flags           = 0x01 (END_STREAM) on the last DATA frame, else 0x00
  Reserved        = 0x0000
  Stream ID       = <mirrors the request's stream ID>

Payload
  N bytes  Body chunk (raw bytes; no framing)
```

A DATA frame with `Payload Length = 0` and `END_STREAM` is valid and is used to terminate a zero-byte body.

---

## 6. Header Encoding

Each header is encoded in one of two forms.

### 6.1 Known Header (table lookup)

```
1 byte   Header ID   (1-8; see table below; never 0)
2 bytes  Value Length (u16)
N bytes  Value       (UTF-8)
```

### 6.2 Custom Header (not in table)

```
1 byte   0x00        (signals custom name)
2 bytes  Name Length (u16; 1-255)
N bytes  Name        (ASCII lowercase)
2 bytes  Value Length (u16)
N bytes  Value       (UTF-8)
```

### 6.3 Header Table

| ID | Name             |
|----|------------------|
| 1  | content-type     |
| 2  | content-length   |
| 3  | server           |
| 4  | date             |
| 5  | connection       |
| 6  | content-encoding |
| 7  | cache-control    |
| 8  | last-modified    |

IDs 9-255 are reserved. A receiver that encounters an unknown ID reads the value length and skips the value bytes without error.

---

## 7. ERROR Frame

Sent by either side to signal a fatal condition. The connection is closed after sending.

```
Frame Header (12 bytes)
  Payload Length  = 4 + message length
  Frame Type      = 0x04
  Flags           = 0x00
  Reserved        = 0x0000
  Stream ID       = 0x00000000

Payload
  2 bytes  Error Code   (u16)
  2 bytes  Message Length (u16, bytes in message)
  N bytes  Message      (UTF-8)
```

---

## 8. Status Codes

| Code | Meaning     | When sent                                 |
|------|-------------|-------------------------------------------|
| 200  | OK          | File found and being delivered            |
| 400  | Bad Request | Malformed request payload or method != GET|
| 404  | Not Found   | Path not found under document root        |

---

## 9. File Transfer Behavior

1. Server sends a RESPONSE frame (`END_STREAM = 0`) containing status 200 and at least `content-type` and `content-length` headers.
2. Server sends one or more DATA frames containing the file content in order, each at most 16 384 bytes.
3. The last DATA frame carries `END_STREAM = 1`.
4. A zero-length file is served as a RESPONSE frame followed by a single DATA frame of length 0 with `END_STREAM = 1`.

Error responses (400, 404) are a single RESPONSE frame with `END_STREAM = 1` and no DATA frames.

---

## 10. Connection and Stream Lifecycle

- One TCP connection carries all exchanges in order.
- The client sends request N+1 only after receiving `END_STREAM` for stream N (sequential, not multiplexed).
- On a fatal error (oversized frame, unrecoverable parse failure) the affected side sends an ERROR frame on stream 0 and closes the TCP connection.
- Clean client disconnection (TCP FIN) is handled gracefully; the server closes its socket without error.

---

## 11. Path Security

The server resolves the requested path under its document root with `os.path.realpath`. Paths that resolve outside the document root (e.g., `/../secret.txt`) return 404.

---

## 12. Malformed Frame Handling

| Situation                              | Server action                             |
|----------------------------------------|-------------------------------------------|
| `Payload Length > 16384`              | Send ERROR (stream 0), close connection   |
| Payload truncated before `END_STREAM` | Connection reset treated as clean EOF     |
| REQUEST path missing leading `/`       | RESPONSE 400 on the request's stream ID   |
| REQUEST method != 0x01                | RESPONSE 400 on the request's stream ID   |
| Unknown Frame Type                     | Skip (consume payload bytes), read next   |
