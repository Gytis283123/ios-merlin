#!/usr/bin/env python3
"""Boot the real merlin shim (shim/out/Image built with -DSHIM_QEMU) in QEMU.

  qemu-shim.py SHIM PAYLOAD OUTDIR [--secs N] [--gdb] [--qargs ARG]

Emulates what LK does on the phone:

  0x40080000  shim Image (entry: _head, x0 = DTB)
  0x47c80000  SWEETXNU payload (the boot image "ramdisk")
  0x4bc80000  minimal FDT with /chosen linux,initrd-start/end
  0x40200000  stub: x0 = DTB, br shim entry

The guest is QEMU's virt board with 4G of RAM, so both the merlin
framebuffer (0x7e605000, 1080x2340) and the kernel band (0xb0000000)
are plain memory.  After N seconds the run dumps:

  fb.png / fb.txt   the merlin console plane, decoded with shim/font.h
  bb.txt            the black-box page at 0xbffff000
  regs.txt qemu.log serial.txt

fb.txt is exact glyph matching of the shim's own 8x16 font at scale 2,
so loader lines read back as text instead of needing a phone photo.
"""
import argparse
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import zlib

IS_WIN = sys.platform == 'win32'
SHIM_PA = 0x40100000	# clear of QEMU's own DTB at 0x40000000..0x40100000
INITRD_PA = 0x47C80000
DTB_PA = 0x4BC80000
STUB_PA = 0x40200000
FB_BASE, FB_W, FB_H = 0x9C000000, 1080, 2400
FB_STRIDE = FB_W * 4
BB_PA = 0xBFFFF000


def qemu_binary():
    cand = os.environ.get('MERLIN_QEMU')
    here = os.path.dirname(os.path.abspath(__file__))
    paths = [cand] if cand else []
    if IS_WIN:
        paths.append(os.path.join(here, '..', 'research', 'qemu-win',
                                  'qemu-system-aarch64.exe'))
    paths.append('qemu-system-aarch64')
    for p in paths:
        if p and os.path.isfile(p):
            return p
    raise SystemExit('qemu-system-aarch64 not found (set MERLIN_QEMU)')


def posix_path(p):
    return os.path.abspath(p).replace('\\', '/')


def fdt_blob(path, initrd_start, initrd_end):
    strings = bytearray()
    sb = bytearray()

    def nameoff(n):
        o = len(strings)
        strings.extend(n.encode() + b'\0')
        return o

    def begin(n):
        sb.extend(struct.pack('>I', 1))
        sb.extend(n.encode() + b'\0')
        while len(sb) & 3:
            sb.append(0)

    def end():
        sb.extend(struct.pack('>I', 2))

    def prop(n, data):
        sb.extend(struct.pack('>III', 3, len(data), nameoff(n)))
        sb.extend(data)
        while len(sb) & 3:
            sb.append(0)

    begin('')
    prop('#address-cells', struct.pack('>I', 2))
    prop('#size-cells', struct.pack('>I', 2))
    begin('memory@40000000')
    prop('device_type', b'memory\0')
    prop('reg', struct.pack('>4I', 0, 0x40000000, 0, 0xC0000000))
    end()
    begin('chosen')
    prop('linux,initrd-start', struct.pack('>Q', initrd_start))
    prop('linux,initrd-end', struct.pack('>Q', initrd_end))
    end()
    end()
    sb.extend(struct.pack('>I', 9))
    off_rsv = 40
    off_struct = off_rsv + 16
    off_strings = off_struct + len(sb)
    total = off_strings + len(strings)
    hdr = struct.pack('>10I', 0xd00dfeed, total, off_struct, off_strings,
                      off_rsv, 17, 16, 0, len(strings), len(sb))
    open(path, 'wb').write(hdr + b'\0' * 16 + bytes(sb) + bytes(strings))


def stub(dtb_pa, entry_pa):
    return struct.pack('<4I2Q', 0x58000080, 0x580000a1, 0xd61f0020,
                       0xd503201f, dtb_pa, entry_pa)


def parse_font(path):
    """font8x16[95][16] from shim/font.h -> list of 16-byte glyphs."""
    txt = open(path).read()
    glyphs = []
    for m in re.finditer(r'\{([^{}]*)\}', txt):
        vals = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', m.group(1))]
        if len(vals) == 16:
            glyphs.append(bytes(vals))
    if len(glyphs) != 95:
        raise SystemExit(f'{path}: parsed {len(glyphs)} glyphs, want 95')
    return glyphs


