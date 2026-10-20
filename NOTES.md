# iOS 16 on merlin (Redmi Note 9, MT6768 / Helio G85) - working notes

## Agent handoff / active work (2026-10-20 LATEST-5: PHONE BOOT CONFIRMED - shim runs on the device! boot7 bigfacts built)

### 0006 result: THE SHIM RUNS ON THE PHONE

User booted (one of) the 0006-shim images and got the full diag screen -
labels SHIM/EL/FREQ/DTB/WDT/MEMBASE/MEMSIZE/INITLO/INITHI/ATAGFB/chosen/
psci/TIRQ/CPU visible on the LK splash, over the Redmi logo.  THE 16s
BOOTLOOP IS GONE: the screen holds (wdt disarm + pet).  LK decompresses
our gzip(Image)+FDT blob and jumps to it.  The red/green start.S proof
blocks ARE visible (photo confirms the top-left red block; our start.S
paints it) -> entry code + console + FB base 0x7e605000 are all right.
The right-hand text column on the splash is LK's own panel log.

Photo of the diag screen (user's Iriun-webcam capture of the phone):
`research/merlin-boot/diag-frame-*.jpg` and user's
`C:\Users\gycioc\Pictures\Capture.PNG` (480x802: too small to read
SCALE-2 hex values - each glyph is a couple px).

### boot-7: bigfacts page (camera-readable values)

`shim-boot-merlin-0007-big.img` (64MB stock byte-patch) and
`shim-boot-merlin-0007b-big.img` (368KB, our packer): same gzip(Image)+
FDT shape, shim now shows:
1. the small scale-2 diag (wiped below),
2. a scale-8 facts page on top: EL, CNTFRQ, DTB, WDTMODE, WDTLEN,
   MEMB0/MSZ0, MEMB1/MSZ1, INITLO, INITHI, ATAGFB, T0/T1/T2 (timer
   interrupt cells), NCPU, MPIDR - 8x16 px glyphs, ~16 cols x 18 rows,
   readable from any camera (console.c con_big_mode/con_big_hex/
   con_big_str; shim.c bg_* globals filled by diag_fdt + diag_small()
   runs twice: before and after the big page),
3. then the full small diag repeats below the facts page.

TOOLING: Iriun webcam live capture works on this PC via ffmpeg dshow
(device "Iriun Webcam"); first grabs were 480px tall.  The device
supports up to 2560x1440 - capture with:
`ffmpeg -f dshow -video_size 2560x1440 -i video="Iriun Webcam" -frames:v 3 out-%d.jpg`

NEXT: when user boots 0007b-big and reports, read the values, finalize
mkadt.py phone constants (PHYS_BASE/MEM_SIZE/ATAGFB/timer intids), then
wire the payload loader into MERLIN shim_main.

## Agent handoff / active work (2026-10-20 LATEST-4: KERNEL BLOB DECODED - stock kernel is gzip(Image)+raw FDT)

### 0005 result: no paint on 0005b-probe (the probe never entered)

Confirms LK does not accept our plain-Image blobs. While checking WHY, the
stock kernel blob finally got decoded:

**The merlin stock "kernel" in boot.img is NOT an Image. It is:**
```
koff 0x800: [ gzip member -> 27,873,280 bytes of plain ARM64 Image
              (text_offset 0x80000, image_size 0x228f000, flags 0xa,
               ARM\x64 magic at +0x38) ]
            + [ raw FDT, 181,203 bytes (identical to the dt-pack's inner
                FDT - see LATEST-2) ]
```
gzip stream ends at blob offset 9,958,158; the FDT is the blob's last
181,203 bytes. No size trailers, just gz + FDT.

ALL our previous attempts (0003, 0004B/E, 0005 probes) shipped a PLAIN
uncompressed Image with no trailing FDT - LK never recognized them as a
kernel and rebooted (~16s cycle), whatever the packing (stock-patch or
our packer). This also explains "bootloop with a do-nothing shim": LK
died before ANY of our code.

### boot-6 images (gzip(Image)+FDT, the stock shape)

- `research/merlin-boot/shim-boot-merlin-0006-probe.img` (64MB): stock
  byte-patch, kernel = gzip(192B probe) + blob-fdt, STOCK ramdisk kept.
- `shim-boot-merlin-0006-shim.img` (64MB): same with the full shim.
- `shim-boot-merlin-0006b-probe.img` (360KB) / `0006b-shim.img` (366KB):
  our packer variants (stock fields, wrapped dtb, 512B cpio ramdisk).
- NEW tool `tools/mkgzblob.py` (gzip(Image)+FDT); `blob-fdt.bin` =
  the blob's inner FDT extracted standalone.

Expected: probe = red block + green band on the splash (parked; possible
16s blink since the probe pets once). Text diag = all the facts. If
STILL nothing paints but 0004C keeps booting Android, the remaining
variables are (a) text_offset 0x80000 placement of the inflated image,
(b) LK allocating/verifying by image_size (ours 192 vs stock 0x228f000)
- remedy: pack the probe with the SAME padded image_size/decompression
behaviour (e.g. embed the probe inside a header-clone of the stock
Image: real image_size, probe code at text_offset).

## Agent handoff / active work (2026-10-20 LATEST-3: 0004c boots ANDROID - packer proven; probe round)

### 0004 results

- **0004C (our packer, stock kernel+ramdisk+dtb, stock fields): BOOTS ANDROID.**
  The whole boot.img path is healthy: packer, page size 2048, addresses,
  cmdline, the MTK dt-pack (d7b7ab1e, FDT at +0x40), os_version. Nothing
  to fix there.
- 0004B (our packer, shim kernel): bootloop.
- 0004E (mkboot-edit byte patch: shim kernel in the stock image): bootloop.

=> The only remaining variable is the KERNEL BLOB itself: the stock
kernel runs through the identical image, our shim's first stores never
paint. Next question: does LK hand control to a NON-stock Image at all?

### probe round (boot-5) - assembly-only 192-byte kernel, no C at all

`research/merlin-boot/probe.S` (+build-probe.sh): Image header + exactly:
msr daifset; pet 0x10007000+0x8 <- 0x1971; paint 96x48 RED block at
0x7e605000; paint a GREEN band below; wfe forever. 192 bytes; literal
pools inside. Packed twice:
`shim-boot-merlin-0005-probe.img` (mkboot-edit stock patch, ramdisk
zeroed) and `shim-boot-merlin-0005b-probe.img` (own packer, stock-shape
everything, wrapped dtb, 512B cpio).

Expected on the phone: the LK splash with a red block, then a green
band, then nothing else (the probe parks). NOTE: the probe does NOT
disarm the watchdog and does not pet while parked - if LK's credits
outlast the pet, the box resets after ~16s and the probe runs again:
a steady or 16s-BLINKING red/green pattern is the HEALTHY result (LK
enters our code). No paint at all = LK never entered us.

### Interpreting the probe

- red+green visible (steady or blinking): LK runs arbitrary Image code
  fine - the real shim's failure is in OUR build (bss/stack/vectors/
  literals/EL state). Debug the full shim against these pins next.
