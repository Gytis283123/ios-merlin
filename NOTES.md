# iOS 16 on merlin (Redmi Note 9, MT6768 / Helio G85) - working notes

## Agent handoff / active work (2026-10-23 LATEST-22: 0079+0082 KERNEL + LOCAL CONSOLE, rd=msdcroot0 IMAGE READY)

- Branch **msdc-0079** (347e190 = upstream 0079 + 0082 only) built
  successfully in CI: run 39991300459, artifact 12519256732
  (`xnu/out-0079/kernel.development.sweet`, SHA256 65c85ab7...8507b).
  The main-branch hang at `SWEET CPU: 1/1 CPUs initialized` was the
  0080/0081 upstream patches, so the test uses this base.
- The driver is linked in: `_merlin_msdc_rootdev`, `_merlin_msdc_*`,
  `msdcroot0`/`rmsdcroot0`, `MERLIN MSDC:` log strings.
- fbcon in this kernel moved by -0x120: `_fbcon_init` 0xfffffe0007a7bae4
  (0xc4) / `_fbcon_transmit_data` 0xfffffe0007a7bbb0 (0x3e4) - same func
  sizes and the same __DATA globals/`_iso_font`, so only the two link
  addresses changed in `tools/fbcon-1x.ld` and `tools/patch-fbcon1x.py`;
  blobs relinked and re-applied (objdump confirms the 8x16 prologue).
  Patched kernel `kernel.development.sweet.merlinfb`, SHA256 1bf2400c...1f9d7.
- Payload `xnu/out-0079/merlin-phone-msdc-payload-fb1x.bin` (same ADT
  `xnu/out-0001/merlin-phone-msdc.adt`, cmdline `debug=0xc serial=3
  cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=msdcroot0`),
  packed with the proven stock header + `research/merlin-boot/msdc-blob.bin`
  shim into **`research/merlin-boot/shim-boot-merlin-msdc-fb1x-0079.img`**
  (16,989,139 B).  ADT verified: `/merlin-msdc` reg 0x11230000/0x10000,
  `sweet-fbcon` base 0x7e605438.
- NEXT: `fastboot boot` that image and read `MERLIN MSDC: cfg ... ps ...
  sts ...` plus the GPT/partition log.  Android userdata holds no HFS, so
  an HFS mount failure is expected; the point is the read path + GPT scan.
  Then build the HFS+ root image from the IPSW dmgs and flash userdata
  (destructive - ask first).

## Agent handoff / active work (2026-10-23 LATEST-21: DRIVER BUILT; MAIN KERNEL HANGS, 0079 BASE REBUILD)

- The 0082 driver compiled in CI (run 39988046415, success; kernel
  xnu/out-0082, SHA256 79967397...177a) and is present
  (`_merlin_msdc_rootdev`, `/merlin-msdc` strings).  CI had failed once
  first on name collisions with sweet_ufs.c (static `dma_sync`, macros
  `BOUNCE_SIZE`/`CMD_TIMEOUT_NS`, stale `R1_ERRORS`); all renamed
  (`msdc_dma_sync`, `MSDC_*`).  The driver is appended to
  `bsd/dev/sweet_ufs.c` because dxb's `bsd/conf/files` context differs.
- **The latest-main kernel (0080 net-trace + 0081 USB link) hangs at
  `SWEET CPU: 1/1 CPUs initialized, 3011 verified`** on the phone with
  `rd=msdcroot0`, before IOKitBSDInit - the driver never runs.  The
  0079-era kernel booted to userspace, so the regression is in the new
  upstream patches, not the driver.
- Rebuild: branch **msdc-0079** = 347e190 (0079) + 0082 only, pushed to
  the fork; workflow_dispatch run 39991300459 builds it.  The plan is to
  use this kernel for the driver test, re-resolve the fbcon symbols and
  re-apply the 1x/scroll patch (tools/fbcon-1x.ld, patch-fbcon1x.py),
  then build `rd=msdcroot0` and read the driver log.

## Agent handoff / active work (2026-10-23 LATEST-20: MERLIN eMMC (MSDC0) ROOT DRIVER PATCHED)

- Goal: iOS 16.7 userland.  The sweet port's recipe (its NOTES) is an
  **HFS+ root image on userdata** plus a read-only block driver and
  `rd=ufsroot0`; APFS is not needed (the kernel has HFS/bindfs/nullfs,
  no APFS kext), and the IPSW build (20H392 / 16.7.16) is the same one
  sweet ran.  Merlin's gap is storage: eMMC, not UFS.
- New **`xnu/patches/0082-merlin-msdc-root.patch`** (copied to
  ios-sweet/xnu/patches, needs a CI build):
  - `bsd/dev/merlin_msdc.c`: read-only block device for the ABL/MSDC0
    controller.  Polled CMD17 (512-byte, R1) reads from the user area,
    basic DMA (64 KiB physically-contiguous bounce, 64-byte burst),
    GPT scan for `msdcroot=` (default "userdata"), exposes
    `/dev/msdcroot0` + `/dev/rmsdcroot0`, `rd=msdcroot0` hook in
    `IOKitBSDInit.cpp`.  The CI compiles it by appending the code to
    `bsd/dev/sweet_ufs.c` (the dxb `bsd/conf/files` context differs from
    upstream, so a new build-file entry does not apply).
  - Register map and command/DMA sequence taken from the stock ComboA
    driver (`drivers/mmc/host/mediatek/ComboA/{msdc_reg.h,sd.c}`):
    MSDC_CFG 0x00, SDC_CFG 0x30, SDC_CMD 0x34 (opcode/R1/512<<16/
    dtype 1<<11), SDC_ARG 0x38, SDC_STS 0x3c, SDC_RESP0 0x40,
    DMA_SA(_HIGH)/LEN/CTRL 0x90/0x8c/0xa8/0x98, INT bits 8..23.
  - Reuses the bootloader's controller state: no reset, no clock/bus
    width/tuning changes; if the bootloader gated the clock the driver
    logs `MERLIN MSDC: cfg ...` and fails cleanly.
  - Known risks for the first hardware test: eMMC native block size
    (assumed 512), any inline encryption, and LK leaving the MSDC clock
    off.  The driver prints cfg/ps/sts before touching anything.
