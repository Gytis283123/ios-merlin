# iOS 16 on merlin (Redmi Note 9, MT6768 / Helio G85) - working notes

## Agent handoff / active work (2026-10-20, latest)

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
