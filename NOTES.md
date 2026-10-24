# iOS 16 on merlin (Redmi Note 9, MT6768 / Helio G85) - working notes

## Agent handoff / active work (2026-10-24 LATEST-37: FLASH #3 COMPLETE (47/47 OK, decoy tail worked); BOOT #5 = DYLD CACHE ACCEPTED + launchd RAN DEEP USERLAND JOBS; NEW WALL DECODED "Unable to find AMFI" = launchd_cache_loader's IOKIT LOOKUP; FIX = launchd_unsecure_cache BOOT-ARG; BOOT #6 IMAGE READY)

- FLASH #3 SUCCESS: `fastboot flash userdata iosroot-v2.img` with the
  64 MiB `0xFF` decoy tail appended (17,226,006,528 B) -> 47/47 chunks
  ALL OKAY, "Finished. Total time: 1013.498s". The decoy changed the
  sparsifier geometry (7x~256MB chunks instead of 92x~128MB) and under
  that geometry EVERY chunk incl. the last wrote OKAY. The eMMC volume
  is now complete (incl. the ~123 MiB lost in flashes #1/#2). The
  LK final-chunk root cause is NOT solved - the decoy is the standing
  mitigation (keep it for future userdata flashes); root-cause from LK
  source later if time permits.
- BOOT #5 (0083 image + flashed v2 rootfs): **THE SHARED-CACHE FIX
  WORKS.** No "no dyld cache" wall. launchd ran REAL iOS jobs on HW:
  FudEarlyBoot (Starting/Exiting Early Boot, no accessories, critical
  entries 0.000000 sec), tzinit (nonfatal "Bad zonelnfo Link : no such
  file", "Invalid current symlinks; resetting to system partition"),
  FinishRestoreFromBackup/finish_restore/systemstasuschack,
  prng_prngseedctl ("apple rng seed: (-76) no such file" - expected
  without APCFS; "failed to load virtual random (-356870212)").
  then: `panic(cpu 0 caller 0xffffffe0007a7b2fc): launchd_cache_loader[231]
  exited -- exit reason namespace 7 subcode 0x1 description: Unable to
  find AMFI` (+ "pid 23 exited" line, core-gen errno 14 harmless).
  reason.h decode: ns 7 = **OS_REASON_LIBXPC** (reconfirms ns 9 = EXEC,
  0xe = WRONG_PLATFORM for boot #4). "handshake structure not
  initialized" = xnu kdp out_shmem.c panic-printer path - red herring,
  ignore. "launchd_cache_loader" is NOT in xnu = userspace helper.
- AMFI ROOT CAUSE DECODED (disassembly of /usr/libexec/
  launchd_cache_loader, 72,336 B, extracted to research/forensics/):
  - It is launchd's bootstrap verifier: opens launchd's stashed mach
    ports (mach_ports_lookup), logs to
    /var/log/com.apple.xpc.launchd/launchd_cache_loader.log, reads
    /System/Library/xpc/launchd.plist + .sig, SecStaticCodeCreateWithPath
    -> SecCodeSetDetachedSignature -> SecStaticCodeCheckValidity ->
    SecCodeCopySigningInformation (kSecCodeInfoUnique = cdhash),
    then IOKit: IOServiceMatching("AppleMobileFileIntegrity") ->
    IOServiceGetMatchingService -> cbz w0 -> abort "Unable to find
    AMFI" -> libxpc exit reason ns 7 -> launchd panics the system.
    (Later: IOServiceOpen type 0 + IOConnectCallMethod selector 6 with
    cdhash bytes -> "cdhash trusted"/"not in trust cache"; amfid has
    the identical dependency: "Unable to find AMFI service." /
    "Unable to open AMFI user client".)
  - SWEET's builtin AMFI (patches 0025/0035/0036) is kernel-internal
    only: amfi_interface_register() (libkern/amfi/amfi.h) +
    SweetEntitlements + CS_SIGNED/platformBinary marking. It publishes
    NO IOKit IOService -> nothing userspace can find.
  - **ESCAPE HATCH FOUND IN THE BINARY**: it reads sysctl kern.bootargs
    and substring-searches for **`launchd_unsecure_cache=`** (presence
    only, any value). When present it prints "Using unsecure cache:
    <path>" and jumps STRAIGHT to the send-to-launchd path (mmap plist
    -> copy into launchd's mapped memory -> "Cache sent to launchd
    successfully"), BYPASSING SecStaticCode + the entire AMFI
    handshake. Apple-internal testing mechanism shipped on both sides
    (sender + launchd). This is a cmdline-only fix: no CI, no reflash.
- BOOT #6 BUILT + SELF-VERIFIED:
  research/merlin-boot/shim-boot-merlin-msdc-0083-simlaunch-unsec.img
  (16,989,139 B; same 0083 kernel 66750d31..., same proven cmdline PLUS
  `launchd_unsecure_cache=1`).
- NEXT USER STEPS:
      fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0083-simlaunch-unsec.img
  Photograph: (1) the EARLY screen with `MERLIN MSDC: "userdata" first
  sector 0x..., NNNN MiB` line (still never captured - settles the true
  partition size + win/esp grow-back); (2) launchd_cache_loader lines
  (expect "Using unsecure cache: /System/Library/xpc/launchd.plist" +
  "Cache sent to launchd successfully" instead of the AMFI abort);
  (3) whatever comes next - the next candidates are amfid (same IOKit
  dependency; if IT panics, the escalation is a kernel-side IOKit
  "AppleMobileFileIntegrity" service + user client, a real patch), the
  preboot/errno-25 ignition path, and personableness.
- AMFI DISASM ARTIFACTS (gitignored research/forensics/): amfid,
  launchd_cache_loader binaries, lcl-strings.txt, lcl-disasm.txt (full
  symbol-annotated, 1349 lines), amfid-bind.txt. probe-amfi{1,2,3}.sh
  in research/tmp-msdc-split/. WSL mounts /tmp/mOSv (OS dmg) +
  /tmp/mDSCv (DSC dmg) are FRESH user-mode apfs-fuse mounts (previous
  /tmp/apfs* died in a VM restart; stale root-owned dirs block
  remounting AT THE SAME PATH - always mkdir fresh names).

## Agent handoff / active work (2026-10-24 LATEST-36: launchd RAN (libignition prints on HW!) BUT DYLD 'no dyld cache' KILLED THE STAGED RE-EXEC; ROOTFS MISSING THE WHOLE SHARED CACHE - SOURCE = SECOND IPSW DMG 087-86593-047.dmg; mkiosroot v2 READY; USER TO REBUILD + REFLASH)

- BOOT #4 (shim-boot-merlin-msdc-simlaunch.img = SAME kernel artifact
  69a42869 + boot-arg `unentitled_ios_sim_launch=1`): THE PLATFORM-GATE
  FIX WORKS. iOS 16.7.16 launchd EXECUTED AND RAN USERLAND CODE ON HW:
  libignition state dump (`initproc 0x1`, `rootfs mount flags
  0x04048001`, `platform 0xffffffffffffffff` (watch), `boot space 0x2`,
  `stage count 0x7`), `hello: commence primary ignition`, `hello: hello
  from launchd,1`; then `preboot : mounting preboot` ->
  `failed to to lookup preboot : 25` -> `preboot : failed to get preboot
  devices: 25` -> `ignite() returned 25` -> `ignition boot failed: 25`.
  launchd CONTINUED past the ignite failure to its next stage.
- NEW WALL = the staged re-exec (same pid 1, vfork-exec of
  /sbin/launchd): dyld `Library not loaded:
  /usr/lib/libSystem.B.dylib ... Reason: tried '/usr/lib/libSystem.B.dylib'
  (no such file), no dyld cache), '/usr/local/lib/libSystem.B.dylib'
  (no such file)` -> `pid 1 exited -- exit reason namespace 6 subcode
  0x1` (ns 6 = OS_REASON_DYLD); core dump attempt failed errno 14;
  kernel panic `initproc failed to start -- exit reason namespace 6
  subcode 0x1 description: library not loaded: /usr/lib/libSystem.B.dylib`
  (the CORRECT kern_exit.c proc_handle_critical_exit panic, caller
  0xfffffe000807af02f0c; panic machinery all working as designed).
- ROOTFS FACTS (7z listing research/ipsw-x/iosroot.img, 318k entries):
  /usr/lib/dyld loader PRESENT (922,912 B); /System/Library/dyld ABSENT
  entirely; /System/Library/Caches has NO com.apple.dyld. The SOURCE
  is dirty too: apfs-fuse of BOTH 087-86698-044.dmg (the OS dmg) and
  rootfs.img (its previous raw conversion) show NO dyld dir anywhere.
  -> THE CACHE LIVES IN THE SECOND IPSW DMG: `087-86593-047.dmg`
  2,743,074,816 B - never mounted by previous sessions (the "no
  cryptex dmgs" verdict came from size-guessing; it IS a cryptex-like
  dsc volume). apfs-fuse shows
  `/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64{,
  .01..40}` + `.27/.41.dylddata` + `.28/.42.dyldlinkedit` + `.symbols`
  = 44 files, 3,330,359,296 B LOGICAL (dmg 2.55 GB compressed; sparse
  split-map clone layout - du shows 0, logical sizes are real);
  headers `dyld_v1  arm64` verified; head/tail/sha256 probes all read
  PROBE script: research/tmp-msdc-split/probe-dsc.sh (WSL apfs-fuse
  works USER-MODE, /dev/fuse is 666 - no sudo needed for the dmg side).
  The trampoline loose dylibs (usr/lib/libobjc-trampolines.dylib,
  libffi-trampolines.dylib, libstdc++*) are in the dsc volume too;
  mkiosroot's loose-file cryptex loop will link them into the root.
- FIX COMMITTED (ios-merlin 2ccbfc5): tools/mkiosroot.sh ALSO hard-links
  the cache to `/System/Library/dyld` (the regular iOS 13+ lookup path)
  in addition to the existing `/System/Library/Caches/com.apple.dyld`
  (script comment: ignition_level=1 looks there). Neither path was
  reached before because the A11 build passed `-` for sysos.
- NEXT USER STEP (WSL build ~10-20 min, then flash ~15-25 min):
    wsl: cd /mnt/d/things/Merlin/ios-merlin
         sudo bash tools/mkiosroot.sh \
             research/ipsw-x/087-86698-044.dmg \
             research/ipsw-x/087-86593-047.dmg \
             - research/ipsw-x/iosroot-v2.img 16G
    then Windows:
         fastboot flash userdata research\ipsw-x\iosroot-v2.img
         (same reflash decision as LATEST-28; wipes phone-rootfs state
          incl. journal mutations of boots #3/#4)
         fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0083-simlaunch.img
  (0083 kernel = permanent platform-gate fix; the
  unentitled_ios_sim_launch=1 boot-arg stays in the cmdline as harmless
  redundancy.)
- OPEN RISKS for boot #5: (a) the preboot-volume lookup may STILL fail
  (single-partition root, errno 25 was non-fatal pre-cache); (b) 3.1 GB
  cache maps lazily - file-backed/evictable, fine on 3-4 GB RAM;
  (c) dyld will hammer the driver with scattered reads across 3GB of
  sparse split files - reads are proven through 0082.
- FORK CI: 0083-merlin-launchd-platform @79c3634 - run 40096809453
  COMPLETED SUCCESS. ARTIFACT-GOTCHA RESOLVED (do not repeat): the
  repo-wide artifact list shows an `xnu-kernel` id 12561570287
  (178 KB, kdk-libs only, EMPTY SHA256SUMS) - that one belongs to
  STALE run 40096726697 @7350bf4 (the cancelled duplicate; its upload
  still landed, created 13:08:20Z). The REAL artifact for run
  40096809453 is id 12560954555 (60 MB, created 13:15:52Z).
  LESSON: an artifact id from the generic list must be cross-checked
  against its `workflow_run` (run id + head sha) or the job log line
  `Artifact xnu-kernel has been successfully uploaded! ... Artifact
  ID is ...` - never take the newest-looking id.
- 0083 KERNEL FETCHED + VERIFIED: research/art-0083/ now holds the
  real payload: kernel.development.sweet 17,207,192 B,
  SHA256 66750d3185e4d978e65c44ff6d0a974f3d3d26bd0cba6f573b2c2da9733c48c5
  == artifact's SHA256SUMS (verified). Same byte size as the
  on-device-proven 69a42869 build, different SHA - consistent with
  the small in-place process_signature change (0083 adds no strings).
  Chain: artifact <- run 40096809453 <- head 79c3634 (msdc-0079 +
  0083).
- BOOT IMAGE BUILT: research/merlin-boot/
  shim-boot-merlin-msdc-0083-simlaunch.img 16,989,139 B,
  SHA256 71f9c3e6cb112f254e00bf9cc9ae3d896707c46a952c17fa21987f0d6bafe5f0
  - kernel = art-0083 0083 build; cmdline IDENTICAL to the proven
  simlaunch image (`... rd=msdcroot0 unentitled_ios_sim_launch=1`;
  boot-arg KEPT - harmless redundancy next to the in-kernel 0083
  fix); repacker self-checks passed (shim slot + dtb byte-identical
  to the E1 image; payload 16,611,984 B).
- BOOT #5 SHOULD USE THIS IMAGE (kernel-side gate fix + boot-arg).
- **USER BUILT research/ipsw-x/iosroot-v2.img** (2026-10-24 ~17:00):
  OS copy + sysos -> /private/preboot/Cryptexes/OS + the 44 split-cache
  files hard-linked to BOTH /System/Library/Caches/com.apple.dyld and
  /System/Library/dyld (also the DSC's System/DriverKit inner cache +
  trampolines); df 16G total / 12G used (8.6 OS + 3.3 cache counted
  once) / 4.4G avail. fsck needed two -y repair passes (thread/leaf
  record counts flip-flopped) but ended "repaired successfully";
  the final read-only -n pass reports ONLY the documented benign
  "Volume header needs minor repair (1,0)" (exit 8, journal
  mkfs-inherent bit - same as the control volume in LATEST-27).
- WSL GOTCHAS REENCOUNTERED + FIXED IN mkiosroot.sh: (a) the out-of
  tree hfsplus.ko needed re-insmod after a VM restart; (b) FIRST FIX
  USED A WRONG GREP - /proc/filesystems lists hfsplus WITHOUT the
  nodev prefix (block-device fs) so the detection never matched ->
  twice false-failed; commits 4aaeeb1 then 3fdfe57 (final: `grep -qw
  hfsplus`, tolerates insmod EEXIST when already inserted). Module
  is loaded in the VM now; /root/hfsmod/hfsplus.ko SURVIVES VM
  restarts, only the /lib/modules copy is transient.
- **FLASH-SIZE FACT UPDATED (v2 flash run #1, 2026-10-24 ~17:20)**: even
  after truncating to 16300 MiB the final chunk (92/92, 126,165 KB)
  FAILED `sparse image write failure` - chunks 1..91 wrote OKAY.
  Chunk-size sums (~11.78 GiB) + a tailscan of the image
  (research/tmp-msdc-split/tailscan.py) prove the sparse transfer
  carried ONLY nonzero bytes: the file's last nonzero byte is at
  11.6565 GiB (filesystem data), followed by 4.5 GiB of zeros. OLD
  INTERPRETATION OF THE V1 FLASH IS THEREFORE WRONG: chunk covers are
  data-relative, not file-range-contiguous - the old failed chunk did
  NOT establish a >=15.9425 GiB partition end. Conclusions: (a) the
  partition-end theory is DEAD (the failed chunk's range ~11.4-11.66
  GiB is FAR inside even the most conservative end estimate, and v1's
  flash fill-wrote that physical region successfully); (b) the
  failure hits the LAST data chunk at ANY location (v1: last chunk;
  v2: last chunk at a totally different offset) - something in the
  LK sparse-write path chokes on the final chunk (root cause
  unresolved, need LK source later); (c) CONSEQUENCE: the flashed
  eMMC volume was left WITHOUT ~123 MiB of real fs content around
  ~11.4-11.66 GiB (would likely fail mount/painfully).
- COUNTERMEASURE (committed decision): append a ZERO-RUN to the image
  so the real-data chunk is no longer the final chunk - the new final
  chunk is an all-zero fill whose failed write loses NOTHING
  (independent of which LK-last-chunk theory holds). DONE: image
  padded via truncate/research/tmp-msdc-split/pad-img.py: 17,091,788,800
  -> 17,158,897,664 bytes (+64 MiB zeros; data still ends at
  11.6565 GiB).
- PAD REFLASH (#2) RESULT: IDENTICAL output - 92/92 chunks, same
  last chunk (126,165 KB) FAILED, all others OKAY. FASTBOOT'S
  SPARSIFIER DROPS TRAILING ZERO RUNS ENTIRELY (the pad was never
  transmitted; trailing zeros are implicit) - so flash #1 and #2
  were the SAME transfer: one identical final data chunk at
  ~[11.53..11.66 GiB) failed twice. Cannot yet distinguish
  "LK fails EVERY final chunk" from "that eMMC range is bad".
  (Fill-write counterpoint: v1's flash carried fill chunks over the
  same physical region with OKAY - weakens "range is bad" but is
  not decisive because the v1 range semantics were never decoded.)
- SPLIT EXPERIMENT (next flash #3): 64 MiB of 0xFF decoy appended
  past the real data (research/tmp-msdc-split/decoy-append.py; file
  now 17,226,006,528 B = 16,428 MiB). The decoy lives in the HFS+
  volume's own FREE blocks (bitmap free; also below the oldest
  conservative partition-end estimate) -> writing it is harmless and
  losing it is harmless. Predicted outcomes: (A) "final-chunk
  always fails": all 92 data chunks OKAY, only the new final decoy
  chunk(s) fail -> data intact -> boot. (B) "range ~11.4-11.66 GiB
  is bad": chunk 92 (now NON-final) fails again -> hardware issue in
  that eMMC region -> switch to mtkclient surgery for precise
  writes. Also still want the `MERLIN MSDC: "userdata" first sector
  0x..., NNNN MiB` line from the boot to settle the true partition
  end once and for all.

## Agent handoff / active work (2026-10-24 LATEST-35: launchd SIGKILL DECODED = EXEC_EXIT_REASON_WRONG_PLATFORM; ROOTFS MOUNTS; FIX = unentitled_ios_sim_launch BOOT-ARG (no CI needed) + FORK PATCH 0083 (79c3634, CI building))

- BOOT #3 (shim-boot-merlin-msdc-blknum.img, kernel artifact
  69a42869d99d7a9e79b3f72e2db1753938228a7e590ad84beb68cc8d17a1d405, CI
  40093673378 @7350bf4) - MILESTONE: the whole eMMC/MSDC/GPT/HFS+ stack
  works END-TO-END ON HARDWARE. Console proof: `BSD root: msdcroot0,
  major 1, minor 0`; `hfs: Initializing the journal...` (no more
  strategy err 0x1e - the CMD24/RMW write path makes the journal!);
  `hfs: mounted iOSBoot on device h(1, 0)`;
  `hfs: root volume is not authenticated (error 25); continuing
  unsealed` (SSV gate passed unsealed); Serial Keyboard started; then
  `load_init_program: attempting to load /usr/appleinternal/sbin/launchd`
  -> `/sbin/launchd` -> PANIC.
- PANIC (photo): `panic(cpu 0 caller 0xfffffe0027ac63dc): unexpected
  SIGKILL of launchd (CS_KILLED) with reason -- namespace [9] code
  [0xe] description [..]`. Transcription of digits was fuzzy; symboli
  zation of the caller failed BOTH raw forms - RESOLVED: caller =
  `psignal_internal()` (bsd/kern/kern_sig.c, a STATIC function -> not
  in symtab by design; static panic-neighbor symbols made the address
  look off). True caller is 0xfffffe0007ac63dc-adjacent; the leading
  `2` in the photo read was a blur artifact.
- DECODE (source of truth now vendored ENTIRELY at research/xnu-full =
  apple-oss xnu-8796.141.3 tarball, the EXACT tag CI builds via
  darwin-xnu-build macos-135 release.json):
  - panic strings found in the kernel binary; site = kern_sig.c
    `psignal_internal`: on SIGKILL of initproc it prints
    `unexpected SIGKILL of %s %s with reason -- namespace %d code
    0x%llx description %.800s` ((CS_KILLED) is the 2nd %s).
  - namespace 9 = OS_REASON_EXEC; code 0xe = EXEC_EXIT_REASON_WRONG_
    PLATFORM (both in bsd/sys/reason.h, 8796.141.3 lines 244-262).
  - kill path = kern_exec.c `process_signature()`: checks BEFORE the
    platform gate all PASSED (`ip_mac_return==0`, `ip_cs_error==NULL`
    => vnode/sig validation during activation SUCCEEDED, no codesign
    rejection at all!) -> `#if XNU_TARGET_OS_OSX` gate: launchd (iOS
    binary) execs with NO posix_spawn attrs, and is only allowed if
    DEVELOPMENT-config `unentitled_ios_sim_launch` boot-arg is set or
    the binary carries com.apple.private.security.no-sandbox (SWEET's
    builtin AMFI grants nothing) -> EACCES -> CS_KILLED +
    psignal_vfork_with_reason(SIGKILL, EXEC/WRONG_PLATFORM).
- FIX (a), NO CI NEEDED: `unentitled_ios_sim_launch` is `static
  TUNABLE(bool, ..., false)` (kern_exec.c segment-comment) = boot-arg.
  Built research/merlin-boot/shim-boot-merlin-msdc-simlaunch.img TWO
  SHA checks: kernel artifact == 69a42869... (same as booted run),
  image SHA 66d466a8552ce4428d09b808e0453dec06f639e86eb9980c940e7f0f32
  c00fb8; cmdline
  `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam
  -noprogress rd=msdcroot0 unentitled_ios_sim_launch=1`.
  build-msdcroot0.py now takes --cmdline/--out (defaults unchanged);
  its self-check asserts 'rd=msdcroot0' in cmdline (prev. endswith).
- FIX (b), PERMANENT: fork patch `xnu/patches/0083-merlin-launchd-
  platform.patch` (msdc-0079 79c3634, PUSHED; only kern_exec.c hunk in
  that region; 0042 is the only other patch touching it - context
  written post-0042). Under ARM64_BOARD_CONFIG_SWEET set
  no_sandbox_entitled=TRUE = same as the DEVELOPMENT boot-arg path.
  CI run 40096809453 building 79c3634 (in progress); stale duplicate
  run 40096726697 (dispatched before push, building old 7350bf4) was
  CANCELLED.
- EXPECTED after the gate: fork 0042 prints `exec launchd` (SWEET
  run-every-iOS-binary log) at the allow branch, then launchd really
  execs: dyld maps /usr/lib/dyld, text pages validate against the
  embedded CMS blob captured at activation (no trust cache involved
  for the embedded-signature path - watch for the next wall wherever
  it appears: page validation, disk fifo, sandbox, launchd hitting a
  missing AppleXPC service, etc.).
- Housekeeping: research/xnu-ref file grab was superseded by
  research/xnu-full (whole 8796.141.3 tree ~135MB);
  research/xnu-ref/*.c kept for reference. research/ is gitignored.

## Agent handoff / active work (2026-10-24 LATEST-34: SDC_BLK_NUM FIX WORKED - CMD17 READS + GPT SCAN + ROOTDEV OK; NEW WALL = DRIVER REFUSES ALL WRITES (EROFS) AT HFS+ JOURNAL; CMD24 WRITE PATH COMMITTED + CI BUILDING)

- BLK-NUM IMAGE BOOT VERDICT (shim-boot-merlin-msdc-blknum.img, one
  photo): PAST THE READ WALL. `BSD root: msdcroot0, major 1, minor 0`
  printed = the driver read the GPT (multiple sectors - the GPT header
  AND the entry table), matched the partition and returned a dev_t.
  The mount attempt then fails in hfs journal init, RETRIED by
  IOFindBSDRoot at least through attempts 4/5/6 (constant NotFound
  loop, no panic observed on this screen; attempts 1-3 scrolled off the
  console ring).
- Failure anatomy (identical each attempt):
  `hfs: Initializing the journal (joffset 0x628000 sz 0x6800000)` ->
  `jnl: do_jnl_io: strategy err 0x1e` (0x1e = 30 = EROFS) ->
  `write_journal_header: error writing the journal header!` ->
  `journal_create: failed to write journal header.` ->
  `hfs: late_init: failed to open/create the journal (retval 0).` ->
  `hfs_late_journal_init returned (22)` (EINVAL) ->
  `hfs_mount: hfs_mountfs returned error=22 for device unknown-dev` ->
  `cannot mount root, errno = 19`.
  Note: `journal_create`, not replay - the volume wants a NEW journal
  created at mount time (iosroot.img journal state from the LATEST-27
  build pipeline), and every single one of those writes EROFSes.
- ROOT CAUSE: BY DESIGN - the 0082 driver was read-only: open() refused
  FWRITE with EROFS, strategy() refused write buffers, d_write returned
  EROFS, DKIOCISWRITABLE=0. `do_jnl_io strategy err 0x1e` = OUR OWN
  strategy refusing the journal header write. Not an iosroot.img state
  problem.
- FIX (committed ios-sweet msdc-0079 7350bf4): CMD24 single-block write
  path mirroring the read path - SDC_CMD raw = 24 | R1(1<<7) | RW
  (1<<13, direction per stock sd.c `rawcmd |= (1 << 13)` for
  MMC_DATA_WRITE) | BLKLEN 512 | DTYP single (1<<11); SDC_BLK_NUM=1
  before ARG/CMD; same basic-DMA SA/LEN/LASTBUF/burst; same dat_int
  wait with the enriched failure dump; trailing wait_idle consumes card
  R1b busy; bdev strategy writes with read-modify-write around partial
  sectors; d_write -> physio B_WRITE; DKIOCISWRITABLE=1; open() no
  longer refuses FWRITE. Reference cross-checks: single-SGE always
  BASIC mode regardless of direction; no extra direction programming
  beyond the RW bit.
- eMMC write viability is established: LK WROTE the boot image to this
  card and left working timing config - reads already pass with it.
- Validation: patch hunks consistent under strict git apply (hunk1 7/25
  unchanged; hunk2 4/702 via fix-hunk.py; 736 lines). Context lines
  still untouched from the CI-validated chain; bare-tree apply still
  fails only with "No such file" for files created by earlier patches.
- PUSHED msdc-0079 (f2a9322 -> 7350bf4) + workflow_dispatch run
  40093673378 in progress (approved by user, same loop as LATEST-33).
- AFTER BUILD: fetch-kernel-artifact.py GET <artifact_id> (from run
  40093673378, name xnu-kernel) -> research/art-writecmd24/ ->
  build-msdcroot0.py <kernel.development.sweet> (payload-new.bin +
  shim-boot-merlin-msdc-blknum... image name shim-boot-merlin-msdc-
  blknum.img is reused - the script overwrites it) -> unpack verify ->
  cold power-off -> fastboot boot -> photograph.
- EXPECTED next outcomes: (a) journal_create's writes succeed -> mount
  proceeds -> `BSD root` + HFS+ mounts + launchd (WINS); (b) CMD24
  fails: first write/command failures will print
  `MERLIN MSDC: CMD24(...) failed/data failed: int ... sts ... dcfg ...
  ca ... fifocs ...` -> diagnose from the dump; (c) mount succeeds
  but hits a LATER fs/sandbox/log wall - read the next failure.
- FYI observation: `for device unknown-dev` in hfs_mountfs = cosmetic
  (alias vnode naming), and `cannot mount root, errno = 19` mapping
  (ENODEV) is IOFindBSDRoot's wrapper errno - the real error is the 22
  from hfs_mountfs. Don't chase either.

## Agent handoff / active work (2026-10-24 LATEST-33: MSDC DATA-PHASE FAILURE ROOT-CAUSED - SDC_BLK_NUM NEVER WRITTEN; PATCH FIXED + COMMITTED ON msdc-0079 (f2a9322); PUSH+CI AWAITING USER GO)

- Panic photo parsed (E1 boot, LATEST-32): `MERLIN MSDC: cfg ... ps
  ... sts ...` (take_over OK - alive/clocked/idle), then
  `MERLIN MSDC: CMD17(1) data failed ...` - the FIRST data read, LBA 1
  = the GPT header - fails in the DATA phase (command phase passed:
  RSPTYP=R1 response OK, no CMDTMO/RSPCRCERR), then
  `panic(cpu 0 caller 0xfffffe0007a42a5d): "root msdcroot0 unavailable: 5"
  @IOKitBSDInit.cpp:736`. The `:5` = EIO returned by our driver; the
  panic site = our patched IOKitBSDInit.cpp branch (verified against
  the patch source). NOT an iosroot.img problem - the driver never got
  past its first 512-byte read.
- ROOT CAUSE (from reference code): we never wrote SDC_BLK_NUM (0x50).
  The stock MT6768 driver writes it before EVERY data command
  (research/msdc-ref/sd.c, msdc_do_request_prepare, ~line 3004:
  `MSDC_WRITE32(SDC_BLK_NUM, data->blocks)`). LK left its count from
  the boot-image read (multi-block); our CMD17 with DMA_LEN=512 then
  streams LK's count x 512 bytes - once our 512 B buffer is full the
  DMA stops draining and the FIFO overflows -> DATCRCERR/DATTMO.
  Exactly our signature. High confidence: not a guess - the register
  semantics come from the real driver.
- Reference sources (gitignored, research/msdc-ref/): sd.c 147 KB +
  msdc_reg.h 57 KB + msdc_io.h 7 KB from UBports
  ubports/porting/community-ports/android11/xiaomi-redmi-9/
  kernel-xiaomi-mt6768 branch halium-11
  (drivers/mmc/host/mediatek/ComboA/; Xiaomi never released merlin's
  sources - MiCode request issue still open; this tree is the same
  MT6768 SoC).
- Cross-checks vs reference (all CONFIRMED correct): our SDC_CMD word
  = 17 | 1<<7 (RSPTYP R1) | 512<<16 (BLKLEN bits 27:16) | 1<<11
  (DTYP single block) matches msdc_reg.h fields; our basic-DMA shape
  matches the stock MSDC_MODE_DMA_BASIC path one-for-one (SA_HIGH low
  nibble, SA low 32, LASTBUF, DMA_LEN, BRUSTSZ=6=64 B burst,
  MODE bit=0); DMA offsets verified (SA_HIGH 0x8c SA 0x90 CA 0x94
  CTRL 0x98 CFG 0x9c LEN 0xa8).
- Patch edited (xnu/patches/0082-merlin-msdc-root.patch, local +
  copied into ios-sweet): (1) `msdc_wr(SDC_BLK_NUM, 1)` + comment
  before the SDC_ARG/SDC_CMD go-write in msdc_read_sector; (2) added
  `#define MSDC_DMA_CA 0x94`; (3) enriched the data-failed printf to
  dump int/sts/dcfg/ca/fifocs so any NEXT failure self-identifies.
  Only '+'-lines changed; both hunks' context lines are untouched from
  the last CI-validated build.
- Patch-file hygiene fixed: git apply (strict) rejected the file the
  CI's `patch -p1` (lenient) had tolerated - hunk counts were 1-off
  and a trailing-empty line. research/tmp-msdc-split/fix-hunk.py now
  keeps counts internally consistent: hunk1 (IOKitBSDInit.cpp)
  old7/new25, hunk2 (sweet_ufs.c add) old4/new608, 641 lines, ends
  with single newline. Local `git apply --check` still fails ONLY with
  "No such file" for iokit/bsddev/IOKitBSDInit.cpp +
  bsd/dev/sweet_ufs.c (files created by earlier patches 0028+ in the
  chain) - can't simulate the full local chain (research/xnu-8796 is
  osfmk/pexpert only); residual risk accepted, CI runs make -k.
- D:\things\Merlin\ios-sweet: branch msdc-0079 (tracks fork/msdc-0079
  = 531e93f) now has commit f2a9322 "msdc: write SDC_BLK_NUM=1 before
  data commands + failure diag dump". NOT pushed.
- IMPORTANT workflow fact: .github/workflows/xnu.yml push trigger
  fires ONLY for branches: [main] (paths xnu/patches/**). Branch
  builds are therefore triggered via workflow_dispatch on the ref:
  POST /repos/Gytis283123/ios-sweet/actions/workflows/xnu.yml/
  dispatches body {"ref":"msdc-0079"} (gho token has workflow scope;
  dispatch uses the workflow's defaults: DEVELOPMENT/SWEET/13.5,
  make -k). Build ~30-60 min -> artifact xnu-kernel.
- BLOCKED on user decision: pushing msdc-0079 to the fork + running
  the CI build (same loop previous sessions used).
- After CI: download artifact via tools/fetch-kernel-artifact.py (GET
  <repo> <artifact_id> <destdir>), mkpayload from the NEW
  kernel.development.sweet with adt.bin (research/tmp-msdc-split/) +
  cmdline `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam
  -noprogress rd=msdcroot0`, NO --ramdisk; mkbootimg with the same
  header set as shim-boot-merlin-msdc-noconsole.img (page 2048,
  kernel 0x40080000 + kernel_size, ramdisk 0x47c80000, dtb_addr
  0x4bc80000, os_version 11.0.0, patch 2021-07); verify via
  unpack_bootv2, then boot (cold power-off first) and photograph.

## Agent handoff / active work (2026-10-24 LATEST-32: E1 VERDICT - THE FBCON-1X BINARY PATCH WAS THE SUM16-FREEZE KILLER; BOOT REACHES MERLIN MSDC AND DIES AT AN EXPLICIT PANIC; PANIC TEXT PHOTO PENDING)

- E1 result (research/merlin-boot/shim-boot-merlin-msdc-noconsole.img,
  the surgical A/B: ONLY the fbcon-1x patch removed): THE BOOT DID NOT
  FREEZE. It sailed through the exact point where the msdcroot0 image
  always stopped (SUM16 ... PASSED), printed the full
  ifnet_attach "have been scheduled at least once / Proceeding."
  sequence for lo0/gif0/stf0, Skywalk self-tests PASSED,
  `bsd_autoconf: calling kminit`, then MERLIN MSDC lines appear (the
  0082 driver code finally EXECUTED - it never ran in any earlier
  boot), and the boot ends in an EXPLICIT kernel panic screen (banner
  "...report this panic" visible) instead of a silent freeze.
- VERDICT: the fbcon-1x binary patch on the msdc-0079 kernel is guilty
  of the SUM16 freeze. Implication for bring-up: keep the stock scale-2
  console for msdcroot0 boots; the 1x patch is not worth re-deriving
  until after iOS boots.
- The first (blurry) photo allowed reading the stage progression but not
  the panic message. User is taking one clear photo of the panic screen
  (it persists until reboot). Parse pending: panic(pc/caller/user
  message, backtrace) and the MSDC/GPT/BSD-root lines around it.
- Next-step forks by panic content:
  (a) root mount failure / IOFindBSDRoot messages -> iosroot.img state
      issue (remember the userdata flash ended with a last-chunk sparse
      write failure - only the alternate HFS+ header missed, primary
      intact). Likely fix = re-flash iosroot.img (FLASH = explicit user
      confirmation) or mount-side tweak.
  (b) data abort / register fault inside the MSDC driver -> missing
      clock/power gating for MSDC0 in the bare-metal path; instrument
      or gate cfg bits.
  (c) launchd/panic later than mount -> read the message first.
- Environment facts for reading console photos: stock scale-2 console
  ring-wraps (newest lines at top after wrap, oldest at bottom); photos
  are rotated 90 deg.

## Agent handoff / active work (2026-10-24 LATEST-31: FETCHER FIXED + UNPATCHED 0079+0082 KERNEL BACK FROM CI + E1 NO-CONSOLE MSDC IMAGE BUILT - A/B PAIR SURGICAL; PHONE TEST NEXT)

- User truth (confirmed): the msdcroot0 image froze AGAIN at
  `DLIL: running SUM16 self-tests ... PASSED` after a cold power-off,
  and the very next cold boot of the dlilplain image reached userspace
  (LATEST-30). Environment no longer explains the msdc image's freeze.
  Remaining candidates: the fbcon-1x BINARY PATCH vs the
  0082-compiled-in code/layout.
- tools/fetch-kernel-artifact.py FIXED: urllib forwarded the GitHub
  Authorization header on the cross-host 302 to the signed Azure blob
  URL (productionresultssa15.blob.core.windows.net) and Azure 401s
  ("Server failed to authenticate... www-authenticate" = an AZURE
  error). fetch() now follows redirects via a _NoRedirect opener and
  drops auth on cross-host hops. curl.exe always dropped it - that is
  why the docstring route worked on Oct 18. GitHub metadata calls
  (list) worked all along with the same gho_ token.
- Artifact 12519256732 (msdc-0079 run 39991300459) re-downloaded to
  research/art-msdc-0079/ (zip 60,029,832 B):
  kernel.development.sweet SHA256
  65c85ab77bc5d0ae74447efb22644cf06f86749af59e9f489c318f3e62c8507b =
  recorded value. Also kernel.development.sweet.link/, SHA256SUMS/,
  kdk-libs/. The UNPATCHED 0079+0082 kernel Mach-O is thus locally
  available again (no CI build needed for A/B experiments).
- PACKED-KERNEL DISSECTION of the stuck image (unpack_bootv2 ->
  research/tmp-msdc-split/; scripts split.py, payload-diff.py,
  adtpeek.py live there): payload = 16,611,984 B SWEETXNU v1, nsegs=10
  = KERNEL SEGMENTS ONLY (seg9 = __LINKEDIT 3,887,000 B at 0xc203f0),
  **NO embedded ramdisk** - correct for rd=msdcroot0 (roots on
  iosroot.img, not a mockfs). The earlier "last seg = merlin-init" read
  was WRONG; bogus merlin-init.bin / payload-noconsole.bin /
  payload-md0.bin and the invalid
  shim-boot-merlin-msdc-fb1x-0079-rdmd0.img were DELETED.
  cmdline at payload 0x48 (debug=0xc serial=3 cpus=1 keepsyms=1
  -enable_kprintf_spam -noprogress rd=msdcroot0); ADT at 0xfd5390 =
  9,976 B merlin-phone-msdc.adt WITH /product (identity theory
  weakens) + /merlin-msdc reg 0x11230000 + sweet-fbcon reg 0x7e605438
  1080x2340 stride 4320.
- QEMU check of the patched payload (qemu-shim shim/out-qemu-phone,
  research/tmp-msdc-qemu/): kprintf init, console 0x7e605438 w=1080
  h=2340, then EARLY abort at `pe_arm_map_interrupt_controller: failed
  to find the interrupt-controller` -> data abort (esr 0x56000010,
  far 0xfffffe000b380000, pc 0xfffffe0007a79a20, SWEET GIC virtual
  timer INITID before it). EXPECTED: payload carries the PHONE ADT;
  QEMU virt GIC regs differ. So QEMU cannot cross-examine the DLIL
  region for this payload as-is; a hybrid-ADT rebuild (mkpayload with
  a mkadt --qemu-gic ADT) is now POSSIBLE (kernel Mach-O available)
  but optional.
- E1 (splits fbcon-patch vs 0082-layout): research/tmp-msdc-split/
  payload-noconsole2.bin built by mkpayload (CI kernel + extracted
  ADT + original cmdline, NO --ramdisk) = 16,611,984 B, byte-size
  identical to the stuck payload, same kernel_end 0xfffffe00084cc000,
  same seg table; payload-diff.py: all differing bytes confined to
  0xa77ed4..0xa78384 (~1.9 KB in __TEXT_EXEC = the two patched fbcon
  functions) - PURE A/B. Packed with the same shim blob (190,674 B)
  and dtb (181,203 B) into research/merlin-boot/
  shim-boot-merlin-msdc-noconsole.img (16,990,208 B), verified by
  unpack_bootv2 (header mirrors the stuck image, ramdisk 16,611,984,
  rd=msdcroot0 intact).
- NEXT: cold power-off; fastboot boot
  research/merlin-boot/shim-boot-merlin-msdc-noconsole.img; watch
  >= 5 min; photo the settled screen bottom. MSDC/GPT/BSD-root lines
  visible -> the CONSOLE PATCH was the killer (then drop 1x for
  bring-up, or re-derive it for this kernel). Still frozen at SUM16 ->
  0082-compiled-in suspect -> merge 0083 DLIL prints onto msdc-0079
  (needs push + CI build = user approval). If clear to launchd ->
  first real iOS userspace on iosroot.img.
- Commit: "fetch-kernel-artifact: drop auth on cross-host artifact
  redirects; notes LATEST-31" (research/ paths are gitignored; only
  the tool fix + notes go in).

## Agent handoff / active work (2026-10-24 LATEST-30: DLILPLAIN BOOTS PHONE TO USERSPACE - DLIL THREADS VERIFIED RUNNING ON HW; MSDC COLD-RETRY OUTCOME PENDING)

- Photo (rotated 90; read with ring-wrap semantics - the dlilplain kernel
  uses the STOCK scale-2 console, newest lines wrap to the TOP):
  **research/merlin-boot/shim-boot-merlin-dlilplain.img (a00abe2+0083
  DLIL-instrumented kernel, rd=md0) booted the phone ALL THE WAY TO
  USERSPACE.** Visible chain: `DLILDBG: detacher func entered` /
  `detacher lock taken` / `detacher block now` / `main cont embryonic,
  decr` -> `dlil_init: All the created dlil kernel threads have been
  scheduled at least once. Proceeding.` -> `SK101: skmem_region_init` ->
  full Skywalk self-test battery PASSED -> `bsd_autoconf: calling
  kminit` -> ifnet_attach waits for lo0/gif0/stf0 all `Proceeding.` ->
  `BSD root: md0, major 1, minor 0` -> userspace `MERLIN init: still
  alive` x6 (newest lines at the top post-wrap).
- This ANSWERS LATEST-23's open question for the healthy case: the DLIL
  main input + detacher threads get created, scheduled AND call
  dlil_decr_pending_thread_count - scheduler and locks fine in principle.
  Also re-proves environment sensitivity: the same phone that freezes at
  SUM16 in other boot states boots the instrumented kernel cleanly.
- PENDING (asked the user): was the msdcroot0 image
  (shim-boot-merlin-msdc-fb1x-0079.img) cold-retried BEFORE the dlilplain
  boot, and did it still freeze at SUM16? Fork:
  (a) still frozen at SUM16 (cold) -> the 1x fbcon binary patch on the
  msdc-0079 kernel is a suspect (a console-side hang looks identical:
  last printf drawn, kernel may live on; note LATEST-23's Test C only
  exonerated the console for the OLD dlil-region hang, which is one step
  LATER than this one). Next: pack a no-1x-console msdc image locally
  from the unpatched kernel (xnu/out-0079 artifact) and/or merge 0083
  DLIL prints onto msdc-0079 (CI build, user approval).
  (b) not retried yet -> cold power-off, boot the msdc image first.
- The msdcroot0 boot remains the required next step for the LATEST-28
  questions (MERLIN MSDC/GPT/mount lines, `BSD root: msdcroot0`, iOS
  launchd on the flashed iosroot.img).

## Agent handoff / active work (2026-10-24 LATEST-29: MSDCROOT0 BOOT FREEZES RIGHT AFTER `DLIL: SUM16 ... PASSED` - BEFORE THE dlil WAIT PRINT; DLILDBG IMAGE = READY DISSECTION)

- **Correction of LATEST-28 + new datum**: "booted past the dlil hang" was
  never substantiated (the settled-bottom photo was pending). Today the
  user reports the msdcroot0 boot console freezes with
  `DLIL: running SUM16 self-tests ... PASSED` as the bottom line, watched
  ~5 min. Per dlil.c (research/tmp-gic/dlil.c, dlil_init ~2675-2715) and the
  healthy QEMU reference (abtest/fullfix60/fb.txt:72-75), the VERY next
  console line is `dlil_init: Waiting for all the create dlil kernel
  threads...` - it never printed. So the stop is in
  `dlil_create_input_thread` / detacher `kernel_thread_start` /
  `lck_mtx_lock(dlil_thread_sync_lock)` - a step EARLIER than the LATEST-23
  hang (which printed `Waiting...`), and nowhere near the MERLIN MSDC
  driver (no `MERLIN MSDC:` lines at all; storage questions unanswerable
  from this boot). Nothing in that window has a timeout; QEMU clears it
  instantly.
- Top hypothesis unchanged: environment-sensitive DLIL bring-up on warm
  boot (phone reached userspace once, hung repeatedly in this DLIL region,
  cold power-off un-stuck it once; QEMU unaffected with identical payloads).
- Non-destructive plan (fastboot boot only): (1) cold power-off -> (2) retry
  `shim-boot-merlin-msdc-fb1x-0079.img` (rd=msdcroot0; if it clears we get
  the MERLIN MSDC/GPT/mount + `BSD root: msdcroot0` lines finally);
  (3) if still stuck at SUM16, `fastboot boot
  research/merlin-boot/shim-boot-merlin-dlilplain.img` (a00abe2+0083
  DLIL-instrumented kernel, DLILDBG prints: created/pending, waiting,
  thread entry + decr lines; rd=md0; QEMU-validated to userspace) and
  photograph the settle point - that answers whether the DLIL threads get
  created and run at all (scheduler) or block on dlth_lock /
  dlil_thread_sync_lock. NOTE: dlilplain is a DIFFERENT kernel build and
  rd=md0 - it dissects DLIL, not the storage path.
- Fallback: merge the 0083 dlil-debug print patch onto the msdc-0079 branch
  (0079+0082) so one instrumented kernel boots rd=msdcroot0 directly;
  needs an ios-sweet CI build (push = user approval).

## Agent handoff / active work (2026-10-24 LATEST-28: PHONE BOOTED PAST THE DLIL HANG ON THE MSDCROOT0 IMAGE; IOSROOT FLASHED TO USERDATA (66/67 CHUNKS); AWAITING MSDC/GPT LOG)

- **The phone boots the msdcroot0 image past the dlil hang** (cold power-off
  fixed the environmental hang, as suspected): user photo shows
  `SWEET CPU: 1/1 CPUs initialized, 3313 verified`, MKC, SWEET policies,
  Skywalk self-tests PASSED - the exact stage of the LATEST-23 hang, now
  cleared.  Console = fb1x 135 cols (`SWEET FB: AppleCLCD 1080x2340
  stride 4320 at 0x7e605000`).  Next lines expected: MERLIN MSDC driver
  init + GPT scan + `BSD root: msdcroot0` + real iOS launchd.  Photo
  pending of the settled screen bottom.
- **userdata was flashed with iosroot.img by the user** (their decision,
  no backup): 66/67 sparse chunks wrote OK; the LAST chunk (60752KB)
  FAILED `remote: 'sparse image write failure'`.  Analysis of the image
  tail: the final 512MB contains ONLY 4KiB of real content = the
  alternate HFS+ volume header (repair backup at volume end); the primary
  header (chunk 1) and all file data (chunks 1-66) are on the eMMC, so
  the HFS volume is very likely mountable.  Failure cause unconfirmed -
  leading theory: write range crossed the partition end (userdata may be
  SMALLER than 16GB; the notes' "22.8 GiB" was never verified on
  hardware).  The GPT scan from this boot settles it.
- **The eMMC GPT still holds Windows-on-ARM leftovers**: user reports
  `win` 22.1GB + `esp` 4GB partitions carved out (the phone ran WOA
  before).  User wants userdata grown back (~64GB eMMC).  Plan: read the
  real GPT from the boot log -> confirm win/esp disposable with the user
  -> mtkclient GPT surgery (delete win+esp, extend userdata) -> rebuild
  iosroot.img at the final size (mkiosroot.sh OUT SIZE) -> re-flash.
  Growing the partition does NOT grow the HFS+ fs inside.
- Android userdata is overwritten regardless (MIUI unbootable; no backup
  was taken).  Empty-Android restore path exists: stock ROM tgz OS
  partitions + `fastboot format userdata` - personal data unrecoverable.
- NEXT: photo of the settled boot -> MERLIN MSDC/GPT/mount lines decide:
  (a) mount OK -> iOS userland live, then plan the resize+reflash;
  (b) mount fail/GPT shows userdata<16GB -> rebuild image to fit or
  resize first via mtkclient.

## Agent handoff / active work (2026-10-24 LATEST-27: IOSROOT.IMG BUILT - HFS+ iOS 16.7.16 ROOTFS READY FOR FLASH; WSL HFSPLUS MODULE RECIPE)

- **research/ipsw-x/iosroot.img EXISTS**: 16 GB journaled case-sensitive
  HFS+ volume, 8.6 GB used, holds the full 16.7.16 A11 rootfs copied out
  of the OS dmg via apfs-fuse + rsync (built as /root/iosroot.img in WSL
  ext4, copied to D:).  fsck.hfsplus -f -y: "appears to be OK".  NOTE:
  `fsck.hfsplus -n` on ANY journaled volume (even fresh mkfs) reports
  "Volume header needs minor repair (1,0)" - verified with a control
  volume; it is the mkfs-inherent inconsistent bit (attr 0x80002100) so
  the first mount replays the journal.  XNU replays journals; not a
  defect.  The mkiosroot.sh recipe ends with that -n and will exit 8 -
  ignore/rerun-tolerate.
- WSL kernel has NO hfsplus (Microsoft kernel).  Fixed by building the
  module out-of-tree: clone microsoft/WSL2-Linux-Kernel at tag
  linux-msft-wsl-6.18.54.1 (= running kernel), cp Microsoft/config-wsl
  .config, scripts/config -m HFSPLUS_FS, make olddefconfig, make -j
  modules_prepare, then build via a STANDALONE Kbuild dir (/root/hfsmod:
  obj-m := hfsplus.o + the fs/hfsplus/Makefile object list) - building
  M=fs/hfsplus in-tree silently builds nothing; KBUILD_MODPOST_WARN=1
  needed (Module.symvers missing, MODVERSIONS=y but insmod accepts).
  insmod /root/hfsmod/hfsplus.ko works; the copy into /lib/modules
  VANISHED after a WSL VM idle-restart (quirk) - insmod the file
  directly in every new VM session.
- Other fixes that were needed on the way:
  - **CRLF**: git autocrlf checked ALL .sh out with CRLF; `set -euo
    pipefail\r` kills every shell.  Added .gitattributes (*.sh/*.py/*.S/
    *.ld = LF), de-CRLF'd the working tree (commit 790f233).
  - mkiosroot.sh: `-` cryptex args must be compared BEFORE realpath;
    coreutils rejects `install -o <numeric>` ("invalid user: 272") - the
    logd/keybag steps now use python os.chown (committed).
  - WSL VM idle-restarts drop manually insmod'd modules - scripts must
    insmod at start.
- fastboot/adb on this PC: "D:\things\ADB Tools % odin\PlatformTools\
  platform-tools\".  NOT needed yet.
- NEXT: (A) msdc driver hardware log - cold power-off, `fastboot boot
  research/merlin-boot/shim-boot-merlin-msdc-fb1x-0079.img`, photograph
  the `MERLIN MSDC:` + GPT lines (non-destructive).  (C) deploy needs
  the user's explicit OK: `fastboot flash userdata research/ipsw-x/
  iosroot.img` WIPES ANDROID USERDATA (~15-25 min over USB), then
  `fastboot boot` the same image - kernel mounts /dev/msdcroot0, real
  iOS launchd becomes PID 1.  Recovery mode is NOT involved; boot/
  recovery/modem/persist stay untouched.

## Agent handoff / active work (2026-10-24 LATEST-26: QEMU GUI CONFIRMED BY USER; NEXT = MSDC HW TEST + IOSROOT BUILD)

- User confirmed the fixed GUI: the 1080x2340 window boots past the old
  sched-hygiene panic (wdt=-1) through Skywalk self-test (all PASSED -
  the dlil wait completes in QEMU) to `load_init_program: attempting to
  load /sbin/launchd`.  Gotchas fixed on the way (commit 514bd69):
  `--gui` now runs 600 s by default, and this payload's console is on
  the phone plane - `--fb-base 0x7e605000` is REQUIRED for ramfb/dump
  (default 0x9c000000 shows blank).
- mkiosroot.sh now accepts `-` for SYSTEMOS.dmg/APPOS.dmg: the 16.7.16
  A11 IPSW has NO cryptex dmgs (checked via zipremote against the Apple
  CDN: only the 4.731 GB OS dmg + small recovery dmgs), so the merlin
  build is `mkiosroot.sh research/ipsw-x/087-86698-044.dmg - -
  research/ipsw-x/iosroot.img 16G`.  WSL check: rsync present; apfs-fuse
  and hfsprogs MISSING (one-time sudo install; apfs-fuse must be built
  from github.com/sgan81/apfs-fuse: cmake g++ libfuse3-dev libb2-dev
  libicu-dev).
- The msdc read-path test image exists and is untested on hardware:
  research/merlin-boot/shim-boot-merlin-msdc-fb1x-0079.img (0079+0082,
  rd=msdcroot0).  Previous attempt stopped at the environmental dlil
  hang before the driver ran (LATEST-23) - cold power-off first, then
  `fastboot boot`, read/photograph the `MERLIN MSDC:` + GPT lines.
  "HFS mount fails" is the SUCCESS signal (userdata is still Android).
- Order to iOS userland: (A) msdc hardware log (non-destructive) ->
  (B) build iosroot.img in WSL (needs user sudo) -> (C) WRITE iosroot.img
  to the userdata partition (DESTRUCTIVE - fastboot flash userdata wipes
  Android userdata; confirm with the user first) -> boot rd=msdcroot0,
  launchd = real iOS PID 1.

## Agent handoff / active work (2026-10-24 LATEST-25: QEMU GUI PANIC ROOT-CAUSED - SCHED-HYGIENE VS TCG STALL; RUNNERS NOW BOOT --gui WITH wdt=-1)

- The 1080-wide GUI panic screenshot ("Processing of an interrupt (type =
  2, handler address 0xfffffe00079495xx, vector = 0) took 47934992 ns ...
  timeout = 13631488 ns @machine_routines_common.c:839", right after
  "IOKit IOMD setownership ENABLED"/BNK/IPC_PTHREAD_PRIORITY, i.e. mid
  kernel_bootstrap) is XNU's sched-hygiene watchdog, not a driver bug.
  Facts from the xnu-8796.141.3 source (sparse clone kept at
  research/xnu-8796, gitignored):
  - DEVELOPMENT kernels build SCHED_HYGIENE_DEBUG with
    interrupt_masked_debug_mode defaulting to SCHED_HYGIENE_MODE_PANIC
    (osfmk/arm/arm_init.c, TUNABLE "interrupt-masked-debug-mode").
  - The deadline is MACHINE_TIMEOUT "interrupt-masked" = 0xd0000
    timebase ticks; at QEMU virt's 62.5 MHz counter that is 851,968 /
    62.5 MHz = 13.631 ms - exactly the printed "timeout = 13631488 ns".
  - On interrupt exit, ml_handle_interrupt_handler_duration() panics when
    the handler straddled more than the deadline.  Under GTK/ramfb the
    ~10 MB console plane repaint (plus the fbcon scroll) stalls the
    single TCG vCPU for tens of ms, so whichever handler was in flight
    (timer/console bystander - the address is not a buggy driver)
    measures 47.9 ms and the kernel panics.  This also explains
    LATEST-24: 1080x2400 panicked (~17 ms case), 540x1200 survived only
    because the stalls stayed under the deadline.
- The rest of the panic screen is benign fallout: "handshake structure
  not initialized" = osfmk/kdp/output_stages/out_shmem.c (no hw
  debugger), "debug_log_init: Error!! gPanicBase is still not
  initialized" = osfmk/kern/debug.c ordering, "Original panic string:" =
  double-panic bookkeeping.
- FIX (no kernel change needed): boot-arg `wdt=-1` - arm_init.c maps it
  to interrupt_masked_debug_mode = OFF AND
  sched_preemption_disable_debug_mode = OFF (also disables the
  zone-exhaustion timeout via zalloc.c; pexpert does not read "wdt").
  Softer alternatives that keep diagnostics: boot-args
  ml-timeout-interrupt-masked=<picoseconds> or
  ml-timeout-global-scale=<factor> (MACHINE_TIMEOUT scheme, startup.h).
- Implemented in the runners: tools/qemu-merlin.py and tools/qemu-shim.py
  gained append_cmdline() + `--cmdline-append`; `--gui` now appends
  `wdt=-1` automatically (opt out with `--strict-hygiene`).  qemu-shim
  writes the patched payload copy to OUT/payload.bin when the cmdline
  changes (the shim copies the payload cmdline into boot_args verbatim,
  shim/loader.c:428).
- Validated: qemu-payload-fb1x2.bin + `--cmdline-append wdt=-1` boots
  headless to userspace (research/tmp-gic/q-wdt-smoke2: "MERLIN init:
  still alive", exit 0).  NOTE: that payload's ADT is the phone plane -
  console at 0x7e605000 1080x2340, so dump/decode with `--fb-base
  0x7e605000 --fb-geom 1080x2340 --font-scale 1` (default 0x9c000000
  dump reads a blank plane).
- NEXT: rerun the GUI: `python tools/qemu-merlin.py
  research/tmp-gic/qemu-payload-fb1x2.bin research/tmp-gic/qgui2340-fix
  --gui --fb-base 0x7e605000 --fb-geom 1080x2340 --kernel
  xnu/out-0001/kernel.development.sweet --font-scale 1` - the
  `--fb-base 0x7e605000` is REQUIRED for this payload (its ADT puts the
  console on the phone plane; the ramfb window and the post-run dump
  default to 0x9c000000 and show/decode blank otherwise).  `--gui` now
  also defaults to a 600 s session (--secs overrides).  Should reach
  userspace with the readable 135-column console; keep 540x1200 +
  q-adt-540.adt as the low-load fallback for slow hosts.  Validated
  headless with the corrected flags: research/tmp-gic/qgui2340-fix-hl
  boots to `*** MERLIN userspace: init running as PID 1 ***`.

## Agent handoff / active work (2026-10-23 LATEST-24: QEMU GUI LIVE VIEW; 1x CONSOLE FRAGILE ON 0083; PHONE HANG ENVIRONMENTAL)

- **QEMU now has a live, readable GUI**: `tools/qemu-merlin.py --gui`
  boots the proven direct-loader path with `-display gtk,zoom-to-fit=on
  -device ramfb`; the guest side configures QEMU's ramfb from a small
  pre-boot blob (`tools/qemu-ramfb.s` -> `tools/qemu-ramfb.bin`, loaded
  at 0x40180000) that the generated stub calls with the fb base/w/h/
  stride before entering the kernel.  `--fb-geom WxH` sets
  boot_args/ramfb/decode geometry (the 1080x2400 default works, but see
  below).
- 1080x2400 GUI runs panic in XNU's sched-hygiene check
  (`Processing of an interrupt ... took ~17 ms`,
  osfmk/arm/machine_routines_common.c): QEMU's ramfb scanout of the
  10 MB plane stalls the vCPU.  **540x1200 + a matching ADT** (make one
  by patching `sweet-fbcon`: width 0x21c, height 0x4b0, stride 0x870,
  reg size 0x278d00; saved as research/tmp-gic/q-adt-540.adt) boots to
  userspace without the panic; with the stock 16x32 console the 540-px
  window is readable.  MTTCG (`-accel tcg,thread=multi`, now default in
  the runner) alone did not stop the stall.
- **The 1x/scroll console patch crashes the 0083 debug kernel in early
  boot** (`SWEET EARLY PANIC: Invalid kernel stack pointer` right after
  `serial_init returned`, pc in early boot) while the unpatched kernel
  boots.  Guards added in tools/fbcon-1x.S (rows clamp, skip clear when
  fb base/stride/cols are unset, skip newline when rows==0) let the
  kernel reach `kprintf startup complete`, but the console then stays
  silent (transmit guard sees cols==0), so this patch is still not
  usable on the 0083 kernel.  Use the stock console for diagnostics.
- Consequently the phone screens from the 1x-patched dlildbg/dlildbg2
  images were **stale framebuffers** from the previous session (the
  kernel died before touching the FB).  `shim-boot-merlin-dlilplain.img`
  = the unpatched a00abe2+0083 kernel + adt-0022 + merlin-init +
  rd=md0; it boots in QEMU to userspace and prints the DLILDBG lines
  (`created, pending=2`, `waiting, pending=2`, thread entries, decr).
- The phone hangs at the dlil wait even with the proven 0022 image, so
  the trigger is phone state/timing, not the kernel build; QEMU boots
  the same kernels.  The phone's DLILDBG screen from dlilplain is the
  pending datum: if the threads never print `main func entered` the
  scheduler never runs them; if they stop at `main lock taken` the
  dlth_lock is held.

## Agent handoff / active work (2026-10-23 LATEST-23: dlil THREAD-SCHEDULING HANG, ENVIRONMENT-SENSITIVE; NOT THE DRIVER)

- The `rd=msdcroot0` image on the proven base (a00abe2 + 0082 + 1x
  console) still stops at `dlil: Waiting for all the create dlil kernel
  threads to get scheduled at least once.` - same point as
  0079+0082.  Test C (0079+0082, **no** console patch) stops there too,
  so the console is exonerated (and QEMU boots the same kernel to
  userspace).
- **The known-good 0022 image now also hangs at the same dlil line**
  (user, 22:0x, after 5 min), although the same file booted to userspace
  at 18:18.  So the hang depends on phone/boot state or timing, not only
  on the kernel build.  The 0022 file is untouched since 18:11.
- Provenance: the Oct 18 kernel that booted is dipa-studio run
  39154142684, commit **a00abe2 = 0079 + upstream 0080 (net trace)**.
  A rebuild of a00abe2 today is **byte-identical in every loaded
  segment** (`__TEXT_EXEC`, `__DATA`, `__BOOTDATA`, `__KLD`, ...) to the
  Oct 18 artifact; only `__TEXT` metadata and an empty `__CTF` differ.
  Both builds used Xcode 15.0.1 / MacOSX14.0.sdk.  So CI is reproducible
  and the toolchain did not change.
- Layout facts: +0082 grows `__TEXT_EXEC` by ~0x1040 and `__DATA` by
  0x4000; fbcon/globals move with it (see tools/fbcon-1x.ld).  The
  payload's kernel_end moves +0x4000, so the ADT/boot_args PA moves by
  the same amount (mkpayload places them at kernel_end).
- `dlil_init()` creates the main input thread and the ifnet detacher
  thread, then waits (msleep on dlil_pending_thread_cnt) for both to be
  scheduled and call `dlil_decr_pending_thread_count()`.  Both threads
  are created (no panic from kernel_thread_start); the hang is that they
  never reach their decrement.
- Diagnostic build in progress: branch **dlil-debug** = a00abe2 + a
  temporary 0083 patch (prints in dlil_init, the wait loop, both thread
  entry funcs and their continuations), CI run 40008642131.  The first
  attempt's hand-written patch was rejected (`corrupt patch at line
  47`); it is now generated with diff from xnu-8796.141.3 sources.
- NEXT: boot the dlil-debug kernel and read the `DLILDBG:` lines to see
  whether the threads run at all (scheduler) or block on dlth_lock /
  dlil_if_lock.  Also try a cold power-off before the boot: if a cold
  cycle restores the 0022 boot, the trigger is warm-boot state.

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
