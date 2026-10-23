#!/usr/bin/env python3
"""Boot a MERLINXNU payload (tools/mkpayload.py) in QEMU's virt board.

  qemu-merlin.py PAYLOAD OUTDIR [--secs N] [--gdb]

Does what shim/loader.c does on the phone, but on the host: places the
kernel segments, ADT and boot_args at their physical addresses and starts
the CPU at a 6-instruction stub that jumps to the entry with x0 = boot_args.
virt RAM starts at 0x40000000; with enough -m it covers the console plane
(0x9c000000) and the kernel's phys_base (0xb0000000) as plain memory.

After N seconds (or when the guest stops) it writes into OUTDIR:
  fb.png     the 1080x2400 console plane (what the phone screen would show)
  regs.txt   QEMU's view of CPU state
  qemu.log   exceptions with ESR/FAR/ELR (-d int,guest_errors)

With --kernel KERNEL (the matching unstripped Mach-O), also decode the
console plane using its iso_font into fb.txt and write result.json. This is
a snapshot of the circular screen, not a complete boot log. --fail-on-panic
returns 2 when a panic is visible; absence of a panic does not prove boot.
An undecodable or blank screen returns 3 with --fail-on-panic.

The payload magic stays 'SWEETXNU' (v1): the shim/loader contract is shared
with ios-sweet on purpose.
"""
import argparse, json, os, socket, struct, subprocess, sys, time, zlib

IS_WIN = sys.platform == 'win32'
HERE = os.path.dirname(os.path.abspath(__file__))

FB_BASE, FB_W, FB_H = 0x9c000000, 1080, 2400
FB_STRIDE = FB_W * 4
PAGE = 0x4000
STUB_PA = 0x40200000	# above the dtb QEMU places at RAM base
RAMFB_PA = 0x40180000	# tools/qemu-ramfb.bin (preboot -> ramfb_init)
BOOT_LINE_LENGTH = 608


def qemu_binary():
    """Path of qemu-system-aarch64 (env MERLIN_QEMU, PATH, repo research tree)."""
    cand = os.environ.get('MERLIN_QEMU')
    paths = [cand] if cand else ['qemu-system-aarch64']
    if IS_WIN:
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             '..', 'research', 'qemu-win', 'qemu-system-aarch64.exe')
        paths.append(local)
    for p in paths:
        if not p:
            continue
        found = subprocess.run(['which', p] if not IS_WIN else ['where', p],
                               capture_output=True, text=True)
        if (not IS_WIN and found.returncode == 0) or (IS_WIN and found.stdout.strip()):
            return p.strip().splitlines()[0]
        if os.path.isfile(p):
            return p
    raise SystemExit('qemu-system-aarch64 not found (set MERLIN_QEMU); see tools/env-ubuntu.sh')


def posix_path(p):
    """QEMU on Windows wants absolute paths with forward slashes."""
    return os.path.abspath(p).replace('\\', '/')


def build_image(payload):
    """Return (phys_base, ram_image, boot_args_pa, entry_pa)."""
    magic, ver, nsegs = struct.unpack_from('<8sII', payload, 0)
    assert magic == b'SWEETXNU' and ver == 1, 'not a SWEETXNU v1 payload'
    virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size = \
        struct.unpack_from('<7Q', payload, 0x10)
    cmdline = payload[0x48:0x48 + BOOT_LINE_LENGTH]
    delta = phys_base - virt_base
    adt_pa = kernel_end + delta
    ba_pa = (adt_pa + adt_size + PAGE - 1) & ~(PAGE - 1)
    top = ba_pa + PAGE
    img = bytearray(top - phys_base)
    for i in range(nsegs):
        vmaddr, vmsize, foff, fsize = struct.unpack_from('<4Q', payload, 0x2a8 + 32 * i)
        o = vmaddr + delta - phys_base
        img[o:o + fsize] = payload[foff:foff + fsize]
    img[adt_pa - phys_base:adt_pa - phys_base + adt_size] = payload[adt_off:adt_off + adt_size]
    ba = struct.pack('<HH4x4Q6QI4xQI', 2, 2, virt_base, phys_base, mem_size, top,
                     FB_BASE, 1, FB_STRIDE, FB_W, FB_H, 32, 0, adt_pa - delta, adt_size)
    ba += cmdline + b'\0' * 4 + struct.pack('<QQ', 0, mem_size)
    assert len(ba) == 736
    img[ba_pa - phys_base:ba_pa - phys_base + len(ba)] = ba
    return phys_base, bytes(img), ba_pa, entry_va + delta


