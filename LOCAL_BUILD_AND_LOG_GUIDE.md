# Build and inspect the local 0117 image

This guide covers the experimental Redmi Note 9 (`merlin`) XNU 0117 image:
build the kernel in Ubuntu on WSL, package it with the known-good shim and
device tree, temporarily boot it, then retrieve and inspect the persistent
kernel log.

**Nothing in this guide flashes a partition. Use `fastboot boot` only.** The
0117 image has been packaged and structurally verified, but has not yet been
booted on the phone. Experimental iOS bring-up can fail to start or hang.

## What you need

- The project at `D:\things\Merlin\ios-merlin`.
- The existing Ubuntu/WSL cross-build environment at `~/xnu-cross`.
- Android platform-tools (`adb` and `fastboot`) on Windows. The log pull
  helper also needs `adb` available inside WSL.
- A bootloader-unlocked Redmi Note 9, with its important partition backups
  kept safe.

The current verified local image is already available at:

```text
research\merlin-boot\shim-boot-merlin-msdc-0117-linux-cpus8.img
```

You can skip to **Temporarily boot the image** to try it. The separate CI-built
image is
`research\merlin-boot\shim-boot-merlin-msdc-0117-ci-41306087077-cpus8.img`.

## 1. Build the kernel in WSL

Open Ubuntu/WSL and run the kernel-only phase:

```bash
bash /mnt/d/things/Merlin/xnu-cross/scripts/build-linux.sh kernel
```

This assumes the existing `~/xnu-cross` source tree is already patched through
0117 and the cross-build tools are installed. The script reuses the configured
object/build directories and writes the kernel to:

```text
/home/gycioc/xnu-cross/obj/DEVELOPMENT_ARM64_SWEET/kernel.development.sweet
```

Check the build result and SHA256:

```bash
test -s "$HOME/xnu-cross/obj/DEVELOPMENT_ARM64_SWEET/kernel.development.sweet"
grep -F 'done building xnu' "$HOME/xnu-cross/log/kernel-build.log"
sha256sum "$HOME/xnu-cross/obj/DEVELOPMENT_ARM64_SWEET/kernel.development.sweet"
/usr/lib/llvm-21/bin/llvm-otool -h \
  "$HOME/xnu-cross/obj/DEVELOPMENT_ARM64_SWEET/kernel.development.sweet"
```

For the verified 0117 build, the kernel was an ARM64 Mach-O, 19,476,064 bytes,
SHA256
`9ae24dc87e3b5e09d27aafda05c2ba437393e09d5c5f077374c8bb56c11a070f`.
Do not assume a later build has the same hash.

To keep a new build instead of replacing the saved research artifact, copy it
to a fresh, descriptive directory. In PowerShell:

```powershell
$repo = 'D:\things\Merlin\ios-merlin'
$artifact = Join-Path $repo 'research\art-0117-rebuild'
if (Test-Path $artifact) { throw "Choose a new artifact directory: $artifact" }
New-Item -ItemType Directory -Path $artifact | Out-Null
wsl.exe -d Ubuntu -- cp `
  /home/gycioc/xnu-cross/obj/DEVELOPMENT_ARM64_SWEET/kernel.development.sweet `
  /mnt/d/things/Merlin/ios-merlin/research/art-0117-rebuild/kernel.development.sweet
Get-FileHash (Join-Path $artifact 'kernel.development.sweet') -Algorithm SHA256
```

The current tree was incrementally brought from 0112 to 0117. Do not run the
`tree`, `obj`, or full/default build phases casually: those phases delete and
recreate existing source/object directories. If starting from a fresh WSL
environment or changing the patch base, first follow the cross-build setup
notes and back up any existing build tree.

## 2. Package a new image

Packaging needs three known-good boot inputs from the verified 0116 image:
the shim, DTB, and ADT. The ADT is inside the existing SWEETXNU payload. The
commands below extract those inputs and reuse the payload's boot arguments.
Run them from PowerShell:

```powershell
$repo = 'D:\things\Merlin\ios-merlin'
Set-Location $repo
$work = Join-Path $repo 'research\build-0117-repro'
if (Test-Path $work) { throw "Choose a new work directory: $work" }
New-Item -ItemType Directory -Path $work | Out-Null
$base = Join-Path $work 'base'
$sourceImage = Join-Path $repo 'research\merlin-boot\shim-boot-merlin-msdc-0116-msgrecv-cpus8.img'
python .\tools\unpack_bootv2.py $sourceImage $base
```

Extract the ADT and XNU command line from the unpacked SWEETXNU payload:

