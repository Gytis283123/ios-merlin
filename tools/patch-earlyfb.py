#!/usr/bin/env python3
"""Retarget the SWEET early console from the sweet panel to merlin's splash FB.

kernel.development.sweet (xnu-8796; last retargeted for the 0105 CI
kernel, see below) hardcodes the sweet
bring-up framebuffer: PA 0x9c000000, 1080x2400, stride 4320.  Merlin's ABL
splash FB is 0x7e605000, 1080x2340, stride 4320.  Without this the kernel's
sweet_early marks/panics go to plain DRAM and the phone screen tells us
nothing.

Three code sites and one data word, all verified before patching.  The
code VAs are kernel-build-specific: the ones below were re-derived for
research/art-0105/kernel.development.sweet (sha256 f576189d21e8161e...) by
scanning __TEXT_EXEC for the expected original words (each is unique, and
the white-band pair is adjacent).  On a new kernel the asserts fire -
re-derive the same way, do not drop the asserts.

  0xfffffe00074885dc  arm_vm_init (inlined sweet_early_map_final):
                      movk x8, #0x9c00, lsl #16   -> #0x7e00
                      (TTE block PA 0x9c000000 -> 0x7e000000)
  0xfffffe0007492340  start.s FB block map:
                      movk x10, #0x9c00, lsl #16  -> #0x7e00
                      (same flat L2 array; index 78 -> 63, still < 2048)
  0xfffffe0007492104  start.s stage-0 white band (MMU off, physical):
                      movk x0, #0x9c9c / movk x0, #0x1800
                      -> merlin FB + (2340-32)*4320
  __DATA 8-byte word   static early_fb = 0x9c000000 -> 0x7e605000

  python3 tools/patch-earlyfb.py IN OUT
"""
import struct
import sys

LC_SEGMENT_64 = 0x19

# vmaddr -> expected instruction word, patched instruction word
FIXUPS = [
    (0xfffffe00074885dc, 0xF2A00000 | (0x9C00 << 5) | 8,
                         0xF2A00000 | (0x7E00 << 5) | 8),
    (0xfffffe0007492340, 0xF2A00000 | (0x9C00 << 5) | 10,
                         0xF2A00000 | (0x7E00 << 5) | 10),
]

MERLIN_FB = 0x7E605000
MERLIN_H = 2340
BAND = MERLIN_FB + (MERLIN_H - 32) * 4320
BAND_LO = BAND & 0xFFFF
BAND_HI = (BAND >> 16) & 0xFFFF
FIXUPS += [
    (0xfffffe0007492104, 0xF2A00000 | (0x9C9C << 5) | 0,
                         0xF2A00000 | (BAND_HI << 5) | 0),
    (0xfffffe0007492108, 0xF2800000 | (0x1800 << 5) | 0,
                         0xF2800000 | (BAND_LO << 5) | 0),
]

OLD_PTR = struct.pack('<Q', 0x9C000000)
NEW_PTR = struct.pack('<Q', MERLIN_FB)


def segments(buf):
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = \
        struct.unpack_from('<8I', buf, 0)
    assert magic == 0xfeedfacf, 'not a 64-bit Mach-O'
    off, segs = 32, []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', buf, off)
        if cmd == LC_SEGMENT_64:
            name = buf[off + 8:off + 24].split(b'\0')[0].decode()
            vmaddr, vmsize, fileoff, filesize = \
                struct.unpack_from('<4Q', buf, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff, filesize))
        off += size
    return segs


def va2off(segs, va):
    for name, vmaddr, vmsize, fileoff, filesize in segs:
        if vmaddr <= va < vmaddr + filesize:
            return fileoff + (va - vmaddr)
    raise SystemExit(f'va {va:#x} not in any segment')


def main():
    src, dst = sys.argv[1:3]
    buf = bytearray(open(src, 'rb').read())
    segs = segments(buf)
    print(f'band address {BAND:#x} (lo {BAND_LO:#x} hi {BAND_HI:#x})')

    for va, old, new in FIXUPS:
        o = va2off(segs, va)
        got, = struct.unpack_from('<I', buf, o)
        assert got == old, \
            f'{va:#x}: expected {old:#010x}, found {got:#010x}'
        struct.pack_into('<I', buf, o, new)
        print(f'{va:#x}: {old:#010x} -> {new:#010x}')

    hits = []
    start = 0
    while True:
        i = buf.find(OLD_PTR, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    assert len(hits) == 1, f'early_fb data word: {len(hits)} hits at {hits}'
    i = hits[0]
    buf[i:i + 8] = NEW_PTR
    print(f'early_fb @ file 0x{i:x}: 0x9c000000 -> {MERLIN_FB:#x}')

    open(dst, 'wb').write(bytes(buf))
    print(f'{dst}: {len(buf)} bytes, {len(FIXUPS) + 1} patches')


if __name__ == '__main__':
    main()
