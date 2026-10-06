# BHTP/1 — Binary Hypertext Transfer Protocol, Version 1

A custom binary HTTP-like protocol running over persistent TCP. Course project — Track 1 (server).

---

## Project structure

```
.
├── bserve.py               Server entry point
├── bcurl.py                Client (with -v hexdump mode)
├── bhtp/
│   ├── protocol.py         Frame codec, header encoding, request/response builders
│   └── reader.py           Buffered TCP stream reader (handles partial reads)
├── protocol/
│   └── bhtp1-spec.md       Complete wire protocol specification (~2 pages)
├── docs/
│   └── annotated-hexdump.md  Byte-by-byte annotation of a real exchange
├── www/                    Document root for testing
│   ├── index.html
│   ├── hello.txt
│   └── data.bin
├── tests/
│   └── run_tests.py        Automated test suite (5 scenarios)
└── tools/
    └── capture_hexdump.py  Live exchange annotator
```

---

## Quick start

```bash
# Start the server
python bserve.py ./www 9000

# Fetch a file (body to stdout)
python bcurl.py 127.0.0.1:9000/index.html

# Inspect the wire (hexdump of every frame to stderr)
python bcurl.py -v 127.0.0.1:9000/hello.txt

# Run the automated test suite (server must be running)
python tests/run_tests.py

# Capture and annotate one exchange
python tools/capture_hexdump.py /hello.txt
```

---

## Protocol summary

Every frame has a fixed **8-byte header**:

```
Bytes 0-3  Payload Length (u32, big-endian)
Byte  4    Frame Type     (u8)
Byte  5    Flags          (u8)
Bytes 6-7  Stream ID      (u16, big-endian)
```

Frame types: `REQUEST (0x01)`, `RESPONSE (0x02)`, `DATA (0x03)`, `ERROR (0x04)`.

- Connections are persistent — unlimited sequential request/response exchanges per TCP session.
- Unknown frame types are skipped cleanly by their length field.
- Path traversal is blocked: the server resolves all paths under the document root with `os.path.realpath`.
- Partial TCP reads are handled transparently by `FrameReader`.

See [`protocol/bhtp1-spec.md`](protocol/bhtp1-spec.md) for the complete specification.
See [`docs/annotated-hexdump.md`](docs/annotated-hexdump.md) for a byte-annotated wire capture.

---

## Demonstrated scenarios

| Scenario | How to trigger |
|---|---|
| Successful 200 | `bcurl.py 127.0.0.1:9000/index.html` |
| 404 Not Found | `bcurl.py 127.0.0.1:9000/missing.txt` |
| 400 Malformed | `tests/run_tests.py` (Test 3) |
| Multiple requests, one connection | `tests/run_tests.py` (Test 4) |
| Unknown frame type skipped | `tests/run_tests.py` (Test 5) |
