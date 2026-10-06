# Annotated Hexdump — Complete BHTTP/1 Exchange

Exchange: `GET /hello.txt` from `127.0.0.1:9001`  
File size: 140 bytes (`www/hello.txt`)

Captured with:
```bash
python client_repo/bcurl.py --dump scratch/exchange localhost:9001/hello.txt
python scratch/hexdump.py
```

---

## CLIENT → SERVER: REQUEST frame (26 bytes total)

```
Bytes    Hex                  Field
-------  -------------------  ---------------------------------------------------
000-003  00 00 00 0E          Payload Length = 14
004      01                   Frame Type     = 0x01 (REQUEST)
005      01                   Flags          = 0x01 (END_STREAM)
006-007  00 00                Reserved       = 0x0000
008-011  00 00 00 01          Stream ID      = 1

--- Payload (14 bytes, offset 12) ---

012      01                   Method         = 0x01 (GET)
013-014  00 0A                Path Length    = 10
015-024  2F 68 65 6C 6C 6F    Path           = "/hello.txt"
         2E 74 78 74
025      00                   Header Count   = 0  (no request headers)
```

Total on wire: **12 bytes header + 14 bytes payload = 26 bytes**

---

## SERVER → CLIENT: RESPONSE frame (34 bytes total)

The server always sends a RESPONSE frame containing only status and headers.  
`END_STREAM` is NOT set here — DATA frames follow.

```
Bytes    Hex                  Field
-------  -------------------  ---------------------------------------------------
000-003  00 00 00 16          Payload Length = 22
004      02                   Frame Type     = 0x02 (RESPONSE)
005      00                   Flags          = 0x00 (no END_STREAM; DATA follows)
006-007  00 00                Reserved       = 0x0000
008-011  00 00 00 01          Stream ID      = 1  (echoes request stream)

--- Payload (22 bytes, offset 12) ---

012-013  00 C8                Status Code    = 200 (0x00C8)
014      02                   Header Count   = 2

--- Header[0]: content-type (known, ID=1) ---
015      01                   Header ID      = 1 (content-type)
016-017  00 0A                Value Length   = 10
018-027  74 65 78 74 2F 70    Value          = "text/plain"
         6C 61 69 6E

--- Header[1]: content-length (known, ID=2) ---
028      02                   Header ID      = 2 (content-length)
029-030  00 03                Value Length   = 3
031-033  31 34 30             Value          = "140"
```

Total on wire: **12 bytes header + 22 bytes payload = 34 bytes**

---

## SERVER → CLIENT: DATA frame (152 bytes total)

The entire file body (140 bytes) fits in one DATA frame. `END_STREAM` is set.

```
Bytes    Hex                  Field
-------  -------------------  ---------------------------------------------------
000-003  00 00 00 8C          Payload Length = 140 (0x8C)
004      03                   Frame Type     = 0x03 (DATA)
005      01                   Flags          = 0x01 (END_STREAM — last DATA frame)
006-007  00 00                Reserved       = 0x0000
008-011  00 00 00 01          Stream ID      = 1

--- Payload (140 bytes, offset 12) ---

012-025  48 65 6C 6C 6F 2C    "Hello, BHTP/1!\n"
         20 42 48 54 50 2F
         31 21 0A
026-...  54 68 69 73 20 69 73  "This is a plain-text file served by bserve..."
         ...
139+12   2E 0A                ".\n"  (final two bytes of file)
```

Total on wire: **12 bytes header + 140 bytes payload = 152 bytes**

---

## Full Exchange Summary

| Frame    | Dir    | Size    | Stream | Flags      | Notes                        |
|----------|--------|---------|--------|------------|------------------------------|
| REQUEST  | C → S  | 26 B    | 1      | END_STREAM | GET /hello.txt, 0 headers    |
| RESPONSE | S → C  | 34 B    | 1      | (none)     | 200 OK, content-type+length  |
| DATA     | S → C  | 152 B   | 1      | END_STREAM | 140 body bytes, stream ends  |

Total bytes exchanged: **26 sent, 186 received**

---

## Field Reference

| Field          | Type   | Encoding | Example bytes   | Decoded value |
|----------------|--------|----------|-----------------|---------------|
| Payload Length | u32 BE | 4 bytes  | `00 00 00 0E`   | 14            |
| Frame Type     | u8     | 1 byte   | `01`            | REQUEST       |
| Flags          | u8     | 1 byte   | `01`            | END_STREAM    |
| Reserved       | u16 BE | 2 bytes  | `00 00`         | (ignored)     |
| Stream ID      | u32 BE | 4 bytes  | `00 00 00 01`   | 1             |
| Status Code    | u16 BE | 2 bytes  | `00 C8`         | 200           |
| Header ID      | u8     | 1 byte   | `01`            | content-type  |
| Value Length   | u16 BE | 2 bytes  | `00 0A`         | 10            |
| Method         | u8     | 1 byte   | `01`            | GET           |
| Path Length    | u16 BE | 2 bytes  | `00 0A`         | 10            |
| Header Count   | u8     | 1 byte   | `02`            | 2             |

---

## Reproduce This Exchange

```bash
# Start server
python bserve.py www 9001

# Capture raw bytes
python client_repo/bcurl.py --dump scratch/exchange localhost:9001/hello.txt

# Inspect with verbose frame trace
python client_repo/bcurl.py -v localhost:9001/hello.txt
```
