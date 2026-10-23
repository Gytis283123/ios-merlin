#!/usr/bin/env python3
"""Rewrite the sweet fbcon in a built kernel from FBCON_SCALE=2 to 1.

The CI kernel compiles pe_serial.c's fbcon with FBCON_SCALE 2 (16x32 px
cells, 67 columns on a 1080-wide panel), so panic lines wrap and only the
left half of the frame is used.  This replaces the two compiled functions

  _fbcon_init          (region 0xc4)
  _fbcon_transmit_data (region 0x3e4)

with the 8x16-cell versions assembled from tools/fbcon-1x.S (build with
tools/fbcon-1x.ld; blobs tools/fbcon-1x.{init,tx}.bin).  All globals they
touch keep the same addresses.

  patch-fbcon1x.py IN_KERNEL OUT_KERNEL
"""
import struct
import sys

HERE = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
INIT_VA, INIT_SIZE = 0xfffffe0007a7bb44, 0xc4
TX_VA, TX_SIZE = 0xfffffe0007a7bc10, 0x3e4
NOP = 0xd503201f


def segments(buf):
    magic, cputype, cpusub, ftype, ncmds = struct.unpack_from('<5I', buf, 0)
    assert magic == 0xfeedfacf, 'not a 64-bit Mach-O'
    segs, off = [], 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', buf, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = buf[off + 8:off + 24].split(b'\0')[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', buf, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff, filesize))
        off += size
    return segs


def file_off(segs, va):
    for name, vmaddr, vmsize, fileoff, filesize in segs:
        if vmaddr <= va < vmaddr + vmsize:
            assert va - vmaddr < filesize, f'{va:#x} is bss'
            return fileoff + (va - vmaddr)
    raise SystemExit(f'{va:#x} not in any segment')


def main():
    src, dst = sys.argv[1], sys.argv[2]
    buf = bytearray(open(src, 'rb').read())
    segs = segments(buf)
    init = open(f'{HERE}/fbcon-1x.init.bin', 'rb').read()
    tx = open(f'{HERE}/fbcon-1x.tx.bin', 'rb').read()
    assert len(init) <= INIT_SIZE, len(init)
    assert len(tx) <= TX_SIZE, len(tx)
    for va, blob, size in ((INIT_VA, init, INIT_SIZE), (TX_VA, tx, TX_SIZE)):
        o = file_off(segs, va)
        first = struct.unpack_from('<I', buf, o)[0]
        assert first != NOP, f'{va:#x}: already patched?'
        buf[o:o + len(blob)] = blob
        struct.pack_into(f'<{(size - len(blob)) // 4}I', buf, o + len(blob),
                         *([NOP] * ((size - len(blob)) // 4)))
        print(f'{va:#x}: {len(blob)} B code + {size - len(blob)} B nop '
              f'(was {first:#010x})')
    open(dst, 'wb').write(buf)
    print(f'wrote {dst} ({len(buf)} bytes)')


if __name__ == '__main__':
    main()