```powershell
$payloadSource = Join-Path $base 'ramdisk'
$adtPath = Join-Path $work 'adt-0115.bin'
$cmdlinePath = Join-Path $work 'xnu-cmdline.txt'
@'
from pathlib import Path
import struct, sys
payload = Path(sys.argv[1]).read_bytes()
adt_off, adt_size = struct.unpack_from("<QQ", payload, 0x20)
Path(sys.argv[2]).write_bytes(payload[adt_off:adt_off + adt_size])
cmdline = payload[0x48:0x48 + 608].split(b"\0", 1)[0].decode("ascii")
Path(sys.argv[3]).write_text(cmdline, encoding="ascii")
'@ | python - $payloadSource $adtPath $cmdlinePath
```

Build a new SWEETXNU payload using the kernel from step 1 (or the existing
`research\art-0117-linux\kernel.development.sweet`):

```powershell
$kernel = Join-Path $repo 'research\art-0117-rebuild\kernel.development.sweet'
$payload = Join-Path $work 'sweetxnu-payload.bin'
$xnuCmdline = Get-Content $cmdlinePath -Raw
python .\tools\mkpayload.py $kernel $adtPath $payload --cmdline $xnuCmdline
if ($LASTEXITCODE -ne 0) { throw 'mkpayload.py failed' }
```

Pack the new boot image. These addresses, page size, Android command line, OS
version, and patch level match the known-good image format:

```powershell
$image = Join-Path $work 'shim-boot-merlin-local.img'
python .\tools\mkbootimg.py `
  --kernel (Join-Path $base 'kernel') `
  --ramdisk $payload `
  --dtb (Join-Path $base 'dtb') `
  --output $image `
  --kernel_addr 0x40080000 `
  --ramdisk_addr 0x47c80000 `
  --tags_addr 0x4bc80000 `
  --dtb_addr 0x4bc80000 `
  --page_size 2048 `
  --name merlin-local `
  --os_version 11.0.0 `
  --os_patch_level 2021-07 `
  --cmdline 'bootopt=64S3,32N2,64N2 buildvariant=user'
if ($LASTEXITCODE -ne 0) { throw 'mkbootimg.py failed' }
Get-FileHash $image -Algorithm SHA256
```

The Android boot header command line is separate from the XNU command line
inside the payload. Keep both as shown. The XNU arguments include `cpus=8`
and `rd=msdcroot0`.

Before using a newly packaged image, unpack it into another fresh directory
and inspect `header.txt`:

```powershell
$verify = Join-Path $work 'roundtrip'
python .\tools\unpack_bootv2.py $image $verify
Get-Content (Join-Path $verify 'header.txt')
Get-FileHash (Join-Path $verify 'kernel') -Algorithm SHA256
Get-FileHash (Join-Path $verify 'ramdisk') -Algorithm SHA256
Get-FileHash (Join-Path $verify 'dtb') -Algorithm SHA256
```

For the verified reference image, the boot format is Android v2, page size
2048, shim size 190,674 bytes, and DTB size 181,203 bytes. The local 0117
image was additionally checked so all ten file-backed kernel segments in its
payload exactly match the built kernel. A checksum and successful unpack alone
do not prove those segment contents match; do not skip validation when
changing the packer or inputs.

## 3. Temporarily boot it

Boot the phone to its bootloader/fastboot screen, connect USB, and run in
PowerShell:

```powershell
fastboot devices
fastboot boot $image
```

This sends the image to memory for this boot only. **Do not use `fastboot
flash` or any GUI partition-write operation.** Wait for the kernel and
userland to start, then reproduce the behavior whose trace you want to inspect.
The receive tracer is diagnostic and capped at 30,000 records; it does not
guarantee that Setup Assistant becomes visible or completes.

## 4. Retrieve and inspect the logs

After the test, boot into OrangeFox/recovery without flashing anything. Confirm
ADB sees the recovery device and that its shell is root:

```powershell
adb devices
adb shell id
```

From WSL, pull and decode the persisted SWEET log. The helper reads only the
last 1,025 blocks of the userdata partition; it does not write to the phone.
Replace the timestamp so each capture gets a unique filename:

```bash
cd /mnt/d/things/Merlin/ios-merlin
mkdir -p research/logs
bash tools/sweet-log-pull.sh research/logs/sweetlog-0117-local-YYYYMMDD-HHMMSS.txt
```

The command creates a decoded `.txt` log and a corresponding raw `.txt.bin`
capture. The log is persisted in the userdata area and flushed periodically,
so recover it from recovery after the test. The ring is finite; if it wrapped,
older records are already lost. The helper prints the ring header, including
the flush sequence and byte counts.

Search the decoded log for the receive trace, send errors, Setup launch, or
crashes:

```bash
grep -nE 'SWEET MSGRECV|SWEET MSGERR|exec budd|CRASH budd' \
  research/logs/sweetlog-0117-local-YYYYMMDD-HHMMSS.txt
```

`SWEET MSGRECV` reports a kernel-dequeued Mach message, not proof that the
process received or handled it successfully. Treat correlations between
message errors and process crashes as clues, not established causes. Keep raw
device logs local; they can contain process names and system details, and
should not be committed.