- no paint on BOTH 0005 variants (with C having booted Android): LK
  refuses control to non-kernel-shaped bytes. Next: replicate more of
  the stock kernel head (real image_size values), then LK archaeology
  (mt6768 LK is not in this workspace) or memory read-back via mtkclient.

## Agent handoff / active work (2026-10-20 LATEST-2: 16s loop survives the wdt fix; boot.img-shape bisect kit ready)

### Symptom after the wdt fix: 16s cycle, MI logo, NO red pixels at all

The user reports "still bootloop exist": resets every **~16 s**, screen shows
the MI logo or nothing - never our shim's red block/text. The 0003 build DID
pet + disarm correctly (verified in the disassembly), so, per the first
instruction of shim_main painting the fb, the failure is BEFORE our code
runs: the boot.img layer / LK, not the shim.

### Stock boot.img reference facts (extracted 0004 session, repo root tgz)

From `merlin_global_images_V12.5.1.0.RJOMIXM...tgz` ->
`research/merlin-boot/stock-boot.img` (64 MB, padded to 0x4000000):
- header v2, page_size **2048** (our mkbootimg used 4096!)
- kernel @ 0x40080000 size 10139361; ramdisk @ 0x47c80000 size 787819 -
  ramdisk and tags addrs differ from our defaults
