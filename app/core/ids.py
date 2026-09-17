import os
import time
import uuid


def generate_id() -> str:
    """UUIDv7 (RFC 9562): a 48-bit millisecond timestamp in the high bits
    followed by random bits, so ids sort chronologically by creation time
    while staying globally unique. Implemented manually since Python's
    stdlib doesn't gain uuid.uuid7() until 3.14 and this project targets 3.12.
    """
    unix_ts_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    version_and_rand_a = (0x7 << 12) | rand_a
    variant_and_rand_b = (0b10 << 62) | rand_b

    uuid_bytes = (
        unix_ts_ms.to_bytes(6, "big")
        + version_and_rand_a.to_bytes(2, "big")
        + variant_and_rand_b.to_bytes(8, "big")
    )
    return str(uuid.UUID(bytes=uuid_bytes))