- `tools/mkadt.py`: MSDC0 corrected to **0x11230000** (mt6768.dts
  `msdc@11230000`, IRQ SPI 100), `/merlin-msdc` node emitted for the real
  phone, and the phone `sweet-fbcon` base now includes the +1080-byte
  (270 px) scanout offset (LATEST-19).  `--qemu-gic`/`--qemu` unchanged.
- Patch numbering: the upstream main already has 0080 (net trace) and
  0081 (USB link), so this is **0082**.  Pushed to the fork
  Gytis283123/ios-sweet main (the dipa-studio repo rejects this account).
  CI history: run 39981655627 **skipped 0082** (`patch failed:
  bsd/conf/files:104` - dxb source context differs), hence the
  sweet_ufs.c append.  The first compile of the append (run 39986075173)
  failed on **name collisions with sweet_ufs.c**: static `dma_sync`,
  macros `BOUNCE_SIZE`/`CMD_TIMEOUT_NS`, plus a leftover `R1_ERRORS`.
  Renamed to `msdc_dma_sync`/`MSDC_BOUNCE_SIZE`/`MSDC_*_TIMEOUT_NS` and
  fixed the R1 check; run 39988046415 rebuilds.  If the macOS queue
  keeps failing, the fallback is the dipa-studio account.
- NEXT: push 0080 to ios-sweet so CI builds the kernel (no macOS here;
  user approval needed), then build the HFS+ root image from the IPSW
  dmgs (`tools/mkiosroot.sh`), flash it to userdata (22.8 GiB partition;
  destructive - ask), and boot `rd=msdcroot0`.  After the new kernel:
  either re-apply the fbcon 1x/scroll binary patch (symbol addresses
  move) or set FBCON_SCALE=1 + scrolling in patch 0003 at the source.

## Agent handoff / active work (2026-10-23 LATEST-19: PANEL SCANOUT OFFSET FOUND - CONSOLE ALIGNED + SCROLLS)

- The "two column / misaligned log" was a **panel scanout offset**, not a
  font or stride problem.  A quadrant probe (research/merlin-boot/
  geomprobe.S, packed as shim-boot-merlin-geomprobe.img) painted
  TL red / TR green / BL blue / BR yellow plus a white cross: the phone
  showed red-blue bands at BOTH left and right edges with green-yellow
  in the middle.  That means each display row starts **270 px (1080 bytes)
  into the framebuffer row** and reads 1080 px, crossing into the next
  row: the console's line head wraps to the screen's right, the tail
  stays left.  Evidence matches the old "same lines twice, horizontally
  offset" note from the shim days.
- Probe iterations (all buggy/explanatory, kept for the record):
  first probe had x/y swapped on 3 blocks; fixed corner probe showed the
  right-edge blocks missing; the quadrant probe made the offset obvious.
- Fix: the kernel fbcon's framebuffer base (ADT `sweet-fbcon` `reg[0]`)
  is shifted by +1080 bytes (0x7e605000 -> **0x7e605438**).  Console rows
  then start exactly at the scanout window.  reg size 0x9a3f80 is kept;
  writes stay inside vram.
- The console also **scrolls now** instead of ring-wrapping: the fbcon
  1x replacement's newline, when at the last row, memmoves the text area
  up by one 16-px row (16 MB/s-ish only when sitting at the bottom) and
  clears the last row, so new logs keep appearing at the bottom.
  QEMU 110 s run: log scrolled, newest `MERLIN init: still alive` lines
  at the bottom.
- **`research/merlin-boot/shim-boot-merlin-0022-scroll.img`**
  (17,004,544 B, sha256 c879d786...f39e, flashed 2026-10-23) =
  0019 + fbcon scrolling + ADT base shift.  0021 is the same base shift
  without scrolling.  The probe image is temporary.
- Remaining: the *shim/loader* pages still write at 0x7e605000, so they
  are still offset on the panel; rebuild the shim with FB_BASE
  0x7e605438 (and keep the boot_args Video block consistent) to align
  them too.  mkadt.py should also emit the shifted base for `--phone`
  once the hardware result is confirmed.

## Agent handoff / active work (2026-10-23 LATEST-18: PHONE BOOTS XNU TO USERSPACE - PANIC GONE)

- **0019 result on hardware (photo 2026-10-23-17-21-45-036.jpg, rotated
  90 deg): the phone boots our XNU all the way to userspace.** Visible
  console lines:
  `load /sbin/launchd`, `*** MERLIN userspace: init running as PID 1 ***`,
  `MERLIN init: still alive` (repeating), plus the kernel_bootstrap
  zone/IOKit log above it.  No Apple panic.  The GICR fix is confirmed
  on real MT6768 silicon, and the 8x16 console makes the log readable.
- This closes the panic: the phone XNU died in `_pe_init_fiq`'s GICR
  TYPER scan because the ADT put the redistributor at 0x0c400000; the
  hardware/Linux GICR is 0x0c040000 (LATEST-16).  0019 = GICR fix +
  fbcon 1x (LATEST-17), flashed to boot on 2026-10-23.
- Note on reading phone photos: the framebuffer is portrait 1080x2340;
  a landscape-held phone needs a 90 deg rotation before OCR/reading.
- Next: MSDC0 eMMC driver + root on userdata (merlin-init is served as
  /sbin/launchd by mockfs from the ramdisk and is PID 1; a real rootfs
  needs storage).  Also pending: SMP (cpus=8 shape), restoring d22ap.adt
  for /product before regenerating the ADT.