- tags_addr 0x4bc80000; appended dtb section (181267 bytes) = MTK dt-pack
  wrapper: magic d7b7ab1e 64-byte header, real FDT (d00dfeed) at +0x40;
  LK overlays it at tags_addr = the /chosen FDT the kernel receives
- cmdline `bootopt=64S3,32N2,64N2 buildvariant=user`; os_version 0x16000157
  (11.0.0, patch 2021-07); name empty; recovery_dtbo 0; header_size 1660.
  Files beside it in research/merlin-boot: stock-kernel.bin,
  stock-ramdisk.img, stock-dtb.bin (the wrapped 181267-byte section).

### boot-4 experiment kit (stock-faithful packing removes the header variables)

| file | kernel | ramdisk | built by | expectation |
| --- | --- | --- | --- | --- |
| `shim-boot-merlin-0004c.img` (11.1 MB) | stock | stock | our packer, ALL stock fields | boots MIUI exactly like flash: proves the packer |
| `shim-boot-merlin-0004e.img` (64 MB) | shim | size=0 | `tools/mkboot-edit.py` byte-patch of the stock image | red block then green block then boot4 text: proves LK accepts a patched stock image |
| `shim-boot-merlin-0004b.img` (330 KB) | shim | 512B cpio | our packer, stock fields + wrapped dtb | same as 0004e with OUR packer |

Shim changes for this round (commit fdd4151, shim/start.S + shim/shim.c):
- `start.S`: under `#ifdef MERLIN`, FIRST instructions pet toprgu
  (+0x0008 <- 0x1971) and paint a 96x48 RED proof block at the splash
  top-left (fb 0x7e605000 a8r8g8b8, stride 4320); after bss zero a GREEN
  block one band lower.  Guarded with C-preprocessor directives (cpp runs
  on .S in clang).
- `shim_main` MERLIN diag: no more full-screen con_clear (the logo stays
  behind the proof blocks + text so a dead console still leaves blocks).

### Test protocol (user, fastboot boot only - nothing flashed)

```
fastboot boot research/merlin-boot/shim-boot-merlin-0004c.img   # control: MIUI must boot
fastboot boot research/merlin-boot/shim-boot-merlin-0004e.img   # 64MB transfer, slow, image only
fastboot boot research/merlin-boot/shim-boot-merlin-0004b.img   # fails both E and B => LK won't run our binary via boot path
```
Interpretations:
- 0004c boots MIUI + red/green blocks appear in E/B => boot.img shape WAS
  the blocker: proceed with the stock-shape packing from now on.
- 0004c boots MIUI, E/B show nothing: LK won't execute our binary through
  `fastboot boot` (kernel-magic / path checks?). Next moves: run
  mkboot-edit again but keep the STOCK ramdisk_size (zeroing maybe the
  blocker), or stage the shim inside `second`/"recovery_dtbo"...
- Still nothing on any of E/B AND C fails to boot MIUI => our packer/
  header is still wrong; record what C does (bootloop? reject?).
- A red block appears then reset: report WHICH blocks (red only? red+
  green?) and the diag text if seen - that pinpoints the crash stage precisely.

## Agent handoff / active work (2026-10-20 LATEST-1: phone bootloop root-caused)

### Phone bootloop root cause: the watchdog "fix" petted the WRONG register (commit 573d0a1)

**Symptom**: `fastboot boot` of the merlin shim images kept the phone rebooting
continuously even with a do-nothing shim (research/merlin-boot 0001/0001b/0002,
built 2026-10-20 19:33-20:04).

**Root cause (proven against the stock mt6768 kernel source)**:
`wdt_pet()` wrote the RESTART key `0x1971` to RGU+0x14. Per the stock
`wdt_v2/mtk_wdt.h` (merlin_defconfig selects `CONFIG_MTK_WATCHDOG_COMMON_V2`,
skywalker toprgu @ 0x10007000), +0x14 is **WDT_SWRST** (its key is 0x1209;
with the wrong key the write is ignored), while **WDT_RESTART is RGU+0x0008**.
So the watchdog was never fed: LK hands the phone to us with the AP watchdog
armed + the box resets as soon as confirmed.

