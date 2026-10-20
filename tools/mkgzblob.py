#!/usr/bin/env python3
"""Build an MTK-style compressed kernel blob: gzip(Image) + raw FDT.

The merlin (MIUI V12.5.1.0 mt6768) stock kernel blob inside boot.img is not
a plain ARM64 Image - it is one gzip member whose payload is the plain
Image, followed by the raw FDT the LK uses (the same tree the boot.img dtb
section carries, without its 64-byte dt-pack wrapper).  LK decompresses and
treats the Image per its header, and takes the blob's trailing FDT for the
boot FDT.  Plain (uncompressed, FDT-less) blobs - like all our earlier
shim/probe kernels - are NOT recognized: LK bails and the box resets after
~16s.  Hence the bootloop that survived every earlier packing strategy.

  mkgzblob.py KERNEL.bin FDT.bin OUT.bin
"""
import gzip
import io
import struct
import sys


def main():
    kpath, fdtpath, opath = sys.argv[1:4]
    kernel = open(kpath, 'rb').read()
    assert kernel[0x38:0x3c] == b'ARM\x64', \
        f'{kpath}: not an ARM64 Image (magic {kernel[0x38:0x3c]!r})'
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as g:
        g.write(kernel)
    blob = buf.getvalue()
    if fdtpath != '-':
        fdt = open(fdtpath, 'rb').read()
        assert fdt[:4] == bytes.fromhex('d00dfeed'), 'FDT magic missing'
        blob += fdt
    open(opath, 'wb').write(blob)
    print(f'{opath}: {len(blob)} bytes = gzip({len(kernel)}) + '
          f'fdt({0 if fdtpath == "-" else len(fdt)})')


main()
