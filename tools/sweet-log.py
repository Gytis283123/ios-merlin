#!/usr/bin/env python3
"""Decode the SWEET persistent console log (kernel patch 0047).

  sweet-log.py AREA.bin [OUT.txt]

AREA.bin is a block-aligned userdata tail capture. It can be exactly the
header plus ring, or the 16-MiB pull area containing a smaller legacy ring
at its end. The header ("SWEETLOG", u32 version, u32 ring size, u64 total
bytes, u64 flush seq) is followed by the ring. Byte n of the console stream
is at ring offset n % size.
"""
import struct
import sys

BLOCK_SIZE = 4096
HEADER_SIZE = 4096
HEADER = struct.Struct('<8sIIQQ')
MAGIC = b'SWEETLOG'


def parse_area(data):
    if len(data) < HEADER_SIZE or len(data) % BLOCK_SIZE:
        raise ValueError(f'raw capture must be a 4-KiB block multiple, got {len(data)} bytes')

    candidates = []
    invalid = []
    for offset in range(0, len(data) - HEADER_SIZE + 1, BLOCK_SIZE):
        if data[offset:offset + len(MAGIC)] != MAGIC:
            continue
        _, version, size, total, seq = HEADER.unpack_from(data, offset)
        end = offset + HEADER_SIZE + size
        if version != 1:
            invalid.append(f'unsupported version {version} at byte {offset}')
        elif size == 0 or size % BLOCK_SIZE:
            invalid.append(f'invalid ring size {size} at byte {offset}')
        elif end != len(data):
            invalid.append(f'header at byte {offset} describes an end at byte {end}, file ends at {len(data)}')
        else:
            candidates.append((offset, version, size, total, seq))

    if len(candidates) != 1:
        if candidates:
            raise ValueError(f'ambiguous SWEETLOG headers at {[entry[0] for entry in candidates]}')
        if invalid:
            raise ValueError('; '.join(invalid))
        raise ValueError('no SWEETLOG header (log never flushed, or wrong area)')

    offset, version, size, total, seq = candidates[0]
    ring_start = offset + HEADER_SIZE
    ring = data[ring_start:ring_start + size]
    return offset, version, size, total, seq, ring


if len(sys.argv) < 2:
    sys.exit('usage: sweet-log.py AREA.bin [OUT.txt]')

try:
    data = open(sys.argv[1], 'rb').read()
    header_offset, version, size, total, seq, ring = parse_area(data)
except (OSError, ValueError, struct.error) as error:
    sys.exit(str(error))

if total <= size:
    text = ring[:total]
else:
    start = total % size
    text = ring[start:] + ring[:start]
out = text.decode('utf-8', 'replace').replace('\r', '')
header_location = f', header offset {header_offset}' if header_offset else ''
print(f'# version {version}, ring {size}, total {total} bytes, flush #{seq}'
      f'{" (wrapped: oldest bytes lost)" if total > size else ""}'
      f'{header_location}', file=sys.stderr)
if len(sys.argv) > 2:
    with open(sys.argv[2], 'w', newline='') as output:
        output.write(out)
else:
    sys.stdout.write(out)
