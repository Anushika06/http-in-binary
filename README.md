# BHTTP/1 — Binary HTTP Protocol, Version 1

A custom binary HTTP-like protocol running over persistent TCP. Course project — Track 1 (server).

---

## Project structure

```
.
|-- bserve.py               Server entry point
|-- bhtp/
|   |-- protocol.py         Frame codec, header encoding, constants
|   |-- reader.py           Buffered TCP stream reader (handles partial reads)
|   `-- __init__.py
|-- protocol/
|   `-- SPEC.md             Complete wire protocol specification
|-- docs/
|   `-- annotated-hexdump.md  Byte-by-byte annotation of a real exchange
|-- www/
|   `-- hello.txt           Sample document root file
`-- .gitignore
```

---

## Quick start

```bash
# Start the server (docroot = ./www, port = 9000)
python bserve.py ./www 9000

# Fetch a file using the BHTTP/1 client (body to stdout)
python bcurl.py 127.0.0.1:9000/hello.txt

# Inspect the wire — hexdump of every frame printed to stderr
python bcurl.py -v 127.0.0.1:9000/hello.txt

# Fetch multiple files over one TCP connection
python bcurl.py 127.0.0.1:9000/hello.txt /hello.txt
```

> `bcurl.py` is the external BHTTP/1 reference client provided for testing.
> It is not part of this repository. Obtain it from:
> https://github.com/PratyushMishra-2nd/BHTTP-1-HTTP-in-Binary

---

## Protocol summary

Every frame has a fixed **12-byte header**:

```
Bytes 0-3   Payload Length  (u32, big-endian; max 16384)
Byte  4     Frame Type      (u8)
Bytes 5     Flags           (u8; bit 0 = END_STREAM)
Bytes 6-7   Reserved        (u16, always 0x0000)
Bytes 8-11  Stream ID       (u32, big-endian)
```

Frame types: `REQUEST (0x01)`, `RESPONSE (0x02)`, `DATA (0x03)`, `ERROR (0x04)`.

Key behaviour:
- Connections are persistent — multiple sequential request/response exchanges per TCP session.
- Stream IDs are assigned by the client (1, 2, 3 …); the server echoes the same ID on all frames for that response.
- REQUEST on stream 0 is a protocol error: the server sends an ERROR frame and closes the connection.
- A file response is always a RESPONSE frame (headers only) followed by one or more DATA frames.
- Unknown frame types are skipped cleanly by their length field.
- Path traversal is blocked: all paths are resolved under the document root with `os.path.realpath`.

See [`protocol/SPEC.md`](protocol/SPEC.md) for the complete specification.  
See [`docs/annotated-hexdump.md`](docs/annotated-hexdump.md) for a byte-annotated wire capture.

---

## Demonstrated scenarios

| Scenario                       | How to trigger                                          |
|--------------------------------|---------------------------------------------------------|
| 200 OK                         | `bcurl.py 127.0.0.1:9000/hello.txt`                    |
| 404 Not Found                  | `bcurl.py 127.0.0.1:9000/missing.txt`                  |
| 400 Bad Request (malformed)    | Send a malformed REQUEST frame over a raw TCP socket    |
| Multiple requests, one session | `bcurl.py 127.0.0.1:9000/hello.txt /hello.txt`         |
| Unknown frame type skipped     | Inject a frame with type 0x99 before a valid REQUEST    |
| Path traversal blocked (404)   | `bcurl.py "127.0.0.1:9000/../secret.txt"`              |