**Fix (in shim/shim.c, built + packed)**:
- `wdt_pet()` writes 0x1971 to **RGU+0x08** (correct RESTART offset), called
  from delay_ms throttled to every ~125ms.
- New `wdt_disarm()` at MERLIN shim entry: MODE read, `|0x22000000` (MODE_KEY)
  `& ~1` (clear ENABLE) - the exact disable sequence of stock
  `mtk_wdt_v2.c`. Bring-up wants hangs on-screen, not silent resets.
- diag restored into the MERLIN shim_main (the planned boot-2 screen):
  EL/SCTLR/CNTFRQ/MPIDR, **WDT MODE/LENGTH/STATUS/NONRST_REG printed BEFORE
  the disarm** (STATUS bit31 = last reset was the hw watchdog; NONRST_REG
  shows LK's bootloop-exit bookkeeping), then the full `diag_fdt()` dump
  (live DRAM banks from /memory, initrd, chosen/psci props, timer IRQs,
  cpus+MPIDRs).

**Boot-3 image (packed, ready for the phone)**:
`research/merlin-boot/shim-boot-merlin-0003.img` - 159744 bytes, shim
`out/Image` (merlin diag build, min main removed), empty 512B ramdisk, no
dtb, name `merlin-shim-3`, cmdline `console=null merlin.shim-3`. Verified
the packed strings + the disassembly (`str 0x1971 -> [RGU+0x8]`, the MODE
key/clear-enable sequence, throttled pet in the spin loop).

**Next step (user, destructive-free `fastboot boot` only - nothing flashed)**:
```
fastboot boot research/merlin-boot/shim-boot-merlin-0003.img
```
Read the screen: it must now STAY UP (no reset). The `MEMBASE/MEMSIZE`
lines are the live DRAM banks LK patched in - they fix mkadt.py's
PHONE_PHYS_BASE/PHONE_MEM_SIZE (currently 0xb0000000/0x10000000
provisional). cpus lines say the real MPIDR shape; timer IRQ lines the
vtimer INTID. Then rebuild the phone payload with corrected ADT and boot
it as the NEXT image (payload in the ramdisk + MERLIN loader not wired
into shim_main yet - that wiring is the step after the live facts land).

**Unresolved hygiene** (answered 2026-10-20 by the user): unsure whether
anything was ever flashed - the phone may not even have been used with
these images yet. Keep `fastboot boot` only when it happens; if a flash
turns out to have happened, first restore via the stock ROM tgz
(`merlin_global_images_...tgz` on disk holds boot.img of
V12.5.1.0.RJOMIXM) or recovery before more tests. The 0-byte
`stock-boot-backup.img` is an artifact of an interrupted backup attempt.

## Agent handoff / active work (2026-10-20, QEMU parity)

### QEMU boots to userspace; the "SWEET EARLY 20 stall" was never a kernel stall (2026-10-20)

**Result**: `xnu/out-0001/merlin-payload.bin` (kernel.development.sweet from artifact
12146286873, head 347e190, + regenerated merlin-q.adt + merlin-init ramdisk) boots in
QEMU *(research/qemu-win/qemu-system-aarch64.exe, Windows side)* **exactly like the
sweet reference to userspace**: full kernel_bootstrap, IOKit platform expert / CPU /
AppleCLCD / HID / battery, Skywalk + bsd_autoconf, `BSD root: md0`,
`load_init_program: attempting to load /sbin/launchd`,
`*** MERLIN userspace: init running as PID 1 ***` with alive ticks
(evidence `research/abtest/fullfix60`, untouched control `research/abtest/sweetref60`).

**Both phantom symptoms explained - two building/consumer bugs, not kernel bugs:**

1. *Console freeze at "SWEET EARLY 20" (what looked like a stall).* The payload had
   been built with an explicit `--cmdline 'debug=0xc'`, overriding mkpayload's default
   (`... serial=3 ...`). Without `serial=3` (SERIALMODE_OUTPUT off), after stage 20
   (`if (serial_exists) sweet_early_disable();` in arm_init, patch 0012) every kprintf
   goes through the pe_serial console chain (patch 0003: sweet-fbcon renderer) which
   never transmits when serial output is off => the fb shows the stage-20 line forever.
   serial.txt stays empty (not a UART issue); the ADT `sweet-fbcon` node is fine and
   identical to sweet's (prop-level diff `research/adtdiff2.py`). The stages 1-19 lines
   get wiped by fbcon_init's full clear, so the frozen screen looks "empty except 20".
2. *Real halt right after "ATM subsystem is initialized" (masked by 1).* My
   2026-10-20 rebuilds used the STALE `xnu/out-0001/merlin-q.adt` (timestamp 10/19
   17:46, i.e. generated BEFORE the mkadt.py cpu-compatible fix at 19:17). cpu0
   `compatible` must be `qcom,kryo470|ARM,v8` for the SweetCPU personality (patch
   0018); with the stale ADT the CPU-register cascade never runs (no
   `[0]ml_processor_register>` / `SWEET CPU:` rows, which the sweet control prints
   right after "platform expert registered", before the BSD copyright) and boot stops
   after ATM forever (60 s and 120 s identical). FIX: regenerate
   `xnu/out-0001/merlin-q.adt` with the fixed mkadt.py. That fix IS in mkadt.py - the
   failure mode was only using the stale copy. `research/abtest/merlin-q.adt`
   (10/19 19:17:26) was already fixed; out-0001 was not.

**Payload recipe (verified)**:
```
python tools/mkpayload.py xnu/out-0001/kernel.development.sweet xnu/out-0001/merlin-q.adt \
    xnu/out-0001/merlin-payload.bin --ramdisk xnu/out-0001/merlin-init \
    --cmdline 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=md0'
python tools/qemu-merlin.py xnu/out-0001/merlin-payload.bin research/abtest/OUT \
    --secs 60 --kernel xnu/out-0001/kernel.development.sweet
```
Geometry: 11 segments (kernel 10 + merlin-init), ramdisk @0xb24c8000 size 0x8000,
kernel_end 0x84d0000, entry 0x148b488, phys 0xb0000000, size 16.62 MB. The 2026-10-18/19
hands note that said "cmdline debug=0xc" below is stale for the payload which now
contains the full sweet-parity cmdline baked in (the shim contract is unchanged;
SWEETXNU v1).

**gdb-RSP walk forensics (proven method)**: `tools/qemu-merlin.py --gdb` starts QEMU
stopped with a stub on tcp::1234. A single-process RSP client (Windows temp
gdbwalk.py; qemu spawned in-thread via runpy; attach => `qSupported`, `Z0` symbolic
breakpoint list, `vCont;c`; log pc/x0/x1/lr/sp per stop; **`vCont;s` step-over after
every breakpoint hit - QEMU re-stops forever on resume if PC==bp**; end with Ctrl-C +
`k`). Walk of the fixed payload: every arm_init-tail breakpoint hit in vanilla order
(PE_init_platform FALSE->TRUE, ml_map_cpu_pio, cpu_timebase_init, PE_init_cpu,
fiq_context_init, machine_startup, kernel_bootstrap, kernel_bootstrap_thread), then
SweetCPU::start -> ml_processor_register -> cpu_machine_init (lr=_cpu_start+0x74),
IOWorkLoop::threadMain / IOService arbitration churn, then sched timeshare
maintenance ticks with the CPU parked at cpu_idle = healthy idle, NO stall. Kernel
side was always fine; only the console formatting hid it.

**ADT prop-level diff** (research/adtdiff2.py, merlin-q.adt vs sweet-q.adt): identity
bits only (phandles, random-seed, firmware-version 'merlin-shim', unique-chip-id
'MERLIN', cpu clock/memory-frequency, /arm-io compatible 'merlin-io', extra
panel-width/height on the display node). Nothing functional. The `/device-tree/sweet-fbcon`
node (reg 0x9c000000, 1080x2400, stride 4320) is identical in both.

**Next steps (ordered), updated 2026-10-20**
1. Phone payload: `mkadt.py --phone` regenerates the merlin panel ADT; same
   compatible fix applies (single mkadt.py source). Rebuild the phone payload with
   the cmdline above (phone fb = ABL splash @0x7e605000 1080x2340) and `fastboot boot`
   the rebuilt shim image; the fb now mirrors the QEMU console instead of freezing
   at stage 20.
2. Exercise SMP: generate the 8-cpu ADT shape (mkadt cpus loop per mt6768 topology;
   patch 0078 exists on the sweet side) and validate QEMU with `cpus=8`.
3. MERLIN machine config patch (0004-style), boot.img v2 packing for merlin (kernel
   loading address per stock boot header), shim console tweaks if needed.
4. MSDC0 eMMC driver, root on userdata, iOS root/launchd - same plan as the list
   below (keep those notes).

## Agent handoff / active work (2026-10-18, prior)

### Initial port scaffold created (2026-10-18/19) - READ FIRST

**Project**: `D:/things/Merlin/ios-merlin` (cloned from `D:/things/Merlin/ios-sweet`,
origin currently points at the local path; do not push anywhere without the
user - they chose "local only for now").

**What was built:**
- `tools/mkadt.py` - merlin ADT generator (`mkadt.py OUT.adt` = QEMU twin,
  `--phone` = merlin MMIO). Identity: `xiaomi,merlin` + `xiaomi,sweet` + 
  `mediatek,mt6768` up front, `D22AP`/`iPhone10,3` model strings (iPhone X
  userland compatibility, same trick as sweet). `/product` from
  `research/ipsw-x/d22ap.adt` when present (currently missing, fine).
- `tools/qemu-merlin.py` + `tools/merlin-init.S` + `tools/mkinit.py`
  (unchanged tooling) + `tools/merlin-qemu-test.sh` (end-to-end runner) +
  `tools/dtb-facts.py` (stock-DTB fact extractor) + `tools/env-ubuntu.sh`
  (one-time WSL install) + `tools/fetch-kernel-artifact.py`.
- Payload built OK: `xnu/out-0001/merlin-payload.bin` (16.6 MB) from
  `xnu/out-0001/kernel.development.sweet` + `merlin-q.adt` +
  `merlin-init` ramdisk @0xb24c8000, cmdline
  `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=md0`.

**Kernel in use**: artifact `12146286873` (xnu-kernel, dipa-studio/ios-sweet,
created 2026-10-18T18:32:43Z, repo head `347e190` = the xnu-0079 build),
xnu-8796.141.3 / Darwin 22.6.0. Downloaded with Windows-side curl +
git-credential PAT (WSL git has no GCM helper; the Linux `git credential
fill` prompts forever - set GIT_TERMINAL_PROMPT=0 in tools/fetch-kernel-artifact.py
which then fails fast, or run the curl one-liner documented in its docstring).
Staged at `xnu/out-0001/` (gitignored).

**BLOCKER / next action**: QEMU is NOT yet installed in WSL Ubuntu 26.04.
The user must run (interactive sudo):
    sudo bash /mnt/d/things/Merlin/ios-merlin/tools/env-ubuntu.sh
Then: `cd /mnt/d/things/Merlin/ios-merlin && bash tools/merlin-qemu-test.sh`
and update these notes with the actual boot result. The QEMU twin uses the
sweet-tuned phys band (0xb0000000/0x4d000000) and console plane
(0x9c000000, 1080x2400) so the semantics are identical to the proven
ios-sweet QEMU boots; cpu default cortex-a75.

### Hardware facts (sources)

From `android_kernel_xiaomi_mt6768/arch/arm64/boot/dts/mediatek/mt6768.dts`:
- GIC: `compatible = "arm,gic-v3"` (line 382), GICD 0x0c000000 (0x40000),
  GICR 0x0c040000 declared region 0x200000; separate `gic500` node with
  `gic_cpu` @ 0x0c400000 (0x40000) - live GICR stride/PE size to verify on
  device (8 PEs assumed: 8 * 0x40000 = 0x200000).
- `intpol-controller@0` (mediatek,mt6577-sysirq) @ 0x0c53a650 (0x50) - IRQ
  polarity shim; reserved for later MTK-only IRQ plumbing.
- arch timer: interrupts = <PP13 s>, <PP14 ns>, <PP11 virt>, <PP10 hyp>
  (STANDARD numbering -> vt INTID **27**, unlike Qualcomm's 19),
  clock-frequency = 13 MHz.
- eMMC: MSDC0 @ 0x11cb0000 (driver does not exist yet; no ADT node emitted).

From `merlin.dts` (`&chosen` atags from LK):
- display: `atag,videolfb-fb_base_l = <0x7e605000>`, vram 0x017e8000,
  lcmname `hx83112b_fhdp_dsi_cmd_auo_rt5081_drv`, fps 6000/100=60,
  panel 1080x2340.
- touch: novatek nvt-ts over SPI0 (focaltech fts also referenced).

From the stock boot DTB (`merlin_extracted.dtb`, FDT v17, via tools/dtb-facts.py):
- `/memory` = 0x40000000 + 0x3e605000 - bundled placeholder; LK patches the
  real DRAM at boot (no mem= in bootargs). TREAT DRAM SIZE/TOPOLOGY AS
  UNKNOWN until the live FDT is read on device (shim-0 diag screens will).
- bootargs: `console=tty0 console=ttyS0,921600n1 root=/dev/ram vmalloc=400M
  ...` - there IS a 921600n1 UART console configured; hopefully live ("UART
  test points" on redmi boards).
- 8 cpus: reg 0x000..0x700 sequential (not cluster-per-bank!). cores 0-5 =
  cortex-a55 @0x65633340, cores 6-7 = cortex-a75 @0x8166d4c0. cpu-map
  clusters: cpu@000-003=cluster0, cpu@100-103=cluster1. enable-method=psci.
- `/psci`: `arm,psci-1.0`, method=smc (CPU_ON path same as sweet).
- reserved-memory: consys/sspm/scp/ion/wifi/soter(TEE)/mobicore carve-outs
  with alloc-ranges in the low bank (0x40000000..0x80000000), zmc big CMA +
  ion from 0xc0000000 upward.
- Provisional phone ADT constants (PHONE_PHYS_BASE/PHONE_MEM_SIZE =
  0xb0000000/0x33000000) must be validated against the live LK FDT at the
  first phone boot - mkpayload takes them from the ADT, so fixing = edit
  mkadt.py only.

### Decisions
- Keep `MACHINE_CONFIG=SWEET` for now: the 79-patch series back-references
  the SWEET machine config files (config/MASTER.arm64.sweet etc.); renaming
  now is churn with no function. The MERLIN config lands together with the
  first MTK driver notes (GICR stride, timer, powers).
- Keep the `SWEETXNU` v1 payload magic + header: binary compatibility with
  the ios-sweet shim toolchain (unpack_bootv2 checks etc.).
- QEMU FB stays 1080x2400 @0x9c000000 (sweet twin); phone FB = merlin panel
  (1080x2340 @0x7e605000) only in the phone ADT.
- Kernel CCTFRQ: time-base frequency 13 MHz goes into the merlin ADT
  (`timebase-frequency`), matching MT6768 (Qualcomm was 19.2 MHz).

### Environment (this Windows box)
- WSL Ubuntu 26.04 (user gycioc): python3.14, clang, llvm-nm OK; qemu-system-aarch64,
  aarch64-linux-gnu-gcc, cpio MISSING -> tools/env-ubuntu.sh (sudo needed;
  sudo prompts for password - agent cannot supply it).
- Windows: git 2.x + GCM (PAT for github.com works from Windows side);
  no gh CLI, no adb/fastboot yet (add when phone milestone starts).
- ios-sweet repo here is a fresh clone without research/xnu-out dirs; the
  2026-10-15..18 session artifacts live on the user's other (Linux) machine.

### Next steps (ordered)
1. Run env-ubuntu.sh (user) -> run merlin-qemu-test.sh -> record fb.txt here.
2. If boot lives: iterate QEMU with cpus=8 ADT (8-core MPIDR 0x000..0x700)
   to pre-validate the merlin SMP shape without touching hardware.
3. MERLIN machine config patch (0004-style) + first MTK shim branch:
   boot.img v2 packing for merlin (kernel@0x40080000 etc. per merlin DTB
   boot header), shim console on the lk splash FB (RGB888? verify from the
   live atags left in the shim's own FDT dump screen).
4. First phone boot: fastboot boot shim-boot-merlin.img (nothing flashed);
   read live FDT memory/GIC/FB facts from the shim diagnostics; fix the
   phone ADT constants; repeat QEMU with phone-realistic values.
5. MSDC0 eMMC driver, then root on userdata, then iOS root/launchd.)
