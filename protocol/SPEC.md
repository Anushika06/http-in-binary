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

Maximum payload per frame: **16 384 bytes**. A frame with `Payload Length > 16384` is a fatal protocol error; the receiver sends an ERROR frame and closes the connection.

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

`END_STREAM` signals that the sender has finished sending on that stream. A body-less response (e.g., 404) sets `END_STREAM` on the RESPONSE frame. A file response sets `END_STREAM` on the final DATA frame.

### 2.4 Stream IDs

- The client assigns a new stream ID per request, starting at **1** and incrementing by 1.
- Stream IDs are u32; the maximum value is 0xFFFFFFFF.
- The server echoes the same stream ID on every RESPONSE and DATA frame for that request.
- ERROR frames always use stream ID **0**.
- A REQUEST frame on stream 0 is a protocol error: the server sends an ERROR frame (stream 0) and closes the connection.
- RESPONSE or DATA arriving on stream 0 is similarly invalid.

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
  1 byte   Method       (0x01 = GET)
  2 bytes  Path Length  (u16, number of UTF-8 bytes in path; 1–4096)
  N bytes  Path         (UTF-8, must begin with '/')
  1 byte   Header Count (0–31)
  [Header Count × encoded header]
```

See §6 for header encoding.

**Input limits enforced by the server:**

| Field         | Limit                                    |
|---------------|------------------------------------------|
| Path Length   | 1–4096 bytes (0 is rejected as malformed)|
| Header Count  | 0–31 (>31 is rejected as malformed)      |
| Payload size  | 0–16384 bytes (enforced by frame reader) |
| Path bytes    | Must be valid UTF-8 (strict)             |
| Path content  | Must start with `/`; must contain no NUL bytes |

Any violation returns a RESPONSE 400 on the same stream ID.

---

## 4. RESPONSE Frame

Sent by the server. Contains only the status code and headers — **never** body bytes.

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
  [Header Count × encoded header]
```

Any bytes following the last encoded header are an error (checked by the client; the server never produces them).

---

## 5. DATA Frame

Carries a chunk of the response body. One or more DATA frames follow the RESPONSE frame when the body is non-empty. The final DATA frame sets `END_STREAM`.

```
Frame Header (12 bytes)
  Payload Length  = number of body bytes in this frame (0–16384)
  Frame Type      = 0x03
  Flags           = 0x01 (END_STREAM) on the last DATA frame, else 0x00
  Reserved        = 0x0000
  Stream ID       = <mirrors the request's stream ID>

Payload
  N bytes  Body chunk (raw bytes; no framing)
```

A DATA frame with `Payload Length = 0` and `END_STREAM` is valid and terminates a zero-byte body.

---

## 6. Header Encoding

Each header is encoded in one of two forms.

### 6.1 Known Header (table lookup)

```
1 byte   Header ID    (1–8; see table below)
2 bytes  Value Length (u16; 0–65535)
N bytes  Value        (UTF-8)
```

### 6.2 Custom Header (not in table)

```
1 byte   0x00         (signals custom name)
2 bytes  Name Length  (u16; 1–255)
N bytes  Name         (ASCII lowercase)
2 bytes  Value Length (u16; 0–65535)
N bytes  Value        (UTF-8)
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

IDs 9–255 are reserved. A receiver that encounters an unknown ID reads and skips its value without error.

---

## 7. ERROR Frame

Sent by either side to signal a fatal condition. The sender closes the connection immediately after.

```
Frame Header (12 bytes)
  Payload Length  = 4 + message length
  Frame Type      = 0x04
  Flags           = 0x00
  Reserved        = 0x0000
  Stream ID       = 0x00000000

Payload
  2 bytes  Error Code     (u16; see table below)
  2 bytes  Message Length (u16)
  N bytes  Message        (UTF-8)
```

### 7.1 Error Codes

| Code | Name            | When sent                                          |
|------|-----------------|----------------------------------------------------|
| 1    | PROTOCOL_ERROR  | REQUEST on stream 0; payload length exceeds 16384  |

### 7.2 Receiving an ERROR Frame

When the server receives an ERROR frame from the client, it closes the connection without sending a reply.

---

## 8. Status Codes

| Code | Meaning               | When sent                                              |
|------|-----------------------|--------------------------------------------------------|
| 200  | OK                    | File found and being delivered                         |
| 400  | Bad Request           | Malformed request payload; method ≠ GET; invalid path  |
| 404  | Not Found             | Path not found or escapes document root                |
| 500  | Internal Server Error | File found but could not be opened (e.g., permissions) |

---

## 9. File Transfer Behavior

1. Server sends a RESPONSE frame (`END_STREAM = 0`) with status 200 and at least `content-type` and `content-length` headers.
2. Server sends one or more DATA frames with file content in order, each at most 16 384 bytes.
3. The last DATA frame carries `END_STREAM = 1`.
4. A zero-length file is served as RESPONSE + one zero-length DATA frame with `END_STREAM = 1`.

Error responses (400, 404, 500) are a single RESPONSE frame with `END_STREAM = 1` and no DATA frames.

---

## 10. Connection and Stream Lifecycle

- One TCP connection carries all exchanges in order (sequential, not multiplexed).
- The client sends the next request only after receiving `END_STREAM` for the previous stream.
- On a fatal error (oversized frame, REQUEST on stream 0) the server sends an ERROR frame on stream 0 and closes the TCP connection.
- Clean client disconnection (TCP FIN) is handled gracefully; the server closes its socket.

---

## 11. Path Security

The server resolves request paths under the document root using `os.path.realpath`. Any path that resolves outside the document root (e.g., `/../secret.txt`) or contains a NUL byte returns 404.

---

## 12. Malformed Frame Handling

| Situation                               | Server action                                    |
|-----------------------------------------|--------------------------------------------------|
| `Payload Length > 16384`               | Send ERROR (code 1, stream 0), close connection  |
| REQUEST on stream 0                     | Send ERROR (code 1, stream 0), close connection  |
| Received ERROR frame                    | Close connection without reply                   |
| REQUEST path missing leading `/`        | RESPONSE 400 on the request's stream ID          |
| REQUEST path contains NUL byte          | RESPONSE 400 on the request's stream ID          |
| REQUEST method ≠ 0x01                  | RESPONSE 400 on the request's stream ID          |
| REQUEST header count > 31              | RESPONSE 400 on the request's stream ID          |
| File exists but cannot be opened        | RESPONSE 500 on the request's stream ID          |
| Unknown frame type                      | Skip (consume payload bytes by length), read next|
| Payload truncated / connection reset    | Treated as clean EOF; connection closed silently  |