## Agent handoff / active work (2026-10-23 LATEST-17: PANIC CONSOLE DOWN TO 8x16 CELLS + 0019)

- The phone panic screen was unreadable: the CI kernel's sweet-fbcon is
  compiled with **FBCON_SCALE=2** (16x32 px cells).  On the 1080-wide
  panel that means 67 columns - panic lines wrap mid-value and only the
  left ~1072 px are used.  Live fbcon vars in QEMU confirmed it
  (width 1080, cols 0x43, rows 0x49).
- Fix (binary patch of the CI kernel, no rebuild needed):
  `tools/fbcon-1x.S` + `tools/fbcon-1x.ld` assemble drop-in 8x16-cell
  replacements for `_fbcon_init` (0xfffffe0007a7aea4, 0xc4 B) and
  `_fbcon_transmit_data` (0xfffffe0007a7af70, 0x3e4 B); every global
  keeps its address (fbcon_* in __BOOTDATA 0x8074150.., iso_font
  0x7b5fec0).  `tools/patch-fbcon1x.py IN OUT` writes them into a
  kernel Mach-O (pad with NOPs).
  - cells 16x32 -> 8x16, cols = width/8, rows = height/16
  - row pitch 32 -> 16 px, x advance 16 -> 8 px, 1x glyph blit
  - wrap path renders the character after the implicit newline
  - init/newline save x30 (they call clear_row); the char is saved at
    [sp,#16] because [sp,#8] holds the saved LR
- Validation in qemu-shim (phone plane 0x7e605000, 1080x2340):
  fbcon vars read width 0x438, **cols 0x87 (135), rows 0x92 (146)**;
  the panic text now fits; hybrid ADT (QEMU GIC) boots the fb1x kernel
  all the way to IOKit (`SWEET FB: AppleCLCD 1080x2340 ... presented
  as 1125x2436`) - no regression.
- Built `xnu/out-0001/kernel.development.sweet.merlinfb.fb1x` and
  `xnu/out-0001/merlin-phone-payload-fb1x.bin` (same 16,627,424 B
  layout), then **`research/merlin-boot/shim-boot-merlin-0019-fbcon1x.img`**
  (17,004,544 B, sha256 2d39c34a...cc503).  It is 0018 + the fbcon
  patch only (diff confined to the two function regions); flashed to
  boot and rebooted on 2026-10-23.
- Still open: the phone panic itself.  0019 contains the 0018 GICR fix;
  the smaller console is there so the panic text can be read.  Need the
  phone screen's panic string / pc / FAR to know whether the GICR fix
  worked or where it now dies.
- Source note: `xnu/patches/0003-sweet-framebuffer-serial-console.patch`
  still says FBCON_SCALE 2 (that is what the CI artifact was built
  from).  If the kernel is rebuilt, either set it to 1 there or re-run
  tools/patch-fbcon1x.py on the new artifact.

## Agent handoff / active work (2026-10-23 LATEST-16: PHONE XNU PANIC ROOT-CAUSED - WRONG GICR BASE IN ADT)

- **Symptom**: on the phone the Apple XNU panics instead of continuing past
  interrupt init.  Root cause found in the ADT, not in the loader/payload:
  `mkadt.py --phone` declared the GIC redistributor at **0x0c400000**, taken
  from the `gic_cpu@0c400000` node of mt6768.dts.  That node is vendor
  leftover - no driver in the stock tree references `mediatek,gic_cpu`
  (checked drivers/irqchip); the node Linux actually runs on is
  `interrupt-controller` with `reg = <0x0c000000 0x40000>,
  <0x0c040000 0x200000>, <0x0c53a650 0x50>` and the gic-v3 driver maps
  reg[1] as the redistributor.  Every MTK GICv3 DTS in the tree
  (mt6768/6781/6785/6833/6853/6873/6877/6885/6893) uses 0x0c040000.
- XNU must therefore map the GICR at **0x0c040000** (SOC-relative in the
  ADT: 0x0b040000).  With 0x0c400000 it maps an address that is not a
  redistributor; the first TYPER read faults/returns garbage and
  `_pe_init_fiq` panics.
- Proof from QEMU (phone ADT, real GIC): the phone payload runs the shim
  to `xnu entry` and dies at exactly one instruction -
  `_pe_init_fiq` (0xfffffe0007a78de0) `ldr x13,[gicr_va+8]`, the GICR
  TYPER scan (0x20000 stride).  Note: ml_io_map hands out IO VAs
  independent of the phys argument, so the faulting VA looks identical
  before/after the fix and QEMU cannot distinguish the two GICR phys
  (both unmapped on virt); the ADT the kernel receives was dumped from
  0x824d0000 and shows the corrected reg, so the fix does reach XNU.
- Fixes applied:
  - `tools/mkadt.py`: GICR 0x0c400000 -> 0x0c040000 (+ comment/header
    correction).  Do NOT regenerate `merlin-phone.adt` from scratch yet
    (d22ap.adt still missing -> no /product).
  - `xnu/out-0001/merlin-phone.adt` patched in place (one u64, keeps the
    9,828-byte ADT with /product).
  - `xnu/out-0001/merlin-phone-payload.bin` rebuilt
    (kernel.development.sweet.merlinfb, same cmdline); byte-identical to
    the old payload except offset 0xfdb2f2 (0x40 -> 0x04).
- **New image: `research/merlin-boot/shim-boot-merlin-0018-gic.img`**
  (17,004,544 B).  Same as 0017 (loader/reloc 0017, shim/out/Image
  159,744, kernel blob 190,674, stock dtb) and differs from it by exactly
  one byte at image offset 0x100aaf2 (0x40 -> 0x04).  This is the image
  to flash for the next phone attempt; 0017 keeps the wrong GICR.
- Phone result still unconfirmed: the user's panic photo/text has not
  been seen.  If 0018 still panics, photograph the Apple panic text
  (panic string + PC) - if it is past `_pe_init_fiq`, the next suspects
  are the MTK GICR frame stride (0x40000 vs the 0x20000 the scan
  assumes), GICD security/DS, and PPI 27 timer wiring.

## Agent handoff / active work (2026-10-21 LATEST-15: PHONE PAYLOAD VALIDATED ON QEMU + GUI)

- **QEMU GUI preview works.** `shim/ramfb.c` publishes the shim framebuffer
  to QEMU's `ramfb` device via fw_cfg (`etc/ramfb`, 28-byte big-endian
  XR24 struct, written through the DMA interface - the byte port would
  arrive as 28 one-byte callbacks and ramfb ignores those).  `tools/
  qemu-shim.py --gui` = `-device ramfb -display gtk,zoom-to-fit=on`, so
  the window shows the real guest framebuffer live.  The harness also
  saves QEMU's own `screendump` as `screen.ppm` (proof of what the window
  shows).  `ramfb_init()` is called only in the `SHIM_QEMU` path.