def decode_fb(raw, glyphs, scale=2, margin=24):
    """Exact glyph match of console.c's renderer (SCALE=2, MARGIN=24)."""
    rev = {g: chr(i + 32) for i, g in enumerate(glyphs)}
    ch_w, ch_h = 8 * scale, 16 * scale
    rows = []
    for r in range((FB_H - margin) // ch_h):
        line = []
        for c in range((FB_W - margin) // ch_w):
            g = bytearray(16)
            x0, y0 = margin + c * ch_w, margin + r * ch_h
            for gy in range(16):
                for gx in range(8):
                    o = (y0 + gy * scale) * FB_STRIDE + (x0 + gx * scale) * 4
                    if raw[o:o + 4] == b'\xff\xff\xff\xff':
                        g[gy] |= 0x80 >> gx
            line.append(rev.get(bytes(g), '?'))
        rows.append(''.join(line).rstrip())
    return '\n'.join(rows).rstrip() + '\n'


def write_png(path, raw):
    rows = []
    for y in range(FB_H):
        line = raw[y * FB_STRIDE:(y + 1) * FB_STRIDE]
        rgb = bytearray(FB_W * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        rows.append(b'\0' + bytes(rgb))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', FB_W, FB_H, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b''.join(rows), 6)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def qmp(sock, *cmds, pmemsave=None):
    s = socket.socket(socket.AF_UNIX if isinstance(sock, str) else socket.AF_INET)
    s.connect(sock)
    f = s.makefile('rw')
    f.readline()

    def call(execute, **args):
        f.write(json.dumps({'execute': execute, 'arguments': args}) + '\n')
        f.flush()
        while True:
            r = json.loads(f.readline())
            if 'return' in r or 'error' in r:
                return r

    call('qmp_capabilities')
    out = []
    for c in cmds:
        r = call('human-monitor-command', **{'command-line': c})
        out.append(r.get('return', ''))
    if pmemsave:
        for val, size, fname in pmemsave:
            r = call('pmemsave', val=val, size=size, filename=fname)
            if 'error' in r:
                print(f'qmp pmemsave {fname}: {r["error"]}', file=sys.stderr)
    s.close()
    return out


def append_cmdline(payload, extra):
    """Append a boot-arg to the payload's fixed 608-byte cmdline field."""
    boot_line = 608
    cmd = payload[0x48:0x48 + boot_line].split(b'\0', 1)[0]
    if extra.encode() in cmd.split():
        return payload
    cmd += b' ' + extra.encode()
    assert len(cmd) < boot_line, 'cmdline overflow'
    return payload[:0x48] + cmd.ljust(boot_line, b'\0') + payload[0x48 + boot_line:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('shim')
    ap.add_argument('payload')
    ap.add_argument('outdir')
    ap.add_argument('--secs', type=float, default=None)
    ap.add_argument('--gdb', action='store_true')
    ap.add_argument('--gui', action='store_true',
                    help='show the guest framebuffer in a QEMU/GTK window (ramfb); '
                         'appends wdt=-1 to the payload cmdline unless --strict-hygiene')
    ap.add_argument('--qargs', action='append', default=[])
    ap.add_argument('--fb', type=lambda x: int(x, 0), default=None,
                    help='framebuffer physical base to dump (default 0x9C000000)')
    ap.add_argument('--fb-geom', default=None,
                    help='framebuffer WxH to dump (default 1080x2400)')
    ap.add_argument('--pmem', action='append', default=[],
                    help='extra pmemsave ADDR:SIZE:FILE (ints accept 0x)')
    ap.add_argument('--cmdline-append', default=None,
                    help='append a boot-arg to the payload cmdline, e.g. wdt=-1')
    ap.add_argument('--strict-hygiene', action='store_true',
                    help='keep XNU sched-hygiene panics enabled under --gui')
    a = ap.parse_args()
    global FB_BASE, FB_W, FB_H, FB_STRIDE
    if a.fb is not None:
        FB_BASE = a.fb
    if a.fb_geom:
        fw, fh = a.fb_geom.lower().split('x')
        FB_W, FB_H = int(fw), int(fh)
        FB_STRIDE = FB_W * 4
    out = os.path.abspath(a.outdir)
    os.makedirs(out, exist_ok=True)

    payload = open(a.payload, 'rb').read()
    assert payload[:8] == b'SWEETXNU', 'not a SWEETXNU payload'
    if a.cmdline_append:
        payload = append_cmdline(payload, a.cmdline_append)
    if a.gui and not a.strict_hygiene:
        # Same QEMU vCPU-stall issue as qemu-merlin.py: the DEVELOPMENT
        # kernel's sched-hygiene panics on handlers stretched by GTK/ramfb
        # repaints; wdt=-1 turns the hygiene modes off (arm_init.c).
        payload = append_cmdline(payload, 'wdt=-1')
    payload_file = a.payload
    if payload != open(a.payload, 'rb').read():
        open(f'{out}/payload.bin', 'wb').write(payload)
        payload_file = f'{out}/payload.bin'
    fdt_blob(f'{out}/shim.dtb', INITRD_PA, INITRD_PA + len(payload))
    open(f'{out}/stub.bin', 'wb').write(stub(DTB_PA, SHIM_PA))
    print(f'shim={a.shim} payload={len(payload)} bytes '
          f'initrd={INITRD_PA:#x} dtb={DTB_PA:#x}', file=sys.stderr)

    qemu = qemu_binary()
    mon = f'{out}/mon.sock'
    if os.path.exists(mon):
        os.unlink(mon)
    if IS_WIN:
        sport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sport.bind(('127.0.0.1', 0))
        port = sport.getsockname()[1]
        sport.close()
        mon = ('127.0.0.1', port)
        qmp_arg = f'tcp:127.0.0.1:{port},server,nowait'
    else:
        qmp_arg = f'unix:{mon},server,nowait'

    cmd = [qemu, '-M', 'virt,gic-version=3', '-cpu', 'cortex-a76',
           '-smp', '1', '-m', '4G',
           '-display', 'gtk,zoom-to-fit=on' if a.gui else 'none',
           '-device', 'ramfb',
           '-serial', 'file:' + posix_path(f'{out}/serial.txt'),
           '-qmp', qmp_arg, '-d', 'int,guest_errors,unimp',
           '-D', posix_path(f'{out}/qemu.log'), '-no-reboot',
           '-device', f'loader,file={posix_path(a.shim)},addr={SHIM_PA:#x},force-raw=on',
           '-device', f'loader,file={posix_path(payload_file)},addr={INITRD_PA:#x},force-raw=on',
           '-device', f'loader,file={posix_path(out + "/shim.dtb")},addr={DTB_PA:#x},force-raw=on',
           '-device', f'loader,file={posix_path(out + "/stub.bin")},addr={STUB_PA:#x},force-raw=on',
           '-device', f'loader,addr={STUB_PA:#x},cpu-num=0'] + a.qargs
    if a.gdb:
        cmd += ['-S', '-gdb', 'tcp::1234']
    kw = {'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **kw)
    try:
        if a.gdb:
            print('gdb stub on :1234', file=sys.stderr)
            p.wait()
            return 0
        t0 = time.time()
        secs = a.secs if a.secs is not None else (600.0 if a.gui else 25.0)
        while p.poll() is None and time.time() - t0 < secs:
            time.sleep(0.2)
        result = {'status': 'qemu_exited', 'qemu_returncode': p.returncode}
        if p.poll() is None:
            regs = qmp(mon, 'stop', 'info registers',
                       f'screendump {posix_path(out + "/screen.ppm")}',
                       pmemsave=[(FB_BASE, FB_STRIDE * FB_H, f'{out}/fb.raw'),
                                 (BB_PA, 0x1000, f'{out}/bb.raw')] +
                                [(int(addr, 0), int(size, 0), path)
                                 for addr, size, path in
                                 (s.split(':', 2) for s in a.pmem)])[1]
            open(f'{out}/regs.txt', 'w').write(regs)
            p.kill()
            p.wait()
            raw = open(f'{out}/fb.raw', 'rb').read()
            write_png(f'{out}/fb.png', raw)
            font = parse_font(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           '..', 'shim', 'font.h'))
            screen = decode_fb(raw, font)
            open(f'{out}/fb.txt', 'w').write(screen)
            os.unlink(f'{out}/fb.raw')
            bb = open(f'{out}/bb.raw', 'rb').read()
            magic, seq, stage = struct.unpack_from('<QQQ', bb, 0)
            text = bb[24:88].split(b'\0')[0].decode('latin1')
            open(f'{out}/bb.txt', 'w').write(
                f'magic={magic:#x} seq={seq} stage={stage} text={text!r}\n')
            result = {'status': 'ran', 'bb_seq': seq, 'bb_stage': stage,
                      'bb_text': text, 'fb_lines': len(screen.splitlines())}
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    open(f'{out}/result.json', 'w').write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), file=sys.stderr)
    print(f'{out}/fb.png {out}/fb.txt {out}/bb.txt {out}/qemu.log', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
