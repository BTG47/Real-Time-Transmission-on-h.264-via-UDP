import struct

PST_TRUE, PST_FALSE, PST_SYMBOL, PST_INT32, PST_DOUBLE = 0x00, 0x01, 0x02, 0x03, 0x04
PST_COMPLEX, PST_NULL, PST_PAIR, PST_VECTOR, PST_DICT = 0x05, 0x06, 0x07, 0x08, 0x09
PST_UNIFORM_VECTOR, PST_UINT64, PST_TUPLE, PST_INT64 = 0x0A, 0x0B, 0x0C, 0x0D
UVI_U8 = 0x00

class PmtDecodeError(ValueError):
    pass

_MAX_DEPTH = 64

def encode_u8vector_pdu(payload: bytes) -> bytes:
    blob = b"\x0a\x00" + struct.pack(">I", len(payload)) + b"\x01\x00" + payload
    return b"\x07\x06" + blob

def _read_exact(data, pos, n):
    end = pos + n
    if end > len(data):
        raise PmtDecodeError(f"PMT truncado en pos {pos}, faltan {n} bytes")
    return data[pos:end], end

def _parse(data, pos=0, depth=0):
    tag, pos = _read_exact(data, pos, 1)
    t = tag[0]
    if t == PST_NULL:
        return None, pos
    if t in (PST_TRUE, PST_FALSE):
        return t == PST_TRUE, pos
    if t == PST_SYMBOL:
        raw, pos = _read_exact(data, pos, 2)
        (length,) = struct.unpack(">H", raw)
        s, pos = _read_exact(data, pos, length)
        return s.decode("utf-8"), pos
    if t == PST_INT32:
        raw, pos = _read_exact(data, pos, 4)
        return struct.unpack(">i", raw)[0], pos
    if t in (PST_INT64, PST_UINT64):
        raw, pos = _read_exact(data, pos, 8)
        return struct.unpack(">q" if t == PST_INT64 else ">Q", raw)[0], pos
    if t == PST_DOUBLE:
        raw, pos = _read_exact(data, pos, 8)
        return struct.unpack(">d", raw)[0], pos
    if t in (PST_PAIR, PST_DICT):
        if depth >= _MAX_DEPTH:
            raise PmtDecodeError(f"anidamiento PMT excede el limite de {_MAX_DEPTH}")
        car, pos = _parse(data, pos, depth + 1)
        cdr, pos = _parse(data, pos, depth + 1)
        return (car, cdr), pos
    if t == PST_UNIFORM_VECTOR:
        sub, pos = _read_exact(data, pos, 1)
        if sub[0] != UVI_U8:
            raise PmtDecodeError("solo se soporta u8vector")
        raw, pos = _read_exact(data, pos, 4)
        (length,) = struct.unpack(">I", raw)
        npad_raw, pos = _read_exact(data, pos, 1)
        _pad, pos = _read_exact(data, pos, npad_raw[0])
        blob, pos = _read_exact(data, pos, length)
        return blob, pos
    if t in (PST_TUPLE, PST_VECTOR):
        raw, pos = _read_exact(data, pos, 4)
        (length,) = struct.unpack(">I", raw)
        if depth >= _MAX_DEPTH:
            raise PmtDecodeError(f"anidamiento PMT excede el limite de {_MAX_DEPTH}")
        items = []
        for _ in range(length):
            item, pos = _parse(data, pos, depth + 1)
            items.append(item)
        return items, pos
    raise PmtDecodeError(f"tag PMT desconocido 0x{t:02x}")

def decode_pdu_data(frame: bytes) -> bytes:
    value, pos = _parse(frame)
    if pos != len(frame):
        raise PmtDecodeError("datos extra después del mensaje PMT")
    node = value
    while isinstance(node, tuple) and len(node) == 2:
        node = node[1]
    if not isinstance(node, bytes):
        raise PmtDecodeError("el cdr final del PDU no es un u8vector")
    return node