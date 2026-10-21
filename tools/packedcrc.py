# packedcrc.py: test the hypothesis that the mish checksum (0xDEE926A4) is a
# CRC32 over the table's PACKED (compressed) source byte stream, in chunk
# order -- not over the decoded content.
import plistlib
import zlib

root = plistlib.load(open('research/ipsw-x/blkx.plist', 'rb'))
for ent in root['resource-fork']['blkx']:
    if ent['Name'] != 'Apple_APFS':
        continue
    mish = ent['Data']
    n = int.from_bytes(mish[0xc8:0xcc], 'big')
    crc = 0
    for c in range(n):
        o = 0xcc + c * 40
        clen = int.from_bytes(mish[o + 32:o + 40], 'big')
        if clen == 0:
            continue
        coff = int.from_bytes(mish[o + 24:o + 32], 'big')
        with open('research/ipsw-x/087-86698-044.dmg', 'rb') as f:
            f.seek(coff)
            left = clen
            while left:
                b = f.read(min(64 << 20, left))
                crc = zlib.crc32(b, crc)
                left -= len(b)
    print('packed-CRC32 of Apple_APFS chunk sources =', hex(crc & 0xffffffff))
    print('mish recorded checksum                   = 0xdee926a4')