- **Phone-plane shim:** `FB=0x7e605000 FB_H=2340 OUT=out-qemu-phone bash
  shim/build-qemu.sh` builds the same shim on the phone's LK splash
  plane/geometry (`shim/out-qemu-phone/Image`, 159,744 B).  `console.h`
  now takes `SHIM_FB_BASE/W/H` overrides, so boot_args Video == the phone
  ADT's sweet-fbcon node (0x7E605000, 1080x2340).
- **Hybrid ADT for QEMU:** `mkadt.py OUT --phone --qemu-gic` keeps the
  phone RAM band + panel but uses QEMU's GIC/timebase/CPU tree (the phone
  GIC 0x0C400000 is unmapped on virt).  Payload:
  `xnu/out-0001/merlin-phone-qemu-payload.bin` (16,621,872 B, phys
  0x80000000, mem 0x4D000000, entry_pa 0x8148B488, ADT 4,336 B).
  With `shim/out-qemu-phone/Image` it boots **the exact phone memory
  band/panel** to userspace: `*** MERLIN userspace: init running as PID
  1 ***`, 72 fb lines (the console is at 0x7E605000, not 0x9C000000 -
  dump with `--fb 0x7e605000 --fb-geom 1080x2340`).  Loader: SRCWORD
  14000719, WORD0/1 14000719 D503201F, WRTEST ok, MEMOK 0x000FFFFF.
- So the phone payload itself is sound.  The only unvalidated parts of
  the 0015/0016 image are (a) the real MT6768 GIC and (b) whether
  0x80000000 accepts writes/retains them on the phone.  The QEMU MEMOK
  pass is *not* hardware evidence: QEMU RAM is uniform.
- **New loader hold (0016):** before the jump, if the destination entry
  word != the source entry word (i.e. the copy never reached DRAM - the
  0xB0000000 failure), the loader does NOT jump.  It paints a big-font
  blue page `HOLD=destination not writable` + PHYS/ENTRY/WANT/GOT/MEMOK
  and WFI's, so one photo names the bad base and the writable map.
  `research/merlin-boot/shim-boot-merlin-0016-hold.img` (17,002,496 B,
  page 2048, kernel 0x40080000, ramdisk 0x47c80000, dtb 0x4bc80000) is
  packed and verified: same payload (SWEETXNU, phys 0x80000000, msz
  0x4D000000, entry 0x8148B488), kernel blob 189,858 B.
- **Base probing + relocation (0017):** `choose_base()` probes the
  declared base plus 0x90000000/0xA0000000/0x80000000/0xB0000000 at four
  points (base, entry, kernel middle, ADT landing) with write/read/
  restore.  The first that holds is used: segments are copied there, the
  copied ADT's /chosen/dram-base is rewritten (two 4-byte stores - the
  value is only 4-byte aligned) and boot_args.physBase follows.  Tested
  in QEMU with `-DSHIM_RELOC_TEST=0x90000000` (payload still declares
  0x80000000): boots from 0x90000000 to userspace, and the ADT dumped
  from 0x924D0000 reads `dram-base = 0x90000000`.  Normal runs (declared
  base good) are unchanged.  **Flash `shim-boot-merlin-0017-reloc.img`**
  (17,004,544 B, same payload/ADT 9,880 B with /product); 0016 has only
  the hold screen.
- **Do not regenerate `merlin-phone.adt` right now:** `research/ipsw-x/
  d22ap.adt` is missing on this box, so mkadt now emits a 4,284-byte ADT
  without `/product`; the existing `merlin-phone-payload.bin` embeds the
  9,880-byte ADT *with* `/product` (kept from the earlier build).  Pack
  new images from that payload, or restore d22ap.adt first.
- Phone testing is still paused by the user; 0016 is built, not flashed.

## Agent handoff / active work (2026-10-21 LATEST-14: QEMU RIG + XNU IS NOT BASE-LOCKED)

- New test rig: `tools/qemu-shim.py` boots the *real* shim
  (`shim/build-qemu.sh` -> `shim/out-qemu/Image`, `-DSHIM_QEMU`) on
  QEMU virt, 4G RAM, with a generated FDT; dumps `fb.png`/`fb.txt`/
  `bb.txt`/`regs.txt`/`qemu.log`.  Full chain proven: shim -> XNU ->
  userspace (`*** MERLIN userspace: init running as PID 1 ***`).
- `--fb ADDR --fb-geom WxH` dumps the *kernel's* framebuffer (the
  phone payload writes 0x7E605000, not the QEMU shim's 0x9C000000).
