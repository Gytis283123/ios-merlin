#!/usr/bin/env python3
"""Minimal newc cpio (TRAILER only) for boot images that need a non-empty
ramdisk slot but no content."""
import sys

magic = b"070701"
fields = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]  # 13 x u32 (ino..check)
name = b"TRAILER!!!"
fields[11] = len(name) + 1                        # c_namesize
hdr = magic + "".join(f"{f:08X}" for f in fields).encode()
out = hdr + name + b"\0"
while len(out) % 4:
    out += b"\0"
while len(out) % 512:
    out += b"\0"
assert len(out) == 512, len(out)
open(sys.argv[1], "wb").write(out)