def stub(ba_pa, entry_pa, ramfb=None):
    """x0 = boot_args, jump to entry; with ramfb=(pa,base,w,h,stride) also
    configure QEMU's ramfb for the guest framebuffer first."""
    if ramfb is None:
        # ldr x0, =ba ; ldr x1, =entry ; br x1 ; nop ; .quad ba ; .quad entry
        return struct.pack('<4I2Q', 0x58000080, 0x580000a1, 0xd61f0020, 0xd503201f,
                           ba_pa, entry_pa)
    preboot_pa, base, w, h, stride = ramfb
    movz = lambda rt, imm: 0x52800000 | ((imm & 0xffff) << 5) | rt
    ins = (
        0x58000149,             # ldr x9, [pc, #0x28]  (preboot)
        0x58000160,             # ldr x0, [pc, #0x2c]  (fb base)
        movz(1, w),             # movz w1, #w
        movz(2, h),             # movz w2, #h
        movz(3, stride),        # movz w3, #stride
        0xd63f0120,             # blr x9
        0x58000100,             # ldr x0, [pc, #0x20]  (boot_args)
        0x58000121,             # ldr x1, [pc, #0x24]  (entry)
        0xd61f0020,             # br x1
        0xd503201f,             # nop
    )
    return struct.pack('<10I4Q', *ins, preboot_pa, base, ba_pa, entry_pa)


def write_png(path, raw):
    rows = []
    for y in range(FB_H):
        line = raw[y * FB_STRIDE:(y + 1) * FB_STRIDE]
        rgb = bytearray(FB_W * 3)	# a8r8g8b8 little endian = B G R A in memory
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        rows.append(b'\0' + bytes(rgb))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', FB_W, FB_H, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b''.join(rows), 6)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def macho_iso_font(kernel_path):
    """VA of _iso_font from the kernel's LC_SYMTAB (portable; no llvm-nm)."""
    MH_MAGIC_64, LC_SYMTAB = 0xfeedfacf, 2
    blob = open(kernel_path, 'rb').read()
    if struct.unpack_from('<I', blob, 0)[0] != MH_MAGIC_64:
        raise SystemExit(f'{kernel_path}: not an arm64 Mach-O')
    ncmds, = struct.unpack_from('<I', blob, 16)
    symoff = nsyms = stroff = None
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', blob, off)
        if cmd == LC_SYMTAB:
            symoff, nsyms, stroff = struct.unpack_from('<III', blob, off + 8)
        off += cmdsize
    if symoff is None:
        raise SystemExit(f'{kernel_path}: stripped (no LC_SYMTAB); need an unstripped kernel')
    found = []
    for i in range(nsyms):
        o = symoff + 16 * i			# nlist_64: strx u32, type u8, sect u8, desc u16, value u64
        n_strx, n_type = struct.unpack_from('<IB', blob, o)
        n_value, = struct.unpack_from('<Q', blob, o + 8)
        if (n_type & 0x0e) == 0x0e and (n_type & 0x01):  # N_SECT + N_EXT: defined
            s = blob[stroff + n_strx:blob.index(b'\0', stroff + n_strx)]
            if s == b'_iso_font':
                found.append(n_value)
    if len(found) != 1:
        raise SystemExit(f'{kernel_path}: found {len(found)} _iso_font symbols, need exactly 1')
    return found[0]


def payload_data(payload, va, size):
    """Read initialized segment bytes by VA (the payload has no slide)."""
    nsegs = struct.unpack_from('<I', payload, 12)[0]
    for i in range(nsegs):
        vmaddr, _, foff, fsize = struct.unpack_from('<4Q', payload, 0x2a8 + 32 * i)
        if vmaddr <= va and va + size <= vmaddr + fsize:
            offset = foff + va - vmaddr
            return payload[offset:offset + size]
    raise ValueError(f'VA {va:#x}+{size:#x} not in initialized payload segments')