- **XNU is not tied to physBase 0xB0000000.**  0xB8/0x80/0x4D all
  looked base-locked only because memSize was 0x10000000.  The real
  rule: arm_vm_init sizes the bootstrap tables from
  `physmap_base + memSize` (physmap_base = phystokv(topOfKernelData)),
  so the 0xFFFFFE000B700000 IO/FB window is covered only when
  `physBase + memSize >= ~0xC40E4000`.  Failure is
  `_pmap_map_bd.cold.1` (line 1885) with x19=0xFFFFFE000C000000.
  - 0xB0000000 + 0x10000000 (top 0xC0000000): panic.
  - 0x80000000 + 0x1C000000 (top 0x9C000000): panic.
  - 0xA0000000 + 0x30000000 (top 0xD0000000): boots into IOKit.
  - 0xA0000000 + 0x4D000000 (top 0xED000000): **userspace**.
- Phone payload moved: `mkadt.py --phone` now defaults to
  phys 0x80000000 / mem 0x4D000000 (top 0xCD000000, clear of the LK
  splash FB which ends ~0x7FDED000).  Rebuilt payload 16,627,424 B,
  entry_pa 0x8148B488; through the QEMU shim it boots XNU to
  `pe_arm_init_interrupts` and stops at the expected phone-GIC data
  abort (0x0C400000 is not mapped in QEMU) - same stopping point as
  the old 0xB0000000 payload.
- Boot image `research/merlin-boot/shim-boot-merlin-0015-8000.img`
  (17,002,496 B) ready for the next phone attempt: page 2048, kernel
  0x40080000, ramdisk 0x47c80000, dtb 0x4bc80000, kernel blob =
  gzip(phone shim Image 159,744) + blob-fdt.bin.
- loader.c diagnostics (WORD0/1, WRTEST, MEMOK/MEMB0/MEMTOP) are
  uncommitted; MEMOK bit 1 = 0x80000000, bit 3 = 0xA0000000.
- `fb.txt` glyph decoding is still broken (all `?`); read `fb.png`.

## Agent handoff / active work (2026-10-21 LATEST-13: SOURCE/COPY/DESTINATION TRIPLE CHECK)

- 0012 result (photo 2026-10-21-19-47-30-121.jpg): SCTLR_EL2 reads
  0x0000000030C50830 -> MMU, D-cache and I-cache are OFF when we run, so
  our writes are uncached and go straight to DRAM.  WORD0 and WORD1 are
  identical garbage (w0=BFD1DD7F w1=DFDA7E5F), i.e. cleaning the
  destination changed nothing: the bytes at 0xB148B488 were simply never
  the kernel entry.  SCTLR_EL1=8 (M=0), TTBR0_EL1=0, TCR_EL1=0 at EL1.
- Since write and readback use the same PA arithmetic, the copy is either
  reading a stale ramdisk (LK wrote it with caches on, then turned them
  off without cleaning what was still dirty) or the copy loop lands
  somewhere else.  0013 (`shim-boot-merlin-0013-src.img`) checks all
  three: ESRC (entry file offset + PA), SRCWORD s0/s1 (source word before
  and after `dc civac` over the payload), EDST (destination the copy loop
  actually used for the entry segment), WORD0/WORD1 (destination before
  and after cleaning) and WRTEST (write 0xdeadbeef to entry_pa and read
  it back).  The source is cleaned before the copy now.

- 0011 result (user photo 2026-10-21-19-19-18-776.jpg, read after rotation):
  - **The black box works**: `BBOX n=00000012 stage=00000009` - i.e. two
    boots x nine markers - and the text `xnu entry`, so the previous boot
    reached the call.  The page at 0xBFFFF000 survives the watchdog reset.
  - `POSTEL el=00000001` - the EL2->EL1 drop is good.
  - `MEMBASE 40000000`, `MEMSIZE C0000000` (3 GB bank at 4 GB base confirmed).
  - `HCR_EL2 80000002`, `CPTR_EL2 33FF`, `SCTLR_EL1 30800000` (MMU/D/I off).
  - Then our vector caught a **SYNC at EL1, slot 4**: `ESR=02000000`
    (EC=0 = undefined instruction), `ELR=00000000B148B488` = entry_pa,
    `FAR=0`.  So the CPU fetched something other than the expected
    `b _start_first_cpu` (kernel file offset 0x487488 = `19070014`, and
    the payload copy is byte-identical - verified with check-entry.py).
- 0012 (`shim-boot-merlin-0012-word.img`, flashed): prints, at EL1:
  SCTLR_EL1/TTBR0_EL1/TCR_EL1, then `WORD0` = the 8 bytes at entry_pa read
  through the EL1 regime, then `dc civac`-cleans [phys_base, bootargs top)
  and re-reads as `WORD1`.  Cases: WORD0 already 14000719 => DRAM fine;
  WORD0 bad + WORD1 good => LK left the caches on at EL2 and our copy
  never reached DRAM (clean fixes it); both bad => copy/source/PA wrong.
- Photo reading gotcha: the panel shows the same console lines twice,
  horizontally offset (labels in one copy, value tails in the other), and
  the user's camera crops each copy differently - combine both columns to
  reconstruct a 16-digit value.

## Agent handoff / active work (2026-10-21 LATEST-11: EL2 WAS THE WALL - DROP TO EL1 + BLACK BOX)

- 0009 diagnosis from the user's photo (917x917, first clear capture):
  the shim diag ran completely - and the line reads **EL cur=00000002**,
  i.e. LK hands the kernel control at **EL2**.  The diag also filled all
  73 panel rows, so the loader's own INITRD/PHYS/... lines were clipped
  off the bottom of the screen on 0009 (the "no red screen => jumped"
  reading was wrong; nothing about the jump was visible).
