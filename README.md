# ios-merlin

**Apple's iOS 16 XNU bring-up for the Xiaomi Redmi Note 9 (`merlin`).**

This repository ports Apple's open-source XNU kernel (xnu-8796, the iOS 16
generation, Darwin 22.6) to the Redmi Note 9 (MediaTek MT6768 / Helio G85).
It is modeled 1:1 on [ios-sweet](https://github.com/dipa-studio/ios-sweet)
(iOS 16 on Redmi Note 10 Pro) and reuses its proven patch series as the
generic ARMv8.2 bring-up base; the device identity, ADT and test tooling
here are merlin's.

## Status

| Area | State |
| --- | --- |
| Kernel source | 79-patch series applied to xnu-8796 (macOS 13.5), builds as `MACHINE_CONFIG=SWEET` (generic non-PAC arm64 bring-up) on GitHub macOS runners |
| Boot payload | `tools/mkpayload.py` (SWEETXNU v1, shared with the ios-sweet shim) + merlin ADT + init RAM-disk root built and verified |
| Test environment | QEMU `virt` (local, WSL) — `tools/qemu-merlin.py` boots the payload, snapshots + decodes the kernel framebuffer console, reports result.json |
| Phone boot | Not yet (next milestone; needs the MTK-image path below) |
| iOS userland | Planned, unmodified iPhone X (iPhone10,3 / D22AP) iOS 16.7 IPSW, exactly like ios-sweet |

## How it works

1. **Kernel**: `xnu/patches/*.patch` are applied to xnu-8796 and built via
   `.github/workflows/xnu.yml` on GitHub's macOS runners using
   [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build)
   (MIT) at a pinned commit. A merlin-flavored machine config comes later;
   for now the generic SWEET config is reused on purpose (see NOTES.md).
2. **Payload**: `tools/mkpayload.py` resolves the kernel's chained-fixups,
   embeds the merlin ADT (identity `xiaomi,merlin` + iPhone10,3 userland
   compatibility) and boot-args, and appends the init RAM disk.
3. **Test**: `tools/qemu-merlin.py` boots the payload on QEMU's virt board
   (GICv3, cortex-a75 default) exactly like the shim does on the phone, and
   decodes the framebufer console using the kernel's own `_iso_font`.

## Quick start (local, WSL)

```sh
# one-time environment (needs sudo password)
sudo bash tools/env-ubuntu.sh

# fetch a kernel artifact (until this repo is pushed/CI'd, use ios-sweet's):
#   python3 tools/fetch-kernel-artifact.py latest dipa-studio/ios-sweet xnu/out-0001
# on Windows (credential manager holds the PAT) see NOTES.md for the exact curl line

# end-to-end test: ADT + init + payload + QEMU boot + console decode
bash tools/merlin-qemu-test.sh
```

QEMU boot-args (same as the ios-sweet QEMU tune): `debug=0xc serial=3 cpus=1
keepsyms=1 -enable_kprintf_spam -noprogress rd=md0`.

## merlin hardware facts (vs sweet)

| Fact | sweet (SM7150) | merlin (MT6768 / Helio G85) |
| --- | --- | --- |
| CPU | Kryo 470: 6×A55 + 2×A76 | 6×A55 (1.7 GHz) + 2×A75 (2.17 GHz), MPIDR 0x000..0x700 |
| GIC | GICv3, GICD 0x17a00000, GICR 0x17a60000 | GIC-500: GICD 0x0c000000, GICR 0x0c400000, sysirq intpol @ 0x0c53a650 |
| vTimer | INTID 19 (Qualcomm) | INTID 27 (standard PPI 11), CNTFRQ 13 MHz |
| Storage | UFS | eMMC 5.1 (MSDC0, 0x11cb0000) — driver TBD |
| Display | ABL splash FB @ 0x9c000000, 1080×2400 | LK splash FB @ 0x7e605000 (vram 0x17e8000), 1080×2340 HX83112b DSI-CMD |
| Console | FB only | DT says `console=ttyS0,921600n1` (UART test points may exist on the PCB) |
| PSCI | smc | smc (`arm,psci-1.0`) |

Sources: `android_kernel_xiaomi_mt6768/arch/arm64/boot/dts/mediatek/`
(mt6768.dts, merlin.dts) and the stock boot DTB
(`D:/things/Merlin/merlin_extracted.dtb`, parse with `tools/dtb-facts.py`).

## File map

| Path | Purpose |
| --- | --- |
| `xnu/patches/` | The 79-patch bring-up series (applied to xnu-8796) |
| `tools/mkadt.py` | Builds the merlin Apple Device Tree (`--qemu` twin / `--phone`) |
| `tools/dtb-facts.py` | Stock-DTB fact extractor (source of the ADT constants) |
| `tools/mkpayload.py` | Packs kernel + ADT + boot-args (+ RAM disk) into the boot payload |
| `tools/merlin-init.S`, `tools/mkinit.py` | Static PID-1 for the RAM-disk root (ad-hoc signed static Mach-O) |
| `tools/qemu-merlin.py` | QEMU `virt` boot + framebuffer console decode |
| `tools/merlin-qemu-test.sh` | End-to-end local test runner |
| `tools/env-ubuntu.sh` | One-time WSL environment (QEMU + toolchains) |
| `tools/fetch-kernel-artifact.py` | Downloads CI kernel artifacts (needs a token; see NOTES.md) |
| `shim/` | ABL-stage bootloader (fastboot boot path; loader is generic, Qualcomm diagnostics stay for now) |

## Roadmap

1. QEMU bring-up test of the current kernel with the merlin ADT (this session).
2. MERLIN machine config (GICR stride 0x40000, timer INTID 27, CNTFRQ 13 MHz).
3. Phone `fastboot boot` path: MTK boot.img v2 packing (`--dtb merlin`),
   live LK quirks (GIC grouping state, splash FB format/stride) probed from
   the shim's diagnostics screens.
4. MSDC0 eMMC driver (`rd=md0` → real root), MTK USB, IOMFB/DSI display, Novatek touch.
5. iOS root: `mkiosroot.sh` with the iPhone X iOS 16.7.16 IPSW (userdata partition).

> Experimental bring-up — not a usable phone OS, and Apple's security model
> is mostly switched off. Nothing here touches the phone's recovery, modem
> or bootloader partitions.
