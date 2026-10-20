#!/usr/bin/env python3
"""Replace the kernel inside a stock merlin boot.img, byte-identical layout.

LK rejects reasons we cannot spell (yet) have to do with how a boot.img is
shaped: our mkbootimg.py output diverged from the stock header in page_size
(4096 vs 2048), ramdisk/tags addresses and the cmdline.  This tool avoids
the question: take the STOCK boot.img, copy the shim kernel over its kernel
region in place, zero the ramdisk size, and keep every other header byte
exactly as the factory wrote it.

  mkboot-edit.py STOCK_BOOT.img NEW_KERNEL.bin OUT.img
"""
import sys


def main():
    stock_path, kernel_path, out_path = sys.argv[1:4]
    stock = bytearray(open(stock_path, 'rb').read())
    assert stock[:8] == b'ANDROID!', 'not a boot image'
    import struct
    ksz, kaddr, rsz, raddr, ssz, saddr, taddr, page, hv, ov = \
        struct.unpack('<10I', bytes(stock[8:48]))
    assert hv == 2, f'header_version={hv}: tool handles v2'
    kernel = open(kernel_path, 'rb').read()
    assert len(kernel) <= ksz, f'shim {len(kernel)} > stock kernel {ksz}'

    # AOSP v2 layout with this page size: header page, then kernel page-1.
    koff = page
    roff = koff + (ksz + page - 1) // page * page
    print(f'stock: kernel@{koff:#x}({ksz}) ramdisk@{roff:#x}({rsz}) '
          f'page={page}')
    stock[koff:koff + len(kernel)] = kernel
    if len(kernel) < ksz:                       # wipe the rest of the region
        stock[koff + len(kernel):koff + ksz] = b'\0' * (ksz - len(kernel))
    stock[8:12] = struct.pack('<I', len(kernel))
    if len(sys.argv) > 4 and sys.argv[4] == '--zero-ramdisk':
        stock[16:20] = struct.pack('<I', 0)
    stock[576:608] = b'\0' * 32                 # id: leave neutral
    open(out_path, 'wb').write(bytes(stock))
    print(f'{out_path}: {len(stock)} bytes ({len(stock)//(1024*1024)} MB), '
          f'kernel={len(kernel)}, ramdisk_size='
          f'{struct.unpack("<I", bytes(stock[16:20]))[0]}')


main()
