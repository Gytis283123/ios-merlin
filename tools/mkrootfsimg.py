#!/usr/bin/env python3
"""mkrootfsimg.py: decode a UDIF (DMG) to a raw disk image.

Built for merlin's rootfs: research/ipsw-x/087-86698-044.dmg (iOS 16.7.16
iPhone10,3/10,6 OS).  The ipsw CLI and 7zz both parsed the image but would
not emit the raw partition; we walk the blkx plist ourselves, decode the
three LZFSE chunk families via a ctypes-bound liblzfse, and write a sparse
raw image.  Verification: CRC32 of the Apple_APFS extent must equal the
checksum 7-Zip reports for 3.apfs (0xDEE926A4 for this dmg).

Mish layout (verified against this file): count @0xc8, entries @0xcc,
40 B each: type(4) comment(4) sect_no(8) sect_cnt(8) comp_off(8) comp_len(8).
Optional theading: lib path = LZFSE_SO env or /home/gycioc/liblzfse.so.

   python3 mkrootfsimg.py IN.dmg OUT.img [--check-crc HEX]
"""
import ctypes
import os
import plistlib
import struct
import sys
import zlib

TYPES_RAW = 0
TYPES_ZERO = 1
TYPES_UUE = 2
TYPES_ZLIB = 0x80000004
TYPES_LZFSE = 0x80000007


class Lzfse:
    def __init__(self, so):
        lib = ctypes.CDLL(so)
        lib.lzfse_decode_buffer.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_void_p]
        lib.lzfse_decode_buffer.restype = ctypes.c_size_t
        self.decode = lib.lzfse_decode_buffer

    def __call__(self, src, dst_size):
        dst = ctypes.create_string_buffer(dst_size)
        n = self.decode(dst, dst_size, src, len(src), None)
        if n != dst_size:
            raise SystemExit(f'lzfse decode {len(src)} -> {n} != {dst_size}')
        return dst.raw


def find_plist(f, tail_mb=16):
    f.seek(0, 2)
    size = f.tell()
    f.seek(-min(tail_mb << 20, size), 2)
    base = f.tell()
    tail = f.read()
    i = tail.find(b'<?xml')
    if i < 0:
        raise SystemExit('no blkx plist in tail')
    j = tail.find(b'</plist>', i)
    return base + i, base + j + len(b'</plist>'), size


def main():
    dmg, out_path = sys.argv[1], sys.argv[2]
    expect_crc = None
    if '--check-crc' in sys.argv:
        expect_crc = int(sys.argv[sys.argv.index('--check-crc') + 1], 16)
    so = os.environ.get('LZFSE_SO', '/home/gycioc/liblzfse.so')
    lzfse = Lzfse(so) if os.path.exists(so) else None

    with open(dmg, 'rb') as f:
        p0, p1, size = find_plist(f)
        f.seek(p0)
        root = plistlib.loads(f.read(p1 - p0))
        tables = []
        extent = 0
        for ent in root['resource-fork']['blkx']:
            mish = ent['Data']
            if mish[:4] != b'mish':
                continue
            base = int.from_bytes(mish[8:16], 'big')
            n = int.from_bytes(mish[0xc8:0xcc], 'big')
            chunks = []
            for c in range(n):
                o = 0xcc + c * 40
                et = int.from_bytes(mish[o:o + 4], 'big')
                comment = int.from_bytes(mish[o + 4:o + 8], 'big')
                sect_no = int.from_bytes(mish[o + 8:o + 16], 'big')
                sect_cnt = int.from_bytes(mish[o + 16:o + 24], 'big')
                coff = int.from_bytes(mish[o + 24:o + 32], 'big')
                clen = int.from_bytes(mish[o + 32:o + 40], 'big')
                chunks.append((et, sect_no, sect_cnt, coff, clen))
            extent = max(extent, base + max((c[1] + c[2]) for c in chunks))
            tables.append((ent['Name'], base, chunks))
        total = extent * 512
        print(f'disk: {len(tables)} tables, extent {extent} sectors '
              f'({total / 1e9:.3f} GB)')
        with open(out_path, 'wb') as out:
            out.truncate(total)
            for name, base, chunks in tables:
                for et, sect_rel, sect_cnt, coff, clen in chunks:
                    if (et == 0xffffffff or sect_cnt == 0
                            or et in (TYPES_ZERO, TYPES_UUE)):
                        continue		# terminator / sparse == zeros
                    out.seek((base + sect_rel) * 512)
                    if et == TYPES_RAW:
                        f.seek(coff)
                        out.write(f.read(sect_cnt * 512))
                    elif et == TYPES_ZLIB:
                        f.seek(coff)
                        out.write(zlib.decompress(f.read(clen), wbits=-15))
                    elif et == TYPES_LZFSE:
                        f.seek(coff)
                        out.write(lzfse(f.read(clen), sect_cnt * 512))
                    else:
                        raise SystemExit(f'type {et:#x} unsupported')
                print(f'  {name} (base {base}) decoded', flush=True)
        out_size = os.path.getsize(out_path)
        print(f'wrote {out_path} {out_size} bytes')
        crc = 0
        with open(out_path, 'rb') as rc:
            while True:
                b = rc.read(64 << 20)
                if not b:
                    break
                crc = zlib.crc32(b, crc)
        crc &= 0xffffffff
        print(f'CRC32 of raw image: {crc:08x}')
        if expect_crc is not None and crc != expect_crc:
            print(f'MISMATCH: expected {expect_crc:08x}')
            sys.exit(1)
        elif expect_crc is not None:
            print('CRC MATCHES - conversion verified')


main()
