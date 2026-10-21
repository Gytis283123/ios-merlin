# apfsfletcher.py: verify APFS fletcher64 of decoded blocks in rootfs.img.
# On-disk: bytes[0:8] = checksum, bytes[8:] covered. fletcher over u32 LE words:
# s1 = (s1 + w); s2 = (s2 + s1), mod 2^32.
import struct

f = open('research/ipsw-x/rootfs.img', 'rb')
BASE = 34 * 512


def fletcher(block, start=8):
    s1 = s2 = 0
    for o in range(start, len(block), 4):
        w = int.from_bytes(block[o:o + 4], 'little')
        s1 += w
        s2 += s1
        # APFS checksums reduce modulo 2^32-1 (deferred carry), not 2^32
        while s1 > 0xffffffff:
            s1 = (s1 & 0xffffffff) + (s1 >> 32)
        while s2 > 0xffffffff:
            s2 = (s2 & 0xffffffff) + (s2 >> 32)
    return s1, s2


def check(off, label):
    f.seek(off)
    blk = f.read(4096)
    c1 = int.from_bytes(blk[0:4], 'little')
    c2 = int.from_bytes(blk[4:8], 'little')
    s1, s2 = fletcher(blk)
    ok = (s1 == c1 and s2 == c2) or (s2 == c1 and s1 == c2)
    magic = blk[8:12]
    print(f'{label} @ {off:#x}: stored=({c1:#010x},{c2:#010x}) '
          f'calc=({s1:#010x},{s2:#010x}) magic={magic} '
          f'{"OK" if ok else "MISMATCH"}')
    return ok


# candidate nx_superblock locations: partition block 0, and the block
# containing the NXSB we saw at +32
check(BASE, 'part block0')
check(BASE + 32, 'part +32 not aligned - expect fail')
# scan first 64 blocks for NXSB magics and fletcher-verify each
f.seek(BASE)
region = f.read(64 * 4096)
pos = 0
found = 0
while True:
    i = region.find(b'NXSB', pos)
    if i < 0:
        break
    bstart = (i // 4096) * 4096
    check(BASE + bstart, f'NXSB block {bstart // 4096}')
    found += 1
    pos = i + 4
    if found > 6:
        break
print('NXSB occurrences scanned:', found)