- Why EL2 is fatal: the xnu entry `__start` -> `_start_first_cpu` begins
  with `msr OSLAR_EL1, xzr` and programs SCTLR_EL1/TTBR1_EL1 - at EL2 the
  MMU that governs execution is SCTLR_EL2, and start.s has no EL2 drop.
  It dies at instruction #1, which is also why the stage-0 white band
  (drawn at 0x7ef87380 = row 2308, first thing in _start_first_cpu) never
  appeared.  LK gets away with it for Linux because head.S drops EL2->EL1
  itself.
- 0010 (`shim-boot-merlin-0010-el1.img`): loader.c `drop_to_el1()`
  (HCR_EL2.RW=1, CPTR_EL2=0x33ff, CNTHCTL_EL2=3, SP_EL1=sp, SPSR=0x3c5,
  eret) before the call; shim_main clears to black before loader_boot and
  reprints MEMBASE/MEMSIZE so the loader status is at the top of the panel.
  Flashed - the phone now reaches the loader page and reboots after ~23 s
  (the MTK watchdog: after the jump nobody pets it any more).
- 0011 (`shim-boot-merlin-0011-bb.img`): instrumentation for the next
  photo - a DRAM black box at 0xBFFFF000 (magic "BLOG!", stage + text)
  that survives the watchdog reset and is printed as `BBOX` at the top of
  the next boot; `POSTEL el=` after the drop (proof we really reached
  EL1); HCR_EL2/CPTR_EL2 readout before the drop.  Stage ids: 1 shim
  start, 2 diag done, 3 loader entry, 4 payload ok, 5 segments copied,
  6 bootargs ready, 7 dropping, 8 at EL1, 9 xnu entry.
- Live values captured on the 0009 diag: INITLO=47c80000,
  INITHI=4bc5b6e0, ATAGFB=7e605000, CNTFRQ=00c65d40, SCTLR_EL1=30800000,
  FDT magic=d00dfeed, CPU regs 0,100,200,300,400,600,700; MEMBASE/MEMSIZE
  were cut in the photo - likely 0x40000000/0xC0000000 (4GB MTK layout),
  0011 reprints them cleanly.
- Next: photograph the 0011 loader page (top BBOX lines + POSTEL line),
  then read the second-boot BBOX stage to see whether xnu actually got
  entered at EL1.

## Agent handoff / active work (2026-10-21 LATEST-10: KERNEL EARLY CONSOLE RETARGETED - 0009 flashed)

- 0008 result on the phone: NO red screen (loader accepted the payload and
  jumped) but the screen stayed on our shim page (yellow labels) -> xnu
  stopped before serial_init/fbcon, i.e. somewhere in early init.  With the
  sweet constants the early console wrote to DRAM (0x9c000000), invisible.