def decode_screen(raw, font):
    """Exact glyph matching for pe_serial.c's 2x, white-on-black fbcon."""
    glyphs = {font[c * 16:(c + 1) * 16]: chr(c) for c in range(32, 127)}
    rows, unknown = [], 0
    for row in range(FB_H // 32):
        chars = []
        for col in range(FB_W // 16):
            glyph = bytearray(16)
            for y in range(16):
                offset = (row * 32 + y * 2) * FB_STRIDE + col * 16 * 4
                for x in range(8):
                    if raw[offset + x * 8:offset + x * 8 + 4] == b'\xff' * 4:
                        glyph[y] |= 1 << x
            key = bytes(glyph)
            char = glyphs.get(key, '?')
            unknown += key not in glyphs
            chars.append(char)
        rows.append(''.join(chars).rstrip())
    return '\n'.join(rows).rstrip() + '\n', unknown


def screen_result(screen, unknown):
    if 'panic(cpu ' in screen or 'SWEET EARLY PANIC:' in screen or 'MERLIN EARLY PANIC:' in screen:
        status = 'panic'
    elif unknown:
        status = 'incomplete_decode'
    elif screen.strip():
        status = 'no_panic_observed'
    else:
        status = 'blank_screen'
    return {'status': status, 'unknown_glyphs': unknown, 'snapshot_only': True}


def qmp(sock_path, *cmds, pmemsave=None):
    """Run QEMU human-monitor commands over QMP (synchronous, unlike the echoing HMP socket)."""
    s = socket.socket(socket.AF_UNIX if isinstance(sock_path, str) else socket.AF_INET)
    s.connect(sock_path)
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
        if 'error' in r:
            print(f'qmp {c!r}: {r["error"]}', file=sys.stderr)
        out.append(r.get('return', ''))
    if pmemsave:	# native QMP: HMP's argument parser chokes on '-' in paths
        for val, size, fname in (pmemsave if isinstance(pmemsave[0], tuple) else [pmemsave]):
            r = call('pmemsave', val=val, size=size, filename=fname)
            if 'error' in r:
                print(f'qmp pmemsave: {r["error"]}', file=sys.stderr)
    s.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('payload'); ap.add_argument('outdir')
    ap.add_argument('--secs', type=float, default=20)
    ap.add_argument('--gdb', action='store_true', help='start halted, gdb stub on :1234, no timeout')
    ap.add_argument('--hmp', action='append', default=[], help='extra monitor command run after stop (repeatable), e.g. "x /8gx 0xfffffe..."')
    ap.add_argument('--cpu', default='cortex-a76')	# ARMv8.2 class (MT6768's A75 has no named QEMU model); proven default from ios-sweet
    ap.add_argument('--kernel', help='matching unstripped kernel, for exact framebuffer text decoding')
    ap.add_argument('--fail-on-panic', action='store_true', help='exit 2 for a visible panic, 3 for incomplete/blank decoding; requires --kernel')
    ap.add_argument('--dump-ram', action='store_true', help='keep a pmemsave of the whole RAM image for post-mortem string forensics')
    ap.add_argument('--gui', action='store_true',
                    help='show the guest framebuffer in a QEMU/GTK window (ramfb on --fb-base)')
    ap.add_argument('--fb-base', type=lambda s: int(s, 0), default=FB_BASE,
                    help='framebuffer VAs to dump/decode/GUI (default 0x9c000000)')
    ap.add_argument('--qargs', action='append', default=[], help='extra raw QEMU CLI args (repeatable), e.g. -trace enable=arm_gt_cval_write')
    ap.add_argument('--fb-geom', default=None,
                    help='framebuffer WxH for boot_args/ramfb/decode (default 1080x2400)')
    a = ap.parse_args()
    global FB_W, FB_H, FB_STRIDE
    if a.fb_geom:
        fw, fh = a.fb_geom.lower().split('x')
        FB_W, FB_H = int(fw), int(fh)
        FB_STRIDE = FB_W * 4
    if a.fail_on_panic and not a.kernel:
        ap.error('--fail-on-panic requires --kernel')
    payload = open(a.payload, 'rb').read()
    font = None
    if a.kernel:
        fonts = [macho_iso_font(a.kernel)]	# portable LC_SYMTAB walk (llvm-nm on Linux is equivalent)
        font = payload_data(payload, fonts[0], 256 * 16)
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)

    phys_base, img, ba_pa, entry_pa = build_image(payload)
    open(f'{out}/ram.bin', 'wb').write(img)
    open(f'{out}/stub.bin', 'wb').write(
        stub(ba_pa, entry_pa,
             (RAMFB_PA, a.fb_base, FB_W, FB_H, FB_STRIDE) if a.gui else None))
    print(f'phys_base={phys_base:#x} boot_args={ba_pa:#x} entry={entry_pa:#x}', file=sys.stderr)

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
    # virt RAM starts at 0x40000000: cover the payload's RAM (mkadt --phone needs 8G too).
    mem_size = struct.unpack_from('<Q', payload, 0x40)[0]
    ram_gib = max(4, -(-(phys_base + mem_size - 0x40000000) // (1 << 30)))
    cmd = [qemu, '-M', 'virt,gic-version=3', '-cpu', a.cpu, '-smp', '1', '-m', f'{ram_gib}G',
           '-accel', 'tcg,thread=multi']
    if a.gui:
        cmd += ['-display', 'gtk,zoom-to-fit=on', '-device', 'ramfb',
                '-device', f'loader,file={posix_path(os.path.join(HERE, "qemu-ramfb.bin"))},'
                           f'addr={RAMFB_PA:#x},force-raw=on']
    else:
        cmd += ['-nographic']
    cmd += ['-serial', 'file:' + posix_path(f'{out}/serial.txt'), '-qmp', qmp_arg,
           '-d', 'int,guest_errors,unimp', '-D', posix_path(f'{out}/qemu.log'), '-no-reboot',
           '-device', f'loader,file={posix_path(f"{out}/ram.bin")},addr={phys_base:#x},force-raw=on',
           '-device', f'loader,file={posix_path(f"{out}/stub.bin")},addr={STUB_PA:#x},force-raw=on',
           '-device', f'loader,addr={STUB_PA:#x},cpu-num=0'] + a.qargs
    if a.gdb:
        cmd += ['-S', '-gdb', 'tcp::1234']
    kw = {}
    if IS_WIN:
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **kw)
    try:
        if a.gdb:
            print('gdb stub on :1234; QMP socket:', mon, file=sys.stderr)
            p.wait()
            return
        t0 = time.time()
        while p.poll() is None and time.time() - t0 < a.secs:
            time.sleep(0.2)
        result = {'status': 'qemu_exited', 'qemu_returncode': p.returncode}
        if p.poll() is None:
            dumps = [(a.fb_base, FB_STRIDE * FB_H, f'{out}/fb.raw')]
            if a.dump_ram:  # post-mortem forensics: whole RAM (VM pages live anywhere in the 5G)
                dumps.append((0x40000000, 0x140000000, f'{out}/ram-dump.raw'))
            _, regs, *extra = qmp(mon, 'stop', 'info registers', *a.hmp, pmemsave=dumps)
            open(f'{out}/regs.txt', 'w').write(regs + ''.join(f'\n(qemu) {c}\n{r}' for c, r in zip(a.hmp, extra)))
            p.kill()
            p.wait()
            raw = open(f'{out}/fb.raw', 'rb').read()
            write_png(f'{out}/fb.png', raw)
            result = {'status': 'not_decoded'}
            if font is not None:
                screen, unknown = decode_screen(raw, font)
                open(f'{out}/fb.txt', 'w').write(screen)
                result = screen_result(screen, unknown)
            os.unlink(f'{out}/fb.raw')
        else:
            print(f'qemu exited early: {p.returncode}', file=sys.stderr)
    finally:
        if p.poll() is None:  # never orphan a 5G guest, even on a harness crash
            p.kill()
            p.wait()
    for f in ('ram.bin',):
        os.unlink(f'{out}/{f}')
    open(f'{out}/result.json', 'w').write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), file=sys.stderr)
    print(f'{out}/fb.png  {out}/regs.txt  {out}/qemu.log', file=sys.stderr)
    if a.fail_on_panic and result['status'] == 'panic':
        return 2
    if a.fail_on_panic and result['status'] in ('incomplete_decode', 'blank_screen'):
        return 3
    if result['status'] == 'qemu_exited':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