- 0009 fixes both issues:
  - shim: big 8x facts page removed; con_clear(0) + diag_small at the
    default scale-2 font, then loader_boot (0007b-big keeps the facts page).
  - kernel: `tools/patch-earlyfb.py` retargets the early console to the
    merlin splash.  5 verified patches in kernel.development.sweet ->
    kernel.development.sweet.merlinfb:
      * arm_vm_init (inlined sweet_early_map_final) TTE block PA
        0x9c000000 -> 0x7e000000 (movk x8 #0x9c00->#0x7e00 @7483c9c)
      * start.s FB block map same change (@748d340)
      * start.s stage-0 white band 0x9c9c1800 -> 0x7ef87380
        (FB + 2308*4320, the last 32 panel rows) (@748d104/108)
      * __DATA early_fb pointer 0x9c000000 -> 0x7e605000 (file 0xb5d6d8)
    Why the block-map patch is safe: the bootstrap table at x25+2*PGBYTES
    is a flat 2048-entry L2 array indexed by VA bits 25..; 0x9c000000 hits
    slot 78, 0x7e000000 hits 63 - both in range, still V=P.
  - payload rebuilt from kernel.development.sweet.merlinfb + merlin-phone.adt
    + merlin-init (same cmdline); image `shim-boot-merlin-0009-merlinfb.img`
    17,000,448 B, gzip round-trip byte-identical, SWEETXNU at 0x2e800.
- Flashed (fastboot flash boot 16,602 KB) + rebooted.
  EXPECT: black screen + small diag -> LOADER lines -> a white 64x32 band
  at the BOTTOM-LEFT = start.s entered -> "SWEET EARLY n: ..." text
  (stages 1..20; the stage colour bars are still drawn at rows 2368+
  so they stay off-screen, text is the signal).  Then either kprintf /
  fbcon output or a frozen SWEET EARLY line naming the last stage.

## Agent handoff / active work (2026-10-21 LATEST-9: FIRST XNU PAYLOAD DEPLOYED - phone boot in progress)

- User chose to skip the bigfacts capture ("JUST DO 2"): payload handoff
  wired and flashed with the provisional phone constants.  Values in
  0007b-big remain outstanding but no longer block the payload track.
- shim/shim.c MERLIN shim_main now does: small diag -> big facts page
  -> small diag -> `loader_boot(dtb)` -> on refusal `con_clear(RED)` +
  reason + hold.  On success the kernel fbcon clears the screen.
- Rebuilt from current sources (no stale artifacts): `mkadt.py
  xnu/out-0001/merlin-phone.adt --phone` (dram 0xb0000000/0x10000000,
  sweet-fbcon 0x7e605000 1080x2340 stride 4320) and `mkpayload.py ...
  --ramdisk xnu/out-0001/merlin-init --cmdline 'debug=0xc serial=3
  cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=md0'`
  -> merlin-phone-payload.bin 16,627,424 B (10 kernel segs + init
  ramdisk @0xb24c8000).
- Boot image `research/merlin-boot/shim-boot-merlin-0008-payload.img`
  (17,002,496 B): gzip(shim out/Image 155,648) 7,659 + raw FDT 181,203
  (stock shape, zlib round-trip verified byte-identical), ramdisk =
  the payload at image off 0x2F000 (SWEETXNU magic verified), dtb =
  stock-dtb.bin, page 2048, stock addrs (kernel 0x40080000, ramdisk
  0x47c80000, tags/dtb 0x4bc80000), osv 0x16000157 (11.0.0/2021-07).
- Kernel binary NOT patched for this attempt.  Analysis: sweet_early's
  0x9c000000 writes (stage-0 marker + marks, 2400-row geometry) land in
  plain DRAM on merlin with MMU off and under the start.s V=P block
  map later, so they scribble memory but cannot fault; the real output
  starts at serial_init when fbcon maps the ADT node (0x7e605000), and
  patch 0012 prints stages 17-20 there.  If the screen freezes before
  that, the next step is the in-place patch of 0x9c000000/2400 and the
  start.s block-mapping constant in kernel.development.sweet.
- Flashed to boot (`fastboot flash boot`, 16,604 KB) and rebooted.
  EXPECTED screen: red/green proof blocks -> shim diag -> facts page ->
  diag -> LOADER INITRD/PHYS/JUMP lines -> kernel console (or RED
  screen + reason if the loader refused).
- Iriun webcam still reports its "Please start Iriun Webcam"
  placeholder; captures bigfacts-frame-*/payload-frame-* are useless.

## Agent handoff / active work (2026-10-21 LATEST-8: ROOTFS CONVERTED TO RAW APFS IMAGE - verified)

- User's Firefox download landed at
  `D:\things\Merlin\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw`
  (5.747 GB).  Extracted `087-86698-044.dmg` (4.731 GB) via
  `tools/mkrootfs.py` into `research/ipsw-x/` (patched to tolerate the
  UTF-16 BuildManifest).
- The dmg is a NEW-format UDIF: `ipsw disk dmg` DOES NOT parse it
  ("chunk output length 73400320 out of range" - its heuristic rejects
  the pattern).  7-Zip 25.01 parses it fine (~/7zz/7zz on WSL, static
  build already in research/), and parsing the blkx plist MYSELF gave
  the full map.  Wall of the layout (keep for other dmgs):
  - koly trailer at EOF-512; the blkx plist lives right AFTER the data
    fork (`dataForkLen` bytes from 0); find it by scanning the tail for
    `<plist ... </plist>` (223 KB here).  koly XMLOffset field is NOT a
    usable byte offset in this variant (mine read 1), so search, don't
    decode fields.
  - Each blkx entry (`resource-fork`->`blkx` list, plistlib returns
    base64-decoded Data as bytes directly) is a mish: SectorNumber
    (LE? no - BIG-endian) @0x8 (partition start LBA), SectorCount
    @0x10, chunk count @0xc8, chunk entries @0xcc, 40 bytes each BIG-
    endian: type(4) comment(4) sect_no(8) sect_cnt(8) comp_off(8)
    comp_len(8).  The 32-byte-entry / @0x200-start guess is WRONG and
    silently produces garbage histograms.
  - Layout of THIS dmg: MBR @0, GPT hdr @1, GPT table @2, one
    Apple_APFS partition @LBA 34 (NOT 2048 - it starts right after the
    GPT), 11,005,952 sectors = 5.635 GB, backup GPT at the end.  Disk
    total = 11,006,019 sectors = 5,635,081,728 bytes.
  - Apple_APFS chunks: 3,633 real (3,261 lzfse type 0x80000007, 369
    zero type 1, 3 `uue` type 2 with coff=clen=0 -> sparse/zeros, 1
    terminator type 0xffffffff).  First lzfse chunk starts at file
    offset 0x172 - offsets are byte offsets, NOT sector multiples.
- Conversion: `tools/mkrootfsimg.py` (python, run under WSL because it
  ctypes-loads lzfse): lzfse lib built at ~/liblzfse.so from
  github.com/lzfse/lzfse (gcc -O2 -fPIC -shared of the decode sources:
  lzfse_decode.c lzfse_decode_base.c lzfse_fse.c lzvn_decode_base.c
  -> ~37 KB .so; bind lzfse_decode_buffer, scratch=NULL ok).  Writes
  sparse raw image directly to /mnt/d/...; each lzfse chunk decoded to
  EXACTLY its sect_cnt*512 (all 3,261 clean).
- RESULT: `research/ipsw-x/rootfs.img`, 5,635,081,728 bytes
  sha256 ECFB14570D7A96AC0FE16AAAC11D701091A0582BD5396B6329370521E5F80CFF
  (dmg sha256
  80F426D5B8FCA8552F95BE427434F1911DBB4C2C6D28AAD94F2426DDD0C92483).
  GPT + APFS image; Apple_APFS at byte 0x1100 (LBA 34).
- VERIFICATION (three independent ways; the mish's own recorded CRC
  0xDEE926A4 does NOT match either decoded-content CRC (0x9324df65)
  or packed-source CRC (0xb6a6fa8b) - its semantics options are
  probably the no-source uue regions or a compute variant; unresolved
  and not blocking):
  1. APFS fletcher64 (sums mod 2^32-1, words LE u32, cover [8:block);
     stored as two u32 LE) - the s2 half matches EXACTLY on 7
     independent NXSB checkpoint blocks.  s1 half disagrees (not
     chased; likely a final-reduction variant).  tools/apfsfletcher.py.
  2. 7zz OPENS OUR rootfs.img natively (Type = GPT -> APFS) and lists
     the whole fs: 181,683 files / 136,387 folders / 8.29 GB logical.
  3. Extracted files through 7zz from OUR image are valid: Weather.app
     Info.plist is a well-formed bplist00; SystemVersion.plist in our
     image reads ProductVersion 16.7.16, Build 20H392, SystemImageID
     0184D69E-C5E7-4A69-B716-C4E166CD8A97.  Genuine rootfs confirmed.
- Practical consequence: 7zz (WSL) can now browse/extract ANY file from
  the rootfs for the port (dyld caches, kexts, binaries).
- Tools added in tools/: mkrootfsimg.py (the converter),
  apfsfletcher.py, blkxdump.py (mish/chunk inspector), packedcrc.py.
  Scratch attempts deleted: dmginfo.py, kolydump.py, xmlfind.py,
  uuedump.py, apfshead.py, rootfscrc.py.
- 16:2x incident + repair: a stray re-conversion (scratch dmginfo.py
  redone while reconstructing session state) briefly replaced rootfs.img
  with a mis-based variant (chunks at partition-relative LBAs; 7zz
  refused it).  Rebuilt with `python3 tools/mkrootfsimg.py
  research/ipsw-x/087-86698-044.dmg research/ipsw-x/rootfs.img
  --check-crc DEE926A4` -> byte-identical recovery: size 5,635,081,728,
  sha256 ecfb1457...f80cff, 7zz lists 181,683 files / 136,387 folders.
  Scratch dmginfo.py removed again; mkrootfsimg.py stays canonical.
  The mish CRC 0xDEE926A4 was already known not to match decoded
  content; its --check-crc failure is informational only.

NEXT options (user to pick):
1. Bigfacts capture re-boot (0007b-big) -> fill mkadt.py --phone
   constants, then wire loader_boot into shim_main -> PHONE BOOT of our
   xnu with the real APFS knowledge.
2. Pull artifacts from rootfs.img for the payload prep (e.g. check dyld
   cache versioning + kext layout the sweet kernel expects under
   xnu-8796).
3. Disk-space check: ipsw (5.747 GB) + dmg (4.731 GB) + rootfs.img
   (5.635 GB) all on D:.  dmg/ipsw can be re-derived; ask before
   deleting anything.

## Agent handoff / active work (2026-10-20 LATEST-7: ROOTFS VERIFIED REMOTELY - waiting on user's Firefox download)

- tools/zipremote.py: lists/fetches members of a REMOTE zip via HTTP
  Range (Apple CDN serves 206).  Ran against the 16.7.16 restore URL
  with zero download: total 6.171 GB, 91 members, ZIP64 parsed.
- KEY FACTS:
  - rootfs = `087-86698-044.dmg`, **4.731 GB, zip method 0 = STORED**
    (not streamed; not AEA - plain UDIF, expect lzfse/UDZO blocks)
    -> extraction is a slice-copy; `ipsw extract --dmg fs` or
    mkrootfs.py both fine once the local IPSW exists.
  - restore ramdisk dmg = `087-86593-047.dmg` (1.098 GB) - NOT the fs.
  - BuildManifest (fetched remotely, 27.6 KB deflate): build **20H392**,
    iOS 16.7.16; identities **d22ap (iPhone10,3)** + **d221ap
    (iPhone10,6)**, every one's OS -> 087-86698-044.dmg.  Manifest is
    UTF-16LE bytes claiming encoding=UTF-8 (handle BOM + truncate at
    </plist> when parsing; multiple deflate members per zip entry - use
    decompressobj and drop leftovers).
  - `kernelcache.release.iphone10b` present (A11) - future source of
    Apple's closed kexts (apfs etc.) if the sweet kernel needs them.
- User opted to download the IPSW via Firefox into
  C:\Users\gycioc\Downloads\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw;
  my background curl died at 44% and its partial was deleted.
- ipsw.exe (blacktop/ipsw v3.1.739) at D:\tools\ipsw\ipsw.exe.

NEXT: when the Firefox download completes -> extract the dmg (4.73 GB
slice), convert with `ipsw disk dmg <dmg> -o rootfs.img`, record
sha256+size, stage in research/ipsw-x/, commit NOTES.  Then decide
integration (real mount needs storage drivers by our xnu on-merlin).

## Agent handoff / active work (2026-10-20 LATEST-6: ROOTFS TRACK STARTED - iOS 16.7.16 rootfs pipeline; bigfacts page CONFIRMED rendering)

### Confirmations from the user's 0007b-big boot

- The big-font facts page rendered (the ~17 huge lines with the live
  values).  User chose not to capture/transcribe them yet ("go for the
  iOS image") - values STILL OUTSTANDING for the phone ADT; the same
  image can be re-booted any time, screen holds indefinitely.
- Disposition: proceed with the rootfs track; wire the MERLIN payload
  loader AFTER the values land (mkadt phone constants still provisional
  until then).

### Rootfs pipeline (tools/mkrootfs.py)

- Target: iOS 16.7.16 (build 20H392) rootfs from the full restore
  https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/1158E502-D76D-4226-AA06-ED5E30CD1111/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw
  (iPhone X combo: iPhone10,3/10,6; Sandcastle-style rootfs base; the
  port's kernel is xnu-8796 = Darwin 22.6, matching 16.7 userland).
- Download running in background -> D:\things\Merlin\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw
  (~5.7 GB expected; keep OUT of git - it is in D:\things\Merlin root).
- Extraction staging: research/ipsw-x/ (gitignored).
- tools/mkrootfs.py: lists members + BuildManifest identities, streams
  the largest .dmg out, prints the UDIF koly trailer.  With the DMG in
  hand, raw conversion is `D:\tools\ipsw\ipsw.exe disk dmg <dmg> -o rootfs.img`
  (`ipsw disk dmg` decodes UDIF blkx incl. LZFSE; keys via -k if the
  image turns out AEA-encrypted - iPhone full restores usually are not).
- ipsw CLI installed at D:\tools\ipsw\ipsw.exe (v3.1.739; Windows x64).

NEXT: when the download completes - run mkrootfs.py, convert, record
hash/size, then decide rootfs integration (real mount needs our kernel
to drive storage; next phone-boot stage first).

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
