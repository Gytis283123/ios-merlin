# iOS 16 on merlin (Redmi Note 9, MT6768 / Helio G85) - working notes


## Agent handoff / active work (2026-10-31 LATEST-98: 0114 BOOT READ AT 40 MIN - argv[0] OUTCOME FIX WORKS (mediaserverd STARTED, REAL PATHS EVERYWHERE); MEDIASERVERD'S STREAM ENDS IN A TIGHT LOOP OF EMPTY 0x20000000 SENDS = SOMETHING FAILS REPEATEDLY, LIKELY A MISSING DESTINATION PORT (AUDIO STACK); SPRINGBOARD t0 FROZEN 7TH BOOT; 0115 = LOG mach_msg2 SEND RESULTS FOR THE TRACED TRIO)

### 0114 boot log (observation; research/logs/sweetlog-0114-20261031.{bin,txt}, pulled at flush 245 = 2,441 s)

- argv[0] outcome fix verified on hardware: outcomes now carry real
  paths (/usr/sbin/fairplayd.H2 241x, /usr/sbin/bluetoothd 240x,
  CoreTelephony/Session/Calendar frameworks...), and **`SWEET EXEC:
  mediaserverd started` exists** (1 hit, /usr/libexec/mediaserverd) -
  mediaserverd's exec completes.
- mediaserverd traced (pid 29): 1,287 sends / 885 recvs of normal XPC
  dispatch traffic (same id families as SpringBoard: 3405, 200, 206,
  3418, 8000, 412...), then its stream ENDS in a tight loop of
  **`send id=536870912 (0x20000000) sz=0`** repeated - an empty send
  attempted over and over. Not a recv wait: a repeatedly FAILING send
  (classic invalid-destination signature when the target service was
  never registered).
- SpringBoard t0 STILL frozen: slide 0x2f304000, 0x1f1915030 -
  0x2f304000 = 0x1C2611030, 7th boot. send id=40232 count 24, still no
  828-byte reply anywhere.
- Working chain hypothesis: SpringBoard/backboardd -> MediaRemote 40232
  -> mediaserverd -> mediaserverd's own sends fail (audio stack missing
  in this port - no audio driver) -> nothing replies anywhere.

### Next (0115)

1. Patch: log the mach_msg2 SEND RESULT (error code) for the traced trio
   (SpringBoard/backboardd/mediaserverd) - a failed send returns
   MACH_SEND_INVALID_DEST / MACH_SEND_TIMED_OUT etc.; hook at the
   syscall return (careful: same lock-safety rules; the return value is
   available where mach_msg2_trap returns) or capture the kernel-side
   error in mach_msg2_kernel's exit path filtered by pid.
2. An INVALID_DEST result on mediaserverd's 0x20000000 loop names the
   missing service; then check launchd/registry for who should own that
   port (audio server: mediaserverd itself hosts AudioServer? or
   appleh13camerad/IOAudio family missing) and stub it (0116), same
   playbook as the GPU stubs.
3. Keep: early pull (~15 min), argv[0] outcomes, mediaserverd in tracer.

## Agent handoff / active work (2026-10-31 LATEST-97: 0114 PACKED - EXEC OUTCOMES NOW NAME THE REAL BINARY (argv[0], hook before free - 0109 logged every daemon as xpcproxy) + MEDIASERVERD JOINS THE MACH TRACER; message 40232 identified as MediaRemote-family (media frameworks); image shim-boot-merlin-msdc-0114-execnames-cpus8-fbup-585.img D8CC8497 READY)

### The 40232 identification (observation, from the RE scan artifacts + image mapping)

- The second RE agent also died silently (no FINDINGS.md), but its
  intermediate scans survived in research/tmp-re2/ and finished the job:
  `scan_imm2.out` lists movz-immediate hits for the 40224..40232 id
  family, and mapping the hit addresses through `images.json` puts them
  in MediaPlayer / MediaToolbox / iTunesCloud / JavaScriptCore / Apple
  MediaServices - a **MediaRemote-family MIG subsystem**. Message 40232
  (40-byte request, 828-byte reply nobody sends) is a media-stack call;
  both SpringBoard (now-playing UI) and backboardd (lock-screen
  controls) send it.
- mediaserverd execs early (log line 814) and is alive all boot (AKS
  calls at lines 3373..12492) - not a startup race. It simply never
  answers.
- Exec-outcome mislabel root-caused: 1,056 "xpcproxy started" outcomes
  for 528 spawn waves = two per wave - the daemon's own exec outcome
  printed with the stale spawner name (posix-spawn-in-place). Daemons DO
  complete execs.

### 0114 (action; msdc-0114 @ `8b07a69`, CI run 41231878288 SUCCESS)

- `xnu/patches/0114-merlin-trace-v3.patch` (two files):
  - kern_exec.c: the exec-outcome hook moves to right after the
    `bad_notrans:` label (BEFORE execargs_free) and names the image from
    `imgp->ip_startargv` (argv[0], %.40s) instead of the stale p->p_name.
  - mach_msg.c: **mediaserverd joins the Mach tracer filter** (its own
    send/recv stream shows what the expected reply producer is itself
    waiting for).
- Attempt history this round: v1-v3 lost to edit-toolchain traps
  (orphan `#if` after relocating the hook -> "unterminated conditional
  directive"; CRLF autocrlf checkout mismatch; cwd resets). Final patch
  verified by ACTUALLY applying it with GNU patch and inspecting the
  result: #if/#endif 124/124, braces 834/834 and 153/153, argv[0]
  strings present, old hook gone.
- Process notes: `fetch-kernel-artifact.py latest` is NOT time-ordered
  (returned the failed run's 178 KB artifact - check size + run
  timestamp, fetch by explicit id); `git apply` silently does nothing
  when cwd is not the intended tree - verify with GNU patch applied for
  real and grep the result.
- Kernel sha256
  `37e55dab7bd0583f5f2e0e8073f17ba065d9f7267335b7972ed332be5342876d`
  (SHA256SUMS match); %.40s + MSG828 strings verified in kernel,
  buildtree (kern_exec 2, mach_msg 1) and image.

### 0114 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0114-execnames-cpus8-fbup-585.img`,
  **17,052,627 B** (grew: argv-name strings), sha256
  `D8CC8497098CD07BB62F7973A4E75DC4370EE2E03B405E21F30B3939FC0409E1`,
  repack bit-exact, strings verified in the packed image.

### Next

1. User: `fastboot boot research/merlin-boot/shim-boot-merlin-msdc-0114-execnames-cpus8-fbup-585.img`
   (never flash), **~15 min only**, TWRP pull ->
   research/logs/sweetlog-0114-*.
2. Read: (a) `SWEET MSG` lines from **mediaserverd** - its sends/recvs
   around the 40232 window show what it waits for; (b) `SWEET EXEC:
   mediaserverd started` (real name now) to confirm the exec completes;
   (c) any `SWEET MSG828` from mediaserverd itself; (d) SpringBoard t0
   vs 0x1C2611030.
3. If mediaserverd is waiting on its OWN dependency (likely: audio
   hardware / IOAudioFamily / AppleH pipework this port lacks), the
   candidate 0115 is a mediaserverd-shaped stub answer or faking its
   dependency the same way the GPU stubs work - same pattern, one level
   up the chain.

## Agent handoff / active work (2026-10-31 LATEST-96: 0113 BOOT READ AT 16 MIN - SPRINGBOARD t0 STILL FROZEN AT 0x1C2611030 (6TH BOOT), SEL 33 ARGS CAPTURED (arg2 CONSTANT 0x34e5b, arg1 NONCE-LIKE), MSG828 HITS = UNRELATED XPC; AWAITING RE AGENT'S 40232 ANALYSIS)

### 0113 boot log (observation; research/logs/sweetlog-0113b-20261031.{bin,txt}, pulled at flush 99 = 980 s - EARLY PULL, the new rule: everything happens in the first minutes)

- Tracer filled its 20,000-line budget (flood fix worked: backboardd
  recvs gone, SpringBoard 777 lines unbroken).
- SpringBoard t0 STILL the frozen reference: slide 0x2b4e0000, pc
  0x1edaf1030 - 0x2b4e0000 = 0x1C2611030, 1 unique stack over 7 samples.
  The active SpringBoard message lines are OTHER threads: a repeating
  dispatch-drain cycle (recv 2440 -> 2720 -> 3372 growing) with sends
  536870912 x2 (sz=0), 268435456 (sz=0), 3240, 1073742536.
- **sel 33 arguments captured**: `sc=bc513372,34e5b` - arg2 CONSTANT
  0x34e5b (217,435) on every call, arg1 varies per attempt (nonce- or
  sequence-like 32-bit values). 24 sends of id 40232 this boot.
- MSG828 watch: only unrelated XPC traffic (coreduetd pid 104 id
  1073742224 sz 808-828; com.apple.migrat pid 121 id 1073742624 sz
  776-780). The real 828-byte reply to 40232 still never sent.
- Exec: 1,079 started, 3 benign ENOENT probes, SetupAssistant 0.

### Next

1. RE agent #2 (research/tmp-re2/FINDINGS.md when done) should name id
   40232's destination + the 828-byte reply's producer and contents;
   combine with arg2=0x34e5b.
2. If 40232 is IOKit-notification-gated (both ends waiting for the same
   message), the candidate fix is making the stub GPU services emit the
   notification (IOServiceNotificationUser delivery) - that would also
   explain backboardd's 279x re-registration loop.
3. If the reply's producer is a daemon that never starts, the exec
   outcome log already proves it is not exec-failing - it is either not
   launchd-scheduled or blocked on something else.

## Agent handoff / active work (2026-10-31 LATEST-95: 0112 TRACER LOG READ - THE SMOKING GUN: SPRINGBOARD'S FROZEN LOOP IS `send id=40232 (40 B)` -> `recv 828-BYTE REPLY` AND NO PROCESS EVER SENDS 828 BYTES; backboardd SENDS THE SAME ID; 0113 TRACER V2 PACKED - image shim-boot-merlin-msdc-0113-machmsg-v2-cpus8-fbup-585.img B4024D09 READY)

### 0112 boot log (observation; research/logs/sweetlog-0112-20261031.{bin,txt}, flush 365, tracer cap 4000 hit at log line 5694 of 14,884)

- **The stall, named:** SpringBoard's last captured pattern, repeated:
  `SWEET MSG: pid 27 (SpringBoard) send id=40232 sz=40` ->
  `recv id=0 sz=828` - it sends a 40-byte request with mach message id
  40232 (0x9D30) and waits for an 828-byte reply. This is the mach_msg2
  wait the sampler has shown since 0104.
- **No process ever sends an 828-byte message** (0 sends in 700..900
  window among the 4000 traced lines). The reply producer either never
  runs or was not traced (only SpringBoard/backboardd were).
- backboardd ALSO sends id 40232 (4x, 40 B) and 40231 (1x); both ends
  speaking the same protocol suggests an IOKit notification/ack that our
  stub GPU services were supposed to trigger, or an XPC transit whose
  third party is missing.
- backboardd flooded the cap (1,914 idle `recv id=0 sz=0` lines = its
  dispatch-loop waits; top sends: 205 312x, 2889 282x, 2880 236x, 2865,
  2802, 2810, 2809, 2801 - the 2800s family dominates; the 40331/40332
  448-byte loop interleaves with the IOAcceleratorES notification
  re-registrations (still 279x).
- SpringBoard's other traffic: 3405, 3418, 3410, 3409 (3400s family),
  1026, 3240, 4811, 40231/40232, 8000, and 0x40000000-prefixed ids.

### 0113 tracer v2 (action)

- `xnu/patches/0113-merlin-machmsg-v2.patch` (msdc-0113 @ `96bbccc`,
  CI run 41221803021 SUCCESS; v1 5acf81c2 failed compile - the edit
  anchor started at the sweet_msg_log signature line but the replacement
  re-added its own `static void`, leaving the original above it:
  "cannot combine with previous 'void' declaration specifier").
- Changes: backboardd idle recv waits no longer log; cap 4000 -> 20000;
  **any process's send in the 700..900-byte window logs as
  `SWEET MSG828: pid %d (%s) send id=%u sz=%u`** - if the missing reply
  producer ever runs, it names itself.
- One process note: fetch-kernel-artifact "latest" returned the FAILED
  run's 178 KB kernel artifact (artifact IDs are not time-ordered); the
  correct artifacts were fetched by explicit id (kernel 13049819091,
  buildtree 13049704128). Always check the artifact size AND the run's
  completion timestamp.
- Kernel sha256
  `d4301d5f4f0b6beb1430c4ce6c6a86f82128f9994a27639b9ead4954ef65b5f8`
  (SHA256SUMS match); MSG828 + SWEET MSG strings verified in kernel,
  buildtree (tar -O pipe) and image.
- Image `research/merlin-boot/shim-boot-merlin-msdc-0113-machmsg-v2-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `B4024D0961010868D1726F7733BBCDEBFA40703BB01C8318343A837436A50438`,
  repack bit-exact.
- RE agent (2nd attempt; the 1st died during setup with no output) is
  disassembling SpringBoard/backboardd for id 40232: destination, reply
  producer, reply contents. Findings -> research/tmp-re2/FINDINGS.md.

### Next

1. User: `fastboot boot research/merlin-boot/shim-boot-merlin-msdc-0113-machmsg-v2-cpus8-fbup-585.img`
   (never flash), ~15 min, TWRP pull -> research/logs/sweetlog-0113-*.
2. Grep `SWEET MSG828`: if ANY line appears, we have the reply producer
   (or a candidate) - cross-check with the RE findings. If none appears,
   the reply producer never runs: the 0114 question becomes "what is
   supposed to start it" (a daemon? IOKit notification delivery from the
   stubs? backboardd's own state machine, gated on the 279x loop?).
3. Cross-check the id histograms (40232/40231/40331/40332/205/2880s)
   against the RE agent's MIG-subsystem mapping.
4. The tracer no longer logs backboardd recvs, so SpringBoard's send/recv
   sequence now reads unbroken up to 20000 lines.

## Agent handoff / active work (2026-10-31 LATEST-94: PIVOT TO THE MACH TRACER - 0112 LOGS EVERY SpringBoard/backboardd mach_msg2 SEND/RECV; BUILT BY A ZCODE WORKFLOW END-TO-END (researchers -> writer -> gates/reviewer -> ship -> CI -> pack); image shim-boot-merlin-msdc-0112-machmsg-cpus8-fbup-585.img d6965f9d READY; RE AGENT STILL RUNNING)

### The pivot (decision, user-approved)

- After 0110's result (sel 33 no-op success unsatisfying, exactly 197
  attempts like the refusal) the user chose to stop the GPU one-selector
  ladder and attack SetupAssistant directly: trace the Mach conversation
  SpringBoard (pid 27) is frozen inside. LATEST-86 proposed this; it was
  outranked by the GPU experiments until now. 0111 (sc= scalar values)
  rides along in the stack for free.

### 0112 mach message tracer (action) - built by a ZCode dynamic workflow end-to-end

- `xnu/patches/0112-merlin-machmsg-trace.patch` (msdc-0112 @ `2e28fa52`,
  CI run 41209617594 SUCCESS): hook at **mach_msg2_trap entry** in
  osfmk/ipc/mach_msg.c, inside the documented "Nothing locked" region,
  after the vector_msg decode, BEFORE any copyin - printf can never run
  with an ipc/port lock held there. One hook covers both processes
  (platform binaries only reach mach_msg2_trap).
  - Filter by proc NAME (proc_name_address strcmp): exactly
    "SpringBoard" or "backboardd" - matched by name, not pid, so pid
    drift between boots does not matter.
  - Format: `SWEET MSG: pid %d (%s) %s id=%u sz=%u` (send/recv). Send id
    = mv_id>>32, send size = mb_ss>>32 (packed scalar trap args, same
    unpacking as the body) - ZERO user-memory reads. Recv lines log
    id=0 (unknowable at trap entry; the post-receive hook was REJECTED
    because the kmsg lock is held there) and recv size = (uint32_t)rs_pr.
  - Cap: static sweet_msg_logged, hard 4000 lines then silent.
- Built by the workflow "Mach tracer patch 0112": two hook researchers
  (entry vs kmsg path) -> writer with the full gauntlet in its
  instructions -> independent adversarial kernel reviewer (round 1 found
  a real gate failure; rounds 2-3 verdict "PATCH IS SOUND") ->
  deterministic gates (git apply --check, GNU patch --dry-run, applied
  content: braces 149/149, literal backslash-n, no signature/header) ->
  shipper (branch/push/dispatch) -> CI poll -> artifact string verify ->
  pack -> repack bit-exact. The writer's evidence dump is in the
  workflow's FINDINGS-style finding; verify script kept at
  research/tmp-0112-wf/verify_gauntlet.py.
- Accepted blind spots (documented): recv id=0, vector sends sz=0,
  combined send+recv = two counted lines, non-atomic counter can
  overshoot 4000 slightly, the global cap lets one process starve the
  other's lines.
- Image `research/merlin-boot/shim-boot-merlin-msdc-0112-machmsg-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `d6965f9d6e50cf86da7735ae479b51563fd1584a00a3aeab22e8e44003fb7b49`;
  SWEET MSG + 0111 sc= strings verified in kernel/buildtree/image;
  kernel sha in research/art-0112 (workflow packed from the 0112 run's
  own artifact).

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0112-machmsg-cpus8-fbup-585.img`
   (never flash), ~15 min unless the log moves, TWRP pull ->
   research/logs/sweetlog-0112-*.
2. Read the SWEET MSG stream around SpringBoard's stall: the last send
   before the rcv wait, its id and destination - that is the request
   nobody answers. Cross-check the RE agent's findings
   (research/tmp-re/FINDINGS.md, still running) for the handler side.
3. The 279x IOAcceleratorES notification loop and the 197x sel-33 loop
   should also appear as message traffic - their ids may explain both.
4. If the ring wraps (4000-line cap may bite: backboardd sends a LOT),
   consider raising the cap or filtering ids in 0113.

## Agent handoff / active work (2026-10-31 LATEST-93: 0110 BOOT READ - SEL 33 NO-OP SUCCESS DID NOT SATISFY IT (EXACT SAME 197 ATTEMPTS AS THE REFUSAL, THEN GAVE UP); 0111 LOGS THE COMMAND'S SCALAR ARGUMENTS; RE AGENT EXTRACTING BACKBOARDD FROM THE DYLD CACHE - image shim-boot-merlin-msdc-0111-gpu-uc-scalars-cpus8-fbup-585.img 38AA5F8C READY)

### 0110 boot log (observation; research/logs/sweetlog-0110-20261031.{bin,txt}, flush 373 at ~3,700+ s)

- sel 33 with `no-op success` was retried **exactly 197 times - the same
  count as 0108's refusals** - then backboardd gave up. The retry loop is
  deterministic (count- or window-bounded), NOT retry-until-success: a
  no-op does not satisfy the command. The GPU stub strategy has hit its
  ceiling at sel 33.
- Exec outcome logging (0109) works: 2,489 `started`, only 3 failures,
  all `err=2` (ENOENT) on early-boot probes (`launchd`, `init`,
  `MSUEarlyBootTask`) - benign. No daemon dies at exec. SetupAssistant
  execs 0.
- SpringBoard t0 still the frozen reference (slide 0x39470000, pc
  0x1fba81030-0x39470000 = 0x1C2611030). IOAcceleratorES notification
  re-registration still 279x. STRATEGIC FACT: five boots of GPU-handshake
  progress, ZERO movement in SpringBoard's stack - the BoardServices
  reply may not be GPU-gated at all.

### 0111 (action) + RE agent (action)

- `xnu/patches/0111-merlin-gpu-uc-scalar-values.patch` (msdc-0111 @
  `5cd1fa31`, CI green run 41202111746): the no-op IOLog now includes up
  to 4 input scalar VALUES in hex (`uc sel %u in %u/%u
  sc=%llx,%llx,%llx,%llx -> no-op success`), so the next boot shows what
  sel 33 is actually being told. Kernel sha256
  `b8c3e4c8271cd5ed8f228b75ac007368bdaccd02111f532d549dc843e4298f18`;
  string verified in kernel + buildtree; image
  `research/merlin-boot/shim-boot-merlin-msdc-0111-gpu-uc-scalars-cpus8-fbup-585.img`
  17,036,243 B, sha256
  `38AA5F8C4B5F62BCB26DA5A0C2AF26D4AE234807347836FC4017B11026E4FDE2`,
  repack bit-exact.
- A background RE agent is extracting backboardd from the on-disk dyld
  shared cache (research/ipsw-x/cache, iOS 16.7.16 arm64; the `ipsw` CLI
  was NOT installed - agent downloads it) to identify: sel 33's meaning
  and its 2 scalar args, the 279x IOAcceleratorES notification loop's
  wait condition, and (if cheap) the 536-byte sel-2 struct. Findings will
  land in research/tmp-re/FINDINGS.md.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0111-gpu-uc-scalars-cpus8-fbup-585.img`
   (never flash), ~15 min, TWRP pull -> research/logs/sweetlog-0111-*.
2. Read the sel-33 line's sc= values and cross-check against the RE
   agent's FINDINGS.md - that combination should identify the command.
3. Then decide: implement sel 33's real semantics in the stub (if it is
   answerable), or pivot to the BoardServices reply path (the GPU walk
   may be a red herring for SpringBoard's stall - see the strategic fact
   above).
4. If the RE agent's findings are solid, fold them into the next patch;
   keep one-variable-per-boot discipline.

## Agent handoff / active work (2026-10-31 LATEST-92: 0108 BOOT READ - PURE QUERY WALK COMPLETED (sel 2/0/4), BACKBOARDD THEN HAMMERED COMMAND sel 33 (2 IN) 197x; 0110 = ANSWER EVERYTHING + 0109 EXEC OUTCOME LOGGING - image shim-boot-merlin-msdc-0110-gpu-uc-all-cpus8-fbup-585.img EBE89972 READY)

### 0108 boot log (observation; research/logs/sweetlog-0108-20261031.{bin,txt}, flush 385 at 3,841 s, no wrap)

- The generalized zero-answer worked: sel 2 (0/536) -> zeroed success,
  sel 0 (0/64) -> zeroed success, AND sel 4 (0/32) -> zeroed success.
- Then `uc sel 33 in 2/0 out 0/0 -> unsupported` fired **197 times** - a
  tight retry loop on an input-carrying COMMAND. backboardd requires it;
  the pure-query generalization could not pass it.
- Exec set expanded (routined, liveactivityd, tccd, coreduetd, dasd,
  calaccessd, remotepairingdeviced, MobileGestaltHelper per the user's
  console photo), 2,599 exec lines total - but SpringBoard t0 is STILL
  the frozen reference (slide 0x3eeb0000, 0x2014c1030-0x3eeb0000 =
  0x1C2611030, 1 unique stack over 31 samples). SetupAssistant 0.

### 0109 + 0110 (action) - user requested exec start/fail logging; commands now answered too

- `xnu/patches/0109-merlin-exec-outcome.patch` (msdc-0109 @ `9a760b07`,
  CI green run 41192339242): at exec_activate_image's single bottom
  return (both paths funnel through it) log the OUTCOME:
  `SWEET EXEC: <name> started` on success, `SWEET EXEC: <name> failed to
  start err=<errno>` on failure. 0042's `exec <name>` allow-line stays.
- `xnu/patches/0110-merlin-gpu-uc-answer-commands.patch` (msdc-0110 @
  `e6016a23`, CI green run 41193228209): the no-input restriction is
  dropped - EVERY selector is answered. Queries (output requested, <=
  16384) keep zeroed output; commands (no output) get a logged no-op
  success (`uc sel %u in %u/%u -> no-op success (shim)`). Oversized
  outputs stay refused. sel 33 should now succeed and the walk continue.
- Both verified with the full gauntlet (git apply + GNU patch + applied-
  content string/brace checks); 0109's process was clean first try.

### 0110 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0110-gpu-uc-all-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `EBE89972FB983E0C1CBC978D59B003BFA86A6EDE295C8D014E5C2A59AB524155`.
  Verified recipe; cmdline = 0104 + cpus=8 + `sweetgpuclient=1`; repack
  reproduced bit-exact; SWEET EXEC started/failed, zeroed-success and
  no-op-success strings all verified in kernel, buildtree and image.
  Kernel sha256
  `154baa4306fc0928b348be37b469d2a088b4e23011b5e83b483b63938358fb57`.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0110-gpu-uc-all-cpus8-fbup-585.img`
   (never flash). ~15 min enough unless the log MOVES.
2. Read: (a) the `uc sel` stream past sel 33 - how far does the walk go,
   does a SECOND client open (IOAcceleratorES); (b) `SWEET EXEC: ...
   failed to start err=` lines - which daemons die and with what errno;
   (c) SpringBoard t0 vs frozen reference 0x1C2611030; (d) new execs /
   SetupAssistant.
3. If sel-33's no-op success misleads backboardd into waiting for real
   GPU work (hang without new selectors), the next step is identifying
   sel 33's true meaning from backboardd's binary (IOKit userspace
   AGX headers compiled into it) rather than more no-ops.
4. The exec outcome lines double the per-exec log volume; if the ring
   starts wrapping (check `flush #` vs `total`), raise the ring or drop
   the allow-line duplicate.

## Agent handoff / active work (2026-10-31 LATEST-91: 0107 BOOT PULLED - SEL 2 ANSWERED, BACKBOARDD IMMEDIATELY ASKED SEL 0 (0/64) AND WAS REFUSED AGAIN; 0108 GENERALIZES: EVERY PURE-OUTPUT QUERY GETS ZEROED SUCCESS - image shim-boot-merlin-msdc-0108-gpu-uc-queries-cpus8-fbup-585.img 0EA17BB3 READY FOR THE NEXT BOOT)

### 0107 boot log (observation; research/logs/sweetlog-0107-20261031.{bin,txt}, 7,979 lines, flush 340 at 3,391 s, no wrap)

- The 0107 answer worked: `uc sel 2 out 536 -> zeroed success (shim)` and
  backboardd ACCEPTED it and asked the next question: `uc sel 0 in 0/0
  out 0/64 -> unsupported (shim)`. Then silence - one open, two selector
  calls, whole boot. The zeros are tolerated (no panic, no complaint).
- Pattern established: backboardd walks a list of pure get-info methods
  (nothing in, struct out). Each refusal stops the walk.
- SpringBoard t0 STILL the frozen reference: cache slide 0x37ad4000
  (CRASH lines), 0x1fa0e5030-0x37ad4000 = 0x1C2611030 = exactly the
  0104/0106 mach_msg2/BoardServices wait; 1 unique stack over all 28
  samples. backboardd notification re-registration still 279x.
  SetupAssistant execs 0; fairplayd.H2/bluetoothd loop continues.

### 0108 answering shim (action) - two patch attempts wasted on toolchain traps, both root-caused

- `xnu/patches/0108-merlin-gpu-uc-answer-queries.patch` (ios-sweet
  msdc-0108 @ `b07f67d`): externalMethod now answers EVERY selector with
  structureInputSize==0 and 0 < structureOutputSize <= 16384 using zeroed
  output + kIOReturnSuccess (`SWEET GPU: uc sel %u out %u -> zeroed
  success (shim)`); anything carrying input stays refused and logged.
- v1 (956dd59) was SILENTLY SKIPPED: its hunk context came from the 0107
  artifact's packaged buildtree, whose IOLog line was corrupted (string
  split across lines - that packaged source could never compile; the
  kernel binary from that run is fine). CI's real source has the string
  on one line, so the context did not match -> "patch failed at :155".
  Diagnosis: read the CI build log (Applying/Skipping lines) + compare
  tar members with `tar -xzf ... -O path | grep` (pipe preserved bytes;
  redirect-to-file extraction on this host mangled them - use -O pipes).
- v2 (308b5a4) applied but broke the parse: the python edit used
  lines[a:b] = new with b pointing AT the base's closing brace - the
  slice excludes b, so the base's brace survived next to the new block's
  own -> externalMethod closed early ("expected unqualified-id" at the
  fallback log, "extraneous closing brace" at function end).
- v3 (b07f67d) GREEN, run 41185837788: kernel sha256
  `a18c54292801390fc574bbb2914a841e5744719a4a0ab9e1dbccd6a05e186270`
  (SHA256SUMS match); generalized string verified in the kernel binary
  AND the buildtree (structureOutputSize <= 16384 present); brace
  balance 25/25 in base and patched file.

### 0108 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0108-gpu-uc-queries-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `0EA17BB38A846CA6BBAF96012230C86524BE8F81F94A428896CEC817F195F53C`.
  Verified recipe; cmdline = 0104 + cpus=8 + `sweetgpuclient=1`; repack
  reproduced bit-exact; the generalized zeroed-success string and the
  cmdline verified in the packed image.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0108-gpu-uc-queries-cpus8-fbup-585.img`
   (never flash). ~15 min is enough unless the log starts MOVING (new
   sels/execs) - then let it run. Pull via TWRP
   (mmcblk0p46, skip 12,710,135) -> research/logs/sweetlog-0108-*.
2. Read the `SWEET GPU: uc sel` stream: with pure-output queries all
   answered, the walk should get further - count how far, and look for
   the first REFUSED selector WITH input (the first real command) or a
   change in SpringBoard t0 (frozen reference pc 0x1C2611030) and new
   execs. If a zeroed struct misleads backboardd into a panic, the
   sampler/panic screen shows it and the next step is pulling the real
   struct layouts from backboardd's binary instead of zeros.
3. Watch for a SECOND user client open (IOAcceleratorES) - the services
   may now be usable enough for backboardd to open more than AGX.

### Process lessons (keep following these)

- After every CI run, string-verify the NEW format string in the kernel
  binary AND the buildtree before packing. Green CI does not mean the
  patch applied (v1 0107, v1 0108 both built green without their change).
- Read the CI build log's "Applying patch/Skipping patch" lines for any
  patch that must apply.
- Patch context must come from the NEWEST run's buildtree read via
  `tar -xzf ... -O path | ...` (pipe), never redirect-to-file, never an
  older artifact.
- After scripted edits: brace-balance check, applied-content inspection,
  and BOTH git apply and GNU patch --dry-run before pushing.

## Agent handoff / active work (2026-10-31 LATEST-90: 0106 LOG PULLED AND READ - GPU STUBS WORK, BACKBOARDD OPENED AGX AND WAS REFUSED ON ITS ONE QUERY (sel 2, 0/536); 0107 ANSWERS IT WITH ZEROED OUTPUT - image shim-boot-merlin-msdc-0107-gpu-uc-sel2-cpus8-fbup-585.img B209AE81 READY FOR THE NEXT BOOT)

### 0106 boot log (observation; research/logs/sweetlog-0106-20261030.{bin,txt}, 8,510 lines, 345 flushes, last 3,441 s, no wrap; user pulled via TWRP mmcblk0p46 skip 12,710,135)

- SWEET CLK FINALLY LANDS: 8 lines at MSDC init, A55 cluster 1174-1175 MHz
  (mpidr 0x0-0x500), A75 cluster 1086-1087 MHz (mpidr 0x600/0x700). The
  0103 open question is settled on hardware: per-cluster OPP, shim's
  2.35 GHz figure was wrong, LK-clock hypothesis right.
- GPU stubs (0105 layer) work: all three `published (stub; no renderer)`
  lines present; `IOAcceleratorES -> 0 found` count = 0 (was 302x in
  0104); the matching storm is gone.
- User client (0106 layer) works: `IOK backboardd: matching1
  AGXAccelerator -> AGXAccelerator`, then `open AGXAccelerator type 1 ->
  0x0`, then EXACTLY ONE selector: `uc sel 2 in 0/0 out 0/536 ->
  unsupported (shim)`. No retry, no IOAcceleratorES open, all hour.
- After the refusal backboardd kept working (SURF create 1125x2436 BGRA,
  FB sels) but re-registered `matching1 IOAcceleratorES ->
  IOAcceleratorES` notifications 279x - a wait loop with no wake.
- SpringBoard t0 is BIT-IDENTICAL to 0104 unslid: this boot's cache slide
  is 0x62ec000 (CRASH lines), 0x1c88fd030-0x62ec000 = 0x1C2611030 and
  lr 0x1c890eb18-0x62ec000 = 0x1C2622B18 = exactly the 0104
  mach_msg2/BoardServices wait. SetupAssistant execs 0; the
  fairplayd.H2/bluetoothd/xpcproxy exec loop continues.
- Conclusion: the single sel-2 refusal is the only GPU-level wall seen;
  answering it is 0107.

### 0107 answering shim (action) - three patch attempts, two CI runs wasted, lessons recorded

- `xnu/patches/0107-merlin-gpu-uc-answer-sel2.patch` (ios-sweet msdc-0107
  @ `8b936f5`, based on msdc-0106-macos15): in IOAcceleratorESUserClient
  ::externalMethod, selector 2 with structureInputSize==0,
  structureOutputSize==536, structureOutput!=NULL -> memset output to 0,
  log `SWEET GPU: uc sel 2 out 536 -> zeroed success (shim)`, return
  kIOReturnSuccess. Every other selector stays refused (one dependency
  revealed per boot).
- v1 (ec94fef): hand-written patch with malformed hunk + git signature
  trailer - build.sh's GNU patcher SKIPPED it with only a warning
  ("corrupt patch at line 47") and the run built green WITHOUT the
  change. Lesson: ALWAYS string-verify the artifact carries the new
  format string; green CI proves nothing about a silently skipped patch.
- v2 (d5c2919): plain git diff, applied - but the IOLog string literal
  contained a raw CRLF (edit-toolchain escape mangling) -> compile error
  at SweetPlatformExpert.cpp:169 ("expected expression", then local-class
  cascades). Also: one v2 dispatch was lost to hosted-runner capacity
  ("job was not acquired by Runner of type hosted").
- v3 (8b936f5) GREEN, run 41178593745: kernel sha256
  `375674be0fb1ee4b6bc0e7d550db841ce27a6df0004af0ff930cb34b11119702`
  (SHA256SUMS match); `zeroed success` verified in kernel AND buildtree
  (1 occurrence in SweetPlatformExpert.cpp).

### 0107 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0107-gpu-uc-sel2-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `B209AE816D198BA47D9098AABBBE051A465273545AE6D8339944116F49EA26B0`.
  Verified recipe; cmdline = 0104 + cpus=8 + `sweetgpuclient=1`; repack
  reproduced bit-exact; the zeroed-success string and the cmdline are in
  the packed image.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0107-gpu-uc-sel2-cpus8-fbup-585.img`
   (never flash), ~1 h, pull via TWRP (mmcblk0p46, skip 12,710,135) ->
   research/logs/sweetlog-0107-*.bin/.txt.
2. Read the `SWEET GPU: uc sel ...` stream: expect sel 2 answered, then
   whatever backboardd asks NEXT becomes 0108's next answer. Watch for
   backboardd behaviour change (IOK lines, SURF/FB activity) and the
   SpringBoard t0 unslid stack (slide from the CRASH lines; 0104/0106
   reference: pc 0x1C2611030, lr 0x1C2622B18).
3. If the zeroed struct panics or misleads backboardd, the sampler and
   panic screen say so - fall back to identifying sel 2's struct from
   backboardd's own disassembly before inventing field values.

## Agent handoff / active work (2026-10-30 LATEST-89: 0106 KERNEL BUILT ON macos-15 (macos-14 IS BROWNED OUT) AND THE SWEETGPUCLIENT IMAGE IS PACKED - shim-boot-merlin-msdc-0106-gpu-uc-cpus8-fbup-585.img 8DA37BED, awaiting the boot test)

### macos-14 CI brownout (root cause, explains LATEST-85 "capacity" failures too)

- Every dispatch on 2026-10-30 18:50-19:09 UTC (10 runs incl. msdc-0079
  controls) was cancelled within seconds, zero steps recorded. The run
  page annotation: "scheduled macOS 14 runner image brownout - macOS 14
  runner images will be retired on November 2, 2026"
  (actions/runner-images#13518). Brownouts run **14:00-00:00 UTC daily**
  through Nov 1; the 17:01 UTC 0105 success was in a gap.
- The workflow pins `runs-on: macos-14` because Xcode 15 iig matches the
  xnu-8796 IORPC ABI. Migration options are macos-15/macos-26 only.

### macos-15 migration test (action + observation) - IT BUILDS

- Branch `msdc-0106-macos15` (ios-sweet `12327eab` = msdc-0106 + one-line
  runs-on: macos-15), pushed to fork, dispatched during the brownout.
- **Run 41113966391 SUCCEEDED in ~8 min.** The Xcode 16 iig
  risk in the workflow comment did not materialize (Deps selects the
  oldest Xcode on the image). This unblocks CI past the Nov 2 retirement;
  only the runs-on line needs migrating for future patches.
- Artifacts xnu-kernel 13005152454 / xnu-buildtree 13004762977 ->
  `research/art-0106/`. Kernel `kernel.development.sweet` sha256
  `eb18ab32b25f0cd52042b886de49d9fd64390e392cc32279c19b1da31e67ce80`
  (SHA256SUMS match).

### 0106 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0106-gpu-uc-cpus8-fbup-585.img`,
  17,036,243 B, sha256
  `8DA37BED68F2F3F877036A9FFAB2A09216D7CC4136E98D3E501611144E8248F8`.
  Verified recipe (make-0099-image.py); cmdline = 0104 with cpus=8 PLUS
  `sweetgpuclient=1` (a superset of 0105: the stub-publish lines still
  print, and IOServiceOpen now succeeds against the stubs); repack
  reproduced the sha bit-exact; shim slot + dtb E1 lineage, Video base
  0x7e39c458. Strings verified in kernel, buildtree (SweetPlatformExpert
  has the PE_parse_boot_argn gate + kIOUserClientClassKey + sel logging)
  and the packed image.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0106-gpu-uc-cpus8-fbup-585.img`
   (never flash), let it run ~1 h, pull the log via TWRP as in LATEST-86
   (mmcblk0p46, skip 12,710,135).
2. Look for: `SWEET GPU: IOAcceleratorES published` (0105 layer),
   `SWEET GPU: user client opened on IOAcceleratorES (shim)` and a stream
   of `SWEET GPU: uc sel N in a/b out c/d -> unsupported (shim)` lines
   (0106 layer = what backboardd actually calls), eight SWEET CLK lines,
   and whether backboardd's IOK lines stop saying `-> 0 found` and
   SpringBoard's frozen mach_msg2/BoardServices stack changes or
   SetupAssistant execs.
3. If the user wants the 0105-behavior control instead, the same kernel
   packs without `sweetgpuclient=1` (or boot-arg absent = identical to
   0105).
4. CI housekeeping: future patch dispatches should use a macos-15 branch
   (or migrate runs-on) - macos-14 dies in brownout windows until Nov 2
   and fully after.

## Agent handoff / active work (2026-10-30 LATEST-88: BUG-FIX SWEEP ON THE SHIM/TOOLS WORKING TREE - 18 findings, 18 independently confirmed, 18 fixed; WSL clang rebuild + QEMU smoke reaches bb stage 9 "xnu entry"; UNCOMMITTED-THEN-COMMITTED as one sweep commit, 0105 image unaffected)

### The sweep (action)

- ZCode dynamic workflow (run dwfrun-e4c8282e): 3 bug hunters (shim C,
  tools Python, cross-file consistency) -> independent confirmer per
  finding -> one Code writer applied fixes -> gcc -fsyntax-only +
  py_compile gate (13 files, all pass). Full report: workflow artifact
  "Bug hunt and fix report"; 18-row findings table alongside.
- Highlights (all confirmed by repro, not just reading):
  - HIGH tools/patch-fbcon1x.py: only pre-write check was `!= NOP`, so on
    any kernel other than out-dlildbg2 it would overwrite ~1.2 KB of
    unrelated __TEXT_EXEC (simulated on art-0105: words 0x53103e69/
    0x3941510a pass the old assert). Now asserts the expected original
    word per site and fails loudly on 0105 / already-patched input.
  - shim/ramfb.c:73: fw_cfg DMA completion poll read a non-volatile
    static; clang -O2 deleted the poll loop entirely. Volatile read
    restored; the loop is back in the disassembly (10M countdown,
    error-bit check).
  - shim/start.S: QEMU builds no longer paint the phone plane
    (0x7e605000 literal absent from out-fixcheck/start.o); GREEN proof
    block had a missing movk (painted opaque black) - fixed; exception
    frame now saves/restores the interrupted lr to regs[29] (X30 on the
    panic screen was stale stack bytes); Image-header flags comment
    corrected to 16K pages (0xa per Linux image.h; value kept).
  - shim/loader.c bb_set: NUL-terminates after the copy (shorter message
    over a previous boot's longer one left residue on the persistent
    0xBFFFF000 page).
  - shim/mmu.h FB_PHYS unified under console.h FB_BASE (was a third
    divergent copy of the FB base, latent).
  - tools/patch-earlyfb.py: FIXUPS VAs re-derived for the 0105 kernel
    (f576189d, method validated bit-exact against art-0083); tool runs
    end-to-end on 0105 now; module-level main() guarded for import.
  - Comments corrected: mkbootimg.py id is the RAW digest; fbcon-1x.ld
    kernel attribution (old "0083" claim wrong); console.h/patch-shim-
    videobase.py now document that fresh shims encode 0x7e605000 and the
    deployed E1 lineage carries 0x7e605438 (--old-base must match).

### Verification (observation)

- WSL clang 21.1.8 (same flags as build-qemu.sh) rebuilt both configs
  into shim/out-fixcheck/ and shim/out-fixcheck-phone/ (7 pre-existing
  warnings, unchanged). start.S also compiled without SHIM_QEMU: paint
  code + green movk + x30 save all present; phone literal 1 hit, QEMU 0.
- QEMU smoke (tools/qemu-shim.py, out-fixcheck Image + 0105 payload):
  black-box seq=7 stage=9 "xnu entry" (the deepest bb_set), 74 console
  lines, no exception/panic screen.
- NOTE: build-qemu.sh always defines SHIM_QEMU, so the phone splash
  paints only exist in build.sh (aarch64-linux-gnu-gcc) builds; the
  "phone" variant of build-qemu.sh only changes FB geometry.

### Next

1. Nothing pending on this sweep - committed as one milestone commit.
2. 0105 boot test still the active hardware step (LATEST-87); the sweep
   changed shim/tools sources only and does not affect the packed 0105
   image (no repack done - source fixes reach images only on the next
   rebuild).
3. 0106 (msdc-0106, ee6b35a) dispatch still awaiting the 0105 boot
   result, per LATEST-87.

## Agent handoff / active work (2026-10-30 LATEST-87: 0105 = printf SWEET CLK + INERT GPU ACCELERATOR SERVICES (IOAcceleratorES/IOAcceleratorESLegacy/AGXAccelerator) SO THE PENDING BACKBOARD MATCHES COMPLETE; CI 41087860631)

### 0105 patch (action)

- `xnu/patches/0105-merlin-gpu-stubs-clk-printf.patch` (3 files), ios-sweet
  msdc-0079 commit `d62f3dc`, pushed to fork/msdc-0079.
  - SweetCPU.cpp: `sweet_report_cpu_clocks()` kprintf -> printf. kprintf is
    the pexpert early console (pe_kprintf) and never reaches the
    serial_console `_cnputs` ring, which is why 0104's late reprint was
    still invisible. printf is the osfmk console path the sampler and MSDC
    code already use.
  - SweetPlatformExpert.cpp: inert `IOAcceleratorES` service plus
    `IOAcceleratorESLegacy` and `AGXAccelerator` subclasses; start()
    registers the service and logs `SWEET GPU: <class> published (stub;
    no renderer)`.
  - KernelConfigTables.cpp: three built-in personalities
    (IOProviderClass IOResources, distinct IOMatchCategory) so IOKit
    instantiates the stubs at boot; clients matching those class names
    (backboardd: 302x IOAcceleratorES 0 found, 29x Legacy none, 2x
    AGXAccelerator none) now get a match/notification. IOServiceOpen
    returns kIOReturnUnsupported (no user client class property), so no
    renderer is claimed; the software framebuffer path is unchanged.
- `git apply` verified against the 0104 buildtree sources.
- CI run 41087860631 (workflow_dispatch msdc-0079 @ `d62f3dc2`) queued
  16:13 UTC and FAILED; the watcher's retries (41090220226/41090318309/
  41091330668 cancelled, 41091501788 failed on runner capacity) ended with
  **41095066351 SUCCESS at 17:01:02 UTC** (same `d62f3dc2`, ~17 min).

### 0105 artifacts + image (done)

- Artifacts xnu-kernel 12996623308 / xnu-buildtree 12996333694 ->
  `research/art-0105/`. Kernel `kernel.development.sweet` 17,252,096 B,
  sha256
  `f576189d21e8161e4660a98252bf936e82da67c73f3c291da97872545ab5a1fc`
  (SHA256SUMS match). Buildtree confirmed patched: SweetCPU.cpp:320
  `sweet_report_cpu_clocks()` now printf; SweetPlatformExpert.cpp +
  KernelConfigTables.cpp contain the IOAcceleratorES/Legacy/AGX
  personalities.
- Image
  `research/merlin-boot/shim-boot-merlin-msdc-0105-gpu-clk-cpus8-fbup-585.img`,
  17,034,195 B, sha256
  `dc696f28aa9db17408926410ec3893b250c7d8f7358d261d39ec70012565ea88`.
  Packed with the verified recipe (make-0099-image.py, cmdline = 0104
  with cpus=8); a from-scratch repack reproduced the sha256 bit-exact.
  Strings verified in kernel and image: `SWEET GPU: %s published (stub;
  no renderer)`, both SWEET CLK formats, `cpus=8`. Shim slot + dtb
  byte-identical to E1, Video base 0x7e605438 -> 0x7e39c458.

### 0106 shim (prepared, not pushed)

- `xnu/patches/0106-merlin-gpu-userclient-shim.patch` on local ios-sweet
  branch `msdc-0106` (commit `ee6b35a`, based on 0105 `d62f3dc`). Kept
  unpushed so the queued 0105 run and the watcher's retry dispatches stay on
  d62f3dc.
- `IOAcceleratorESUserClient` overrides initWithTask/start/clientClose/
  clientDied/externalMethod. When boot-arg `sweetgpuclient=1` is present the
  stub services set kIOUserClientClassKey, so IOServiceOpen succeeds; every
  externalMethod logs `SWEET GPU: uc sel N in a/b out c/d -> unsupported
  (shim)` (first 200 calls) and returns kIOReturnUnsupported. Without the
  boot-arg the 0105 behavior is unchanged. One image can A/B both.
- Dispatch `msdc-0106` only after the 0105 image is packed (or on request):
  the shim is a diagnostic/user-client-presence test, not a renderer.

### Next

1. When CI lands: pack with the verified recipe to
   `research/merlin-boot/shim-boot-merlin-msdc-0105-gpu-clk-cpus8-fbup-585.img`
   (cpus=8) and check the SWEET GPU + SWEET CLK strings.
2. User boots it; look for `SWEET GPU: IOAcceleratorES published` etc. and
   backboardd IOK lines changing from `-> 0 found`/`none` to found, eight
   SWEET CLK lines at MSDC init and per sample, and whether SpringBoard's
   t0 stack changes or SetupAssistant execs. Pull the log as usual.
3. The stubs are inert: if backboardd opens them and needs a renderer, it
   will log; a user-client shim is the next step only if the match alone
   does not unblock the BoardServices reply.

## Agent handoff / active work (2026-10-30 LATEST-86: 0104 LOG PULLED - THE SAMPLER WORKS AND SPRINGBOARD'S MAIN THREAD IS FROZEN IN ONE mach_msg2 / BoardServices CALL FOR THE WHOLE HOUR; SWEET CLK IS STILL ZERO BECAUSE kprintf IS THE PEXPERT EARLY CONSOLE, NOT THE RING)

### 0104 log pull (observation)

- Pulled via TWRP as before (/dev/block/mmcblk0p46, 52,064,911,360 B,
  skip 12,710,135) -> research/logs/sweetlog-0104-20261030.bin ->
  `.txt` 499,537 B, 8,173 lines, 375 flushes, last 3741.558 s. No wrap.
- The 0054 sampler now runs (the 0104 MSDC start fix works): 31 samples
  (`SMP --- sample 0` at 90 s .. sample 30), 695 SMP lines, and the
  per-sample clock reprint call is present.
- SWEET CLK / PMU trapped lines: **0**. `kprintf` is not osfmk printf: it
  is the pexpert early console (`pexpert/arm/pe_kprintf.c`, declared in
  pexpert.h), so it never reaches the serial_console `_cnputs` ring.
  0104's `sweet_report_cpu_clocks()` used kprintf, so it is invisible even
  when called from `printf`-based sampler rounds. A one-word fix (printf)
  remains.

### SpringBoard is not crashed - it is asleep in one call (observation)

- SpringBoard pid 27, `slide 0xc10000 mh 0x104100000`. Thread t0 is
  bit-identical in all 31 samples (90 s .. ~62 min):
  `pc 0x1c3221030 lr 0x1c3232b18 sp 0x16bcfa990 bt 0x1c3232db8
  0x1c3221524 0x18e77a308 0x18e77a694 0x1d27fe0ec 0x19c5bf128
  0x19c5c1e78 0x19c5c1554 0x18e908ce0 0x1a32ac304 0x1c64755c8 0x1a5234344`.
- pc disassembles to the `ret` after `mov x16, #-0x2f; svc #0x80` in
  libsystem_kernel: **Mach trap 47 = mach_msg2_trap** (mach_trap_table
  `/* 47 */ MACH_TRAP(mach_msg2_trap, ...)`). The thread is waiting for a
  Mach message, not spinning or faulting.
- Unslid with the sampler slide and mapped with the iOS 26H392 dyld image
  table (research/ipsw-x/cache): libsystem_kernel+0x12db8 / +0x1524 ->
  libdispatch+0x36308/+0x36694 -> libxpc+0xe0ec -> BoardServices+0x3128 /
  0x5e78 / 0x5554 -> BackBoardServices+0x3ace0 -> FrontBoard+0x5c304 ->
  SpringBoard.framework+0x9b5c8 -> dyld+0x14344. A synchronous
  BoardServices/BackBoard XPC call from SpringBoard's main thread that
  never gets its reply (outer frames are FP-walk, treat as indicative).
- Other SpringBoard threads: t1 in libdispatch (dispatch worker, trace
  frames), t2..t5 at libsystem_kernel+0x14f0 with bt libsystem_pthread,
  i.e. idle pthread workers. No crash, no spin, no kernel wait.
- backboardd pid 57: its t0 is in the same mach_msg2 wait; IOKit trace
  shows 302x `IOAcceleratorES -> 0 found`, 30x `-> none`, 29x
  `IOAcceleratorESLegacy -> none`, 2x `AGXAccelerator -> none`, while it
  does find IOMobileFramebuffer (notify), SweetHIDTouch/Buttons, and
  AppleKeyStore. It keeps presenting layers (last `SWEET FB: 194000
  swaps`), so composition works but the accelerator service is absent.
- Process set: runningboardd 1 exec, backboardd 1, SpringBoard 1,
  frontboardd 0 (not a daemon on this build), SetupAssistant 0.
- Display: the ~1 h Apple-logo/progress screen is the boot UI staying on
  top; swaps stop at 194000 and the console tail becomes visible; the exec
  stage itself starts in the first flushes (~35 s).

### Next

1. 0105: change `sweet_report_cpu_clocks()` kprintf -> printf so the eight
   SWEET CLK lines finally land in the ring (and on screen).
2. Identify the never-answered BKS request: log mach_msg2 trap traffic
   (msgh_id + receiver task) for SpringBoard (pid 27) and backboardd
   (pid 57), or publish a minimal IOAcceleratorES/AGXAccelerator stub and
   see whether backboardd's scene/workspace reply unblocks SpringBoard.
3. Keep the sampler (40 rounds) - it is the first working window into
   userland; the stack above is the wall, not a resource shortage.

## Agent handoff / active work (2026-10-30 LATEST-85: 0103 BOOT LOG ANALYZED - CLOCKS AND SAMPLER WERE INVISIBLE FOR STARTUP-ORDER REASONS; 0104 REPRINTS CLOCKS LATE AND STARTS THE SPRINGBOARD SAMPLER ON THE MSDC PATH; CI RUN 41067047807)

### 0103 boot + log pull (observation)

- User ran the 0103 cpus=8 image; at ~115 min the visible tail was the
  same exec loop (photo at 6912 s). SetupAssistant still never exec'd.
- Pulled the ring via TWRP as before (/dev/block/mmcblk0p46, 52,064,911,360 B,
  skip 12,710,135) -> research/logs/sweetlog-0103-20261030.bin ->
  `.txt` 473,094 B, 9,701 lines, 463,639 B logged, 720 flushes, last
  7193.016 s. No wrap; the whole boot is present.
- 8/8 CPUs on hardware again: requested=8 selected=8, cpu 0..7 including
  mpidr 0x600/0x700 came alive, 8/8 initialized.
- Loop: 4,140 execs (xpcproxy 2,059, fairplayd.H2 713, bluetoothd 710,
  CommCenter 111); 448 CRASH lines; SpringBoard exec'd once (line 557)
  with 4 AKS calls, all 0x0, and no output; 362 IOAcceleratorES
  "-> 0 found" for backboardd; AKS wrap/unwrap all 0x0.

### Why the clocks were invisible (observation, root cause)

- The ring contains NO "SWEET CLK" and no "entered initCPU" line at all,
  not even for cpu0 - in this log or in 0100-0102. initCPU's kprintf is
  emitted before the persistent-log console path is active; the ring's
  first recorded lines are the platform-expert stage (it does capture
  startAll's IOLog lines and the Darwin banner that follow). The
  measurement runs, but its one print is lost. The QEMU run proved the
  measurement itself.

### Why the SpringBoard sampler never ran (observation, root cause)

- No "SMP --- sample" / "SMP SpringBoard" lines in ANY log (0100-0103).
  0054 starts the sampler from the sweet-ufs attach (DT /sweet-ufs), but
  merlin has no such node: the live root/log path is the MSDC driver
  (0098/0099), whose merlin_msdc_init() starts the working "MERLIN LOG"
  thread. The sampler thread was never started. The same is true of the
  0047 sweet_log_thread; the flushes come from merlin_msdc_log_thread.

### 0104 fix (action)

- `xnu/patches/0104-merlin-clk-report-sampler.patch` (3 files), ios-sweet
  msdc-0079 commit `56359c9`, pushed to fork/msdc-0079.
  - SweetCPU.cpp: store per-CPU MHz/mpidr at initCPU; new
    `sweet_report_cpu_clocks()` reprints the same "SWEET CLK" lines.
  - sweet_ufs.c: call it in `merlin_msdc_init()` next to
    `merlin_cpu_report()`; start `sweet_sample_start()` at the MSDC attach
    (the path that actually runs).
  - sweet_sample.c: one-shot start guard; print the CPU clocks at the top
    of each of the 40 sampler rounds (first at 90 s, then every 120 s), so
    the numbers also stay visible in the screen tail.
- `git apply` verified against the 0103 buildtree sources.
- CI: run 41067047807 failed and 41069390347 was cancelled on macOS-runner
  capacity; the retry run **41070303179** (msdc-0079 @ `56359c90`)
  succeeded at 14:15:44 UTC (~6 min). Artifacts xnu-kernel 12985701427 and
  xnu-buildtree 12985326712 -> `research/art-0104/`. Kernel
  `kernel.development.sweet` 17,241,512 B, sha256
  `7B92386DFDAE94B2697CBE5A5EEEEF8617C05B8615AF20A6D7781574221F423E`
  (SHA256SUMS match); the buildtree SweetCPU.cpp/sweet_ufs.c/sweet_sample.c
  contain `sweet_report_cpu_clocks` and the MSDC `sweet_sample_start()`.

### 0104 image (action)

- `research/merlin-boot/shim-boot-merlin-msdc-0104-clksmp-cpus8-fbup-585.img`,
  17,023,955 B, sha256
  `08CB1661EDFD5819B393F5B330AEF5CFFCF7C8C453DF61656F43F16883F25C3C`.
  Same verified recipe (0102 reproduced bit-exact earlier); cmdline = 0103
  cpus=8; shim slot + dtb unchanged. Strings verified in kernel and image:
  the SWEET CLK formats, `SMP --- sample`, `SMP %s[%d] slide`, `cpus=8`.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0104-clksmp-cpus8-fbup-585.img`
   (never flash), let it run, then pull the log via TWRP as before.
2. Expect 8 SWEET CLK lines at MSDC init (~34 s, also in the console), then
   "SMP --- sample 0" at 90 s with SpringBoard/backboardd user stacks, then
   clocks again at every sampler round. Symbolicate the SpringBoard pcs
   with `tools/sweet-crash.py` (shared cache + root) to see the blocking
   frame.
3. That stack decides the next fix (IOAcceleratorES service, a missing
   Mach service, or a UIKit assertion) - do not guess before it lands.

## Agent handoff / active work (2026-10-30 LATEST-84: PER-CPU CLOCK MEASUREMENT BUILT - 0103 KERNEL REPORTS `SWEET CLK` (PMCCNTR), QEMU SHOWS THE LINE, 0103 cpus=8 IMAGE READY FOR THE PHONE)

### Correction to LATEST-83 (observation, from the source)

- The "Patch 0083 written" clock patch never applied anywhere: it was
  generated against a stale SweetCPU.cpp/SWEET.h (expected
  `SWEET_SMP_MAX_CPUS 6` and `phys_id > 0x500`). The msdc-0079 CI branch
  already carries 0078 (`SWEET_SMP_MAX_CPUS 8`, `phys_id > 0x700`), so both
  hunks would have been rejected by `git apply`. The CI run that LATEST-83
  called "triggered" (41042841361) was a workflow_dispatch on 063b1967 and
  built 0102 again, not the clock patch.
- The CPU-management fix itself (A75 mpidr 0x600/0x700 accepted, eight
  cores) is 0078 and is already proven on hardware by the 0102+cpus=8 boot;
  no further management change was needed for this measurement.

### 0103 clock patch (action)

- `xnu/patches/0103-sweet-clk-measure-debug.patch` (114 lines), ios-sweet
  msdc-0079 commit `9103b39`, pushed to fork/msdc-0079.
  - SWEET.h: PMCR_E/PMCR_C/PMCR_D/PMCNTENSET_CNTEN0 bit definitions; the
    8-core comment now says six A55 + two big (A76 on sweet, A75 on merlin).
  - SweetCPU.cpp: `sweet_pmu_start_counter()` clears PMCR.D (else the
    counter runs /64), sets E|C, enables CNTEN0 and ISBs;
    `sweet_measure_cpu_mhz()` compares PMCCNTR_EL0 with CNTPCT_EL0 over
    ~10 ms; initCPU() prints `SWEET CLK: cpu=N mpidr=0xNNNN <mhz> MHz`, or
    `SWEET CLK: cpu=N PMU trapped, clock unknown` when the counter does not
    advance. The stale "A76 cores require separate work" header is fixed.
  - `git apply` verified clean against the 0102 buildtree sources; the
    PMCCNTR/PMCR/PMCNTENSET register names compile with clang
    -target arm64-apple.
- CI run **41046396796** (workflow_dispatch, msdc-0079 @ `9103b392`):
  success, ~6 min (11:12:59-11:19 UTC). Artifacts xnu-kernel 12972223904
  and xnu-buildtree 12973265829 -> `research/art-0103/`. Kernel
  `kernel.development.sweet` 17,241,256 B, sha256
  `FD023B17DE56313D79A9BCA90EE639D61D4B9253D9393CD6C704364BE877C18E`
  (SHA256SUMS match); the buildtree SweetCPU.cpp contains the SWEET CLK
  code, so the artifact really is the patched build.

### QEMU validation (observation)

- Payload from the 0103 kernel + `xnu/out-0001/merlin-q.adt` + merlin-init
  (`research/tmp-clk/merlin-payload-qemu-0103.bin`), 20 s headless run.
  fb console snapshot `research/tmp-clk/qemu-0103/fb.txt` shows:
  `SWEET CPU: cpu=0 entered initCPU mpidr=0x0 EL1 IRQs=1`,
  `SWEET CLK: cpu=0 mpidr=0x0 1003 MHz`,
  `SWEET CPU: cpu=0 mpidr=0x0 came alive; SGI1 OK`,
  `SWEET CPU: 1/1 CPUs initialized, SGI1 verified`; no panic
  (result.json `no_panic_observed`).
- The 1003 MHz is a TCG artifact (QEMU's cycle counter tracks guest time,
  not a real core clock). It proves the PMU enable/read/ratio path and the
  print; on hardware the same line is the real OPP.

### 0103 image (action)

- Recipe re-verified before use: rebuilding the 0102 image from
  `research/art-0102/kernel.development.sweet` with build-msdcroot0.py +
  patch-shim-videobase (0x7e39c458) reproduced its sha256 `95899D15...`
  bit for bit. The same recipe then packed 0103.
- `research/merlin-boot/shim-boot-merlin-msdc-0103-clk-cpus8-fbup-585.img`,
  17,021,907 B, sha256
  `2702C241EE2A7469528113AEEF3C37012476293E8C4BECF8416E67B56E4672B1`.
  cmdline identical to 0102 except `cpus=8`; shim slot + dtb unchanged;
  the image differs from the 0102+cpus=8 image only inside the kernel
  region.
- Strings verified in both the CI kernel and the packed image: the two
  SWEET CLK formats and `SWEET CPU: requested=%u selected=%u (limit=%u)`;
  `cpus=8` present.

### Next

1. User: `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0103-clk-cpus8-fbup-585.img`
   (never flash), let it run, then pull the log via TWRP as in
   LATEST-81/83.
2. Expect eight `SWEET CLK: cpu=N mpidr=0xN00 <MHz> MHz` lines.
   Interpretation: ~1170 MHz on both clusters means the shim's 2.35 GHz
   figure assumed 2 cycles/iter and the real OPP is the LK one; A75s
   markedly above the A55s means per-cluster OPP; `PMU trapped` means the
   loop-shape fallback is needed. Do not quote the QEMU 1003 MHz as
   hardware data.
3. This measurement settles the open clock question in LATEST-83. A
   DVFS/OPP driver is still out of scope: nothing in XNU raises MT6768
   clocks today.

## Agent handoff / active work (2026-10-30 LATEST-83: 0102 + cpus=8 BOOTED - ALL 8 CORES ONLINE (incl. both A75s), kAKSUnwrapKey NOW RETURNS 0x0 (12/12) AND kAKSWrapKey TOO (177/177); BOOT STILL PARKS AT THE SAME fairplayd/bluetoothd LOOP, SPRINGBOARD STILL DRAWS NOTHING)

### 0102 + cpus=8 boot, log pulled (observation)

- Image `research/merlin-boot/shim-boot-merlin-msdc-0102-cpus8-fbup-585.img`
  (sha256 `E1099FBB...`, one byte different from the cpus=1 0102 image:
  `cpus=1` -> `cpus=8`), flashed by the user, ran ~60 min, phone to TWRP.
- Pulled read-only as before -> `research/logs/sweetlog-0102-20261031.bin`
  (4,198,400 B) -> `.txt` **404,769 B, 7,248 lines, 363 flushes, last
  3621.523 s (~60.4 min)**, ring not wrapped.
- **SMP WORKS ON HARDWARE (first time in this project):** `SWEET CPU:
  requested=8 selected=8 (limit=8)`, then for cpu 1..7
  `CPU_ON target=0xN00 entry_pa=0x81492000 context=N` /
  `PSCI CPU_ON rc=0` / `mpidr=0xN00 came alive; SGI1 OK`, ending
  `8/8 CPUs initialized, SGI1 verified`. That includes **0x600 and 0x700 =
  the two A75s**, i.e. the second cluster's power domain works through the
  same PSCI path. Patches 0065+0078 are proven on hardware.
- User observation: boot and log output are visibly faster; 8 cores instead
  of 1 A55. (Not yet measured with a controlled timer.)

### AKS: THE 0101 WALL IS GONE (observation)

- `sel 11` kAKSUnwrapKey: **12 calls, all `-> 0x0`** (0101: 290 x
  `0xe00002c2`). First at 10 s, last at 1980 s. The logged blobs are
  `bag 0 class 40 len 40 out 32 own wlen 32 hdr a65959a600000020` -
  the first 8 bytes are exactly our RFC-5649 header with a 32-byte length,
  i.e. the blob WAS produced by our own kAKSWrapKey. The 0101 guard
  (`out_scalars < 1`) was the whole failure.
- `sel 10` kAKSWrapKey: **177 calls, all `-> 0x0`** (0100: 228 failures;
  0101: zero calls). Logged `wrap #n bag 0 class <7/10/11/...> len 32`.
- securityd's last AKS call is at 2801 s; no retry spin. Remaining
  failures are the old three: profiled sel 31 x3, datamigrator sel 93 x1,
  sel 34 x1 (all 0xe00002c7).

### The boot still parks (observation)

- 2,347 execs / 221 distinct names in 60 min (0101: 2,895 / 218 in 76 min).
  Same loop: fairplayd.H2 358, bluetoothd 357 clean exits (zero CRASH lines
  for either), CommCenter 108 crashes (all have CRASH lines), xpcproxy 1162.
- SpringBoard exec'd once, never crashes, makes 5 AKS calls (50 s and
  950 s, all 0x0) and still emits **zero** output lines.
- **SetupAssistant is still never exec'd.** New daemon names vs 0101 are
  only fitnesscoachingd x9, nanoregistryd, ospredictiond, swcd.
- No panic. No new stage. This is the next wall.

### Display probe result (observation + a flaw in the probe)

- `SWEET FB: panel 2 nonzero 42/1280 sig 824551059856bdbd`,
  `panel 200 nonzero 36/1280 sig 1d3aa312ba7d7eaf`: the frame changed
  between presents 2 and 200, but the sampled patterns are sparse vertical
  stripes, i.e. **2x-scaled console text, not UI**. The thumbnail is taken
  from `fPixels` AFTER the layer copy, and on this port the layer surface
  aliases the same panel memory the fbcon draws into, so the probe cannot
  separate console text from an iOS scene. Next version must hash the
  layer surface BEFORE the copy.
- `SWEET FB: 194000 swaps` at 3281.381 s is the LAST swap-counter line,
  although the log runs to 3621 s: **backboardd stopped swapping ~5.7 min
  before the end.** Unexplained; possibly display idle. Worth a counter
  print when swap stops.

### Timing: "50 min to exec" is a screen artifact (observation)

- launchd exec at **35.1 s** after reset (wall timestamp 16:00:35.098,
  `MERLIN CLK: counter now 33948 ms`), SpringBoard at ~39 s, backboardd
  ~45 s. The log's own flush/exec order proves the exec stage starts in the
  first 10 s of log time.
- What takes ~50 min is the *readability* of the console: until
  backboardd's presents stop (3281 s in this run) the panel is overwritten
  at ~10 Hz by the layer copies, so the fbcon text only becomes stable on
  screen near the end. The user's photo (flush 350 at 3491 s) is 3 min
  after swaps stopped.

### Clock question (open; needs a measurement, not a guess)

- `MERLIN CLK: 4194304 dependent adds in 3569 us -> ~2350 MHz core
  (2 cycles/iter)` is the same figure as 0100/0101. The loop is
  `subs`+`b.ne`; if it retires at 1 cycle/iter the core is ~1.175 GHz, and
  2 cycles/iter gives 2.35 GHz, which is ABOVE this SoC's max (2.0 GHz A75 /
  1.8 GHz A55). So one of the two assumptions is wrong and the real clock
  is probably ~1.17 GHz - i.e. the LK OPP, with no DVFS driver in XNU to
  raise it. **Do not quote 2.35 GHz as fact.**
- Planned probe: enable PMCCNTR_EL0 (PMCR.E/C, PMCNTENSET bit 31) and
  compare cycles vs CNTPCT over a fixed interval on every CPU, printing
  per-CPU MHz. That settles cycles/iter and gives the real OPP. If PMU is
  trapped by the secure monitor, fall back to two loop shapes (subs-only
  and adds-only) to solve for cycles/iter.

### Next

1. 0103 proposal: per-CPU PMCCNTR clock report; layer-surface hash BEFORE
   the panel copy (replaces the contaminated thumbnail); print when swaps
   stop. If the layers hash to a constant (e.g. all zero), SpringBoard is
   not drawing at all and the wall is inside SpringBoard/UIKit, not the
   present path.
2. SpringBoard blocker is the main thread now: it is alive, silent, and its
   last AKS call is at 950 s. Candidate causes (guesses): missing
   IOAcceleratorES (334 `-> 0 found`), waiting on a Mach service that never
   registers, or a UIKit status-bar/screen-size assertion. The 0054 process
   sampler could dump its kernel stack if extended to user threads.
3. cpus=8 is now the default candidate cmdline for future timing tests; keep
   the cpus=1 image for A/B.

### Patch 0083 written (action)

- Created xnu/patches/0083-sweet-clk-measure-debug.patch (2 hunks, 2 files):
  - pexpert/pexpert/arm64/SWEET.h: SWEET_SMP_MAX_CPUS 6→8; added PMCR_E/PMCR_C/PMCNTENSET_CNTEN0 bit defs for PMCCNTR_EL0 enable.
  - iokit/Kernel/arm/SweetCPU.cpp: removed phys_id > 0x500 check in start() (keeps (phys_id & 0xff) != 0 and num_cpus > MAX so A75s mpidr 0x600/0x700 are allowed); added forward declarations for sweet_pmccntr_enable() / sweet_measure_cpu_mhz(); call both from initCPU() and print per-CPU MHz via kprintf ("SWEET CLK: cpu=N mpidr=0xNNNN M MHz"); if PMCCNTR reads don't advance, prints "PMU trapped, clock unknown".
- Patch pushed to ios-sweet origin (commit a2fc114 via merge 2876f1b). Push to ios-sweet triggers xnu.yml CI workflow (per fetch-kernel-artifact.py docstring: CI runs when head touches xnu/patches/**). CI build applies the patch and builds the kernel on macOS runners.
- Remaining after CI: user downloads the built kernel, packs it into a boot image, then `fastboot boot` (never flash) and checks the boot log for `SWEET CLK: cpu=N mpidr=0xNNNN M MHz` lines on all 8 CPUs.

## Agent handoff / active work (2026-10-30 LATEST-82: 0102 BUILT BY CI AND PACKED - shim-boot-merlin-msdc-0102-fbup-585.img READY; WAITING FOR THE USER TO FLASH BOOT)

### 0102: root cause of the 0101 AKS wall (established from the source)

- The 0101 `sel 11` failures never reached the stub. The selector dispatch in
  `AppleKeyStoreUserClient::externalMethod` had
  `case kAKSUnwrapKey: if (out_scalars < 1) { ret = kIOReturnBadArgument; break; }`
  and securityd calls it with `out 0/32` - key bytes only, no length scalar.
  All 290 calls returned `0xe00002c2` from that guard, not from the blob
  header. The 40-byte input may well have been a well-formed blob.
- 0102 removes the guard and writes the key to the structure output descriptor
  without touching `scalarOutputCount` when the caller passed no output scalar.
- Instrumentation in the same build: `SWEET AKS: unwrap #n bag .. class ..
  len .. out .. own/FOREIGN wlen .. hdr <8 bytes>` for the first 8 and every
  128th call; `SWEET AKS: wrap #n bag .. class .. len ..`. That answers both
  open questions from LATEST-81 (what the blob is, and why sel 10 vanished).
- FB: at layer-0 present #2 and #200, `sweet_fb_thumb` logs a 32x40
  luminance ASCII thumbnail of the panel plus `nonzero n/1280` and an FNV
  signature, so a black / static / changing composition is readable from the
  log without a photo.

### 0102 build (observation)

- Patch `xnu/patches/0102-sweet-aks-unwrap-diag-fb-thumb.patch` (6,706 B, LF,
  2 files), ios-sweet commit `063b196`, pushed `10ae489..063b196` to
  `fork/msdc-0079`.
- CI run **41020854873** (sha `063b1967`): success 07:42:47 UTC, ~8 min total.
  Artifacts `xnu-kernel` 12961004586 (60,068,774 B) and `xnu-buildtree`
  12960809979 (23,216,311 B) -> `research/art-0102/`.
  Kernel `kernel.development.sweet` 17,241,256 B,
  sha256 `A3B949D4FFB6F5C1AA133345C43CD0A30B667B566932C4B09A2242F061510B17`.
- Image `research/merlin-boot/shim-boot-merlin-msdc-0102-fbup-585.img`,
  17,021,907 B, sha256
  `95899D154C1330DBE670E878B3213B4576C7A9767F715E3032E78E583AC9EBE8`.
  Builder verify: payload 16,646,048 B, cmdline unchanged, shim slot + dtb
  byte-identical to E1, ADT/Video base 0x7e605438 -> 0x7e39c458, round-trip OK.
- Confirmed the new format strings are inside both the CI kernel and the packed
  image (`SWEET AKS: unwrap #`, `SWEET FB: |`, `panel 200`, `wrap #%u bag`), so
  the image really carries 0102 and not a stale payload.

### SMP variant (user request 2026-10-30): cpus=8

- The port has had SMP support since 0065 (PSCI CPU_ON + secondary reset
  trampoline) and 0078 raised `SWEET_SMP_MAX_CPUS` to 8; the packed ADT has
  all eight `cpu-id` nodes (0x0..0x7). Every boot log so far says
  `SWEET CPU: requested=1 selected=1 (limit=8)`, i.e. only the cmdline kept
  the boot single-core. No log in research/logs shows a boot with cpus>1,
  so the SMP path is UNTESTED on this hardware.
- Built `research/merlin-boot/shim-boot-merlin-msdc-0102-cpus8-fbup-585.img`
  (17,021,907 B, sha256
  `E1099FBB9ABF0F7826CEB4F4182E5A8AE4D07EDBCF7EC456CFEE9A6E5FCB7684`) from the
  same 0102 kernel with `--cmdline` where `cpus=1` -> `cpus=8`. Verified:
  it differs from the 0102 cpus=1 image in exactly ONE byte (offset
  194656, `1` -> `8`), so core count is the only variable.
- Expected in the log if it works: `SWEET CPU: requested=8 selected=8`,
  seven `cpu_start() cpu: N` lines and `cpu=N mpidr=0xN00 came alive;
  SGI1 OK`. Expected failure modes: hang right after `cpu_start() cpu: 1`
  (PSCI CPU_ON rejected / wrong entry), or a panic in
  `sweet_secondary_entry` (cache/MMU state). A75s (mpidr 0x600/0x700) are
  the riskiest pair: different cluster power domain, and the port treats
  them as homogeneous.
- Fallback ladder if 8 fails: `cpus=2` (two A55, same cluster), then
  `cpus=4` (all A55). Both are cmdline-only rebuilds, no CI.
- Core count does NOT address the stall: the boot is single-threaded and
  waiting by SpringBoard time. It only speeds the daemon-start/IO burst
  (218 daemons, 389 execs in the first ~3 min on one A55).

### Next

1. User flashes `boot` with the 0102 image (confirm first), boots, photographs
   the first frame, lets it run, then pulls the log via TWRP as in LATEST-81
   (last 1025 x 4 KiB of `/dev/block/mmcblk0p46`, skip 12,710,135).
2. In the new log: `unwrap #n ... own|FOREIGN` -> does securityd stop retrying
   sel 11 after 0102 answers it, and does anything new appear after that?
   `SWEET FB: panel 2` / `panel 200` thumbnails -> is the composition black,
   static (same sig) or changing?
3. CI run again only after the next change is written; the workflow
   concurrency group cancels queued/in-progress runs.

## Agent handoff / active work (2026-10-30 LATEST-81: 0101 BOOTED ~76 MIN AND ITS ON-DISK LOG PULLED - kAKSWrapKey (sel 10) IS GONE, securityd NOW RETRIES kAKSUnwrapKey (sel 11) x290 WITH A 40-BYTE BLOB THE STUB REJECTS (0xe00002c2); UI STILL BLACK, SAME fairplayd/bluetoothd CLEAN-EXIT LOOP)

### 0101 boot + log pull (observation)

- Device merlin `204719200409`, image `research/merlin-boot/shim-boot-merlin-msdc-0101-fbup-585.img`
  (sha256 `D2391D21...`) flashed 2026-10-29, booted 2026-10-30.
- Photo at flush 361 @ 3611.563 s (1 h 00 m 11 s): Apple logo + static
  progress bar + kernel console; exactly four lines between flushes
  (`exec xpcproxy`, `exec fairplayd.H2`, `exec xpcproxy`, `exec bluetoothd`),
  i.e. the same 10 s respawn cycle as 0100 at 62 min.
- Pulled read-only from TWRP by `adb shell dd` of the last 1025 x 4 KiB of
  userdata (`/dev/block/mmcblk0p46`, 52,064,911,360 B) at skip 12,710,135 ->
  `research/logs/sweetlog-0101-20261030.bin` (4,198,400 B) -> `.txt`
  **418,051 B, 7,884 lines, 455 flushes, last flush 4542.034 s (~75.7 min)**.
  Ring not wrapped (whole boot present, from the kernel banner).
- Boot: `MERLIN CLK ... counter now 33667 ms`, 2349 MHz core,
  `MERLIN MSDC: init took 11 ms`; final MSDC line `245185 cmds 8618040 KiB
  in 285379 ms -> 30198 KiB/s` (last CMD25 x32 731 us). `readverify enabled`,
  no mismatch line at all. **DMA SPILL 128 lines, max count 127000** - the
  same canary false positive as 0100 (118 lines, 117000, see below).
- No panic. 2,895 execs / 218 distinct names; xpcproxy 1436, fairplayd.H2
  **441**, bluetoothd **436**, CommCenter 109 (all 109 have `CRASH` lines),
  homed 12 crashes, driverkitd 1. SpringBoard is exec'd once, never crashes,
  makes 5 AKS calls (sel 0/35/7/35 at 50 s, sel 7 again at 960 s) and emits
  **zero** stdout lines; the only `|backboardd|` lines are the 15 objc
  duplicate-class warnings at 20 s.

### AKS: 0101 changed the failure but did not unblock (observation)

- 2,139 AKS calls, 242 distinct signatures.
- 0100: `securityd sel 10` (kAKSWrapKey) **228 x 0xe00002c7**. 0101: **no
  sel 10 call at all**, at any point in the boot.
- 0101: `securityd sel 11` (kAKSUnwrapKey) **290 x `in 2/40 out 0/32 ->
  0xe00002c2`** (kIOReturnBadArgument), first at 40 s, last at 4202 s;
  ~4/min with long gaps, i.e. a slow retry, not a spin.
- Unchanged failures: `profiled sel 31` 5 x 0xe00002c7 (0/32768 out),
  `com.apple.datamigrator sel 93` 1 x, `sel 34` 1 x.
- Inferences (guesses, NOT established): the 40-byte input is the shape our
  own `sweet_aks_wrap_key` emits (8-byte RFC-5649 header + 32-byte key), but
  it is also the shape of a real keybag blob, and the 0101 stub prints no
  bytes, so the log cannot say which. The disappearance of sel 10 is
  likewise unexplained; the selector change means securityd took a
  different branch than on 0100.

### Display state (observation + one correction)

- `SWEET FB: 206000 swaps` at the end (0100: 205000) and the 0056 present
  path copies layer surfaces to the panel, so backboardd is compositing.
  `IOK backboardd: matching ... IOAcceleratorES ... -> 0 found` x334 and
  `ApplePearlSEPDriver -> none` in both logs. The screen nevertheless shows
  only the shim splash + console text: the composition carries no UI.
- CORRECTION to LATEST-79/80: "console still on screen" is NOT evidence that
  no frame was presented. `sweet_console_muted` is only set when boot-arg
  `sweetfb_noconsole=1` is present (0067), and this cmdline lacks it, so the
  console always draws over the GUI. Absence of UI is established by the
  photo (black + logo + bar + text), not by the console.
- The DMA SPILL lines are a 0085/0098 canary artifact, not corruption: they
  start in the first seconds (count 1: `bad 1984 first 64 len 512`), appear
  on both boots (117000 vs 127000 by the end), and readverify never reported
  a mismatch across ~8.6 GB. Do not chase them.

### Next

1. 0102 (NOT written yet): on a rejected sel 11, print the first 16 bytes +
   length of the blob, and make unwrap tolerant (any 8..40-byte input ->
   deterministic 32-byte key, still logging which branch was taken) so one
   build both diagnoses and unblocks. Also print the sel 10/11 scalar args
   to explain why sel 10 vanished.
2. UI thread is now the bigger question: SpringBoard is alive and silent,
   its last AKS call is at 960 s, and backboardd presents frames that contain
   no UI. Next diagnostic should look at the composited layer mask (which
   surfaces are enabled at present time), not at AKS.
3. Phone is in TWRP as of the pull; nothing else is pending on the device.

## Agent handoff / active work (2026-10-29 LATEST-80: 0101 BUILT BY CI AND PACKED - shim-boot-merlin-msdc-0101-fbup-585.img READY; WAITING FOR THE USER TO FLASH BOOT)

### CI for 0101 (sha 10ae489): five queue deaths, then success

- Attempts 1-4 (40935174767, 40937688647, 40940113658, 40942535153) all died
  to the hosted-runner capacity problem: ~15 min queued, cancelled, **zero
  steps**.  The detached watcher (research/tmp-msdc-split/retry-build-0101.py,
  download step removed - par-dl.py fetches instead) re-dispatched each time.
- User started triggering manually from the UI.  LESSON LEARNED (recorded for
  the next time): the workflow's concurrency group (xnu-msdc-0079,
  cancel-in-progress) means **every new queued run kills the previous one** -
  the watcher's attempt 6 cancelled the user's first in-flight build, and
  each further manual trigger cancelled the previous queued run.  The watcher
  was killed (PID found via CommandLine match) as soon as this was visible.
  **Never run the watcher and manual triggers at the same time.**
- **Run 40949232694 (user's trigger, 20:27:44Z) SUCCEEDED** at 20:35:18Z
  (~7.6 min build).  Artifacts: `xnu-kernel` id **12930279836**
  (60,067,850 B), `xnu-buildtree` id **12931790905** (23,214,759 B); both
  downloaded with par-dl.py in a single round each and extracted to
  research/art-0101/; `kernel.development.sweet` 17,238,288 B, sha256
  `4a996d3e3193096ef68e7654f209b80ae9d0bd2112cadd21aff561951b3e62d8`
  (matches the artifact SHA256SUMS).

### 0101 image BUILT and verified (NOT flashed)

- `research/merlin-boot/shim-boot-merlin-msdc-0101-fbup-585.img`:
  **17,021,907 bytes, sha256
  `D2391D21276743DC159978543A2E3B77C368024BFEDD4FFA7238AB2CFAD61911`**
- Builder verify: SWEETXNU payload 16,645,856 B; cmdline OK (0099 cmdline
  unchanged); shim slot + dtb byte-identical to the E1 baseline; display
  base 0x7e39c458 re-applied (ADT reg at payload+0xfdfcd8 + boot_args Video
  base); shim.gz round-trip OK.
- What 0101 adds vs 0100: AKS WrapKey/UnwrapKey stub (see LATEST-79) - the
  only change is the SweetKeyStore.cpp hunk.

### Next

1. User flashes `boot` with the 0101 image (`fastboot flash boot` +
   `fastboot reboot`, never `fastboot boot`), lets it run, photographs the
   first frame, then reboots to TWRP read-only for the log pull.
2. Read the new log: securityd sel 10 should now return 0x0 (and the first
   kAKSUnwrapKey calls will show their real argument shapes).  Success
   signal: UI presents (console-mute fires) or new AKS selectors get
   exercised; failure signal: fairplayd/bluetoothd loop continues and the
   next wedge should name itself in the log.

## Agent handoff / active work (2026-10-29 LATEST-79: 0100 ON-DISK LOG READ END-TO-END - CPU 2.35 GHz AND CARD ~50 MB/s (BOTH SLOW-THEORIES DEAD); BOOT REACHES SpringBoard+backboardd BUT securityd RETRIES kAKSWrapKey FOREVER; PATCH 0101 (WRAPKEY/UNWRAPKEY) WRITTEN AND REHEARSED, NOT YET BUILT)

### The 0100 log (research/logs/sweetlog-0100-20261029.txt; phone in recovery, pulled read-only via adb dd of the last 1025 4K blocks of userdata)

- Ring flush #416 at 4151 s.  Boot timeline: **33.9 s** power-on -> MSDC
  attach (`MERLIN CLK: ... counter now 33920 ms`), then log start (flush 1
  = 0 s) and userspace.
- **CPU-clock hypothesis DEAD**: `4194304 dependent adds in 3569 us ->
  ~2350 MHz core`.  **Card-path hypothesis DEAD**: MSDC init 11 ms, reads
  steady 49-51.6 MB/s during bootstrap (~29.7 MB/s cumulative by flush 380
  once random I/O dominates).
- The 69 minutes were NOT a freeze: flushes every 10.004 s with no gaps the
  whole run.  launchd did the full bootstrap in minutes (389 execs in the
  first 3 min, 200+ distinct daemons), then idled/respawned for the rest,
  re-reading ~8.1 GB through the crash-respawn churn.
- Userspace got FAR: `exec SpringBoard` at ~5 s (its AKS calls sel 0/35/7
  all -> 0x0), backboardd `open AppleCLCD type 0 -> 0x0`, `SWEET FB:
  display on` at ~50 s.  Yet no frame was ever presented (the console was
  still on screen; 0056 present/0067 console-mute would have hidden it) -
  SpringBoard never drew frame 0.
- AKS stub score: 1732 of 1734 calls succeed.  The failures:
  **securityd sel 10 = kAKSWrapKey, 228 x kIOReturnUnsupported
  (0xe00002c7), retried forever** (in 2/32 out 1/40 - RFC 5649 shape for
  32-byte keys), plus profiled sel 31 x3 and datamigrator sel 93/34 x1.
  securityd never exits - it spins on WrapKey.
- Steady-state respawn loop: fairplayd.H2 x403, bluetoothd x401 (silent
  exits, no jetsam/kill lines, no crash reports - waiting on services),
  CommCenter x108 (crosses the 32-thread watermark each life - spins on
  missing baseband; harmless).
- Survived early errors (context, not the wedge): root volume unsealed
  (error 25), libignition preboot lookup fail 25, launchd
  vm_shared_region check_np failed, Jetsam 50 MB HWM opt-in fail 22.

### Patch 0101 (WRITTEN + REHEARSED, NOT built, NOT flashed)

- `ios-sweet/xnu/patches/0101-sweet-aks-wrapkey.patch` (4,840 B, 2 hunks,
  LF): implements kAKSWrapKey (10) / kAKSUnwrapKey (11) in
  SweetKeyStore.cpp.  Blob = RFC 5649 header (0xA65959A6 + BE32 length) +
  key XOR a fixed 32-byte pad - no corecrypto in the SWEET kernel (0013),
  so this is self-consistent wrap/unwrap, not real AES; protects no
  secrets (no passcode, no keybag).  scalarOutput[0] = blob/key length;
  unwrap validates header and length.  Securityd's next call pattern will
  print itself (every AKS call is logged).
- Rehearsal: `git apply --check` clean against the post-0096 tree
  (research/tmp-0096/xnu, SweetKeyStore.cpp is post-0055; 0097-0100 don't
  touch it), applied result byte-identical to the worked tree after EOL
  normalization; braces/parens balanced; 0097-0100 patch set has no
  SweetKeyStore overlap.
- Reusable downloader for the next CI run:
  `python research/tmp-msdc-split/par-dl.py ARTIFACT_ID TOTAL_BYTES OUT.zip [BUDGET_S]`
  (sizes come from the artifacts API; parallel range parts, resumable).

### Next

1. Confirm with the user, then push ios-sweet and dispatch xnu.yml (the
   local-only rule covers ios-merlin; the fork push is the established CI
   path - but it still gets a yes first).
2. When the run succeeds: par-dl the artifacts, build
   `research/merlin-boot/shim-boot-merlin-msdc-0101-fbup-585.img` with
   make-0099-image.py, flash boot (confirm again), boot, photo + log pull.
3. Read the new log: if securityd proceeds, look for the first UI present
   (console-mute) or the next wedge by name; if fairplayd/bluetoothd still
   loop, their wait target will show in the exec/service pattern.

## Agent handoff / active work (2026-10-29 LATEST-78: 0100 BOOT PHOTOGRAPHED AT ~62 MIN - LAUNCHD ALIVE AND EXEC'ING, BUT fairplayd.H2 + bluetoothd CRASH-RESPAWN IN A ~5 s LOOP AND NO MAIN UI; NEXT = PULL THE ON-DISK LOG VIA TWRP)

### Photo 2026-10-29 20:13 local (phone running the 0100 image, booted ~19:10)

Observations (read off the photo, user: "Just this, no main Display just this"):

- Screen shows only the kernel console, no SpringBoard/main UI.
- `MERLIN LOG: flush N` lines 362..376 at 3611.527 s -> 3751.586 s, every
  **10.004 s** (3611.527, 3621.531, 3631.535, 3641.540, 3651.544, ...,
  3751.586 - deltas all 10.004 s, +4 ms drift).  flush 376 at ~3751 s =
  **~62.5 min after boot start**; MERLIN LOG prints are 0100-only, so this
  is the 0100 image flashed at ~19:05-19:10 local, after LATEST-77 built it.
- Between every consecutive pair of flushes exactly four lines:
  `exec xpcproxy`, `exec fairplayd.H2`, `exec xpcproxy`, `exec bluetoothd`.
  One spawn pair per ~5 s, alternating, stable across the whole visible
  window (>= 140 s of history).
- Console text starts at the very top of the panel (first line half-clipped
  under the bezel) - the 585-row shift behaves as designed ("log at the
  top"); exact overshoot can't be judged because the console wrap point
  scrolls.  Older flushes 362-365 reappear lower on screen (framebuffer
  console wraparound, cosmetic).

Inferences (marked guesses):

- Kernel AND launchd are alive; userspace reached exec'ing daemons - far
  beyond any earlier state.  The arch counter/timer runs at real-time rate
  (10.004 s flush cadence), so the wall clock is not drifting.
- GUESS: fairplayd.H2 and bluetoothd exit within seconds and launchd
  respawn them forever (deterministic ~5 s cycle).  SpringBoard is never
  exec'd, hence no main display.  Prime suspect stays the AKS/0038 stub
  (cf. the captured `SWEET AKS: profiled sel 31 -> 0xe00002c7` boot-loop
  line) or another unimplemented mach service both daemons wait on; the
  earlier "launchd/CommCenter loop" note (0099 planning) is likely the same
  phenomenon at an earlier stage.
- The `MERLIN CLK` (CPU MHz) and `MERLIN MSDC` answers are NOT in the photo
  (they print early and scrolled/wrapped away); they are in the on-disk log.

### Next

1. Reboot the phone to TWRP **read-only** and pull the on-disk log with
   `tools/sweet-log-pull.sh` (needs the user's hands for the button combo).
   The log has: `MERLIN CLK` counter-at-attach + CPU MHz, `MERLIN MSDC`
   per-command/per-16 MiB rates and init time, every flush timestamp, and -
   the actual prize - launchd's exec/exit history: which service call fails
   first and why fairplayd.H2/bluetoothd crash-loop.
2. Diagnose from the log, then pick the next patch (AKS stub extension vs
   CPU clock vs card path).
3. Display: treat the 0100 image's top-anchored console as the working
   585-row baseline; refine dy only if a later photo shows overshoot.

## Agent handoff / active work (2026-10-29 LATEST-77: 0100 CI BUILD SUCCEEDED (run 40899159128); BOTH ARTIFACTS DOWNLOADED TO research/art-0100; 0100 BOOT IMAGE BUILT AND VERIFIED - WAITING FOR PHONE IN FASTBOOT TO FLASH IT)

### What happened to the 0100 build on 2026-10-29 (all sha 833022d, branch msdc-0079)

- Run 40893883100 (14:40Z) and run 40896507205 (14:56Z) both **failed with the
  capacity problem**: job `build` "was not acquired by Runner of type hosted
  even after multiple attempts", cancelled with **zero steps** (annotations
  read directly from the check-runs API).  ~15 min queued each, nothing built.
- Run **40899159128** (created 15:12:17Z by the retry loop) got a macOS runner
  and **succeeded** (first CI success since 40882565021/0099).  Live artifacts
  (unexpired, IDs for re-download):
  - `xnu-kernel` id **12908838442**, 60,058,300 bytes
  - `xnu-buildtree` id **12909162570**, 23,213,210 bytes
- The retry script (`research/tmp-msdc-split/retry-build-0100.py`) dispatched
  that run itself, then hung in its download (~35 min, ESTABLISHED connection,
  no data): **`tools/fetch-kernel-artifact.py::fetch` and `tools/gh-ci.py::req`
  set no socket timeout**, so a stalled TLS connection blocks forever.
  The process later exited having created nothing; `research/art-0100/` was
  still absent.  Sequential curl resume also died twice (link stalls below
  1 KB/s for >60 s; background tasks get killed at ~10 min here).
- Fix that worked: **`research/tmp-msdc-split/par-dl.py`** (local-only,
  research/ is gitignored) - 12 parallel curl range parts, each resuming from
  its own byte offset, `--speed-limit 1000 --speed-time 30` abort + re-run.
  Parallel connections beat the per-connection stall cap (~4x).  Re-running
  it is idempotent; finished parts are kept.
- Both artifacts downloaded and verified (zips kept in `research/art-0100/`):
  - `kernel.development.sweet` 17,241,032 B, sha256
    `3f3c531768dae27621f7b6f28b9ae31a78791fd47f80e132b5ebb545d6ddc036`
    (matches the artifact's SHA256SUMS)
  - `kernel.development.sweet.link/` + dSYM lldbmacros for symbolication;
    `buildtree.tgz` from artifact-12909162570 not yet extracted.

### 0100 image BUILT (2026-10-29, not flashed)

`python research/tmp-msdc-split/make-0099-image.py research/art-0100/kernel.development.sweet --out research/merlin-boot/shim-boot-merlin-msdc-0100-fbup-585.img`

- `research/merlin-boot/shim-boot-merlin-msdc-0100-fbup-585.img`:
  **17,021,907 bytes, sha256
  `8B0122DBD4A4E9ABBAF683E9EAF52F9A4E469361B528E5E5CFD2995D39C3E417`**
- Builder verify output: SWEETXNU payload 16,645,824 B; cmdline OK (0100
  keeps the 0099 cmdline incl. `msdc_readverify=1`); shim slot + dtb
  byte-identical to the E1 baseline; display base 0x7e605438 -> 0x7e39c458
  applied to BOTH the ADT sweet-fbcon reg (payload+0xfdfcb8 - offset moved
  because the payload is regenerated from the 0100 kernel) and boot_args
  Video base (same 585-row shift as the already-flashed 0098 display test);
  patched movz/movk at shim+0x3860, gzip size unchanged (9471 B); shim.gz +
  payload + dtb round-trip OK.

### Next

1. When the phone is in fastboot: **flash `boot` with the 0100 image
   (confirm with the user first)**, `fastboot reboot`, let it run the 40-60
   min boot, boot TWRP read-only and pull the log with
   `tools/sweet-log-pull.sh`.
2. Read the `MERLIN CLK/MSDC/LOG` lines: CPU MHz, counter-at-attach,
   per-command and per-16 MiB KiB/s, flush timeline; pick the next fix
   (CPU clock / card path / pre-driver boot).
3. Display test still waiting: phone flashed with
   `shim-boot-merlin-msdc-0098-fbup-585.img` (sha256 `9C8A3364...`), one photo
   of the first frame decides whether the 585-row shift is right.  The 0100
   image keeps the same display base, so its first frame doubles as that
   photo if the 0098 test is skipped.

## Agent handoff / active work (2026-10-29 LATEST-76: 0100 BOOT-TIMING INSTRUMENTATION PUSHED, CI RUN 40891076950 BUILDING; PHONE NOT IN FASTBOOT, DISPLAY TEST STILL WAITING)

### 0100: what the next boot will tell us (commit `833022d`, CI run 40891076950)

- User's idea: the 40-60 min boot may be a CPU-clock problem, so 0100 measures
  instead of guessing.  Patch `ios-sweet/xnu/patches/0100-merlin-boot-timing.patch`
  (8,018 B) applies on top of 0099; the 0099+0100 chain reproduces the worked
  driver tree byte for byte (66,785 B, LF-normalized), so CI builds exactly what
  was tested locally.
- New prints (`msdcprobe=0` disables only the CPU loop):
  - `MERLIN CLK: cntfrq ... hz ..., counter now N ms` - the arch counter at
    attach.  If the SoC counter starts at zero this is the time from power-on to
    the MSDC driver, which separates a slow LK/shim/kernel-init boot from a slow
    card path.
  - `MERLIN CLK: 4194304 dependent adds in U us -> ~M MHz core (2 cycles/iter)`
    - a core left at ~100 MHz by the bootloader would explain everything; a
    ~2 GHz reading clears the CPU.
  - `MERLIN MSDC: cmd N read/write xS took U us` for the first five commands.
  - `MERLIN MSDC: ... cmds ... KiB in ... ms -> ... KiB/s (last CMD18 xS U us)`
    every 16 MiB.  A per-command timeout stall reads ~100 KiB/s; a healthy CMD18
    path reads tens of MiB/s.  This is also the first hard check of the 0098
    multi-block claim.
  - `MERLIN LOG: flush N at S.mmm s` before every 10 s flush, so the on-disk log
    dates itself.
  - `MERLIN MSDC: init took N ms`.
- Run 40891076950 never got a macOS runner: job `build` sat queued 15 min and
  was cancelled with 0 steps (same GitHub capacity problem as 0098 on
  2026-10-28).  The first retry died on a local DNS blip while polling; the
  script now retries network errors (GET and POST) and adopts a run id given as
  argv[1].  Current attempt: **run 40893883100** (sha 833022d), adopted with
  `python research/tmp-msdc-split/retry-build-0100.py 40893883100`; it
  re-dispatches by itself if this one is cancelled and downloads to
  `research/art-0100` (16 attempts, 6 h cap).
- Plain `fastboot boot`/flash rules unchanged: flash `boot` only, never boot the
  image from fastboot, never touch bootloader/recovery/modem/persist.

### Phone state (2026-10-29 ~14:45Z)

- **Flashed and rebooted** `shim-boot-merlin-msdc-0098-fbup-585.img`
  (sha256 `9C8A3364...`, boot partition, 16,606 KB, `fastboot flash boot` +
  `fastboot reboot`, not `fastboot boot`).  Waiting for the user's photo of the
  first visible frame to judge the 585-row shift.
- Fallback if the ADT move panics or the log block vanishes:
  `shim-boot-merlin-msdc-0098-fbup-585-ba.img` (`E50665AE...`) moves only the
  boot_args UI base.

### Next

1. Flash the display test as soon as the phone is in fastboot; one photo decides
   whether the UI moves up by 585 rows (logo 48%, bar 55%, log at the top).
   Keep it as baseline if right; rebuild with a smaller dy if it overshot; flash
   the `-ba` variant if the ADT move panics.
2. When run 40891076950 succeeds, build the 0100 image with
   `research/tmp-msdc-split/make-0099-image.py research/art-0100/kernel.development.sweet
   --out research/merlin-boot/shim-boot-merlin-msdc-0100-fbup-585.img`
   (or `--fb-base 0x7e605438` to keep the display question separate), flash it,
   let it run, boot TWRP read-only and pull the log with
   `tools/sweet-log-pull.sh`.
3. Read the CPU MHz, counter-at-attach, MSDC KiB/s and flush timeline, then pick
   the next fix (CPU clock / card path / pre-driver boot).

## Agent handoff / active work (2026-10-29 LATEST-75: LAST DISPLAY TEST WAS INVALID - REPACK BUG FOUND AND FIXED; FIRST REAL TEST OF THE "PANEL SCANS 585 ROWS BEFORE THE FB BASE" THEORY IS BUILT AND WAITING FOR THE PHONE IN FASTBOOT; AKS BOOT-LOOP LINES CAPTURED)

### Repack bug that invalidated the previous display test (root cause, confirmed)

- `...-fbdy-585.img` (patched `con_fb`) rebooted at the Redmi logo.  That was
  **not** the display change: `patch-shim-fbbase.py` sliced the ramdisk at
  header `recovery_dtbo_offset`, which is 0 in these images (parts are stored
  sequentially: header page, kernel, ramdisk, dtb).  The rebuilt image carried
  the first page of the boot image as its ramdisk, so the payload/ADT were
  garbage and iOS never started.
- Both repack tools now slice sequentially (`ps + align(ks,ps)`, then
  `+ align(rs,ps)`) and assert `payload[:4] != b"ANDROID!"`; the round-trip
  verify (`tools/unpack_bootv2.py`) compares shim.gz, ramdisk and dtb byte for
  byte.  Same bug class could have hit any earlier hand-repacked image.

### Where the iOS boot-UI base really comes from (disassembly, confirmed)

- `0x7e605438` appears as an 8-byte literal twice in the shim: start.S paint
  code (shim+0x1828, loaded at 0x814) and `con_fb` (.data 0x4c48, used at
  0x2518).  Moving `con_fb` resets the phone before anything is printed.
- The *loader* writes the boot-UI base into `boot_args.Video.v_baseAddr` with
  `mov w9,#0x5438; movk w9,#0x7e60,lsl 16` at **shim+0x3860**, followed by
  v_display=1, v_rowBytes=4320 (0x10e0), v_width=1080 (0x438), v_height=2340
  (0x924), v_depth=32.  That movz/movk pair is unique in the shim.
- New tool `tools/patch-shim-videobase.py` patches that pair, optionally the ADT
  `sweet-fbcon` reg `<0x7e605438,0x9a3f80>` (payload+0xfdbc48; 0x9a3f80 =
  2340*4320 = one full frame), repacks and round-trip verifies.

### Images built 2026-10-29 (not flashed yet)

| file (`research/merlin-boot/`) | change | sha256 |
| --- | --- | --- |
| `shim-boot-merlin-msdc-0098-fbup-585.img` | boot_args base **and** ADT reg = `0x7e39c458` | `9C8A3364055353B9D281F2AB138A030B894E1D0245A1DDEAF4D6BC46438F20B7` |
| `shim-boot-merlin-msdc-0098-fbup-585-ba.img` | only boot_args base (fallback if the ADT move panics) | `E50665AED0ED430BB0CF4EBE0E692AD00A5DF4A2ADECDA331234677A22B77808` |
| `shim-boot-merlin-msdc-0098-window-be-fb270.img` | known-good baseline | `1D776751...` |

- Shim diff vs fb270 is exactly 4 bytes at 0x3861,0x3862,0x3864,0x3865; the
  shim's own console (`con_fb` at C) is untouched, and payload/dtb are
  byte-identical apart from the ADT reg in the first image.

### Panel-start hypothesis, and why 585

- If the panel window starts at B and we draw at D, content appears at
  (D-B)/4320 rows.  Drawing at C=`0x7e605438` puts the logo at 73% / the bar at
  80% of the long axis (iPhone X design: 48%/55%) and the kernel log block
  starts 25% down - one global shift of ~25%.  25% of 2340 = 585 rows exactly,
  so B = C - 585*4320 = **0x7e39c458** and moving the draw base to B should put
  row 0 at the top.  The 585 is still derived from the measured 25%, not from a
  register dump; if it overshoots, rebuild with a smaller dy.
- The ADT reg only drives the kernel text console; patch 0046 feeds the UI from
  `Video.v_baseAddr`.  Moving both keeps logs and UI aligned.

### Boot-loop evidence from the console photo (2026-10-28, current good image)

- `SWEET AKS: profiled sel 31 arg0 0 in 1/0 out 0/32768 -> 0xe00002c7` -
  `profiled` asks for a 32 KiB output buffer that patch 0038's stub does not
  handle.
- `profiled sel 17 ... out 0/4096 -> 0x0` (works),
  `securityd sel 10 arg0 0 in 2/32 out 1/40 -> 0xe00002c7` (WrapKey, unsupported).
- Daemons cycling: `exec xpcproxy`, `corecaptured`, `fairplayd.H2`,
  `bluetoothd`.  The 0098 attach line (`MERLIN MSDC: ... CMD18/CMD25`) has not
  been seen on screen yet.

### 0099 pushed: console log over MSDC (CI run 40882565021, queued)

- Patch `xnu/patches/0099-merlin-msdc-sweetlog.patch`, commit `a3b4153` on
  branch `msdc-0079`, pushed to the fork; `gh-ci.py dispatch ... msdc-0079`
  -> run **40882565021** (sha a3b4153), queued 13:30Z.  The earlier run
  40882322430 was cancelled by the re-dispatch (concurrency group).
- Content: `merlin_msdc_log_thread()`/`merlin_msdc_log_start()`, started at the
  end of `merlin_msdc_init()` after `mo.ready = true`; the same SWEETLOG
  header/4 MiB ring in the last 4 MiB + 4 KiB of userdata, written in 4 KiB
  (8-sector) blocks coalesced up to `msdc_blocks/8` blocks per CMD25 under
  `merlin_msdc_lock`; first flush right after attach, then every `ufslogsecs`
  (default 10 s); `sweetlog=0` disables it.
- Verified `git apply --check --directory=research/tmp-0096/xnu` -> rc 0
  (post-0098 tree); source copy in `research/tmp-0099/`.
- `build-msdcroot0.py` regenerates the payload from `adt.bin`, so the display
  base is **not** inherited from the source image; `make-0099-image.py` now
  re-applies it with `tools/patch-shim-videobase.py` after packing.
  Rehearsal with the 0098 kernel reproduces `fbup-585` byte for byte
  (sha256 `9C8A3364...`), so the two-step build is proven.
- `watch-run.py 40882565021 research/art-0099` runs in the background.
  Image: `python research/tmp-msdc-split/make-0099-image.py
  research/art-0099/kernel.development.sweet` (default source = fb270,
  display base re-applied by the tool).

### Next

1. Flash `...-fbup-585.img` (never `fastboot boot`) once the phone is in
   fastboot, reboot, take one photo: logo should sit at ~48% and the bar at
   ~55% of the long axis, kernel log at the top.
2. Moved correctly -> new display baseline.  Overshot (top cut) -> smaller dy.
   Nothing moved -> 0x3860 is not the UI path and the 0046/ADT route needs a
   register-level look.  Panic/black -> flash the `-ba` variant.
3. 0099 (SWEETLOG over MSDC) is already in CI, run 40882565021; when the
   artifact lands, build the 0099 image and flash it, let it loop for a
   minute, then boot TWRP (read-only) and pull the log with
   `tools/sweet-log-pull.sh` to diagnose the launchd/CommCenter loop.


## Agent handoff / active work (2026-10-28 LATEST-74: 0098 KERNEL BUILT BY CI AND PACKED INTO A FLASHABLE IMAGE; FLASH PENDING THE PHONE ON USB)

### Run 40759087869: success

- Dispatched 21:58:38 local (retry loop), queued, runner acquired
  22:08:42, **build finished ~22:16** - the whole job took ~7.5 min once
  a runner existed (the earlier "~2 h" estimate was wrong).
- Artifacts: `xnu-buildtree` 12848407479 (23,212,175 B) and
  `xnu-kernel` 12847289165 (60,050,508 B), both uploaded 20:16Z.
- `xnu-kernel` downloaded with
  `tools/fetch-kernel-artifact.py get Gytis283123/ios-sweet 12847289165 research\art-0098`
  -> `research/art-0098/kernel.development.sweet`, 17,224,536 B,
  sha256 `18fcdc739ed03805d33272ba7ac82460ae01a0e033e519bb2734b2757adbdf5d`,
  matches the artifact's `SHA256SUMS`.
- Content check (strings in the kernel): `MERLIN MSDC: %u sector(s) per
  data command (CMD18/CMD25), bounce %u KiB`, `msdc_blocks`,
  `merlin-msdc`, `readverify` -> this really is the 0098 driver.
  No `ACMDRDY` literal (register bit name, not a string) - expected.

### Flashable image built (NOT flashed yet)

- `research/merlin-boot/shim-boot-merlin-msdc-0098-window-be-fb270.img`
  - 17,005,523 B, sha256
    `1D776751F72B646FB8700C0E5C4E623CA1CCE8348EA9E3A8D23455819BE975C6`.
  - Built by `research/tmp-msdc-split/make-0098-image.py
    research/art-0098/kernel.development.sweet`; payload 16,629,328 B,
    kernel slot 190,674 B and dtb byte-identical to the flashed 0094
    image, cmdline unchanged (incl. `merlin_excl_pa`), self-verified.
- Rollback: `shim-boot-merlin-msdc-0094-window-be-fb270.img`
  (sha256 `902e5c02...`) is unchanged on disk.

### Blocked: phone is not on USB

- `fastboot devices` and `adb devices` are both empty right now (the
  stray `RZCWA1RND8T offline` device is gone too).  Flash waits for
  merlin (`204719200409`) in fastboot.
- Plan once connected: `fastboot flash boot
  research/merlin-boot/shim-boot-merlin-msdc-0098-window-be-fb270.img`
  then `fastboot reboot` - never `fastboot boot`.

### What to look for after the flash

- Console line `MERLIN MSDC: 128 sector(s) per data command (CMD18/CMD25),
  bounce 64 KiB` (default cap) - proves the multi-block path is active.
- Boot should be much faster than ~7 min; the progress bar should move.
- A/B knob: boot arg `msdc_blocks=1` falls back to the old single-sector
  plan without reflashing (still same image).
- If multi-block misbehaves (timeouts, wrong data, panics in
  `data.kalloc.*`): capture the console, then `msdc_blocks=1` to isolate.

### Next

1. Flash when the phone appears in fastboot; take one boot photo/video.
2. Record the attach line + total boot time vs the ~7 min baseline.
3. Long-axis (~20%) display offset still parked until 0098 boots;
   HFS+ stays 16 GiB (user decision).


## Agent handoff / active work (2026-10-28 LATEST-73: 0098 BUILD NEVER GOT A macOS RUNNER (GITHUB CAPACITY), AUTO-RETRY LOOP RUNNING; 21:53 VIDEO MEASURES THE LONG-AXIS DISPLAY SHIFT)

### Build status: GitHub capacity, not the patch

- Pushed `177ec29` and dispatched; run 40755000295 ended
  `completed/failure` after exactly 15 min (`started_at` 19:31:05,
  `completed_at` 19:46:06) with `runner_name` empty, 0 steps.
- Job annotations fetched from the check-run API:
  - "The job was not acquired by Runner of type hosted even after
    multiple attempts"
  - "Due to capacity constraints, jobs targeting macOS arm64 runners may
    experience longer queue times."
- The repo is public/not disabled, Actions is operational on
  githubstatus.com -> hosted macOS arm64 (macos-14) capacity, not
  billing and not the 0098 patch.  macos-14 is required because its
  Xcode 15 iig matches xnu-8796 (see the workflow comment), so switching
  labels is not free.
- Auto-retry: `research/tmp-msdc-split/retry-build-0098.py` (background,
  16 attempts / 6 h cap).  It waits for each dispatched run to finish
  before dispatching again (the workflow's `cancel-in-progress`
  concurrency group would otherwise kill a queued run), then downloads
  every live artifact into `research/art-0098/`.  First retry:
  run 40759087869 dispatched 21:58:38Z.  The single-run watcher
  `watch-0098.py` is superseded.

### Video 2026-10-28 21:53 (22.4 s, 720x480, 30 fps, current image)

- The phone lies landscape in the frame (portrait top edge = frame right,
  punch-hole top-right).  The boot UI is portrait-correct: the Apple logo
  is upright relative to the phone and the progress bar is below it.
- Measurements from frame 12 (screen long axis 633 px, short axis
  335 px):
  - logo centre 446 px from the phone's top = **70.5%** of the long axis
    (an iPhone boot logo sits at ~45-50%);
  - bar centre **80%** of the long axis (bar length ~60% of the width);
  - logo centre **47.8%** across the short axis (centred).
  -> confirms the still-photo finding: the 270 px fix fixed only the
  short axis; the whole boot UI sits ~20-25% too far along the long
  axis, and it does not move in the 22 s clip.
- Bar static for the whole clip: still the old single-sector kernel
  (0098 unbuilt), so this is the expected slow boot, not a new hang.
- A small glyph sits near the top edge at ~43% across (rounded rectangle
  with a circle, status-bar area).  Unidentified; not blocking.

### Long-axis shift: hypothesis only (user asked to defer until 0098 boots)

- The size (~20% of 2340 = ~470 rows) and the fact that the top of the
  panel is black match the same class of bug as the 270 px column
  offset: the panel/DSI window appears to start ~470 rows before the
  framebuffer, so fb row 0 lands ~470 rows down the panel and the last
  ~470 fb rows are cut off.  This is a hypothesis; it needs the DSI
  window / source base checked (the 270 px fix only adjusted
  `Video.v_baseAddr` by 270 px within the row).

### 0098 image assembly is rehearsed and ready

- `research/tmp-msdc-split/watch-run.py 40759087869 research\art-0098`
  is running in the background (DNS/HTTP retry, 90 s poll, downloads
  every live artifact).
- `build-msdcroot0.py` gained `--src` (source shim+dtb image, default
  unchanged).
- Rehearsal: rebuilding the 0094 kernel with
  `--src shim-boot-merlin-msdc-0094-window-be-fb270.img` and the flashed
  cmdline gives **byte-identical** output, sha256
  `902E5C023E207E189D2BD6EF036C7F981D95ED953774DB5B1EE4FB474489FCE8`
  == the flashed image.  So only the XNU payload changes in the 0098
  image; shim, ADT, fb270 and dtb are reused verbatim.
- One command once the artifact lands:
  `python research/tmp-msdc-split/make-0098-image.py
  research/art-0098/kernel.development.sweet`
  -> `research/merlin-boot/shim-boot-merlin-msdc-0098-window-be-fb270.img`
  (same 17-arg cmdline incl. `merlin_excl_pa=0x9f900000-0x1e700000`).

### Next

1. Let the watcher run; `research/art-0098/` gets the kernel when the
   run finally finishes.
2. Then build the `shim-boot-...-0098-window-be-fb270` image with the
   command above and `fastboot flash boot` + `fastboot reboot` (never
   `fastboot boot`) once the phone is connected.
3. Long-axis offset after 0098 boots; HFS+ stays 16 GiB (user decision).


## Agent handoff / active work (2026-10-28 LATEST-72: 0098 MULTI-BLOCK MSDC PATCH WRITTEN AND VALIDATED (UNBUILT: CI RUNNER STILL DEAD); 270 PX DISPLAY FIX CONFIRMED, ~19% LONG-AXIS OFFSET PRE-DATES IT)

### Display verdict (photo 2026-10-28 20:51, flashed `...-0094-window-be-fb270.img`)

- Horizontal (phone short axis) centering is FIXED: the Apple logo sits at
  ~48-51% across the screen's short axis (pre-fix: ~25%).  The 270 px
  scanout offset (`0x7e605438` vs `0x7e605000`) was the whole cause of the
  left-shifted/wrapped strip.
- A remaining ~19% (~440 panel px) offset along the phone's LONG axis is
  present in BOTH the pre-fix 20:04 photo and the post-fix 20:51 photo, so
  it is not caused by fb270 and is still unexplained (content sits at
  ~69% of the body length; logo bbox x 2509-2923, y 1399-1729 in the
  90-degree-CW photo).  Not yet investigated; separate from the scanout
  fix.

### CI status (this is the current blocker)

- `python tools/gh-ci.py runs Gytis283123/ios-sweet 10` (new helper, token
  via `git credential fill`): the last three xnu runs 40722066010,
  40583707775, 40579028774 are `completed/failure` with the single `build`
  job `completed/cancelled` and no steps started - the macOS runner is
  still unavailable.  Last success: 40400128627 (0094, 2026-10-26).
- Consequence: 0095, 0096, 0097 and now 0098 are committed/written but
  UNBUILT.  The flashed image is still the 0094 kernel + boot-arg window.

### 0098 multi-block MSDC driver: written, tested, patch generated

- Root cause of the slow boot: one CMD17 per 512-byte sector, ~521,735
  sector reads (~267 MB) at ~0.7 MB/s = ~7 min of "iOS is preparing".
- New driver: `msdc_transfer(lba, nblk, is_write)` issues CMD18 (read) /
  CMD25 (write) for nblk > 1 with auto CMD12, `SDC_BLK_NUM = nblk`,
  `MSDC_DMA_LEN = nblk*512`, up to 128 sectors (64 KiB bounce buffer);
  nblk == 1 keeps CMD17/CMD24.  Strategy moves whole sectors in bulk and
  keeps single-sector head/tail handling (RMW on writes);
  `msdc_read()` also goes through the bulk path.  Boot arg
  `msdc_blocks=N` (1..128, default 128) caps the chunk, printed at attach;
  `msdc_blocks=1` is the old single-sector path, so A/B runs stay possible
  with the 0093 `msdc_readverify` double-read and pattern tripwire intact.
- Auto CMD12 handling: ACMD ready/timeout/CRC join the data wait, but the
  wait only ends on XFER_COMPL or an error bit - ACMDRDY alone does not
  (it can arrive before the data engine completes; an ACMD error
  suppresses XFER_COMPL, see sd.c "Autocmd12 issued but error, data
  transfer done INT won't set").  The 0085 DMA-canary scan starts at the
  requested length (a full 64 KiB CMD18 legitimately fills the bounce
  buffer).
- Artifacts (local only until pushed):
  - `D:\things\Merlin\ios-sweet\xnu\patches\0098-merlin-msdc-multiblock.patch`
    - committed on branch `msdc-0079` as `177ec29` (NOT pushed);
    - 20,366 B, 568 LF lines, 9 hunks, +240/-146,
      sha256 `B22C846C08742376B0A02489A9C387684759C008722D44693E464D48703F868C`;
    - `git apply --check` exit 0 on the post-0096 tree; applied result is
      byte-identical to the script output after LF normalisation (local
      git has core.autocrlf=true, so git apply rewrites to CRLF here; CI
      is LF).
  - Canonical driver `research/tmp-0096/xnu/bsd/dev/sweet_ufs.c`:
    59,333 B, sha256 `3BA165E8231CF0B60E2CD2B62EDD8854A6DA590D0DBE679788A2C19A602BD6B2`.
  - `research/tmp-msdc-split/apply-0098.py` (deterministic applier,
    `--restore`/`--check`, base copy `sweet_ufs-0097base.c`),
    `make-0098-patch.py` (regenerates the patch), `test-0098-plan.py`.
- Validation: `test-0098-plan.py` models the old and new strategy loops:
  270,500 plans (all alignments, lengths, block caps, reads and writes)
  cover identical byte ranges, the new loop never issues more commands,
  and an aligned 256 KiB read drops from 512 commands to 4.  Brace /
  paren balance and one definition per helper checked on the patched
  file.  NOT compiled (needs the macOS XNU build); first boot will be the
  real test.
- Push + dispatch: DONE at 2026-10-28 19:31Z - `177ec29` pushed to
  `fork/msdc-0079`, `workflow_dispatch` accepted (HTTP 204), run
  40755000295 queued (job 123051449834, sha 177ec29a).  This is the first
  xnu run since 40722066010 that is not immediately cancelled; watch it
  with `python tools/gh-ci.py runs Gytis283123/ios-sweet 3`.  A background
  watcher (`research/tmp-msdc-split/watch-0098.py`, 4 h cap) polls the run
  and downloads the artifact into `research/art-0098/` on success.
- Next after a green build: `python tools/fetch-kernel-artifact.py latest
  Gytis283123/ios-sweet research\art-0098` (or `get` with the artifact
  id), rebuild the `shim-boot-...-0098` image with the 0094 ADT/fb270
  bits, `fastboot flash boot`, `fastboot reboot` (never
  `fastboot boot`).  Expected attach line: `MERLIN MSDC: 128 sector(s)
  per data command (CMD18/CMD25), bounce 64 KiB`.

### User decisions (2026-10-28, this session)

1. Push 0098 now: yes (done, see above).
2. HFS+ stays 16 GiB for now; grow it after the multi-block driver is
   proven.
3. The ~19% long-axis display offset: investigate after 0098 boots.


## Agent handoff / active work (2026-10-28 LATEST-71: USERDATA RESTORED TO THE STOCK 48.489 GiB LAYOUT VIA ADB/TWRP; DISPLAY-FIX IMAGE FLASHED, VISUAL CHECK PENDING)

### Request

- User: "modify the partition parameters for userdata to have 64gb not 32"
  and, when asked, "Do the Storage parameters NOW with adb (its booted to
  recovery.)"  The phone was in TWRP with adb (`204719200409 recovery
  product:twrp_merlin`).

### Observation: what the device GPT actually held

- Read via `adb exec-out dd` (`research/gpt-restore/adb-gpt-restore.py
  dump`): EXACTLY the 2026-09-04 WOA surgery layout, 50 entries:
  - userdata [20,332,544..67,108,863] = 46,776,320 sec = 22.305 GiB;
  - esp [67,108,864..75,497,471] 4.000 GiB - starts at exactly 32 GiB
    (LBA 67,108,864 x 512 = 34,359,738,368 B); this is the only "32 GB"
    figure in the layout;
  - win [75,497,472..122,019,775] 22.184 GiB.
- Primary-region hash matched the LATEST-63 expectation exactly
  (`50df2a1c4f3e3b26...`, dd skip=0 count=34).
- NOTE: eMMC user area is 122,142,720 LBAs = 58.24 GiB, so a literal
  64 GiB userdata is impossible; stock (max) is 48.489 GiB = 52.06 GB,
  i.e. the advertised "64 GB" phone layout.
- The recorded PRE-check hash for the backup region (19f85c83...) is
  WRONG and was never the device state: the Oct-3 `gpt_backup.bin` dump
  carries a COPY OF THE PRIMARY HEADER (my_lba=1, alt=122142719,
  entries_lba=2).  The real on-device backup header is spec-correct
  (my_lba=122142719, alt=1, entries_lba=122142687) and its table is
  byte-identical to the primary table.  Replaced that hash check with
  the real invariant (backup table == primary table).

### Artifact fix before writing

- `research/gpt-restore/make-gpt-restore.py`: the rebuilt backup header
  now patches my_lba=122142719 and alternate_lba=1 (previously inherited
  the primary's values) and the round-trip validation checks both.
- Regenerated blobs:
  - `gpt-primary-stock.img` 17,408 B sha256
    `ccff6dca1a5df468791511d12c192728e8240eea2e632794c23e65348963b2be`
    (unchanged);
  - `gpt-backup-stock.img` 16,896 B sha256
    `f0d4eec8f759cc9d92066715ca3c7915eef149a2207d3747bd9e558ba30d8e82`
    (NEW; the old e536f4d8... header was spec-invalid).

### Write + verification (observation)

- Tool: `research/gpt-restore/adb-gpt-restore.py write` (pushes both
  blobs to /tmp, dd, read-back, hash + structural verify).
- First attempt wrote the primary region, then the backup dd failed:
  toybox `dd` ftruncates the output device (`dd: ftruncate: Invalid
  argument`).  Read-back showed primary = stock, backup = still old;
  no other change.  Re-ran the backup dd with `conv=notrunc,fsync`
  -> 33+0 records out, rc=0.
- POST-WRITE VERIFY (device read-back, both hashes match the blobs):
  - dd skip=0 count=34          `ccff6dca1a5df468...` OK;
  - dd skip=122142687 count=33  `f0d4eec8f759cc9d...` OK.
- New geometry (both primary and backup headers, CRCs ok, disk GUID
  zeros, 48 entries): userdata [20,332,544..122,021,823] =
  101,689,280 sec = 49,652 MiB = 48.489 GiB, contiguous to otp;
  esp/win entries gone; otp/flashinfo untouched.
- Data bytes untouched (metadata-only).  userdata still starts with a
  valid HFSX volume header at LBA 20,332,544+1024 ("HX" + "HFSJ",
  journaled; no ext4 magic at offset 1080) -> the iOS image is intact.
  TWRP's mount table labels `mmcblk0p45` as ext4 /cache; that label is
  bogus for an HFSX volume.
- `sync; reboot` issued (adb gone from the bus after reboot).

### Display fix (this session, earlier)

- Flashed `research/merlin-boot/shim-boot-merlin-msdc-0094-window-be-fb270.img`
  (16,989,139 B, sha256 `902e5c023e207e189d2bd6ef036c7f981d95ed953774db5b1ee4fb474489fce8`);
  `fastboot flash boot` OKAY, `fastboot reboot` OKAY.  Visual verdict
  (logo/bar centered, wrapped strip gone) still PENDING - the user
  booted TWRP before reporting.  Rollback image:
  `...-window-be.img` sha256 `b51fcced...`.

### NEXT

1. Confirm the Apple logo + progress bar are centered on the new boot;
   if not, roll back to the `-window-be.img`.
2. The HFS+ root volume itself is still 16 GiB inside the now-48.489
   GiB partition, so iOS will still report ~16 GB capacity.  Growing it
   needs a host-side HFS+ resize of `research/ipsw-x/iosroot-v2.img`
   plus a full ~48 GiB userdata reflash (hours, previous flashes had
   silent holes) - decide with the user before starting.
3. The old esp/win DATA now sits inside userdata past the 16 GiB
   volume end; it is unallocated from iOS's point of view and harmless.

## Agent handoff / active work (2026-10-28 LATEST-70: FIX CONFIRMED - THE kalloc.16384 PANIC IS GONE; BOOT REACHES THE APPLE LOGO WITH launchd/XPC DAEMONS RUNNING)

### Observation (user report, this session; no photo yet)

- After flashing `shim-boot-merlin-msdc-0094-window-be.img`
  (sha256 `b51fcced...`, cmdline `merlin_excl_pa=0x9f900000-0x1e700000`)
  the boot NO LONGER panics in `data.kalloc.16384`.
- The console showed userspace daemons being spawned: the user read
  `symptomsd` and `xpcproxy` names near `logd_helper`.
- The console text then stopped scrolling because the display switched to
  the APPLE LOGO - i.e. the kernel, launchd and the early userspace
  bootstrap all ran on the 0094 kernel with the 487 MiB window withheld.
- Conclusion (inference, supported by the above): the "element modified
  after free" panics were the EMI-MPU false-UAF (SCP 0x9f900000-0x9fefffff
  + modem 0xae000000-0xbdffffff); excluding both spans is the correct fix,
  and ~708 MiB usable RAM is enough to get launchd up.
- Still unknown: whether the logo is a stable destination or a hang, and
  whether a progress bar appears.  Needs a photo/video + a wait of a few
  minutes.

### Next diagnostics if the logo is a hang

- The text console is lost once userspace owns the framebuffer, so the next
  step is behavioural first (does the progress bar advance / does the screen
  change at all, do USB or backlight/DPM state change?).
- If it is a hard hang: re-check what launchd waits on (data volume mount,
  `/dev/console`, mach bootstrap), and consider a build that keeps kprintf
  on the 0094 console path while still letting userspace draw (e.g. debug
  print to the same framebuffer with a late handover), which needs CI.
- 0097 (window default = the value proven here, plus the two window prints)
  is still waiting for a CI runner; nothing needs to change in it.

## Agent handoff / active work (2026-10-28 LATEST-69: ROOT CAUSE = EMI-MPU-PROTECTED SCP+MODEM SPANS INSIDE XNU's RANGE; WINDOW WIDENED TO 0x9f900000-0xbe000000 AND FLASHED ON THE 0094 KERNEL)

### Root cause of the kalloc.16384 "modified after free" panics (observation + inference)

- The LK log in `D:\things\Merlin\Dumped\expdb.bin` shows the EMI MPU
  protecting, INSIDE the range XNU is given (`0x80000000-0xcd000000`,
  `memSize 0x4d000000`):
  - `emi_mpu_set_protection start:9f900000 end=9fefffff region=27`
    (SCP; also `mblock_reserve ... 0x9f900000 size 0x600000 SCP-reserved`,
    `[SCP] load_scp: dram_addr=0x9f900000`).
  - `emi_mpu_set_protection start:ae000000 end=bdffffff region=30`
    (modem; `mblock_reserve 0xae000000 size 0x10000000 md_mem_usage`)
    plus subranges 0xae000000-0xaf6fffff, 0xafc00000-0xafc9ffff,
    0xb0000000-0xb1a2ffff, 0xb1a30000-0xb24cffff, 0xb24e0000-0xb250ffff,
    0xb2600000-0xb267ffff, 0xb5000000-0xb56fffff, 0xb5700000-0xb5dfffff.
  - No MPU range lies in `0x80000000-0x9f900000` or `0xbe000000-0xcd000000`.
- `zfree()` bzeroes the element (`zalloc.c:6244`) and
  `zalloc_validate_element()` later demands it still be zero.  A page in a
  protected span drops the AP's writes, so the zero check reads stale
  bytes and fires "element modified after free".  That is a FALSE
  use-after-free, not a live scribbler.
- Decisive evidence (observation): boot 28's victim bytes
  `06 d2 04 6c 00 6d 17 4e 0a b7 40 19 b3 51 00 65` occur VERBATIM in
  `D:\things\Merlin\Dumped\md1img.bin` at offset `0x76cc0` (modem
  firmware).  The AP could never have written that.  The earlier victims
  (0x9f98a000/0x9f9ea000 boot 20, 0x9fa08000 boot 21, 0x9fae0000 boot 27)
  are all inside the SCP span 0x9f900000-0x9fefffff.
- Therefore the 8 MB window was too small on BOTH counts: it started at
  0x9f800000 (below the span, harmless) and ended at 0xa0000000, while the
  allocation frontier then ran into the modem span starting at 0xae000000.
- Correction to LATEST-68: boot 28's `val` is `0x4e176d006c04d206` and the
  ptr is `0xffffffe30002c000` (photo misreads in the previous entry).

### What is flashed now

- DEVICE NOW: `research/merlin-boot/shim-boot-merlin-msdc-0094-window-be.img`
  - 16,989,139 B, sha256 `b51fcced86ffa8dcc8a4a3575b580c1fdca71179ad3e708b3e3a3ec4160cc169`.
  - Built from the UNCHANGED 0094 kernel
    (`research/art-0094/kernel.development.sweet`) with
    `build-msdcroot0.py --cmdline "<0094 cmdline>
    merlin_excl_pa=0x9f900000-0x1e700000"` (318 chars, BOOT_LINE_LENGTH
    is 608 in both the shim and XNU arm64).
  - DELTA vs `0094-w8.img` is exactly 6 bytes in `0x2f975-0x2f985`
    (the start/len digits).  Kernel payload, shim slot and DTB are
    byte-identical, so this boot isolates the window.
- Flash: `fastboot flash boot ...` OKAY (16590 KB, 0.386 s) +
  `fastboot reboot` OKAY.  No `fastboot boot` used.
- Boot-arg parsing re-verified before flashing: `PE_parse_boot_argn()`
  returns the full `START-LEN` string (no truncation at 608 or at the
  318-char cmdline length).
- Window semantics: withhold `0x9f900000-0xbe000000` = `0x1e700000` B =
  487 MiB = 31,168 16 KiB pages.  Managed RAM becomes
  `0x80000000-0x9f900000` (505 MiB) + `0xbe000000-0xcd000000` (240 MiB)
  = 745 MiB, ~708 MiB after the kernel image.
- 0094 has no window print of its own (that arrives with 0097), so the
  verdict is behavioural: does the kalloc.16384 panic disappear.

### Patch 0097 (rewritten in place, committed + pushed, still NOT built)

- `D:\things\Merlin\ios-sweet\xnu\patches\0097-merlin-window-8m-drop-early-jump.patch`
  default window is now `merlin_excl_start = 0x9f900000`,
  `merlin_excl_len = 0x1e700000`; comment names both MPU spans, the
  `md1img@0x76cc0` proof and the 708 MiB arithmetic; prints renamed to
  "exclusion window" / "withheld N exclusion-window pages".
- ios-sweet `msdc-0079`: commit `529c476` (new window/comments/prints) and
  `82d71ba` (comment arithmetic fix), pushed to `fork`.
- `git apply --check -p1` clean against the post-0096 tree; applied
  result byte-identical to the edited tree.
- CI still dead: last success 0094 (run 40400128627); later dispatches
  failed with no runner.  Do not dispatch 0097 until a runner exists.

### NEXT

1. Photograph/video the current boot.  Success = boot gets past the
   kalloc.16384 panic (the HFS signature wall or deeper is fine).
2. If kalloc.16384 still panics, the `pa=` line is above the visible
   screen area: take a short VIDEO of the boot so a frame showing the
   first panic's `MERLIN FORENSICS: victim ... pa=0x...` can be extracted.
   A victim inside `0xbe000000-0xcd000000` would mean a second garbage
   source (that span contains LK's `atf-log 0xbfe00000`, `atf-ramdump
   0xbff80000`, `tee-log 0xbfc00000` mblocks - not MPU-protected, but
   ATF could still be writing its log there).
3. If boot reaches HFS and 708 MiB turns out to be too little, revisit the
   window (the modem span alone is 256 MiB of the 487 MiB withheld).
4. When CI recovers: dispatch 0097 and pack with
   `build-msdcroot0.py`; the build should print
   `MERLIN: exclusion window PA 0x9f900000-0xbe000000 (31168 pages kept
   out of the VM)` and `MERLIN: withheld 31168 exclusion-window pages from
   the free pool`.

## Agent handoff / active work (2026-10-28 LATEST-68: SCRIBBLER WINDOW WIDENED TO 8 MB AND DEPLOYED ON THE EXISTING 0094 KERNEL VIA BOOT-ARG; 0097 PATCH COMMITTED + PUSHED)

### What was flashed (this session, no CI needed)

- DEVICE NOW: `research/merlin-boot/shim-boot-merlin-msdc-0094-w8.img`
  (sha256 `f4ded48b51c1c46aa586aa3e8877a1961a3dbfe712224e171becfd3bb8f53d29`,
  16,989,139 B, same size as 0094-fv).  Built with
  `python research/tmp-msdc-split/build-msdcroot0.py
  research/art-0094/kernel.development.sweet --cmdline "<0094-fv cmdline>
  merlin_excl_pa=0x9f800000-0x800000" --out research/merlin-boot/shim-boot-merlin-msdc-0094-w8.img`.
- DELTA VERIFIED (observation): the new image differs from the flashed
  0094-fv image in exactly 35 bytes, file range 0x2f961-0x2f983, and the
  difference is the appended boot-arg string
  ` merlin_excl_pa=0x9f800000-0x800000`.  The kernel payload, shim slot and
  DTB are byte-identical to 0094-fv.  So this boot tests ONLY the window.
- Flash: `fastboot flash boot ...` OKAY (16590 KB, 0.230 s) +
  `fastboot reboot` OKAY.  No `fastboot boot` was used.
- Boot-arg path recap: 0092 parses `merlin_excl_pa=START-LEN` into
  `merlin_excl_start/len`; 0094 withholds matching pages at release
  (`merlin_excluded_ppnum_p`).  No kernel rebuild was required.

### Boot 27 panic (the photo this entry answers)

- `panic(cpu 0 caller ...): [data.kalloc.16384]: element modified after
  free (off:11904, val:0xeedffd7f3eefaae9, sz:16384, ptr:...)`.
  Forensics: `victim data.kalloc.16384 size=16384 off=11904
  elem=0xffffffe29b06d400 pa=0x9fae0000`, 2 islands
  `[11904,11968)` and `[15424,15488)` (0x2e80 and 0x3c40), bytes
  `e9 aa ef 3e 7f fd df ee ff 2f cd cf 3d fe fe fc` /
  `cb dd 3e cf df 77 e8 92 ...`.
  `msdc reads=521735/521561 readverify mismatches=0`, `apdma found=0
  quiesced=0`, `pattern hits=0`.
- `pa=0x9fae0000` is 0x600000 PAST the 0092 default window end
  (0x9f800000+0x280000 = 0x9fa80000) - that is why 0094 still panicked.
  All four victims ever photographed (0x9f98a000, 0x9f9ea000,
  0x9fa08000, 0x9fae0000) sit inside 0x9f800000-0xa0000000.
- The island byte patterns do NOT occur in scp1/scp2/scp.img,
  sspm_1/2, spmfwr (5 patterns searched, zero hits): this boot's
  corruption is not verbatim SCP firmware content.
- `elem=0xffffffe29b06d400` is not a physmap address (physmap base +
  offset would be ~11 GB) and its low bits are not 16 KB aligned, so it
  lives in the kernel's dynamic VA; the printed `pa=` comes from
  `kvtophys()` (page-table walk) and is the trustworthy field.  Do not
  derive the PA from the elem digits.

### Patch 0097 (committed, pushed, NOT built - CI runner still dead)

- `D:\things\Merlin\ios-sweet\xnu\patches\0097-merlin-window-8m-drop-early-jump.patch`
  (ios-sweet `msdc-0079` commit `e502844`, pushed to `fork`).
  1. `merlin_excl_len` default `0x280000` -> `0x800000` (window
     `0x9f800000-0xa0000000`, fallback reset updated too).
  2. DROPS 0095's early jump.  `pmap_next_page()` jumped `first_avail`
     to the window end on its first call, but `first_avail` is
     `topOfKernelData` (~0x824e4000, from the shim's ADT/boot_args
     placement), i.e. far BELOW the window: 0095 therefore discarded
     ~476 MB (0x824e4000-0xa0000000), not the ~30 MB its comment claims.
     A packed vm_page array is indexed by physical page, so a hole can
     only be skipped by sacrificing everything below it; 0094's
     suspend-during-enumeration + withhold-at-release is the only
     affordable scheme.  0095's "window pages never enumerated" premise
     also had no mechanism (withheld pages never enter a free queue).
  3. Adds unconditional boot prints (photo-verifiable):
     `MERLIN: scribbler window PA 0x9f800000-0xa0000000 (512 pages kept
     out of the VM)` and `MERLIN: withheld N scribbler-window pages from
     the free pool` (N counted in vm_resident.c during release).
- Verified with `git apply --check -p1` against the post-0096 tree
  (research/tmp-0096/xnu) - applies clean.
- CI state re-checked this session: latest success is still 0094
  (run 40400128627, 2026-10-26); runs 40579028774 / 40583707775 /
  40722066010 all failed/cancelled with no runner steps.  Do NOT
  dispatch 0097 until a runner appears.

### NEXT

1. Photograph/video the current boot.  Success = the boot gets past
   boot 27's kalloc.16384 panic (HFS signature wall or deeper is fine);
   with no rebuild there is no new "MERLIN: scribbler window" line, so
   the verdict is behavioural.
2. If the victim appears at/above 0xa0000000, the writer band is larger
   than 8 MB: widen (e.g. `0x9c000000-0x4000000`) or switch to
   top-of-RAM exclusion before spending a rebuild.
3. When CI recovers: dispatch 0097, then `finish-0095.py`-style pack
   (build-msdcroot0.py with the #19-#22 cmdline + the new prints).

## Agent handoff / active work (2026-10-28 LATEST-67: NEW WALL = HFS REJECTS THE VOLUME HEADER ON THE FLASHED 0094 IMAGE; 0096 DIAGNOSTIC PUSHED BUT CI RUNNER STILL DEAD; BROM READ OF userdata+1024 IN FLIGHT)

- DEVICE NOW: `boot` = `research/merlin-boot/shim-boot-merlin-msdc-0094-fv.img`
  (sha256 9ff05aa5117208759fc2d018d9b36877718057efdf8b95a815ec7841d9ae0b30,
  16,989,139 B).  Flashed twice this session with `fastboot flash boot`
  (both writes OKAY) + `fastboot reboot`.  No `fastboot boot` was used.
  Serial 204719200409, product merlin, unlocked, no A/B slot,
  partition-size:boot 0x4000000, type raw.  Stock restore point:
  `D:\things\Merlin\Dumped\boot.bin` (64 MiB, `ANDROID!` magic verified).
- PHOTO DECODE (full text, rotated 90 deg), repeating every ~5 s:
  `alias vnode 0xffffffe250770000 is in state of change (start)` /
  `(end)` -> `hfs_ValidateHFSPlusVolumeHeader: unknown Volume Signature : 60`
  -> `hfs_mount: hfs_mountfs returned error=22 for device unknown-dev`
  -> `mount(17|18|19|20|21) failed` -> `BSD root: msdcroot0, major 1,
  minor 0` -> `cannot mount root, errno = 19`.
  `mount(N)` = IOKitBSDInit.cpp:695 IOFindBSDRoot retry counter (5 s
  sleep each); `cannot mount root` = bsd_init.c:887 infinite loop;
  errno 19 = ENODEV because HFS mountroot returns EINVAL (22).
  The `hfs: mounted msdcroot0` line at the very top of the photo is a
  leftover of an earlier boot (LK splash does not clear that area).
- EXPECTED MEDIA BYTES: `research/ipsw-x/iosroot-v2.img`
  (17,226,006,528 B, HFS+ volume 16.0 GiB, allocation block 4096) has
  `48 58 00 05 80 00 21 00 48 2b 4c 78` at byte offset 1024.
  Signature printed as %x = BE16 of the first 2 bytes, so "60" means
  the kernel's buffer held `00 60`.  No 512-aligned `00 60` exists in
  the image's first 256 MiB (first hit 0x51b1a00), so this is not a
  shifted read inside the first 85 MB.
- **NEW SOURCE FACT (observation): our kernel is NOT writing userdata.**
  The baked cmdline in the flashed image (verified byte-exact at
  file offset 0x2f88e) is `... rd=msdcroot0 ... -zc msdc_readverify=1`
  with NO `rootrw=1`.  `bsd/vfs/vfs_subr.c:1260-1271` (SWEET-only hunk)
  only clears MNT_RDONLY when `rootrw=1`, so the root mount is
  read-only and HFS takes the `ronly` path: its journal replay blocks
  (`hfs_vfsops.c` `if (!ronly)` around 1608/1707) never run and
  `hfs_flushvolumeheader` is skipped.  Note `sweet_ufs.c:1674
  DKIOCISWRITABLE` still returns 1 unconditionally (cosmetic here,
  `ronly` comes from the mount flags), which is worth tightening later.
- CONSEQUENCE: the wrong volume header is either (a) on the media, or
  (b) produced between `merlin_msdc_strategy` and HFS.  NOTES LATEST-62
  already proved the eMMC content differed from the image at scattered
  blocks (deterministic `0x4600b085` dyld bytes with zero occurrences in
  the image, readverify 0 mismatches), so (a) is the prime suspect.
- 0096 DIAGNOSTIC (written this session, ready):
  `D:\things\Merlin\ios-sweet\xnu\patches\0096-merlin-hfs-read-dump.patch`
  (commit 5bd09f8 on branch msdc-0079, pushed to fork).  Three prints:
  1. `bsd/dev/sweet_ufs.c` `merlin_msdc_init()` right after
     `msdc_find_partition()` (lock held): `msdc_read(first_block+2,1,vh)`
     -> `MERLIN MSDC: attach LBA2 raw .. | bounce ..`.
  2. `merlin_msdc_strategy()` for `off == 1024`:
     `MERLIN MSDC: strategy off 1024 bounce .. | vaddr ..`.
  3. `bsd/sweet_hfs/core/hfs_vfsops.c` after `buf_meta_bread` and after
     the bcopy into mdbp: `MERLIN HFS: mdb_offset/log_blksize/
     phys_blksize/pri/count | raw .. | pri ..` then `MERLIN HFS: mdbp ..`.
  Generated by `research/tmp-msdc-split/make-0096.py`; verified to apply
  with `patch -p1` to pristine post-0093 files and to reproduce the
  scratch tree byte-exactly (scratch tree `research/tmp-0096/xnu` =
  art-0093 + 0094 + 0095 + 0096).
- CI: run 40722066010 (branch msdc-0079, head 5bd09f8) dispatched
  2026-10-28T16:02:51Z, still `queued` with zero steps after 20+ min -
  same lost-macOS-runner infra flake as 40579028774 / 40583707775
  (both cancelled with an empty log zip).  0095 AND 0096 are therefore
  still unbuilt.  Helpers: `research/tmp-msdc-split/ci-status.py`,
  `ci-inspect.py`, `watch-run.py`, `dispatch-0096.py`.
- BROM READ (DONE, decisive): `mtkclient` DA read of `brom/gpt_now.bin`
  (current GPT) and `brom/userdata_start.bin` (1 MiB at `0x26c800000`).
  RESULT: **userdata holds a fresh Android ext4 `/data`, the HFS image is
  not on the partition at all.**  Evidence:
  - byte 0x400 = `00 60 16 00` = ext4 `s_inodes_count` 1,466,368
    (printed as HFS signature "60" = `00 60`),
  - ext4 magic `0xEF53` at 0x438,
  - `s_volume_name` = "data", `s_last_mounted` = "/data",
    `s_lastcheck` = 2026-10-27T19:56:37Z, `s_wtime` = 2026-10-27T21:19:29Z,
    `s_mnt_count` = 5, `s_state` = 0x1 (clean), blocksize 4096,
    5,847,040 blocks = 22.31 GiB, inode size 256,
    uuid `caf317e263a64884bcd4bb957ff5936f`.
  - `48 58` occurs ZERO times in the whole 1 MiB dump.
  GPT readback confirms `userdata first=0x1364000` (0x26c800000) size
  22.30 GiB - the GPT did not move; the partition content changed.
  So an Android boot on **2026-10-27 ~21:19 UTC** created a new ext4
  /data and wiped the iOS root image (the phone must have booted Android
  or an Android recovery then; the earlier sparse-flash "scattered bad
  blocks" theory is superseded - see LATEST-62 note for the 0x4600b085
  history, which is still real but not today's wall).
  Parse helper: `research/tmp-msdc-split/ext4peek.py`.
- FIX IN PROGRESS (user chose mtkclient over fastboot): raw DA write of
  `research/ipsw-x/iosroot-v2.img` (17,226,006,528 B = 0x402c00000) to
  flash offset 0x26c800000 via
  `python mtk.py wo 26c800000 402c00000 <image>`.
  mtkclient `writeflash` streams every byte sequentially with a per-
  packet checksum and a DA status check - no sparse/don't-care skipping,
  so it cannot reproduce the LK sparse-writer failure mode.  Observed
  speed ~4.5 MB/s -> ~55 min.  Post-write verify is staged:
  `research/tmp-msdc-split/verify-write.py gen|check` reads back the
  first 1 MiB, sixteen 64 KiB windows (one per GiB) and the alternate
  HFS+ header at image offset 0x3FFFFF000 via
  `brom/verify.txt` + `brom/verify/*.bin`, then diffs each against the
  image.
  ATTEMPT 1 FAILED at 0x1600000 (~22 MiB written) with
  `DeviceClass - USBError(5, 'Input/Output Error')`.  The first run had
  a concurrent 17 GB sha256 read of the same image, but ATTEMPT 2 with
  a completely quiet disk failed at the **identical offset** and the
  identical error -> deterministic DA/USB-endpoint failure on this host,
  not disk contention, not the image.  (The DA length field is fine:
  0x402c00000 < 2^32, and `writeflash` streams with per-packet
  checksums + a final DA status.)  A drop mid-write only affects
  userdata (raw sequential write, GPT untouched) so retries are safe.
  mtkclient `wo` cannot resume from a file offset (da_wo never passes
  `offset` to writeflash), and chunking would need 17 GB of sliced
  temp files, so the mtkclient route was abandoned after attempt 2.
  FALLBACK NOW RUNNING: `fastboot flash userdata
  research\ipsw-x\iosroot-v2.img` (historically 12-19 MB/s, ~20 min,
  flash #3 reported 47/47 OKAY), followed by the same BROM sample
  verify.  Notes: the phone must be put back into fastboot with
  Vol-Down + Power; the `boot` partition still holds 0094 so a normal
  power-on boots the iOS kernel and a BROM read-back needs another
  power-cycle.
- **CRITICAL ENVIRONMENT RULE discovered:** Android must never boot on
  this phone while the iOS image lives in userdata - Android formats
  /data as ext4 and destroys it (that is what happened on Oct 27).  Any
  Android/MIUI/TWRP boot that mounts or formats /data wipes the iOS
  root.  This also explains why an old image can look "silently
  corrupted" between sessions.
- CI: run 40722066010 (branch msdc-0079, head 5bd09f8) dispatched
  2026-10-28T16:02:51Z, still `queued` with zero steps after 20+ min -
  same lost-macOS-runner infra flake as 40579028774 / 40583707775
  (both cancelled with an empty log zip).  0095 AND 0096 are therefore
  still unbuilt.  Helpers: `research/tmp-msdc-split/ci-status.py`,
  `ci-inspect.py`, `watch-run.py`, `dispatch-0096.py`.  0096 is no
  longer needed for this wall (the media answer is in) but stays queued
  as the read-path discriminator if the verified write still fails to
  mount.

- STILL OPEN: whether the phone actually started the freshly flashed
  image (it was back in fastboot afterwards - user-driven power+vol
  down is the likely explanation, but a bootloader fall-back to
  fastboot is not excluded; the earlier photo proves 0094 does boot).
- Do NOT touch the uncommitted QEMU ramfb/fbcon-1x work (`shim/*`,
  `tools/fbcon-1x*`).


## Agent handoff / active work (2026-10-27 LATEST-66: VBMETA WAS THE SILENT-BOOTLOOP ROOT CAUSE — user discovery ("IT WAS THE FREAKING VBMETA"); image track UNPAUSED; 0095 pushed + CI in flight; 0094-kernel-bytes trigger theory VOID, re-test pending)

- THE DISCOVERY (user, 2026-10-27): the silent bootloops were **vbmeta
  (Android verified boot), not the kernel**.  This confirms the
  BOOT-#24-ROUND-3 deduction "the device state changed, not the images"
  (all sha-frozen images incl. last-known-good 0093 started bootlooping
  silently) — the device change was vbmeta verification state turning
  hostile to the downloaded-image path.  Silent death (no panic screen,
  splash repaint each cycle) is exactly a below-kernel verified-boot
  rejection, matching the observation.
- CONSEQUENCES:
  1. BOOT #24 verdicts "0094 kernel bytes are the trigger" (round 2)
     and the whole geometry line are VOID — 0094's silent bootloop was
     very likely vbmeta too (its text boot never happened in a
     vbmeta-clean window).  0094's QEMU logic validation stands; the
     phone verdict is simply unknown.
  2. 0093's Oct-26 text+2627 panic decode REMAINS VALID (pre-vbmeta
     trouble window) — the 2627 root cause and the 0093 tripwire are
     still untested on device.
  3. Photo boot #24 decode table (LATEST-65) stays usable once images
     boot again.
- 0095 STATUS (this session): ios-sweet 048d42f PUSHED to fork branch
  msdc-0079 (CI runs via workflow_dispatch on that branch — fork/main
  is stale at 0082-era, origin = upstream dipa-studio, do not touch).
  CI run 40579028774 = FAILURE with an EMPTY log zip (22-byte PK stub,
  zero steps) = the known lost-runner infra flake (0093 dispatch-1
  precedent); re-dispatched → run 40581438531 (poller
  research/tmp-msdc-split/poll-ci.sh with 25-min stuck-queued
  re-dispatch guard).  POST-CI PIPELINE READY:
  research/tmp-msdc-split/finish-0095.py (download xnu-kernel artifact
  → research/art-0095/, SHA256SUMS check, 15-probe binary chain
  0086→0095 incl. "MERLIN: pmap early-jump past scribbler window to",
  pack via build-msdcroot0.py with the #19-#22 cmdline verbatim
  [extracted byte-exact from the 0094-fv payload] →
  research/merlin-boot/shim-boot-merlin-msdc-0095-fv.img).
- NEXT: CI green → finish-0095.py → CI-log patch-apply audit (skips =
  known-good five ONLY) → user `fastboot boot` the 0095 image + ONE
  photo/video.  EXPECT (0095 fingerprint): "MERLIN: pmap early-jump
  past scribbler window to 0x… (N pages never enumerated)", NO
  "MERLIN: pmap excluding PA" line, passes vm_resident.c:2627 →
  deeper boot than #22.  Optional A/B while at it: re-boot the frozen
  0094-fv image under the fixed vbmeta to close the "0094 bytes" file.
- Parked uncommitted QEMU ramfb/fbcon-1x work stays untouched
  (LATEST-63 note unchanged).

## Agent handoff / active work (2026-10-26 LATEST-65: XNU KERNEL PANIC FIX 0094 DRAFTED — pmap_startup() contiguous pages)

ROOT CAUSE (confirmed): patch 0092's pmap_next_page() exclusion skips pages in the scribbler window during pmap_startup(), producing non-contiguous phys_page values that trip VM_PAGE_SET_PHYS_PAGE assertion at vm_resident.c:2627 → immediate kernel panic after "MERLIN: pmap excluding PA ..." message.

FIX (0094, written to xnu/patches/0094-merlin-pmap-startup-contiguous.patch):
- pmap.c: add non-static boolean_t merlin_excl_enabled = TRUE; gate exclusion check with `if (merlin_excl_enabled && ...)`; add merlin_excluded_ppnum_p() helper
- vm_resident.c: suspend exclusion (merlin_excl_enabled = FALSE) before vm_page_array init loop; skip excluded pages in both himemory and non-himemory release paths; re-enable (merlin_excl_enabled = TRUE) after release loop
- Excluded pages are NEVER released to free pool → scribbler territory stays off-limits after boot

STATUS: Patch drafted and verified against /tmp/xnu_test copy (0092+0094 applied). NOT YET built or boot-tested. Kernel compilation needs macOS; until repo is pushed, kernels come from ios-sweet's CI. Project is LOCAL ONLY — no push without user approval.

NEXT: Build kernel with 0092+0093+0094 → boot (fastboot boot, never flash) → decode MSDC tripwire output from 0093 → if hits=0 and wall still fires, corruption is above driver (VM/zalloc/UGC)

UNFINISHED: Kernel build not done; next boot not run; no photo; CI not run; push not done (LOCAL ONLY).

- 0094 SHIPPED (user-directed build, this session): re-verified against
  the REAL CI base first (git apply --check CLEAN on art-0093-buildtree
  post-0093 xnu, incl. 0092's pmap.c anchors) → committed ios-sweet
  5964344, pushed (user approved) → CI run 40400128627 GREEN.
  GOLDEN RULE: SHA256SUMS ok; kernel 17,208,152 B (research/art-0094,
  +88 B vs 0093); 10/10 probes (0093 tripwire strings + full 0086→0092
  chain); CI log: 0092+0093+0094 ALL APPLIED, skips = known-good five
  only.  BOOT IMAGE: research/merlin-boot/
  shim-boot-merlin-msdc-0094-fv.img (16,989,139 B, sha
  9ff05aa5117208759fc2d018d9b36877718057efdf8b95a815ec7841d9ae0b30,
  payload 16,612,944 B, shim+dtb byte-identical to E1, cmdline
  verbatim #19-#22 incl. msdc_readverify=1).  NOTE: 0094 adds no new
  print strings — its fingerprint is behavioral (pmap_startup gets
  past where it previously tripped; the exclusion line still prints).
  PHOTO DECODE CONFIRMED (Image/2026-10-26-21-02-03-472.jpg = the
  0093-image boot, taken 21:02 — between the 0093 image build 20:58
  and the 0094 image build 23:08): exclusion line fired, then panic
  vm_resident.c:2627 caller 0xfffffe0007aa6d78 immediately after;
  forensics ALL ZERO (msdc reads=0, lk dma zeros, apdma zeros,
  pattern hits=0) = died before any storage init, 0093 tripwire never
  ran — the 2627/exclusion root cause is photo-confirmed; re-decoded
  2026-10-27 session (workflow dwfrun-6e5b9bc2).  Boot image re-checked
  sha 9ff05aa511720875… == recorded; 0094 patch re-verified git apply
  --check CLEAN on research/art-0093-buildtree/xnu.
- BOOT #24 (0094 image, user report 2026-10-27): BOOTLOOPS — no photo
  yet.  OFFLINE CODE FACTS (art-0093-buildtree, this session):
  (a) arm64 has NO delayed-init path — the delay_above_pnum block is
  x86_64-only (vm_resident.c:1494-1519), stays PPNUM_MAX on arm64 ⇒
  vm_get_delayed_page never runs ⇒ 0094's two release-path guards
  cover everything on this device.
  (b) FINGERPRINT CORRECTION: in a 0094 boot the "MERLIN: pmap
  excluding PA" line must NOT print at all — its only printer is
  0092's skip inside pmap_next_page, gated OFF while the main
  vm_page_array loop crosses the window; after the loop first_avail
  is past the window so the skip can never fire again (LATEST-65's
  "the exclusion line still prints" was wrong).
  BOOT #24 DECODE TABLE (one mid-cycle photo, or short video, + cycle
  duration): exclusion line + 2627 panic = 0094 NOT in effect; deep
  console (root mount, launchd, SpringBoard, dyld 0x4600b085
  "malformed load command") then panic = 0094 SUCCESS and the loop is
  the KNOWN wall recurring each cycle (boot #14 precedent: panic →
  auto-reboot → re-enters the RAM image); kalloc/zalloc UAF panic =
  scribbler back (unlikely — release paths guarded); little/no text +
  fast cycle = early crash above the console (0094 regression).
  ESCAPE: hold Power ~15 s through one reset, then Power+Vol- →
  fastboot.
- BOOT #24 OFFLINE ELIMINATION (2026-10-27, this session): user reports
  NO TEXT, only the Redmi splash, cycling.  RULED OUT so far:
  (1) KERNEL BINARY SOUND — art-0094 kernel ran the full QEMU harness
  45 s clean (AMFI/sandbox/HFS/DLIL + init PID 1 alive, no panic);
  (2) PACK BYTE-PERFECT — embedded payload in
  shim-boot-merlin-msdc-0094-fv.img == regenerated mkpayload output
  byte-for-byte (0093 image likewise), dtb+shim+cmdline identical,
  header differs only in the 2-byte size field;
  (3) LAYOUT BENIGN — payload headers diffed: entry_va, kernel_end,
  phys_base 0x80000000, mem_size, all seg addresses IDENTICAL; only
  __LINKEDIT +88 B (new symbol names) and adt_off +96 B; shim places
  ADT at kernel_end (unchanged) and is size-parametric (boots 0088→0093
  payloads all differed in size);
  (4) FILL THEORY DEAD — pmap_startup's fillPage is `fill`-gated,
  always-on fill is `#if DEBUG` only, this is a DEVELOPMENT kernel and
  no fill= boot-arg ⇒ 0094 never WRITES the scribbler window pages
  (vm_page_init 3rd arg is lopage, not zerofill); arm64 delayed-init
  path nonexistent (x86-only).  Shim choose_base probes identical
  addresses for both payloads (entry/kernel_end offsets unchanged).
  ⇒ 0093/0094 are execution-identical until the 0094 patch's own
  post-console code ⇒ either the crash IS post-console with a brief
  text flash the user missed (LK repaints the splash each cycle), or a
  one-off bad USB download (the bootloop re-runs the SAME RAM copy —
  no re-download).  NEXT (user, ~3 min): (a) re-run fastboot boot 0094
  (fresh download); (b) if still splash-only, FILM one full cycle
  (video into Image\) + note cycle length; (c) optionally confirm 0093
  still shows text.  Frame decode decides: text flash → targeted 0095;
  truly nothing → shim/LK-level hunt.
- BOOT #24 FIX CANDIDATE (2026-10-27, this session): QEMU device-payload
  runs (qemu-merlin.py --fb-base) showed BOTH 0093/0094 device payloads
  die early in QEMU on a QEMU-env MMIO external abort (FAR 0xb3c8008,
  ESR 0x96000010 = sync external abort — environment artifact, kills
  both before console; NOT the phone's death).  QEMU-ADT runs boot the
  0094 KERNEL fully to userspace (twice — incl. once with the fix
  below applied), so the kernel bytes are sound; the phone trigger was
  narrowed to the ONLY untested delta = the +96 B payload geometry
  shift (adt_off 0xfd5750, seg9 +0x58).  FIX CANDIDATE BUILT:
  research/merlin-boot/shim-boot-merlin-msdc-0094-geo.img
  (16,989,139 B, sha a31d8faef842ebdcaf37d0ca0028e53621d996d149b907a5
  82d0e7aa4d8866c6) = 0093 image layout EXACTLY (payload size,
  adt_off, kernel_end, seg table, ADT bytes all == 0093) with 0094's
  kernel bytes; __LINKEDIT truncated 0x58 B (symbol-string tail, never
  read at runtime — QEMU full-boot verified with the same truncation,
  run qgeo2).  Boot 0094-geo EXPECT: console text returns; NO
  "MERLIN: pmap excluding PA" line (0094 fingerprint: gate suspends
  the skip during the vm_page_array loop); passes 2627; deeper than
  boot #22.  If it STILL bootloops silently: geometry exonerated ⇒
  0095 = CI bisect of the 0094 patch (gate-only vs release-guards-only).
- BOOT #24 ROUND 2 (2026-10-27, this session): 0094-geo image (0093
  layout, 0094 kernel, __LINKEDIT -0x58) ALSO bootloops silently per
  user ⇒ GEOMETRY EXONERATED; the trigger is the 0094 kernel's own
  bytes.  NEW QEMU CAPABILITY: mkadt.py --phone --qemu-gic --phys-base
  0x80000000 gives a device-band ADT (window INSIDE managed DRAM) —
  with it, the 0094 window path (gate suspension + contiguous
  enumeration + withheld pages) RUNS IN QEMU AND BOOTS TO USERSPACE
  CLEAN (run qdevwin) ⇒ the 0094 LOGIC is innocent; the phone-only
  factor = the live SCP writer + the window pages being part of the VM
  at all.  (Device-payload QEMU runs are a dead end: QEMU's missing
  MSDC/GIC MMIO external-aborts kill BOTH kernels pre-console — FAR
  0xb3c8008, ESR 0x96000010, identical for 0093/0094 = env artifact.)
  FIX = 0095 (ios-merlin 98c6c8a, ios-sweet 048d42f, NOT pushed):
  pmap_next_page() jumps first_avail past the window on the FIRST call
  (pre-console steal phase, before slot/ppnum alignment matters) ⇒ the
  packed vm_page array enumerates ONE CONTIGUOUS RUN ABOVE the window;
  the mid-loop skip cannot fire (2627 assert impossible); the window is
  never enumerated/touched/handed out; ~30 MB below the window
  sacrificed; merlin_excl_pa override kept.  Patch = ONE pmap.c hunk,
  applies clean on a post-0094 scratch tree (art-0093 + 0094 + 0095
  verified); probe string "MERLIN: pmap early-jump past scribbler
- BOOT #24 ROUND 3 (2026-10-27, user report): USER TESTED EVERY BOOT
  IMAGE — ALL NOW BOOTLOOP SILENTLY, including 0093 (last known-good,
  text+2627 panic on Oct 26).  Images are byte-frozen + sha-verified ⇒
  THE DEVICE STATE CHANGED, NOT THE IMAGES — user's call: firmware/
  hardware issue at the phone level.  IMAGE TRACK (incl. 0095 push/CI)
  PAUSED until the phone boots again.  SILENT DEATH (no panic screen)
  is itself consistent with a below-kernel reset (watchdog/SCP/power),
  not a kernel panic — every earlier kernel death left a visible
  halted panic screen.  RECOVERY LADDER (user hands): (1) full cold
  power-off (hold Power 20-30 s), wait/cool 5 min, wall-charge 30 min
  (battery-low is a classic loop cause after hours of bootlooping);
  (2) re-enter fastboot, boot the 0093 image (last known-good);
  (3) if still looping: FASTBOOT-IDLE STABILITY TEST — stay in
  fastboot mode 10 min untouched: resets even there = preloader/LK/HW
  level (user's theory in the strong form; next = mtkclient BROM
  session, bypassing LK entirely); fastboot stable = the SoC/DRAM/LK
  are fine and only the downloaded-image execution path dies (TZ/XBL
  handoff or watchdog — re-test image boots cold);
  (4) try the oldest proven image (E1-era) to separate "any image"
  from "these images".  0095 stays committed both repos (98c6c8a /
  048d42f, not pushed) — resume CI when the phone boots again.
  READY: user `fastboot boot` + ONE photo.  Decode = the LATEST-64
  0093 table unchanged (PATTERN hit LBA decides content-vs-eMMC-vs-
  HFS-extent; hits=0 + wall fires = above-driver hunt).  A boot past
  the exclusion line also retro-validates 0094's premise.  Buildtree
  artifact 12688807096 → research/art-0094-buildtree/buildtree.tgz
  (unpack to src/ before drafting 0095).

## Agent handoff / active work (2026-10-26 LATEST-64: USER REDIRECT — GPT resize ON HOLD ("nvm"), nothing was written to the device (no push, no dd — procedure remains prepared in LATEST-63); phone left in fastboot. NEW ACTIVE TRACK per user: THE XNU KERNEL — "the reflash WONT HELP", the 0x4600b085 wall is expected to be a KERNEL-side issue. 0093 = THE DISCRIMINATOR, BUILT + VALIDATED + COMMITTED BOTH REPOS (ios-merlin fc156de, ios-sweet 23b39fb NOT pushed): every CMD17 sector is scanned for the garbage bytes 85 b0 00 46; a hit prints the asked LBA (partition-relative AND absolute) + in-sector offset + 16 B context; counters land on the forensics replay tail too. NEXT: user push approval → CI → golden rule → boot #23 (0092+0093, same full cmdline) + ONE photo → the printed LBA picks the verdict branch below)

- OFFLINE EVIDENCE GATHERED THIS SESSION (no boot needed):
  1. DRIVER AUDIT (art-0091-buildtree sweet_ufs.c, the live read path):
     all-u64 math, bounds-checked (beyond-partition blkno → EINVAL ⇒
     esp/win stale regions UNREACHABLE), CMD17 per 512-B sector,
     readverify double-read + compare, DMA spill canaries clean.
     NO block-number bug found statically.
  2. PATTERN SCANS (85 b0 00 46 = LE 0x4600b085): iosroot-v2.img ZERO
     (earlier session); ALL 44 small partition dumps ZERO; win.bin
     (23.8 GB full win-partition read, Oct 3) = exactly 1 hit @
     3,997,072,412 (= abs LBA 83,304,254, ~8 GB past userdata end —
     unreachable through the driver; expected random count for 23.8 GB
     ≈ 5.5) ⇒ the garbage is NOT any dumped flash content.
  3. LOGIC: readverify was ON in #19/#22 with 0 mismatches ⇒ the card
     served the garbage TWICE, CRC-clean, at the LBA the kernel asked.
     With the pattern absent from the image AND from reachable dumped
     regions, the candidates are: (a) the in-partition sparse zero-hole
     (block 47 stale bytes) asked CORRECTLY = content class; (b) the
     card serving wrong-but-stable bytes = eMMC-internal class;
     (c) bytes manufactured above the driver (bounce/buf/VM) that
     readverify cannot see (it compares bounce-to-bounce) = XNU class —
     the user's bet. THE PRINTED LBA + CONTEXT DECIDES:
     - LBA in the hole (abs 24,494,910..24,995,871) + plausible file
       mapping (offline HFS catalog parse maps partition offset →
       owning file extent) ⇒ content class (reflash WOULD fix);
     - LBA in image-backed territory ⇒ bytes below-CMD17 diverge from
       image there ⇒ eMMC-internal (readback-verify at LBA level next);
     - LBA absurd for a Mach-O header read ⇒ HFS extent/blkno bug
       (XNU) — fix the extent math;
     - NO HITS but the wall still fires ⇒ corruption is above the
       driver entirely ⇒ VM/zalloc/UGC hunt with 0094 (instrument the
       buf/mapped-file layer instead).
- 0093 CONTENT (xnu/patches/0093-merlin-msdc-garbage-tripwire.patch,
  3,874 B, make-0093.py vs art-0091-buildtree; git apply clean; t7/t8
  byte-identical): H1 sweet_ufs.c msdc_read_sector tripwire scan (after
  readverify, before return; first 8 + every 256th hit prints
  "MERLIN MSDC: PATTERN 4600b085 hit #%u lba %llu abs %llu off %u:" +
  16 B hex); H2 non-static counters msdc_pt_hits/msdc_pt_first_lba/
  msdc_pt_last_lba (0088 link lesson; generator asserts decl-before-use
  + placement + identifier contract); H3 zalloc.c replay externs +
  "MERLIN FORENSICS: pattern hits=%u first lba=%llu last lba=%llu".
- 0093 CI (user approved push): ios-sweet 23b39fb PUSHED → dispatch 1
  (run 40377227252) = runner LOST mid-build (job "cancelled", log blob
  never uploaded, no steps recorded — infra flake, not the patch);
  re-dispatch → run 40380050874 GREEN.  GOLDEN RULE FULLY VERIFIED:
  SHA256SUMS ok; kernel 17,208,064 B (research/art-0093, +112 B vs
  0092); 12/12 probes incl. "PATTERN 4600b085 hit" +
  "pattern hits=%u first lba=%llu last" + full 0086→0092 chain; CI log
  skips = known-good five ONLY (corrupt-0083 + dxb×4), 0092+0093
  applied.  Buildtree artifact → research/art-0093-buildtree/buildtree.
  tgz (not yet unpacked to src/ — do that before drafting 0094).
- BOOT #23 IMAGE BUILT: research/merlin-boot/
  shim-boot-merlin-msdc-0093-fv.img (16,989,139 B, sha
  83a44425f26117d84ccf7349da2b8c60c92b1d392052808cc388cc08bcfc33d3,
  payload 16,612,848 B, shim+dtb byte-identical to E1, cmdline
  verbatim = #19-#22 incl. msdc_readverify=1).  READY: user
  `fastboot boot` + ONE photo of the settled screen.
- BOOT #23 DECODE TABLE: NEW "MERLIN MSDC: PATTERN 4600b085 hit #N
  lba R abs A off O:" lines = the tripwire (R = partition-relative,
  A = absolute LBA); tail "MERLIN FORENSICS: pattern hits=N first
  lba=A last lba=B" = cached verdict even if early lines scrolled.
  VERDICT BRANCHES: (a) hits>0 and A in [24,494,910..24,995,871]
  (block-47 stale hole) → kernel asked there → map A's partition
  offset to the owning HFS extent offline → content class (repair =
  rewrite those LBAs); (b) hits>0 and A in image-backed territory →
  card serves non-image bytes CRC-clean → eMMC-internal class →
  LBA-level readback verify vs image; (c) hits>0 and A absurd for a
  Mach-O header page → HFS extent/blkno bug (XNU fix); (d) hits=0 AND
  the 0x4600b085 wall still fires → corruption is ABOVE the driver
  (buf/VM/UGC) → 0094 instruments that layer (user's XNU-model branch).
  No hit + boot goes deeper = the tripwire region wasn't touched —
  read the tail for the usual reads/mismatch/spill lines.
- BOOT #23 RUNBOOK (when pushed + CI green): build 0093 image with the
  SAME full cmdline as #19-#22 (msdc_readverify=1 kept — its 2× read is
  the on-media proof the tripwire relies on), fastboot boot + ONE photo
  of the settled tail.  Decode: PATTERN hit lines + replay pattern line
  (+ the usual reads/mismatch/spill/apdma lines).  Compare hit LBA vs
  the hole range above; map partition byte offset via the offline HFS
  catalog walk (research/ipsw-x/iosroot-v2.img is a raw HFS volume —
  parseable in Python) to name the file dyld was reading.
- GPT RESIZE: PAUSED per user (LATEST-63 procedure + blobs remain valid
  and unchanged in research/gpt-restore/).

## Agent handoff / active work (2026-10-26 LATEST-63: USER CANCELLED the block-47 zero-fill repair ("wont help") and DIRECTED: restore userdata partition to ORIGINAL size (phone = 64GB). DONE OFFLINE: stock GPT geometry established from a PRE-SURGERY capture, restore blobs BUILT + VALIDATED — userdata will go 22,840 MiB → 49,652 MiB (48.489 GiB, stock [20,332,544..122,021,823] contiguous to otp), esp+win entries deleted, stock zero disk GUID restored. BLOCKED ON USER HANDS: TWRP + adb (pre-check hashes → dd 2 blobs → post-write hashes). The resize is METADATA-ONLY: no data bytes move; block-47 stale bytes and the dyld-garbage wall are NOT touched by this)

- GPT FACTS (all source-pinned this session):
  - Device NOW (Oct-3 mtkclient dumps D:\things\Merlin\Dumped\gpt.bin +
    gpt_backup.bin; CRCs verified; primary==backup): userdata
    [20,332,544..67,108,863] = 22,840 MiB (matches boot console print),
    esp [67,108,864..75,497,471] 4 GiB, win [75,497,472..122,019,775]
    22.18 GiB, disk GUID 12345678-1234-5678-1234-123456781234.
  - STOCK ground truth: D:\things\Merlin\UEFI\Mu-Silicium\Build\
    gpt-head-34.img = raw LBA0-33 pulled 2026-09-04 21:48 BEFORE the WOA
    sgdisk repartition (Mu-Silicium memory/2026-09-04.md documents the
    surgery verbatim: userdata 48.5 GiB → 22.3 GiB, esp 2→4 GiB, win
    22.2 GiB; --disk-guid/--partition-guid set 2026-09-27 for BCD).
    STOCK userdata = [20,332,544..122,021,823] = 101,689,280 sectors =
    49,652 MiB = 48.489 GiB, CONTIGUOUS to otp @122,021,824 (the 1-MiB
    gap before otp = WOA artifact); stock disk GUID = all zeros; no
    esp/win. Cross-checked vs MIUI stock scatter (extracted from
    D:\things\Merlin\merlin_global_images_V12.5.1.0.RJOMIXM_*.tgz →
    research/gpt-restore/stock/): every partition matches (scatter
    userdata size 0xC0000000 = build-time placeholder; otp/flashinfo
    sizes match GPT exactly).
  - eMMC = 122,142,720 LBAs (58.24 GiB); LastUsableLBA 122,142,686;
    backup table @122,142,687, backup header @122,142,719.
- PREPARED (research/gpt-restore/): make-gpt-restore.py (generator +
  full validator: CRC checks on both captures, stock-vs-current diff =
  ONLY userdata-end/esp/win/GUIDs, round-trip parse of blobs) →
  gpt-primary-stock.img (17,408 B = stock LBA0-33 VERBATIM incl. real
  stock LBA33) + gpt-backup-stock.img (16,896 B = stock 32-sector table
  + RECONSTRUCTED backup header, spec-correct pent=122,142,687, fresh
  CRCs — the stock backup header bytes were never dumped).
- PROCEDURE (user hands, TWRP booted; adb binary reads MUST use
  exec-out — adb shell corrupts binary via PTY):
  1. push both blobs to /tmp.
  2. PRE-CHECK (expect 50df2a1c4f3e3b26… and 19f85c839110e8a3…):
     adb exec-out "dd if=/dev/block/mmcblk0 bs=512 skip=0 count=34" | sha256sum
     adb exec-out "dd if=/dev/block/mmcblk0 bs=512 skip=122142687 count=33" | sha256sum
     MISMATCH ⇒ STOP, pull both regions to files and send for decode
     (device GPT changed since Oct 3 somewhere).
  3. WRITE (destructive to GPT only; userdata start unchanged):
     adb shell "dd if=/tmp/gpt-primary-stock.img of=/dev/block/mmcblk0 bs=512 seek=0 count=34 conv=fsync"
     adb shell "dd if=/tmp/gpt-backup-stock.img of=/dev/block/mmcblk0 bs=512 seek=122142687 count=33 conv=fsync"
  4. POST-WRITE (expect ccff6dca1a5df468… and e536f4d892419ab3…):
     same two exec-out sha256 reads as step 2.
- CONSEQUENCES / NOTES: userdata start (0x1364000) unchanged → HFS +
  msdcroot0 boot flow identical; kernel will print ~49652 MiB. esp/win
  DATA bytes stay on flash until overwritten (unallocated, harmless).
  Block-47 stale bytes (fd118c19 region) live INSIDE the old [0..22,840
  MiB) range and are NOT cleaned by this resize — the SpringBoard
  dyld-garbage wall stands until those LBAs are rewritten (user plans
  the fix path; mtkclient raw write would bypass the sparse zero-skip
  class entirely). Disk GUID reverts to stock zeros — fine, the WOA
  BCD is dead with esp/win gone. Current tree also carries parked
  QEMU ramfb/fbcon-1x work (uncommitted, leave alone).

## Agent handoff / active work (2026-10-25 LATEST-62: BOOT #22 (0092) = **THE SCRIBBLER IS FIXED** — no element-modified-after-free panic, first boot since #10 without one; boot died at the PREDICTED next wall: SpringBoard launch, dyld reads garbage load-command bytes ("size (0x4600b085) not multiple of 4" — the SAME value as boot #19 = DETERMINISTIC).  DECISIVE 17.2 GB IMAGE SEARCH: pattern 85 b0 00 46 (LE of 0x4600b085) has ZERO occurrences anywhere in iosroot-v2.img (282s full scan) ⇒ runtime bytes are NOT any image bytes; with readverify stable (0 mismatches) the only remaining source = THE eMMC CONTENT ITSELF IS WRONG at scattered blocks ⇒ flash #3 ("47/47 OKAY, unverified") also silently failed to write at spots — same failure class as flashes #1/#2.  FIX = VERIFIED REFLASH of userdata from research\ipsw-x\iosroot-v2.img + mtkclient readback hash-compare + boot #23 (same 0092 image, no rebuild).  BLOCKED: user confirmation + hands (fastboot/BROM); flashing = destructive, confirmed per project rules)

- BOOT #22 DECODE (image c5385b80): early "MERLIN: pmap excluding
  PA 0x9f800000-0x9fa80000 (640 pages…)" seen = fix fired ✓; NO
  zalloc panic; deepest failure = SpringBoard/dyld garbage-load-
  command wall (identical garbage to #19 ⇒ deterministic).
- VERDICT CHAIN (all three facts source-pinned): (1) image-side
  bytes good (LATEST-38: 44 cache files sha-matched to IPSW);
  (2) reads stable (readverify 0 mismatches across boots);
  (3) runtime garbage exists NOWHERE in the image (this session's
  full scan) ⇒ eMMC ≠ image at those blocks; reflash+verify is the
  only fix class left for this wall.
- REFLASH PLAN (awaiting user GO): fastboot flash userdata
  research\ipsw-x\iosroot-v2.img (17,226,006,528 B; NOT iosroot.img
  v1, NOT rootfs.img) → mtkclient readback of userdata → hash
  compare vs image → boot #23 = same shim-boot-merlin-msdc-0092-
  full-fv.img → expect SpringBoard past load commands (mockfs-era
  ceiling territory).  If garbage persists AFTER verified-identical
  bytes on media → the divergence is in the read path after all
  (driver/HFS-extent bug hunt reopens with LBA-level evidence).

- FLASH #4 (user, same command): 91/92 sparse chunks OKAY, chunk 92
  (last, ~126 MB) FAILED "sparse image write failure" — LIVE proof of
  the write-loss class (same family as flashes #1/#2/#3's silent
  damage).  The failed region is REAL DATA (51.9% 0xFF, first
  non-0xFF at 0x3fb0cac00 ≈ the HFS volume tail) — retry required;
  fallback = mtkclient payload write (bypasses LK sparse writer);
  ALWAYS readback-verify before booting.
- FLASH #6 VIA TWRP (user): `fastboot flash userdata` from TWRP's
  userspace fastbootd = 47/47 chunks ALL OKAY, 997s ("Finished").
  WRITER MYSTERY SOLVED: LK-bootloader fastboot = 128MB chunks +
  the deterministic final-chunk bug (tonight's two 92-chunk
  failures); TWRP fastbootd = 256MB chunks (same geometry as the
  historical flash #3 "47/47") + working write path.  Use TWRP
  for userdata flashes from now on.
- FULL-PARTITION HASH VERIFY (TWRP on-device dd|sha256sum, no BROM
  needed): MISMATCH — source 64346ce1… vs device b527a185… ⇒ even
  the TWRP 47/47-OKAY flash left the partition ≠ image (or the
  divergence is in don't-care bytes).  LOCALIZATION IN FLIGHT:
  65-block (64x256MB + 44MB tail) hash compare, device side via
  adb dd loop, image side in research/qtest-latest/image-block-
  hashes.txt.  VERDICT BRANCHES: mismatches ONLY in the 64MiB 0xFF
  decoy tail (sparse FILL-chunk handling) ⇒ real volume intact,
  boot #23 immediately; mismatches at sparse chunk boundaries ⇒
  fastbootd sparse bug; scattered ⇒ weak eMMC cells (media) ⇒
  microSD-staged dd rewrite or mtkclient route.
  (last, ~126 MB) FAILED "sparse image write failure" — LIVE proof of
  the write-loss class (same family as flashes #1/#2/#3's silent
  damage).  The failed region is REAL DATA (51.9% 0xFF, first
  non-0xFF at 0x3fb0cac00 ≈ the HFS volume tail) — retry required;
  fallback = mtkclient payload write (bypasses LK sparse writer);
  ALWAYS readback-verify before booting.
- ROOT CAUSE FOUND (65-block diff): ONLY block 47 (256MB @
  12,541,393,920) diverges — IMAGE block 47 = ALL ZEROS (sha
  a6d72ac7 = zeros hash) but DEVICE holds stale fd118c19 content
  ⇒ THE SPARSE FLASH SKIPS ALL-ZERO REGIONS (host sparsifier turns
  zeros into dontcare/fill chunks; fastbootd skips writing them),
  leaving PREVIOUS-flash bytes in place.  THIS EXPLAINS THE WHOLE
  NIGHT: past flashes' zero-holes landed on real file data (dyld
  cache pages) → kernel read STALE flash-#1/#2-era bytes =
  deterministic + stable + not-in-image garbage (0x4600b085).  THE
  eMMC WAS NEVER BAD — the writes were never complete.  REPAIR:
  on-device zero-fill block 47 (dd if=/dev/zero seek=3061782
  count=65536 conv=fsync) → block re-hash → expect a6d72ac7 →
  full hash → expect 64346ce1 → BOOT #23.
  needed): MISMATCH — source 64346ce1… vs device b527a185… ⇒ even
  the TWRP 47/47-OKAY flash left the partition ≠ image (or the
  divergence is in don't-care bytes).  LOCALIZATION IN FLIGHT:
  65-block (64x256MB + 44MB tail) hash compare, device side via
  adb dd loop, image side in research/qtest-latest/image-block-
  hashes.txt.  VERDICT BRANCHES: mismatches ONLY in the 64MiB 0xFF
  decoy tail (sparse FILL-chunk handling) ⇒ real volume intact,
  boot #23 immediately; mismatches at sparse chunk boundaries ⇒
  fastbootd sparse bug; scattered ⇒ weak eMMC cells (media) ⇒
  microSD-staged dd rewrite or mtkclient route.
  (last, ~126 MB) FAILED "sparse image write failure" — LIVE proof of
  the write-loss class (same family as flashes #1/#2/#3's silent
  damage).  The failed region is REAL DATA (51.9% 0xFF, first
  non-0xFF at 0x3fb0cac00 ≈ the HFS volume tail) — retry required;
  fallback = mtkclient payload write (bypasses LK sparse writer);
  ALWAYS readback-verify before booting.
- QEMU TRACK (user asked; ran while flashing): tools/merlin-qemu-test
  harness works — the 0092 KERNEL BOOTED AND RAN 60s in QEMU virt
  (clean timer IRQs, no faults, no panic; research/qtest-latest/q0092*
  + q0092v).  Kernel image itself sound in a clean environment.
  Console visibility limited: SWEET EARLY markers 1-20 visible on the
  fb plane (arm_init → pmap_bootstrap → serial_init → kprintf
  complete), then output stops reaching the plane (console routing
  after kprintf init unresolved; serial=3 sent everything to a
  nonexistent uart — twin ADT has no serial node, kernel has no pl011
  driver).  Next for this track: fix post-kprintf console routing
  (ties into the parked ramfb/fbcon experiment in the tree).
  research\ipsw-x\iosroot-v2.img (17,226,006,528 B; NOT iosroot.img
  v1, NOT rootfs.img) → mtkclient readback of userdata → hash
  compare vs image → boot #23 = same shim-boot-merlin-msdc-0092-
  full-fv.img → expect SpringBoard past load commands (mockfs-era
  ceiling territory).  If garbage persists AFTER verified-identical
  bytes on media → the divergence is in the read path after all
  (driver/HFS-extent bug hunt reopens with LBA-level evidence).

## Agent handoff / active work (2026-10-25 LATEST-61: BOOT #21 (same 0091 image) = SECOND pa= SAMPLE — victim kalloc.type.var2.4096@2688 ALL-0xFF **pa=0x9fa08000**; footprint now THREE points (0x9f98a000, 0x9f9ea000, 0x9fa08000 — all 16K-aligned, span 0x7e000, all inside [0x9f800000, 0x9fa80000)) ⇒ writer PA-anchored and stable across boots ✓.  0092 = THE FIX, COMMITTED + PUSHED (user: "go for the big bang"): pmap_next_page() skips the window (default 0x9f800000+0x280000; boot-arg merlin_excl_pa=START-LEN overrides); ios-merlin 395a298 / ios-sweet c12de27 pushed, CI run 40221667737 in progress.  Next: golden rule → boot #22 = first scribbler-immune boot → expect death point to MOVE (SpringBoard read-divergence wall becomes active).  Reality check recorded: 0092 fixes the SCRIBBLER class, not the SpringBoard bad-bytes wall — that one needs the eMMC-content-vs-image decision)

- BOOT #21 DECODE: same image as #20 (751a2a88), victim zone
  kalloc.type.var2.4096 size=4096 off=2688 val=0xffffffffffffffff
  elem=0xffffffe29a77e4000 pa=0x9fa08000; apdma found=0 quiesced=0;
  reads=546,152 mismatches=0 spill=0; lk dma ctrl 0x6108 cfg 0x4
  sa=0x4c59fc30 (sa varies slightly per boot; ctrl/cfg/len stable).
- 0092 DESIGN (this session, evidence-complete): hook =
  osfmk/arm/pmap/pmap.c pmap_next_page (:2637, the single free-page
  choke point the VM pulls every managed page through); skip block
  jumps first_avail past the window end + decrements avail_page_count
  consistently; merlin_hex/merlin_excl_init parse the override
  boot-arg once; print "MERLIN: pmap excluding PA ..." when it fires.
  Anchors: pmap_next_page_hi block + pmap_next_page head; generator
  make-0092.py vs art-0091-buildtree/src/xnu; VALIDATED t7/t8;
  probes "MERLIN: pmap excluding PA" + "merlin_excl_pa".
- WINDOW MATH: observed min 0x9f98a000 / max 0x9fa08000; default
  [0x9f800000, 0x9fa80000) = 2.5 MB covers both with ≥0x88000 /
  ≥0x78000 margin; if a future victim lands outside, adjust via
  merlin_excl_pa boot-arg (no rebuild needed).
- CI 40221667737 GREEN (~7 min), GOLDEN RULE VERIFIED: kernel sha
  881326f7… (research/art-0092, 17,207,952 B); probes PASS incl.
  "MERLIN: pmap excluding PA" + "merlin_excl_pa"; skip set =
  known-good five; chain 0082→0092 applied.  BOOT #22 IMAGE BUILT:
  research/merlin-boot/shim-boot-merlin-msdc-0092-full-fv.img
  (16,989,139 B, sha c5385b80…, payload 16,612,752 B, cmdline =
  #19/#20/#21).  READY: user fastboot boot + photo(s).  EXPECT:
  early console shows "MERLIN: pmap excluding PA 0x9f800000-
  0x9fa80000 (640 pages…)" (the fix firing); NO more element-
  modified-after-free panics; death point moves to the SpringBoard
  read-divergence wall (dyld malformed load command / CRASH
  SpringBoard sig 6) — that is SUCCESS for 0092; then the next
  milestone = eMMC content verification (userdata reflash decision)
  per LATEST-38 evidence chain.

## Agent handoff / active work (2026-10-25 LATEST-60: BOOT #20 (0091) = pa= DELIVERED — TWO victims, BOTH scribbler classes in ONE boot, PAs CAPTURED: scp-code victim kalloc.24576@8192 pa=0x9f98a000 (Thumb-2 "29 46 00 22 fe f7 b1 fe…"), panic victim kalloc.8192@0 = ALL-0xFF fill pa=0x9f9ea000 (Δ0x60000, same 0x9f9 neighborhood); APDMA REAL verdict found=0 quiesced=0 map=0 (scan ran at fixed PA — UART-DMA EXONERATED); readverify 0 mismatches @544,438 reads; lk dma state identical to #19 (deterministic LK).  MODEL: fixed-PA writer footprint ≈ [0x9f98a000, 0x9f9f0000) copying SCP-firmware dump blocks (code verbatim + 0xFF padding = a structured dump fill); BOTH boot-11/13/14's 0xFF class AND #15/19's code class = one mechanism.  NEXT: one more 0091 boot for a second pa= sample → 0092 = boot-arg physical exclusion of the region)

- PHOTO DECODE (boot #20, image 751a2a88): frame = 0083-skip warning
  + panic [data.kalloc.8192] off:0 val:0xffffffffffffffff
  sz:8192 ptr:0xfffffe2ffff72000; notes ring shows TWO victims:
  1) data.kalloc.24576 size=24576 off=8192 val=0xfeb1ff7fe22004629
     elem=0xfffffe2ffff7e000 pa=0x9f98a000; b[8192..8207] =
     "29 46 00 22 fe f7 b1 fe 00 2…" (mov r1,r5; movs r2,#0; bl …
     = SCP code class, 64-B aligned at 0x2000 inside the elem).
  2) data.kalloc.8192 (the panic one) off=0 ALL-0xFF pa=0x9f9ea000.
  Replay counters: reads=544,438 mismatches=0 spill=0; lk dma
  ctrl 0x00006108 cfg 0x4 sa 0x4c59fe88 ca 0x4c59f8a4 len 0x200;
  apdma found=0 quiesced=0 map=0x00000000 (REAL — fallback scan ran;
  no armed UART VFF channel existed at handoff).
- SCP REGION EVIDENCE (stock kernel source, this session):
  mt6768.dts reserved-memory: scp_share 3MB/16MB-aligned
  alloc-ranges [0x40000000,0x50000000), no-map; sspm_share 5M+64K
  [0x40000000,0x60000000).  scp_reservedmem_define.h: scp_share
  subdivided at RUNTIME (sensor 1MB, audio_ipi 2MB, a-logger 1.5MB,
  vow, mp3…) — no fixed PAs in source; observed victims 0x9f9xxxxx
  are NOT in the stock alloc-ranges ⇒ the writer's target was set by
  some earlier configurator (stock Android/recovery boot or firmware
  default) and is FIXED across our boots (writer is PA-anchored,
  blind to XNU; zone pages walk into its footprint by layout lottery
  — explains zone/offset variety with deterministic content).
- USER CONTEXT: "it just keeps going to a different error always,
  not able to continue further" — answer: same root cause in
  different masks (zone/offset/class vary per layout lottery) plus
  the separate SpringBoard read-divergence wall behind it; each boot
  this session peeled a layer (root mount → launchd → SpringBoard →
  pa=).  The scribbler fix (0092) is what unlocks everything past it.
- NEXT CONCRETE: (1) boot #21 = SAME 0091 image again (no rebuild) —
  second pa= sample; if victims stay in 0x9f9xxxxx ⇒ footprint
  confirmed stable → (2) 0092 = boot-arg `merlin_excl_pa=<start>-
  <end>` honored in the arm64 free-page enumeration (skip PAs in
  range; default the range from the observed footprint + margin);
  validate, CI, boot #22 = first scribbler-immune boot → then the
  SpringBoard read-divergence wall becomes the active blocker
  (eMMC-content verify/reflash decision per LATEST-38 evidence
  chain: runtime bytes ≠ image bytes with stable reads).

## Agent handoff / active work (2026-10-25 LATEST-59: BOOT #19 (0090+full cmdline) = DEEPEST BOOT EVER — launchd PID 1 RAN DEEP USERLAND (routined/passd/logd_helper exec'd, SpringBoard launched); SPRINGBOARD CRASHED (dyld "malformed load command #2" — the LATEST-38 read-divergence wall returns; readverify=0 mismatches @520k reads ⇒ reads STABLE); then the UAF RETURNED in kalloc.8192@3712 with THE SAME PAYLOAD as boot #15 — **BREAKTHROUGH: island = VERBATIM COPY of SCP coprocessor firmware bytes (scp1/scp2.bin@0xa4a60-0xa4aa0, 7/8 words photo-exact + word 4 matches the photo's own OCR)** ⇒ the scribbler copies from the SCP DRAM image into freed kalloc elements; deterministic content, 64-B bursts, load-correlated.  0091 COMMITTED both repos (victim pa= + APDMA fixed-PA fallback); "handshake structure not initialized" = panic core-dump channel, BENIGN.  BLOCKED: push approval for ios-sweet bccd91d → CI → boot #20)

- PHOTO DECODE (boot #19, image c2b04671): the restored userspace args
  WORKED — "launchd_unsecure_cache" path accepted; exec routined /
  passd / logd_helper; SpringBoard start; dyld errors ("malformed
  load command #2 of 39", "size (0x4600b085) not multiple of 4",
  cs_invalid_page "allowing (remove VALID)"); CRASH SpringBoard[27]
  sig 6 (pc/lr/sp/fp/far + bt) — the LATEST-38 shared-cache/read-
  divergence wall class; readverify says reads are STABLE (0
  mismatches, 520,059 reads) so if runtime bytes ≠ image bytes the
  eMMC content or the mapping is the diverging side.  THEN:
  panic [data.kalloc.8192] off:3712 val:0xbf00bd38606b308c
  sz:8192 ptr:0xfffffe30008e5a000; island 3712..3768 = 8 words.
  0090 FORENSICS FIRST REAL RUN ✓: "victim islands" line (cut above
  frame), replay tail (reads/mismatches/spill, lk dma ctrl 0x6108
  cfg 0x4 sa 0x4c59fe88 len 0x200, apdma found=0 quiesced=0
  map=0x00000000 [scan still DT-blind this boot], victim note +
  b[0..15]=all zeros + b[3712..3727] hex).  Caller 0xfffffe0007ab9058
  unnormalized (= zalloc_uaf_panic path as before).
- SCP IDENTIFICATION (offline this session): byte-searched the raw
  partition dumps (research: D:\things\Merlin\Dumped\) — the six
  stable island byte-patterns hit CONTIGUOUSLY in scp1.bin AND
  scp2.bin at 0xa4a68-0xa4a98; full 64-B block at 0xa4a60-0xa4aa0
  matches the victim island word-for-word (word 4 = 0xf003d509
  4604071a per the photo OCR; my earlier 84-read was the error).
  Context: 0xa4a40-0xa4ab0 = repeated Thumb-2 record structure
  {ptr-pair 0x00031908/0x00085f38 + 0x000861b4/0x000874ed, code,
  38 bd / 00 bf epilogues} — SCP firmware internal tables/code.
  Writer model: SCP (or an engine it drives) copying 64-B-aligned
  blocks of its DRAM image into a fixed/stale PA that XNU zone
  memory now occupies; deterministic source, load-correlated
  timing (thermal/sensor reporting during heavy userspace), varies
  victim by layout lottery.  Boots 11/13/14's 0xFF fill = a
  different report phase or channel (unresolved detail).
  NEXT OFFLINE: mine D:\things\Merlin\android_kernel_xiaomi_mt6768
  SCP driver (drivers/misc/mediatek/scp/) for the AP-side shared
  buffer PA / IPI config — the PA 0091's pa= print will confirm.
- "handshake structure not initialized" = kdp panic core-dump
  channel (osfmk/kdp/output_stages/out_shmem.c:492-505
  panic_spin_shmcon): no firmware XHSDCI shared-memory debug
  handshake exists on this port → informational print during panic
  shutdown, right before the panic.apple.com footer.  NOT an error
  to fix.
- IOCTL GAP ALREADY CLOSED: the 0082 driver's merlin_msdc_ioctl
  now implements DKIOCSYNCHRONIZE→0, DKIOCGETFEATURES, sane
  MAXBLOCKCOUNTs (sweet_ufs.c:1618-1625 post-0090 tree) — the
  LATEST-38 gap was fixed in a later 008x rev; nothing to do.
- 0091 = xnu/patches/0091-merlin-victim-pa-apdma-fixedpa.patch
  (2,536 B; make-0091.py vs art-0090-buildtree/src/xnu; VALIDATED
  t7/t8 + regenerated==committed; kvtophys already used 3x in
  zalloc.c so the decl is visible): H1 replay victim line prints
  pa=kvtophys(elem) (0092 will reserve that PA); H2 apdma quiesce
  DT-fail → "using fixed PA 0x11000000+0x1000" fallback (scan
  finally runs; found/quiesced/map become real).  Commits:
  ios-merlin 05972e0, ios-sweet bccd91d (NOT pushed).
- NEXT CONCRETE: push approval for bccd91d → CI (golden rule +
  probes "pa=0x%llx" + "using fixed PA") → boot #20 (same full
  cmdline) → its panic names the victim PA (expect the SAME PA as
  any earlier SCP-write if the buffer is fixed) + REAL apdma
  verdict → 0092 = reserve that PA range from the physical
  allocator (or quiesce the caught channel); separately the
  SpringBoard read-divergence wall (eMMC verify/reflash decision)
  waits behind the scribbler fix.
- DISPATCHED (user approved "go on"): ios-sweet bccd91d PUSHED → CI
  run 40218760447 (workflow_dispatch) in progress; background poll
  running.  On green: artifacts → research/art-0091*, golden rule
  (probes + "pa=0x%llx" + "using fixed PA 0x11000000+0x1000") →
  build-msdcroot0.py → shim-boot-merlin-msdc-0091-full-fv.img (SAME
  full cmdline as #19) → boot #20 flash + ONE photo (expect: victim
  pa= names the stale buffer; apdma verdict REAL).
- CI 40218760447 GREEN (~6 min), GOLDEN RULE FULLY VERIFIED: kernel
  sha 4e1a04d4… (research/art-0091); 19/19 probes (incl. "pa=0x%llx"
  + "using fixed PA 0x11000000+0x1000"); skip set = known-good five;
  chain 0082→0091 applied.  BOOT #20 IMAGE BUILT:
  research/merlin-boot/shim-boot-merlin-msdc-0091-full-fv.img
  (16,989,139 B, sha 751a2a88…, cmdline identical to #19).  READY:
  user fastboot boot + ONE photo → decode victim pa= + apdma
  found=/quiesced=/map= (now REAL) → 0092 design.

## Agent handoff / active work (2026-10-25 LATEST-58: BOOT #16 (0090) = NO PANIC IN FRAME — DEEPEST BOOT EVER: root FS mounted from userdata (read-only, journal replayed, SWEET unsealed), serial keyboard started, swap ON; the kalloc.16384 UAF that killed boots 11/13/14/15 did NOT fire in frame.  APDMA VERDICT = SCAN SKIPPED EVERY BOOT: runtime DT lacks /ap_dma@11000000 (slot dtb HAS it w/ reg, but runtime tree ≠ slot tree — sweet-ufs/merlin-msdc = 0 hits in slot dtb yet resolve at runtime) ⇒ 0089's DT-based quiesce was structurally dead code.  WHAT HAPPENED AFTER THE FRAME = UNKNOWN → user report / next photo decides)

- PHOTO DECODE (rotated 90°, left edge blurred; no MERLIN FORENSICS
  or panic lines in frame — consistent, those print only ON panic):
  skywalk self-tests pass → bsd_auto_conf kminit → ifnet lo0/gif0/
  stf0 → "MERLIN MSDC: readverify enabled (double-read compare)" →
  "apdma: no /ap_dma@11000000 reg (skip)" [OCR "110100000" =
  garble] → "cfg 0x02200159 ps 0x01f00002 sts 0x00000000 sa
  0x4c59f080" → "dma ctrl 0x0006f100 cfg 0x00000004 sa 0x4c59f080
  ca 0x4c59f8a4 len 0x00000200" → ""userdata" first sector
  0x1364000, 22840 MiB, read-only" → "BSD root: msdcroot0 major 1
  minor 0" → jnl: replay done → hfs: mounted (volname OCR-uncertain)
  → "SWEET: root volume is not authenticated (error 25); continuing
  unsealed" → "Serial keyboard started" → "v_swap Subsystem is ON".
- DT PROOF (offline this session): boot16 dtb slot (img offset
  16807936, 181,203 B) HAS /ap_dma@11000000 AT ROOT with
  compatible="mediatek,ap_dma" + reg={0,0x11000000,0,0x1000}
  (custom FDT walker; an earlier "node has no props" readout was a
  print-filter bug, corrected).  BUT sweet-ufs / merlin-msdc = 0
  hits in the slot dtb while the kernel resolves both at runtime ⇒
  the runtime tree is a CURATED MINIMAL TREE built somewhere in the
  shim/payload chain (construction point not yet located; shim/
  fdt.c is diagnostics-only parsing) ⇒ the 0089 DT lookup could
  never succeed; skip fired every boot (explains why no photo ever
  showed apdma win lines).
- LK MSDC0 DMA SNAPSHOT (first-ever read): ctrl 0x0006f100,
  cfg 0x4 (bit2 set), sa 0x4c59f080, ca 0x4c59f8a4, len 0x200 —
  LK left a 512-B transfer window configured at handoff;
  interpretation pending.
- WHY NO UAF — UNKNOWN, 3 candidates: (a) race/timing variability
  (but boots 11/13/14/15 = 4/4 hits), (b) layout lottery if the
  writer targets fixed PAs (0089 kernel 17,224,136 B vs 0090
  17,207,856 B, payload +96 B — addresses moved), (c) different LK
  boot-path state this boot.  0090 is inert by design (panic-path
  prints only) — NO CREDIT claimed; the UART-APDMA theory is NOT
  disproven either (the scan never ran even once).
- NEXT CONCRETE: (1) USER reports what the screen showed AFTER the
  photographed frame (still alive? SpringBoard slide line? froze?
  eventual panic?) — if it panicked later, that screen now carries
  the 0090 payoff (victim islands run-map + apdma found= verdict),
  one photo decodes it.  (2) 0091 design updates regardless:
  APDMA scan via HARDCODED PA 0x11000000/0x1000 (kill the DT
  dependency); HW-watchpoint discriminator unchanged (parked).
- FOLLOW-UP (same session): user reports boot #16 STUCK at the
  photographed stage (no panic, no userspace; console frozen at
  v_swap ON).  Boot #17 image BUILT:
  research/merlin-boot/shim-boot-merlin-msdc-0090-usb-fv.img
  (16,989,139 B, sha cb032b5c…; cmdline = #16 + sweetusb=2 ONLY,
  kernel unchanged — the USB gadget boot-arg defaults to 1 =
  report-only, which is why #16 has no USB).  DISCRIMINATOR at the
  next hang: plug USB → Windows Device Manager, gadget VID 0x1209
  PID 0x0001 (pid.codes test ID; CDC-ECM class 02/06, no in-box
  Win10 driver — ENUMERATION ITSELF is the signal: device listed =
  kernel/IOKit/interrupts ALIVE → hang = blocked thread, prime
  suspect launchd first-exec stuck on a root-volume storage read;
  "Device Descriptor Request Failed" = hard wedge).  With a Linux
  host or WSL2+usbipd, tools/sweet-usbnet.sh (192.168.7.1 ↔ .2,
  live console on udp/5140) gives the streamed tail.  0091 queue
  unchanged (heartbeat + apdma hardcode) if this doesn't localize.
- BOOT #17 (usb image cb032b5c): STUCK AGAIN but the frame goes
  further — last line = "load_init_program: attempting to load
  /usr/appleinternal/sbin/launchd.development" then SILENCE (no
  "failed loading", no next "attempting", no panic).  Source
  (kern_exec.c:6834-6930): init_programs = {debug?, development,
  /sbin/launchd}; ENOENT falls through SILENTLY, other errors print,
  all-fail panics.  Silence ⇒ execve() of the development variant
  NEVER RETURNED ⇒ blocked inside namei/parse_machfile (storage
  reads via msdc, or a lock).  readverify mismatch path PRINTS and
  returns (not the hang).  HISTORY: 0083-era consoles show the
  ENOENT fall-through to /sbin/launchd (so launchd.development does
  NOT exist on iosroot-v2.img) and /sbin/launchd exec'd — but only
  ever from RAMDISK-MOCKFS roots; NO msdc-root boot ever reached
  exec before ⇒ this hang is the FIRST arrival at this path, not a
  regression.  A missing-file lookup needs only catalog reads; the
  walk itself is stuck (or the console died — USB check tells).
  BOOT #18 image BUILT: shim-boot-merlin-msdc-0090-lrel-fv.img
  (sha 57534d6b…; cmdline + launchdsuffix=release — kern_exec.c
  6890-6902 forces /sbin/launchd directly, shallow path, skips the
  appleinternal walk; on exec error it PANICS with errno + full
  replay instead of hanging silently).
- BOOT #18 (lrel image 57534d6b): THE SHALLOW PATH EXEC'D — no hang!
  Console: "load_init_program: attempting to load /sbin/launchd" →
  launchd became PID 1 → immediately SIGKILLed → terminal panic
  "unexpected SIGKILL of launchd [no reason provided]" (kern_sig.c:
  2061-2074 — initproc SIGKILL with NULL reason; "(CS_KILLED)" tag
  presence OCR-unresolved; caller 0xfffffe0007afdc34 unnormalized).
  So #17's hang WAS specific to the /usr/appleinternal deep walk;
  /sbin/launchd lookup+exec over msdc WORKS.  ROOT CAUSE OF THE
  KILL (high confidence): CMDLINE REGRESSION — the proven 0083-era
  cmdline carried `unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`
  (platform gate + AMFI/cache-loader escape; boot #6 reached
  SpringBoard with them; even early msdcroot0 boots had them —
  NOTES:894/1191), but the 0084-era trimmed cmdline DROPPED both.
  Boots #11-#15 never noticed (UAF killed them pre-exec).  The
  bypasses still exist in this DEVELOPMENT kernel
  (kern_codesigning.c:71-139: amfi=/amfi_allow_any_signature=/
  amfi_get_out_of_my_way=/cs_enforcement_disable= all parse on
  DEVELOPMENT).  BOOT #19 IMAGE BUILT:
  shim-boot-merlin-msdc-0090-full-fv.img (sha c2b04671…, cmdline =
  #18 + the two restored args).  EXPECT: launchd_cache_loader
  prints "Using unsecure cache: /System/Library/xpc/launchd.plist"
  → "Cache sent to launchd successfully" (LATEST-37 decode) →
  deeper userland than ANY boot (boot #6 ceiling = SpringBoard
  launch + shared-cache slide overflow — that wall's 0084+
  readverify verdict stays relevant).  If launchd still dies:
  full-screen photo of the panic block (backtrace + "Original
  panic string:" + System diagnostics follow the banner).

## Agent handoff / active work (2026-10-25 LATEST-57 (upd): 0090-v1 WAS pushed (ios-sweet 59ced39) and CI-RED — run 40208702420, build exit 2: v1 declared 'years' but used 'beyond' 3x (diff-verified in the committed patch; t7/t8 byte-compare cannot catch this class — both sides share the same edit). 0090-v2 (identifier fix + generator identifier-contract asserts) committed local BOTH repos (ios-merlin d3dc0b3 / ios-sweet 0adeac7, ahead 1), re-validated t7/t8 + regenerated==committed. PUSHED 0adeac7 (user-approved) → CI run 40212507739 GREEN, GOLDEN RULE FULLY VERIFIED (sha 20e6fd54…; 17/17 probes incl. "victim islands"+"apdma found="; skip set = known-good five ×2; merlin chain 0082→0090 applied) → shim-boot-merlin-msdc-0090-fv.img BUILT (16,989,139 B, sha 1d76f240…, payload 16,612,640 B, cmdline = 0088/0089 + msdc_readverify=1, shim+dtb byte-identical to E1) → READY FOR BOOT #16: user fastboot boot + ONE photo)

- 0090 = `xnu/patches/0090-merlin-island-map-apdma-verdict.patch`
  (v2 4,318 B, sha 8b15a2a5…) by make-0090.py from
  research/art-0089-buildtree/src/xnu; git apply clean; both files
  byte-identical (t7/t8).  v2 commits: ios-merlin d3dc0b3, ios-sweet
  0adeac7 (msdc-0079 ahead 1, NOT pushed).  SUPERSEDED: v1
  ios-merlin 2be10a0 / ios-sweet 59ced39 — v1 was PUSHED (remote
  == local at check time) and CI run 40208702420 went RED (build
  exit 2, 7m29s on 59ced39; detailed log sign-in-only; cause per
  make-0090.py lesson = 3x undeclared 'beyond').
- CONTENT:
  1. zalloc_uaf_panic: bounded island run-map — nonzero 8-byte runs
     (≤8, "0x%x-0x%x " entries + "+%u more" overflow), one line
     "MERLIN FORENSICS: victim islands %u %s" printed BEFORE the
     (panic) call so it is the LAST thing before the banner →
     bottom of the visible frame by construction (boot #15's buf
     copy lost the 15872 island via the 1024 B cap; the run-map
     makes that truncation harmless).
  2. sweet_ufs.c: verdict cache statics after msdc_lk_*:
     `uint32_t msdc_apdma_map;` (bitmask, bit = window>>7),
     `uint8_t msdc_apdma_count, msdc_apdma_stopped;` — set inside
     merlin_apdma_quiesce's scan (map |= 1u << (w >> 7) for any
     live-state window; count/stopped copied after the summary
     print).  NON-static (0088 link lesson; assert in generator).
  3. zalloc replay: externs + "MERLIN FORENSICS: apdma found=%u
     quiesced=%u map=0x%08x" → the tail screen finally carries the
     APDMA story every boot.
- GENERATOR ASSERTS: verdict vars non-static + decl-before-use;
  island map printed before the panic line; probes for both new
  formats; mbuf[128] (8 runs × ≤13 chars + overflow marker); v2 adds
  the identifier contract (no 'years', exactly 4 'beyond' refs,
  decl-before-use) — the class t7/t8 cannot catch.
- SECOND-AGENT VERIFICATION + CORRECTIONS (same day):
  1. RE-VALIDATION: make-0090.py re-run → VALIDATED; regenerated
     v2 byte-identical to committed d3dc0b3.
  2. BUF-CAPACITY CORRECTION (LATEST-56/0090 premise): dump line
     format "\n%5d: 0x%016lx" = 26 chars; boot #15 = 39 nonzero
     words (8+8+16+7) = 1014 + 10-byte partial "\n15928: 0" =
     EXACTLY 1024 → the buf HELD the full island list incl.
     15872–15920; the on-screen "15928: 0" fragment IS the buf's
     truncated 40th line (OCR matches verbatim).  Copy B's
     mid-"12856: 0x" cut = SCREEN edge (photo composition), not buf
     truncation.  0090 stays justified: the boots-11/13/14 dense
     all-0xFF class (2048 words) overflows the buf at word 39, and
     the run-map line survives in-frame regardless.
  3. OCR AUDIT (boot #15 trace blocks): "2856: 0x0008632a00031908"
     = 12856 with a lost leading '1' (kills the "uncertain 2856"
     island; value digit 08-vs-88 uncertain, copy A reads 88);
     "12768: 0xkbd702800fdc3f7ff" has non-hex 'k' (strip →
     0xbd702800fdc3f7ff); 12840 is 15-digit in BOTH copies (likely
     0x07ff4070e8bd2302); raw caller 0xffffe0007ab8ec8 = 15 digits
     → normalized 0xfffffe0007ab8e8c stands; ptr 0xffffe30000ac000
     = 15 digits → true %p likely 0xffffe30000ac0000.  Thumb-2
     decode of island words confirms code class (0x4615681b4b0bb538
     = push {r3-r5,lr}; ldr r3,[pc,#44]; ldr r3,[r3]; mov r5,r2).
     Island 3 = 16 words (12736–12856 incl.) = 128 B → spans
     64/64/128/56 B ≈ 312 B, all four START 64-B aligned
     (9920/11904/12736/15872) → 1–2-cache-line burst writer.
  4. PHASE-A ANCHORS VERIFIED (art-0089-buildtree src/xnu):
     zero-on-free contract zalloc.c:3029-3038 (check always-on on
     embedded, x86 20%); zalloc_validate_element zalloc.c:3208-3228
     (Z_NOZZC skip); zalloc_uaf_panic zalloc.c:3166-3205 (buf[1024],
     first-nonzero off/val); zone naming = kalloc.c:170 ("data." /
     KHEAP_ID_DATA_BUFFERS) + kalloc.c:188-190 (KHEAP_DATA_BUFFERS
     "data.kalloc") + zalloc.c:8678 ("kalloc.%d") →
     "data.kalloc.16384" ✓.
- BOOT #16 DECODE TABLE: "victim islands" line = full corruption
  outline (compare island sizes/offsets across boots: 64-B-aligned
  bursts? ::  stride?); "apdma found=" line >0 = LK armed channels
  existed (map shows WHICH windows 0x980/0xa00/0xa80/0xb00 = bits
  19/20/21/22; found>0 with quiesced==found = cleanup complete);
  "lk dma ctrl=" line = LK MSDC0 handoff state; victim b[] byte
  samples = fill class; reads/spill = MSDC canary health.
- NEXT CONCRETE: BOOT #16 — user runs `fastboot boot
  research\merlin-boot\shim-boot-merlin-msdc-0090-fv.img`
  (temporary boot, NO flashing) + ONE photo of the final screen;
  decode per the BOOT #16 DECODE TABLE above (victim islands line +
  "apdma found=" line + lk dma ctrl + victim b[] + reads/spill).
  ASIDE: first builder run used default --out and overwrote
  research/merlin-boot/shim-boot-merlin-msdc-blknum.img (derived,
  regenerable; since deleted) and default CMDLINE LACKS
  msdc_readverify=1 — the fv image was rebuilt with explicit
  --cmdline.  Parked next: 0091 HW-watchpoint prototype; fetch
  art-0090-buildtree (artifact id 12605969599) when drafting 0091.
- Parked next (needs evidence first): 0091 HW-watchpoint prototype
  (freed-elem write watch under cpus=1 → CPU writer traps with PC;
  DMA silent) — the CPU-vs-DMA discriminator.

## Agent handoff / active work (2026-10-25 LATEST-56: BOOT #15 (0089) DECODED — UAF RECURRED but the content class CHANGED: victim = freed elem mostly ZEROED with FOUR SHORT Thumb-2 CODE ISLANDS at elem+0x26c0/0x2e80/0x31c0/0x3e00 (~64–120 B each; val 0x8718681b4b27e034 = first nonzero word); NO MERLIN forensics lines visible in frame (replay scrolled off + buf[1024] truncated the island list mid-12856 — copy A tail shows the 15872 island, copy B head does NOT); apdma verdict NOT readable this boot. NO FIX JUSTIFIED YET — 0090 = forensics completeness (island run-map + cached apdma verdicts in replay) then a HW-watchpoint CPU-vs-DMA discriminator)

- Boot #15 = shim-boot-merlin-msdc-0089-fv.img (verified sha 989C711F…).
  Photo composition: nz-word dump tail (12816…15928) + panic banner +
  "Original panic string:" + the SAME dump's head (9920…) ending
  mid-line at "12856: 0x" = zalloc_uaf_panic's buf[1024] cap (la 0084
  hook) — the SECOND copy loses the ≥15872 island; the copies agree on
  shared offsets ✓.  Reader urged by the template: off/val/ptr fields
  partially OCR-noisy BUT off:9920/val:0x8718681b4b27e034 MATCH the
  dump's first line exactly ✓; caller normalized
  0xfffffe0007ab8e8c = _zalloc_uaf_panic + 0x15c (symtab 70,896 syms;
  dSYM in the artifact zip carries NO DWARF — only lldb scripts).
- CHECK SEMANTICS (exact, this tree): zalloc_validate_element
  (zalloc.c:3208) at ALLOC time runs memcmp_zero_ptr_aligned(elem,
  size) over the taken-from-freelist element and panics unless ALL
  ZERO (ZALLOC_ENABLE_ZERO_CHECK / zzc).  Our 0084 zalloc_uaf_panic
  (3164–3205) re-derives off/val as the FIRST NONZERO 8-byte word →
  so: bytes 0…9919 were ZERO at detection ⇒ islands = writes AFTER
  the zero-fill, BETWEEN free and re-alloc (dwell window).  Island
  spans (both copies deduped): 9920–9984, 11904–11968, 12736–12856,
  15872–15928 (+ an uncertain 2856 line reported by the OCR only).
  Total corrupting bytes ≲ 350 B in SHORT bursts at 64-B-aligned
  offsets — NOT a 16 K stream and NOT 0xFF fill.
- CONTENT: islands are ARM32/Thumb-2 machine code + pointer-pair
  tables (0x00031k08/0x00086xxx…, span ~0x31908–0x874ed ≈ 352 KB →
  an ARM32 image of ≥ ~0x87500 B).  Byte-search of those constants
  (LE) + two 8-byte island words against EVERY local binary
  (unpack-0001/0002 kernel+ramdisk+dtb, ctlB + 0083 boot imgs, art-
  0089 kernel) = ZERO MATCHES → the source image lives only on the
  device (prime candidates: LK itself [ARM32 ~300–600 KB, DDR-
  resident] / stock Android boot chain pages).  DO NOT symbolize the
  dump words as a stack — they are data.
- #15 UNKNOWN (lines not in frame): msdc reads/spill verdict (canary
  probably still clean but unproven this shot); lk dma line; apdma
  armed/quiesced counts (0089 prints them at init-time only — a
  DESIGN GAP).  No SpringBoard slide line visible either.
- MODEL UPDATE: boots 11/13/14 = 0xFF-interpretation (wire/idle-high),
  boot 15 = short CODE bursts → the writer's payload is NOT a fixed
  pattern; classic suspects re-ranked: (a) stale DMA descriptors
  streaming variable source bytes (APDMA theory NOT confirmed — the
  0xFF decode fit boot 11/13/14 ONLY), (b) a CPU-side writer (warm-
  boot stale RAM does NOT self-write), (c) SEVERAL independent scrib
  blers.  The discriminator that settles CPU-vs-DMA: HARDWARE
  WATCHPOINT on a freed element (DMA does not trap; CPU writes do)
  in a cpus=1 boot → 0091 candidate after 0090.
- 0090 PLAN (diagnostics only, no functional change):
  1. zalloc_uaf_panic: replace/augment the buf scan with a bounded
     ISLAND RUN-MAP (≤ 8 runs: start–end offsets), printed AND packed
     into the panic reason line — kills the buf[1024] truncation loss
     permanently.
  2. merlin_apdma_quiesce: record verdict statics (armed windows/
     quiesced/which offsets) and print them in merlin_uaf_replay →
     the ONE-photo tail finally proves/disproves the LK-armed-channel
     story every boot.
  3. Keep everything else untouched (0088 canary/0087 tail chain).
- ASSET NOTE: research/art-0089/kernel.development.sweet.link/ IS A
  DIRECTORY (ships kdk libs + .a + dSYM WITHOUT DWARF + exp files);
  .a = 134 MB TU objects (symtab candidate for future offline
  symbolization needs).
- NEXT CONCRETE: draft make-0090.py against research/art-0089-build
  tree/src/xnu (BASE note: directory layout now src/xnu ✓), validate
  byte-exact, commit both repos, ask push approval; simultaneously
  propose the HW-watchpoint design as 0091.

## Agent handoff / active work (2026-10-25 LATEST-55: 0089 CI GREEN (run 40205264342 @ c8d5aadc) + FULL GOLDEN-RULE VERIFIED (SHA match; 15/15 binary probes; log skip set = known-good ONLY, 0082→0089 all applied); boot image shim-boot-merlin-msdc-0089-fv.img BUILT (16,989,139 B) — READY FOR BOOT #15: user flash + ONE photo; decode table below)

- Run 40205264342 (workflow_dispatch, ref msdc-0079 @ c8d5aadc74d38eaab
  8c180daff4b8e50f8fbbade) = success.  Artifacts: kernel 12603383225
  → research/art-0089; buildtree 12603867217 → research/art-0089-
  buildtree.
- GOLDEN RULE (all satisfied):
  1. SHA256SUMS: kernel sha 98239dbafbcced2f6cbf1bffd2cd58feac50b92
     232c919d45b0eaa97fc38e7d1 == actual ✓ (17,224,136 B = +16,528
     vs 0088).
  2. Binary probes 15/15 True: "MERLIN MSDC: apdma win", "apdma: no
     /ap_dma@11000000 reg", "apdma %u window(s) with live state",
     "lk dma ctrl 0x%08x cfg 0x%08x", "MERLIN FORENSICS: victim
     b[%u..%u] %s", "apdma channel would not stop", "apdma flush did
     not clear", "apdma armed window outside the DT" + 0088 set
     ("MERLIN MSDC: dma ctrl", "DMA SPILL count", "dma spill=%llu",
     "inherited DMA would not stop") + 0086/0087 set.
  3. CI log: SKIPPING = only corrupt-0083 + dxb's
     TrustCache/iobuffermemd_monterey/skywalk_sonoma/
     syntax_checker_sonoma (×2 job logs); 85 patch files applied,
     full merlin chain 0082/0084/0086/0087/0088/0089 present ✓.
- Buildtree layout note: artifact zip = buildtree.tgz with top-level
  build/, fakeroot/, sdk-kernel-platform/, xnu/ — moved under src/ to
  match the 0088 convention → research/art-0089-buildtree/src/xnu is
  the NEXT PATCH BASE (make-0089 base needs updating when drafting
  0090).  Semi-probed: sweet_ufs.c 52,663 B with merlin_apdma_quiesce
  def @1030, snapshot @1128, init call @1733; zalloc.c lk dma line
  @3114, victim-b dump @3156, externs @3079 ✓ = post-0089 tree.
- Boot image: research/merlin-boot/shim-boot-merlin-msdc-0089-fv.img
  = 16,989,139 B, sha 989C711F85B019AC31E0E83403275B9F3658209DD9222F0
  A52FED2BA635FC77D; payload 16,612,544 B; builder verified shim slot
  + dtb byte-identical to E1; cmdline identical to boot #14 (0088) —
  msdc_readverify=1 kept.
- BOOT #15 DECODE TABLE (one photo):
  - "MERLIN MSDC: apdma win 0x%03x en …" lines = LK left VFF channels
    armed (0x980/0xa00 or 0xa80/0xb00 = uart0/uart1 RX+TX); "apdma N
    window(s) with live state, M armed window(s) quiesced" = cleanup
    ran (M>0 = hypothesis CONFIRMED territory).
  - "MERLIN FORENSICS: lk dma ctrl … cfg … sa … ca … len …" = LK MSDC0
    state at handoff (retroactive answer for every earlier boot).
  - "MERLIN FORENSICS: victim b[0..15] …" + "victim b[off..off+15] …"
    = all-0xff → wire-feed scribbler (APDMA or other wire); sparse
    pattern → software poker inside the sweet patch family.
  - ASIDE: readverify mismatches=0 / dma spill=0 must stay; SPILL>0
    would resurrect the MSDC overshoot class (0088 canary).
- VERDICT BRANCHES after #15: (a) armed window found + quiesced +
  boot survives LONGER (ideally past SpringBoard exec) + spill=0 →
  wire-feed confirmed → 0090 moves the quiesce into the SHIM (before
  xnu, kill it at handoff) + attack slide overflow next.  (b) no
  armed window / victim bytes sparse → software-poker hunt in sweet
  family (0083-class reintroduce? bisect 0035-0050?).  (c) unarmed +
  all-0xff victim bytes → wire feed NOT apdma-uart: extend scan to
  OTHER DMA engines (audit 4-cell reg nodes; e.g. MSDC1/i2c/spi).
- NEXT CONCRETE: user flashes shim-boot-merlin-msdc-0089-fv.img
  (fastboot flash boot) + boots + ONE final-screen photo → I decode
  and verdict.

## Agent handoff / active work (2026-10-25 LATEST-54: 0089 DRAFTED, VALIDATED byte-exact (t7/t8), committed BOTH repos LOCAL ONLY — APDMA/UART-DMA quiesce (stock stop sequence; full 4 KB /ap_dma scan prints any armed window; stops only the 4 DT windows) + LK MSDC0 state frozen into msdc_lk_* + forensics gains "lk dma ctrl=…" line + first-victim BYTE DUMPS (head 16 + at-off 16 → all-0xff = wire feed, sparse = software poke). BLOCKED: need push approval for ios-sweet 0089 CI)

- 0089 = `xnu/patches/0089-merlin-apdma-quiesce-victim-dump.patch`
  (9,122 B) generated by `research/tmp-msdc-split/make-0089.py` from
  research/art-0088-buildtree/src/xnu; git apply clean, both files
  byte-identical to expected (`-c core.autocrlf=false`); commits:
  ios-merlin 78739ec, ios-sweet c8d5aad (msdc-0079 @ [ahead 1] of
  deab554 — NOT pushed).
- FACT BASE (from research/merlin-boot/merlin.dtb FDT parse + upstream
  mtk-uart-apdma.c, torvalds master):
  - /ap_dma@11000000 (compat mediatek,ap_dma) reg is 4-cell
    (#address-cells=2): {0, 0x11000000, 0, 0x1000} → base = reg[1],
    size = reg[3] — differs from our injected 2-cell /merlin-msdc node
    (reg[0]/reg[1]); the generator guards size >= 4 words.
  - Four UART VFF windows declared: /dma-controller@11000980 reg =
    {0x11000980,0x80; 0x11000a00,0x80; 0x11000a80,0x80; 0x11000b00,
    0x80} (compat mediatek,mt6577-uart-dma) = 2 UARTs × RX/TX; also
    serial@11002000 (UART0) + serial@11003000 (UART1); msdc@11230000 =
    ours; msdc@11240000 (MSDC1) stock status okay — untouched (no
    card in slot; out of scope).
  - VFF regs per 0x80 window: INT_FLAG 0x00 INT_EN 0x04 EN 0x08 RST
    0x0c STOP 0x10 FLUSH 0x14 ADDR 0x1c LEN 0x24 THRE 0x28 WPT 0x2c
    RPT 0x30.  Stock terminate: FLUSH=1 → poll self-clear; STOP=1 →
    poll EN==0; STOP=0; INT_EN=0; INT_FLAG=0x3; warm RST=1; zero
    ADDR/LEN/THRE.
- 0089 CONTENT:
  - sweet_ufs.c: `uint32_t msdc_lk_ctrl, msdc_lk_cfg, msdc_lk_sa,
    msdc_lk_ca, msdc_lk_len;` NON-static after msdc_spill_count (0088
    lesson: static fails the link — assert in generator), snapshot
    assignments right after the 0085 inherited-state printf in
    take_over.
  - sweet_ufs.c: new `merlin_apdma_quiesce()` before take_over —
    SecureDTLookupEntry("/ap_dma@11000000") + reg (4-cell) +
    ml_io_map(reg[1], reg[3]); scan w in [0,0x1000) step 0x80 reading
    EN/INT_EN/ADDR/LEN/WPT/RPT; ANY nonzero window prints
    "MERLIN MSDC: apdma win 0x%03x en … int_en … addr … len … wpt …
    rpt …"; armed DT windows (0x980/a00/a80/b00) run the terminate
    sequence (FLUSH poll bounded 10 ms; STOP poll bounded
    MSDC_DMA_STOP_NS=2 s), anything else armed prints + is left
    alone (evidence preserved); summary line
    "apdma %u window(s) with live state, %u armed window(s) quiesced".
    Called in merlin_msdc_init after the canary fill, before the lock
    + msdc_take_over (runs per boot, before storage take-over).
  - zalloc.c: extern the msdc_lk_* + replay gains
    "MERLIN FORENSICS: lk dma ctrl 0x%08x cfg 0x%08x sa 0x%08x ca
    0x%08x len 0x%08x" (answers "was LK's MSDC engine in-flight at
    handoff?" from the same photo).
  - zalloc.c: FIRST victim only (console line budget): 2 lines
    "MERLIN FORENSICS: victim b[0..15] <hex>" + "victim b[off..off+15]
    <hex>" when off ≥ 16 and off+16 ≤ size (guards: size ≥ 16, off !=
    ~0u, hex[49], dumped-once assert).  All-0xff here + spill=0 →
    wire-feed class; sparse pattern → software poker inside the sweet
    family.
- GENERATOR ASSERTS (failure-ladder lessons baked in): lk vars
  non-static; declared before first assignment; quiesce defined before
  its call site; call before msdc_take_over; MSDC_DMA_STOP_NS define
  above the function; probes for all new print strings.
- BOOT #15 DECODE TABLE: "apdma win" line(s) = PROOF LK left VFF
  channels armed (+ which uart: 0x980/0xa00 = uart0 RX/TX(or
  swapped), 0xa80/0xb00 = uart1); "quiesced N" = stop ran clean.
  Branches: (a) armed window found + quiesced + boot survives longer
  AND spill stays 0 → hypothesis confirmed → 0090 = move the quiesce
  into the SHIM (before xnu) so the stream never writes post-handoff.
  (b) no armed window / victim dump sparse → software-poker hunt in
  the sweet patch family (next: bisect via 0083-class re-enables? use
  the byte dump first).  Independent: SpringBoard slide overflow may
  persist — separate 009x investigation.
- Golden-rule verify after CI: SHA256SUMS; binary string probes
  expect "MERLIN MSDC: apdma win", "apdma: no /ap_dma@11000000 reg",
  "apdma %u window(s) with live state", "lk dma ctrl 0x%08x",
  "MERLIN FORENSICS: victim b[%u..%u])" + all 0088 probes; CI-log
  grep "Skipping patch" = known-good set ONLY (+ corrupt-0083 — keep).
- Boot image (on artifact): python research\tmp-msdc-split\
  build-msdcroot0.py research\art-0089\kernel.development.sweet
  --cmdline "debug=0xc serial=3 cpus=1 keepsyms=1
  -enable_kprintf_spam -noprogress rd=msdcroot0
  unentitled_ios_sim_launch=1 launchd_unsecure_cache=1
  zlog1=kalloc.8192 zlog2=kalloc.4096 zlog3=kalloc.type.var.4096
  zlog4=kalloc.type.4096 zlog5=kalloc.16384 zlog6=kalloc.12288 -zc
  msdc_readverify=1" --out research\merlin-boot\
  shim-boot-merlin-msdc-0089-fv.img
- NEXT CONCRETE: ASK user → push msdc-0079 (c8d5aad) + CI dispatch →
  poll → verify → build 0089 image → user flash + ONE photo.

## Agent handoff / active work (2026-10-25 LATEST-53: BOOT #14 (0088) DECODED — VERDICT: dma spill=0 in BOTH panic rounds + readverify clean (round 1 at reads=175, round 2 at reads=520175) → MSDC engine class FULLY EXONERATED (inherited LK DMA + our own paths + overshoot all dead); scribbler STILL strikes (UAF on data.kalloc.16384, val=0xff…, elem ≈ 0xfffffe29a02b5800 in both rounds) + SpringBoard slide overflow persists → scribbler is NOT the MSDC → 0089 broaden hunt next)

- BOOT #14 = shim-boot-merlin-msdc-0088-fv.img, ONE photo decoded, TWO
  panic rounds visible (kernel panic → auto-reboot → second panic):
  ROUND 1: `MERLIN FORENSICS: msdc reads=175 readverify mismatches=0 dma
  SPILL=0` + victim block (data.kalloc.16384-ish, elem 0xfffffe29a02b5800,
  val=0xffffffffFFFFFFFF, off≈10366/16K-element tail area) → the first
  round died with barely any storage traffic — scribbler active VERY
  early (seconds after take-over), NOT correlated with read volume.
  ROUND 2 (full second boot): exec list progressed past earlier boots
  (peakpowermanagerd, runningboardd, tccd, bluetoothuserd,
  CloudPairing(?), OTRCrashCopier …), SpringBoard exec'd, then
  `vm_shared_region_slide_page() offset overflow: pageIndex=17564,
  start_off_set=8, slide amount=306499556` + CRASH SpringBoard[271] sig
  10/map/ns 2 code 0xa story; forensics: `msdc reads=520175 readverify
  mismatches=0 dma SPILL=0`; SAME victim element neighborhood
  (0xfffffe2…b58/b5b00, kalloc.16384) as round 1.
- VERDICT (decision tree, LATEST-52 logic branch 3): UAF persists with
  dma spill=0 AND full readverify cleanliness across 520,175 reads →
  the msdc controller/driver/DMA is OUT as the scribbler mechanism.
  (0088 hardening stays in the tree — it protects the only storage
  engine we control; its canary machinery now continuously certifies
  that in EVERY future boot's forensics line.)
- OBSERVATIONS to carry forward:
  - Victim VALUE = all-0xFF (whole-element fill, few deltas) both
    rounds — same class as boots 11/13.  All-FF is the natural content
    of an IDLE-HIGH WIRE read continuously (floating UART RX!) or of
    erased-NAND padding — i.e., a CONTINUOUS BYTE STREAM writer, not a
    one-shot poke.
  - Victims cluster in the SAME physmap neighborhood across rounds
    (0xfffffe2…a02b5_b00-ish) while also differing from boot 13's
    0xfffffe29a02be000 → layout shifted (0088 grew the kernel) but the
    TARGET PATTERN (one contiguous-ish region reused as heap) stands:
    fits a stale DMA descriptor buffer or LK-era boot-image buffer
    being recycled as kernel heap, with the scribbler streaming into
    whatever lands there.
  - The SECOND round ran a COMPLETE mount + deep userspace before
    panicking → the environment is boot-stable; the two remaining
    kill classes: (a) the scribbler (kalloc.16384 victims), (b) the
    SpringBoard shared-region slide overflow (pageIndex≈17.5k,
    amount≈306 MB || boot13's 0x46d14000) — possibly independent bug
    in the sweet pmap/slide path, possibly scribbler-corrupted VM
    metadata; DECIDE by re-testing after the scribbler is cut.
- 0089 PLAN (broadened hunt — draft next, validate locally, push only
  after user approval):
  1) Take-over snapshots: save the inherited MSDC0 DMA regs (ctrl/cfg/
     sa/sa_high/ca/len) into statics AND PRINT THEM inside the FORENSICS
     replay line (`dma spill=%llu lk ctrl=… cfg=… sa=… len=…`) — answers
     "was LK's engine in-flight at handoff?" from the same one photo,
     every boot, retroactively.
  2) Victim CONTENT dump: extend the forensics/zone-log printout with
     the first 16 bytes of the victim element + bytes around the
     reported off (panic-safe reads from the elem VA) — distinguishes
     "wire-fill 0xFF" from "sparse software poke" without guessing.
  3) APDMA hunt (hypothesis #1): stale UART/APDMA RX channel armed by
     LK streaming 0xFF (idle-high serial line) into RAM fits every
     fingerprint: continuous, deterministic-ish target, all-FF content,
     invisible to readverify, active within seconds of boot.  Design
     needs the mt6768 APDMA/UART MMIO bases — pull from research DTB
     dumps + LK tree facts before writing code; quiesce = disable all
     UART DMA channels + APDMA enables very early (shim or rootdev
     time), same pattern as the MSDC0 quiesce.
  4) Forensics-only alternative if APDMA facts are missing: (1)+(2)
     alone still discriminate wire-fill vs software-poke next boot.
- Do NOT reuse 0083 (malformed, deferred — its content is redundant
  with unentitled_ios_sim_launch=1 anyway). Patch numbering: next
  available = 0089+ (0085 = reserved gap).
- NEXT CONCRETE: draft make-0089.py against research/art-0088-buildtree/
  src (post-0088) for items 1+2 (+3 if DTB facts allow), validate
  byte-exact, commit, ASK before push/CI.

## Agent handoff / active work (2026-10-25 LATEST-52: 0088 v3 GREEN + FULLY VERIFIED — kernel + strings + log all confirmed; image packaged: shim-boot-merlin-msdc-0088-fv.img (sha 0b37878a…) — AWAITING user flash + ONE final-screen photo)

- CI: run 40202405879 SUCCESS @ head deab554 (0088 v3).
- ARTIFACTS: xnu-kernel id 12602746907 → research/art-0088/
  (kernel.development.sweet sha 2ac0153d62d400d4289c915a8dffe8fb708762bc1f4e5e
  cc775d15d22ea81c57, size 17,207,608 = +32 B vs 0087's 17,207,576);
  xnu-buildtree id 12602657154 → research/art-0088-buildtree/ (extracted to
  src/; sweet_ufs.c 47,951 B = +2,281 B of 0088) — THE NEXT PATCH BASE.
- VERIFICATION (golden rule, all green): SHA256SUMS match; probes ALL True:
  "MERLIN MSDC: dma ctrl", "DMA SPILL count", "dma spill=%llu",
  "MERLIN MSDC: cfg 0x", "inherited DMA would not stop"; CI log apply
  sequence: 0082 → 0083 (skip, known corrupt, deferred) → 0084 → 0086 →
  0087 → 0088 → dxb known skips (TrustCache/iobuffermemd_monterey/
  skywalk_sonoma/syntax_checker_sonoma).  NO unknown skips.
- IMAGE: python research\tmp-msdc-split\build-msdcroot0.py
  research\art-0088\kernel.development.sweet --cmdline "debug=0xc serial=3
  cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=msdcroot0
  unentitled_ios_sim_launch=1 launchd_unsecure_cache=1 zlog1=kalloc.8192
  zlog2=kalloc.4096 zlog3=kalloc.type.var.4096 zlog4=kalloc.type.4096
  zlog5=kalloc.16384 zlog6=kalloc.12288 -zc msdc_readverify=1"
  --out research\merlin-boot\shim-boot-merlin-msdc-0088-fv.img
  → 16,989,139 B, sha 0b37878a52a5fba518c30ca89a4a521702cd39a728a345840c94df
  82b7d3fb9c; verify pass: SWEETXNU payload 16,612,400 B; shim + dtb
  byte-identical to the standard E1 image; cmdline pinned verbatim.
- AWAITING: user flashes boot_a/boot slot AS USUAL (persistent flash flow,
  NOT fastboot boot) + boots + sends ONE final-screen photo.
- DECODE GUIDE (any agent): early lines should now include the NEW
  take-over state forensics: `MERLIN MSDC: cfg 0x… ps 0x… sts 0x…` then
  `MERLIN MSDC: dma ctrl 0x… cfg 0x… sa 0x… sa_hi 0x… ca 0x… len 0x… fis
  fifo 0x…` — THAT IS WHAT LK LEFT BEHIND (inherited-state evidence!).
  Possibly `MERLIN MSDC: inherited DMA would not stop` (rage-quarantine of
  a stuck engine) and/or early `MERLIN MSDC: DMA SPILL count %llu words
  bad %u first %u (off %u) last %u` prints (first occurrence + every
  1000th; count continues silently).  Settled tail (0087 hook guarantees):
  zone-log headers, victim dumps, `Original panic string:` …
  `handshake structure not initialized` … panic.apple.com footer + spin;
  the round(s) end with `MERLIN FORENSICS: msdc reads=N readverify
  mismatches=N last lba=N dma spill=N`.
- VERDICT LOGIC (decide from photo(s)):
  1) dma spill=0 AND no `element modified after free` AND no
     malformed-load/SIGBUS/slide death reached = inherited-state class
     DEAD → start the multi-boot success streak (criteria LATEST-47).
  2) dma spill>0 (any) = a DMA overshoot is LIVE: its extent (words bad/
     first-off) = the register-map deep dive target; compare with whether
     the UAF alarm still fires.
  3) UAF alarm persists with dma spill=0 = the scribbler is NOT the msdc
     engine → broaden hunt (APDMA/other controller) as 0089+.
  4) boot simply lives longer/deeper than all prior boots = success
     signal regardless of label.
- CLEANUP NOTE: previous art dirs: art-0086-buildtree (pre-0087 base),
  art-0087 + art-0087-buildtree (post-0087 base, superseded by art-0088),
  art-0085-skipped (never use).  Kernel-build iteration now expects:
  patch (make-00NN.py) → 0089+ numbering rule → CI → verify → image.

## Agent handoff / active work (2026-10-25 LATEST-51: 0088 attempt 2 failed at LINK (not compile!): "_msdc_spill_count undefined for arm64" — my counter decl was `static` (file-local) while zalloc.o's replay externs it → v3 makes it non-static (0086-style visibility), re-validated, pushing attempt 3)

- ATTEMPT 2 = run 40201604920 (head d3aea9a) → compile PASSED clean (all
  .o built; no compile errors, only style warnings), final kernel LINK
  failed: `Undefined symbols for architecture arm64: "_msdc_spill_count",
  referenced from: _merlin_uaf_replay in zalloc.o`.  Attempt-1 lesson
  (decl BELOW first use) had been fixed, but the moved decl was `static`
  = file-local; zalloc.c's `extern uint64_t msdc_spill_count;` never
  resolves against a static.  Each TU compiles alone; only the linker
  sees the mismatch.  (Per-TU compile vs whole-program-link lesson.)
- FIX (v3, this commit): counter declared NON-STATIC after the msdc_gpt
  static — exact visibility pattern the 0086 patch already established
  for msdc_rv_mismatches/msdc_rv_last_lba/msdc_strategy_reads (all
  non-static BECAUSE zalloc.o externs them).  Generator now also asserts
  the decl is NOT `static`, plus decl-before-first-use (attempt-1 assert).
  make-0085.py re-generated + byte-exact validated → 0088 v3 (7,229 B).
- FAILURE LADDER STATUS: skip (0085) → renumber ok → compile error (v1)
  → link error (v2) → v3 = both fixed in one place, one identifier.
  Every new symbol that crosses TU boundaries MUST be non-static; every
  generator change gets a matching assertion so the failure class can't
  repeat silently.
- LOG SANITY THIS RUN: 0088/0086/0087 all APPLIED (no skip lines);
  skips = known dxb set (TrustCache/iobuffermemd_monterey/skywalk_sonoma/
  syntax_checker_sonoma) + corrupt-0083 (deferred, see LATEST-50).
- NEXT: push v3 → dispatch → poll → on GREEN: SHA + string probes
  ("MERLIN MSDC: dma ctrl", "DMA SPILL count", "dma spill=%llu") +
  log-grep, then shim-boot-merlin-msdc-0088-fv.img (cmdline unchanged,
  msdc_readverify=1 kept) → flash + ONE photo → decode: the settled tail
  `MERLIN FORENSICS: msdc reads=N readverify mismatches=N last lba=N dma
  spill=N` + early inherited-DMA state line at take-over.  dma spill=0 +
  no UAF/alarm = inherited-state class dead (start streak); spill>0 =
  live overshoot bug (register-map deep dive next).  v1 shell commands:
  `python research\tmp-msdc-split\poll-0086-ci.py <head-sha>`.

## Agent handoff / active work (2026-10-25 LATEST-50: 0088 build attempt 1 FAILED at COMPILE (not apply!) — undedclared msdc_spill_count: my declaration sat BELOW its first use; FIXED + re-validated + re-pushing; SIDE-DISCOVERY: 0083-launchd-platform patch is malformed and has likely NEVER applied — deferred, do not touch exec behavior mid-scribbler-hunt)

- ATTEMPT 1 = run 40200698093 (head d1d4071) → FAILURE, first time a merlin
  patch actually compiled in the build.  Errors:
  `sweet_ufs.c:1168..1172: error: use of undeclared identifier
  'msdc_spill_count'` (4x) → `make[7]: *** [sweet_ufs.o] Error 1`.
  CAUSE: I declared the spill counter in the readverify var block, but that
  block sits AFTER msdc_read_sector_once in file order; the canary check in
  the read tail uses it BEFORE its declaration.  LESSON: git-apply byte-exact
  validation proves PATCH APPLIES, NOT that C links — declaration ordering is
  invisible until a real compile.  Fix also asserts decl-before-use in the
  generator now.
- FIX (this commit): `static uint64_t msdc_spill_count;` moved directly after
  the `msdc_gpt` static (~c.936, above all msdc functions); generator asserts
  decl precedes first use; make-0085.py re-generated the patch (7,199 B) and
  re-validated byte-exact (t7 apply == t8 expected) → 0088 v2.
- WHAT THE FAILURE PROVED (good news): 0088 APPLIES (renumber correct, the
  skip warning this run was only 0083ำ + dxb's own base patches); every other
  identifier I added (MSDC_FIFOCS, MSDC_DMA_CFG_STOP, MSDC_DMA_CFG_STS,
  MSDC_DMA_LEN, SDC_BLK_NUM, deadline_in) compiled fine — H1/H2/H3/H5/H7
  content is C-correct except the counter placement.  0086/0087 unaffected.
- SIDE-DISCOVERY (this run's log also a first full look at ALL skips):
  `Skipping patch 0083-merlin-launchd-platform.patch ... error: corrupt patch
  at line 23` — the 0083 diff hunk counts lines that aren't there (header
  claims more than exists; file ends mid-hunk without trailing context) ⇒
  0083 has likely NEVER applied in ANY CI build.  Its purpose
  (no_sandbox_entitled=TRUE at process_signature for SWEET boards) is
  REDUNDANT with our cmdline's `unentitled_ios_sim_launch=1` — history boots
  reached launchd/dyld/SpringBoard without it.  DECISION: DEFER — fix 0083
  as a fresh 009x patch AFTER the 0088 verdict; do not change exec-signature
  behavior mid-hunt.
- LONG-STANDING dxb baseline skips (every run, blacktop's own patches, files
  already exist in-tree — harmless): TrustCache.patch, iobuffermemd_monterey,
  skywalk_sonoma, syntax_checker_sonoma.  Known-good skip set is now:
  [dxb×4 + possibly 0083 until fixed] — any OTHER "Skipping" line = RED FLAG.
- NEXT: push 0088 v2 → dispatch → poll → verify (SHA + probes "MERLIN MSDC:
  dma ctrl" / "DMA SPILL count" / "dma spill=%llu" + log greps: 0088/0086/
  0087 must APPLY, skips = known set only) → build shim-boot-merlin-msdc-0088
  -fv.img (cmdline unchanged; keep msdc_readverify=1) → flash + ONE photo →
  decode per LATEST-49/48 (dma spill=0 + no UAF = class dead; spill = live
  overshoot; inherited-DMA state line = what LK left behind).

## Agent handoff / active work (2026-10-25 LATEST-49: ROOT CAUSE — the CI SILENTLY SKIPPED the 0085 patch (patch-fail ≠ build-fail!) → renumbered 0085 → 0088 in both repos, re-pushing; GOLDEN RULE: every CI build must be verified by SHA + BINARY STRING PROBES + CI-log grep "Skipping patch" — a "success" artifact is not proof a patch applied)

- ROOT CAUSE (run 40199390379 build log, excerpt saved to
  research/tmp-msdc-split/log-patch-lines.txt line 2):
  `Skipping patch .../dxb/patches/0085-merlin-msdc-dma-quiesce-spill-canary.patch
  (already upstream, previously applied, or malformed): error: patch failed:
  bsd/dev/sweet_ufs.c:1125` — then 0086 + 0087 applied, build "succeeded",
  kernel shipped WITHOUT 0085.  The dxb tool applies dxb/patches/*.patch in
  NUMERIC-SORT order and a patch that fails `git apply` is skipped with a
  warning; the build still exits green.
- WHY 0085 failed: it applied BEFORE 0086/0087 in that order, but its hunks
  were generated against the POST-0087 tree (0086 rewrote the readverify var
  block at sweet_ufs.c:1125-1129 that 0085 anchors on, and 0085's zalloc
  hunks anchor on the post-0086 forensics block) → context mismatch → whole
  patch rejected (git apply is atomic, all-or-nothing).
- RESOLVED MYSTERY: art-0085 kernel string-probe failure (no "MERLIN MSDC:
  dma ctrl" / "DMA SPILL count" / "dma spill=%llu") = patch skipped, NOT a
  generator bug.  make-0085.py validation was byte-exact — TRUSTED.
- FIX (this commit): renumber the patch to 0088-merlin-msdc-dma-quiesce-
  spill-canary.patch in BOTH repos (ios-merlin rename + ios-sweet d1d4071);
  content UNCHANGED (contexts already correct for post-0087).  NUMBERING
  RULE now explicit: a merlin patch that builds on content from patch N
  must sort AFTER N (dxb order is a global numeric sort including blacktop's
  own dxb/patches); 0085 = RESERVED GAP, never reused.  Next patches 0089+.
- VERIFICATION GOLDEN RULE for EVERY future CI kernel: (1) SHA256SUMS ok,
  (2) grep the kernel for the NEW patch's print strings BEFORE flashing,
  (3) grep the CI build log for "Skipping patch" — must be ZERO for
  merlin-*.patch.  Steps 2+3 are what this skipped build evaded.
- REPRO HYG: same-ref kernels are NOT byte-reproducible — vs art-0087, the
  skipped-build kernel differs in ~70 x 64 KiB chunks AND carries an exact
  +16,384 B tail of extra link-table strings ("switch__flow_expire" etc.),
  with 0085 never applied.  CONCLUSION: kernel SIZE deltas are NOT proof of
  patch application; only STRING PROBES + logs count.  (+16,384 anomaly
  closed as build reproducibility noise — not msdc_gpt-related.)
- research/art-0085 renamed → research/art-0085-skipped (60,023,182 B,
  sha 6e0e13bd…, kernel = 0084+0086+0087 build; do NOT use or image from it).
- WORKSPACE HYGIENE: ios-merlin has unrelated in-progress uncommitted work
  (shim/ ramfb+fbcon-1x QEMU banking, tools/fbcon-* files, image.png) — NOT
  part of the msdc work, NOT committed by this handoff, leave alone.
- NEXT: push msdc-0079 (d1d4071) + workflow_dispatch ref msdc-0079 →
  background poll via `python research\tmp-msdc-split\poll-0086-ci.py
  <head-sha>` → VERIFY (golden rule; "MERLIN MSDC: dma ctrl",
  "DMA SPILL count", "dma spill=%llu" must ALL be present in the binary)
  → build shim-boot-merlin-msdc-0088-fv.img (SAME cmdline incl.
  msdc_readverify=1, verbatim from previous boots) → flash + ONE photo →
  decode per LATEST-48 guide: dma state line at take-over (inherited LK
  forensics), early "DMA SPILL" prints if overshoot fires, settled tail
  `MERLIN FORENSICS: msdc reads=N readverify mismatches=N last lba=N dma
  spill=N`.  dma spill=0 + no UAF/slide deaths = inherited-state class
  DEAD (start success streak); spill mid-boot = live overshoot bug (deep
  register-map dive next).

## Agent handoff / active work (2026-10-25 LATEST-48: 0085 MSDC DMA QUIESCE + SPILL CANARY DRAFTED + VALIDATED byte-exact on the CI post-0087 sources (ios-merlin 705037a + ios-sweet msdc-0079 ce8c0f3, NOT pushed — awaits approval); key driver-audit discovery: take_over never quiesced the DMA engine and the read/write paths used READ-MODIFY-WRITE on DMA_CTRL = stale bits survive every START, and readverify's 512B compare is blind to any overshoot BEHIND the bounce target — matching every victim fingerprint)

- DRIVER AUDIT (research/art-0087-buildtree/src/xnu/bsd/dev/sweet_ufs.c,
  the CI's own post-0087 file, full msdc region read):
  - merlin_msdc_rootdev -> merlin_msdc_init (DT /merlin-msdc reg mmap,
    boot-args msdcroot= + msdc_readverify, kmem_alloc_contig 64 KiB
    KMA_PERMANENT bounce -> msdc_take_over -> GPT scan -> devsw).
  - TAKE-OVER GAP: msdc_take_over prints cfg/ps/sts, fixes MODE/CKPDN/
    PIO, INTEN=0 + W1C, waits SDC idle — but NEVER checks MSDC_DMA_CFG
    _STS (engine running?) and NEVER stops/zeros the DMA.  LK loaded
    our boot image through this same engine moments earlier.
  - PER-TRANSFER GAP: read/write paths do READ-MODIFY-WRITE on
    MSDC_DMA_CTRL clearing only START|STOP|MODE|BRUSTSZ|LASTBUF — any
    other inherited bit (e.g. leftover XFERSZ anywhere) survives EVERY
    START; DMA_SA_HIGH is only masked (bits 63:32 kept), never zeroed.
  - BLIND SPOT: readverify double-read compares ONLY the first 512 B at
    mo.dma — a DMA overshooting its requested length spills BEHIND the
    target into other RAM forever undetected; deterministic victims
    (same elem+off across boots), eMMC-stream-like victim contents,
    clean readverify = ALL consistent with overshoot class.
- 0085 DESIGN (validated, make-0085.py, patch 7,210 B):
  1) take_over: print inherited dma ctrl/cfg/sa/sa_hi/ca/len/fifo, then
     STOP a running DMA (bounded 2 s), then ZERO ctrl/sa/sa_high/ca/len
     + SDC_BLK_NUM=1 BEFORE the existing flow.
  2) read (CMD17) + write (CMD24) paths: DMA_CTRL written ABSOLUTELY
     (LASTBUF | burst 6<<12 | START — no rmw, nothing inherited can
     survive); DMA_SA_HIGH written 0 outright; `uint32_t ctrl` decl
     kept for the post-transfer STOP.
  3) SPILL CANARY: on init fill words 64..8191 (offsets 512..64 KiB-8)
     of the bounce with magic 0x4d45524c494e2041 ("MERLIN A"); after
     EVERY successful data phase check words 64/256/2048 (+512 B/+2 KiB/
     +16 KiB); any mismatch -> full 64 KiB scan -> extent printed
     ("MERLIN MSDC: DMA SPILL count %llu words bad %u first %u (off %u)
     last %u", first + every 1000th) and msdc_spill_count++.
  4) forensics replay line (zalloc.c 0086 block) extended:
     `MERLIN FORENSICS: msdc reads=%lu readverify mismatches=%u last
     lba=%llu dma spill=%llu` -> the canary verdict rides EVERY panic
     screen photo.
  INTERPRETATION GUIDE for the next boots: dma spill=0 + panic stops =
  the inherited-state class is dead (0085 fixed); dma spill>0 (moments
  BEFORE hardening could matter — first spill may fire on the very
  first CMD17 runs pre-quiesce ONLY if it was ongoing at take-over;
  later spills after full re-arm = live DEFECT in our own paths —
  mind: our OWN transactions now use absolute ctrl so a spill seen
  MID-BOOT = real overshoot bug worth deep-diving register map).
- NEXT: user approval -> push msdc-0079 (ce8c0f3) -> workflow_dispatch
  -> fetch/cross-check/SHA256SUMS (same pipeline) -> build
  shim-boot-merlin-msdc-0085-fv.img (SAME cmdline incl.
  msdc_readverify=1) -> flash -> ONE photo: settled screen shows
  `MERLIN MSDC: cfg/dma-state lines` early + `DMA SPILL` prints + the
  FORENSICS tail with dma spill=<N>.  Success criteria unchanged
  (LATEST-47): no `element modified after free` + no
  malformed-load/SIGBUS/slide crashes across a several-boot streak.
- poll script: research/tmp-msdc-split/poll-0086-ci.py <head-sha>.

## Agent handoff / active work (2026-10-25 LATEST-47: BOOT #13 (0087) = FORENSICS TAIL HOOK WORKS — VERDICT DELIVERED: readverify reads ≈127k/527k, MISMATCHES=0 across the board, victims still corrupting => READ PATH BLOCK-CLEAN, SCRIBBLER CONFIRMED => 0085 MSDC INIT HARDENING is next per the pre-agreed tree)

- 0087 CONFIRMED WORKING: the settled boot-13 screen shows two complete
  panic tails (looks like the phone panicked, rebooted, and panicked
  again before the photo — two boots share the console ring; counters
  reset per boot), each ending: dumps -> `Original panic string:`
  -> `handshake structure not initialized` -> **`MERLIN FORENSICS:`
  lines** -> `Please go to https://panic.apple.com...`.  The one-photo
  workflow is now fully effective (milestone: boot 12's photo story
  resolved).
- **THE VERDICT NUMBERS** (both tails): `MERLIN FORENSICS: msdc reads=
  127255(? OCR ~127k) readverify mismatches=0 last lba=0` and
  `reads=527255(? OCR ~527k) readverify mismatches=0 last lba=0` —
  every sector read through the readverify path was double-read and
  compared with **ZERO mismatches** across both boots.  `last lba=0`
  is consistent (never set because nothing mismatched).  => THE MSDC
  READ ENGINE READS CLEAN AT BLOCK LEVEL.
- Victims despite clean reads: `MERLIN FORENSICS: victim data.kalloc.
  8192 size=8192 off=2112 val=0x8ffff9fe9e02be00…(ff-poison + few
  deltas) elem=0xfffffe29a02be000` and boot-B tail additionally
  `panic(cpu 0 caller 0xfffffe007ab8a8c?): [data.kalloc.8192]: element
  modified after free (off:2112, val:0x…, sz:8192, ptr:0xfffffe29a02be000)`
  + zone-log header + native dump clumps (2112..2140 ff-heavy; boot-A
  clumps ~3664-3956).  NOTE: the SAME elem address 0xfffffe29a02be000
  and SAME off 2112 appear in BOTH tails (OCR ±) = the hit looks
  DETERMINISTIC (same allocation, same offset every boot) — scribbler
  with a fixed target/stride signature.
- Boot B story (deeper than A): exec nabd?/contextoresentored/healthd/
  mediaremoted/softwareupdated/peakpowermanagerd -> cs_invalid_page
  (0x2247f0c8??): p=27[SpringBoard] (remove VKILL) -> **vm_shared_
  region_slide_page() offset overflow: pageIndex=184, start?_offset=0,
  slide_amount=1188811152** (insane slide parameters = corrupted VM/
  dyld-side metadata) -> CRASH SpringBoard[271] sig 10 (SIGBUS) code
  0x10000000a sub 0x25866e0e0 slide 0x46d14000, pc 0x1beb32ccdb…, bt
  repeated 0x1beb37cc78…, map (far inside) … prot 1/1 tag 32, reason
  ns 2 code 0xa (none) = SpringBoard killed in the shared-cache slide
  machinery — same file/VM corruption class as boots 11/12.
- DECISION (pre-agreed tree): reads>0 + mismatches=0 + victims =>
  scribbler CONFIRMED at the level we can test; the read path is not
  (provably) serving wrong bytes.  NEXT = **0085 MSDC init hardening**
  (number reserved): at driver attach — controller reset + clear
  SA/CFG/CTRL/INT + quiesce/stop any active DMA so whatever the
  bootloader (LK) left armed gets neutralized.  Leading candidate
  (observation vs guess distinction): an ongoing small-burst writer,
  plausibly a wrong-target DMA tied to the driver's OWN WRITE path
  (journal/remount metadata writes spraying eMMC-bound file bytes into
  RAM — reads stay clean by construction); stale-LK post-handoff DMA
  would rather strike once/early, and hits keep recurring minutes into
  boot across boots — record as working hypothesis, not fact.
- HOW 0085 GETS BUILT: generate from the CI PATCH TREE like 0087
  (research/art-0087-buildtree/src/xnu = full post-0087 sources —
  artifact xnu-buildtree id 12598721923, fetched but NOT yet extracted;
  bsd/dev/sweet_ufs.c contains the 0084-hardened driver; validate
  byte-exact t-scratch apply).  After 0085 validates: user push+CI
  approval, same pipeline, same cmdline image (msdc_readverify=1
  STAYS — mismatches=0 is still evidence we need to keep collecting
  until the panic storm stops happening altogether = success signal).
  SUCCESS CRITERION for 0085: boots reach userspace WITHOUT any
  `element modified after free` alarm for a several-boot streak (and
  SpringBoard stops dying with malformed-load/SIGBUS/slide stories).
- poll script research/tmp-msdc-split/poll-0086-ci.py now takes the
  head sha as argv[1].

## Agent handoff / active work (2026-10-25 LATEST-45 ADDENDUM: 0087 CI DONE (run 40192191643, kernel a3c3d3c9..., +104 B = tail hook linked) and shim-boot-merlin-msdc-0087-fv.img BUILT + SELF-VERIFIED (b284a9ab...); user to flash THIS image, boots, ONE photo -> final screen must end with MERLIN FORENSICS verdict + victim ring before the URL footer)

- 0087 BUILT: CI run **40192191643** (head 427eaa5, dispatch 12:13:48Z,
  ~13 min) SUCCESS; fetch artifact xnu-kernel id **12598697010** into
  research/art-0087/ (flat; SHA256SUMS MATCHES computed
  a3c3c3...  = a3c3d3c96dfb8de098953f8214d5a34d0a1c1869c2e213cdc53fb740c6cf2597;
  kernel 17,207,576 B = 0086 +104 bytes = un-static + tail hook ✓;
  sibling buildtree id 12598721923 saved to research/art-0087-buildtree/).
- BOOT IMAGE: research/merlin-boot/shim-boot-merlin-msdc-0087-fv.img
  (16,989,139 B, sha256
  b284a9abf80764c5627945b484905df0d96a3f8d067680e67721083aa9e270a3);
  same cmdline (zlog1..6 + -zc msdc_readverify=1); shim slot + dtb
  byte-identical to E1 base (self-verify ok).
- USER ACTION: flash shim-boot-merlin-msdc-0087-fv.img (normal flow),
  boot, ONE photo of the final screen.  EXPECTED TAIL ORDER (0087
  guarantee): `... dumps ...` / `Original panic string:` + full text /
  `handshake structure not initialized` / `MERLIN FORENSICS: msdc
  reads=N readverify mismatches=N last lba=N` / `MERLIN FORENSICS:
  victim <zone+heap> size= off= val=0x%016llx elem=%p` (up to 4) /
  `Please go to https://panic.apple.com ...` (LAST line).  Verdicts:
  mismatches>0 = MSDC read path guilty (0085 read-engine next);
  reads>0 mismatches=0 = RAM scribbler (0085 = MSDC controller reset +
  clear SA/CFG/CTRL/INT + DMA stop at attach, number reserved);
  reads=0 = panic pre-mount.  If STILL no MERLIN FORENSICS lines on a
  settled screen => the tail hook did not run => investigate (first
  suspect: inline-function/section placement of the hook in debug.c).
- poll script research/tmp-msdc-split/poll-0086-ci.py now takes the
  head sha as argv[1].

## Agent handoff / active work (2026-10-25 LATEST-45: BOOT #12 SETTLED TAIL DECODED = xnu's FIXED panic TAIL (dumps -> "Original panic string:" -> "handshake structure not initialized" (harmless, no Apple hw debugger on merlin, out_shmem.c:499) -> panic.apple.com footer (debug.c:1454) -> spin forever, NOTHING prints after) => 0086 forensics scrolled off; 0087 TAIL-REPLAY PATCH WRITTEN + VALIDATED against the CI's own post-0086 build tree; awaits push approval)

- BOOT #12 (photo 2026-10-25, after flashing
  shim-boot-merlin-msdc-0086-fv.img - image identity not visible on the
  screen, assumed): the console SETTLED at the standard xnu panic tail:
  `[ UAF element dumps (XNU-native `%5d: 0x%016lx`, zalloc.c:3086, ff-
  poison-heavy words, offsets ~384-448 / 1448-1720 / 3336-3394 per
  blurry OCR) ] -> "handshake structure not initialized" -> "Please go
  to https://panic.apple.com to report this panic"`.  DECODE: that is
  NOT a new panic class - the tail = debug.c:1430 (Original panic
  string: re-print) + 1440 panic_spin_shmcon() -> out_shmem.c:499
  "handshake structure not initialized" (NORMAL on merlin: no Apple
  hardware shared-memory debugger; when present it would instead print
  the URL + WAIT forever) + debug.c:1454 URL footer + panic_spin_forever.
  IMPORTANT IMPLICATION: NOTHING PRINTS AFTER THE URL - a settled screen
  is a TAIL WINDOW; everything printed before the last dump block
  (incl. 0086's FORENSICS + zone-log + the actual panic text) scrolled
  off => this boot's readverify verdict = LOST (photo too blurry to
  extract the dump word values reliably).
- 0087 FIX (research/tmp-msdc-split/make-0087.py -> xnu/patches/
  0087-merlin-forensics-tail-replay.patch): (a) zalloc.c un-statics
  merlin_uaf_replay (0086's replay printer), (b) debug.c calls it right
  BEFORE the URL footer on the panic tail => the settled screen ends
  with: `...dumps`/`Original panic string: <full text>`/`handshake
  structure not initialized`/`MERLIN FORENSICS: msdc reads=... lines
  (verdict + up to 4 victims)`/`Please go to ...` = complete one-photo
  decode, immune to scroll.  Validated BYTE-EXACT against THE CI'S OWN
  post-0086 files (from xnu-kernel's sibling artifact xnu-buildtree id
  12598525203 -> nested buildtree.tgz extracted under research/
  art-0086-buildtree/src/xnu; this is the superior patch-generation
  base vs synthetic trees - REUSE for all future patches).  GOTCHA
  recorded while validating: build the t5 scratch from ONLY the files
  being patched (pruning a copied buildtree deleted needed dirs).
  Local commits: ios-merlin + ios-sweet msdc-0079 (patch file) - NOT
  pushed yet; NEEDS USER PUSH+CI APPROVAL (the "start the 0086 CI
  build" approval was for 0086 specifically).
- AFTER 0087 approval: push msdc-0079, workflow_dispatch, fetch
  (cross-check run id + head sha), verify SHA256SUMS, build
  shim-boot-merlin-msdc-0087-fv.img with the SAME cmdline (zlog1..6 +
  msdc_readverify=1).  User flashes THAT image (no point re-flashing
  0086) and sends ONE photo.
- Decoding the 0087 final screen: forensics lines sit between the
  "handshake structure not initialized" line and the URL footer;
  mismatches>0 => driver read path guilty; reads>0 mismatches=0 =>
  scribbler (0085 next: MSDC controller reset + clear
  SA/CFG/CTRL/INT + DMA stop at attach; number still reserved);
  reads=0 => panic pre-mount.

## Agent handoff / active work (2026-10-25 LATEST-44: BOOT #11 DECODED = DEEPEST BOOT EVER, corruption CONFIRMED striking FILE CONTENT (dyld malformed load command #3 of 35 on a just-read SpringBoard[271]) + kalloc.16384 victim full of file-like ASCII; msdc-0079 1a6efd8 PUSHED (user-approved) + CI run 40190497473 DISPATCHED for the 0086 forensics-replay kernel)

- PUSH + CI (user-approved): ios-sweet fork msdc-0079 `00ce338..1a6efd8`
  pushed 2026-10-25; workflow_dispatch POST accepted (HTTP 204); run
  **40190497473**, head_sha 1a6efd8479cf85c58e87bc1d7ccc1edb648f666b,
  status in_progress. ARTIFACT CROSS-CHECK per LATEST-36: use the
  artifact listing of run 40190497473 ONLY (never the newest-looking
  id from /actions/artifacts). Fetch with
  `python tools/fetch-kernel-artifact.py get Gytis283123/ios-sweet <id>
  research/art-0086`, then verify SHA256SUMS before anything else.

- BOOT #11 (photo 2026-10-25; same flashed shim-boot-msdc-0084-rv-zlog5
  image, method A; photo much sharper than previous ones) = the deepest
  boot in the whole log:
  - `exec` lines for MANY userspace daemons (accessoryupdaterd,
    bluetoothd…, a *powermanagerd, wcd, healthd, mediaremoted, misd…,
    atc…, pcpd — OCR best-effort; several never seen before), then
    SpringBoard[271] launched.
  - `cs_invalid_page(0x2b1f98000): p=27[SpringBoard] final status
    0x22008000, allowing (remove VKILL) page` - SWEET CS allowance.
  - `dyld[271]: malformed load command #3 of 35 at 0x2b1f9808 with
    mh=0x2b1af800, size (0x110E9C6) not multiple of 4` then CRASH sig 6,
    sub 0x8, slide 0x42be8000, pc 0x1b5ef75cee4, bt printed; SWEET
    string-scan of SpringBoard heap: `0 KiB scanned, 0 strings` (died
    in dyld, before heap populated); `reason ns 6 code 0x9` =
    OS_REASON_DYLD => SpringBoard murdered WHILE DYLD PARSED ITS
    JUST-READ BINARY: bytes in the load-command page corrupted in RAM.
    iOS binaries have exactly ~35 load commands, so this is the REAL
    binary content with a few bytes scribbled.
  - `MERLIN zone-log: element history (data.kalloc.16384):` header
    PRINTED (first time visible for the 16384 family) => 0084 trap +
    zlog5 tracking confirmed live.  NO `zone-log #N:` lines follow =>
    zero matching btlog entries for that element (allocated before
    log start or entries evicted) - info, not a trap failure.
  - `panic(cpu 0 caller 0xfffffe00...7ab8a50): [data.kalloc.16384]:
    element modified after free (off:9408, val:0x000a64252b3a776f,
    sz:16384, ptr:0xffffffe2e4522e1c00...)`; victim dump words decode
    as ASCII FILE-CONTENT-LIKE fragments (LE: `aw_data,` from
    0x2c617461645f7761; `VFw_0w_r`-style mixed text/binary words) -
    an eMMC-stream-like fill, NOT heap metadata or zeros.  A second
    interleaved dump block starts near off:10560 (same binary+ASCII
    mix).  Bottom of screen: `Original panic string:` = ANOTHER
    16384-family panic (storm again, cut at photo edge).
  - CALLER DIGITS RESOLVED (corrects the LATEST-41/42 zone_nofail
    attribution): printed callers 0x...7ab8a50 recur IDENTICALLY in
    boots 10+11 and 0xab8a50 is in the 0084 symbol table EXACTLY the
    first symbol AFTER _zalloc_uaf_panic (0xab8950).  panic() records
    the RETURN address; a (panic) call as the function's final
    instruction returns to 0xab8a50 = next symbol start => the
    recorded caller IS zalloc_uaf_panic itself.  Text attribution
    (UAF, tracked zone) always matches too.  Consider caller digits
    resolved as OUR function; symbolication no longer needed for them.
- INTERPRETATION AFTER BOOT #11: the corrupter strikes FILE content
  (dyld/dyld-parsed binary pages) AND freed heap elements with the
  SAME file-like byte patterns.  Both mechanisms still alive:
  (i) MSDC read path serves corrupted sectors (readverify would raise
  mismatches), (ii) a RAM scribbler (stale-LK DMA theory) corrupting
  pages after a correct read.  DECIDER = the 0086 replay line
  `MERLIN FORENSICS: msdc reads=%lu readverify mismatches=%u last
  lba=%llu` now building on CI: mismatches>0 => driver read path
  guilty => 0085 read-engine investigation; reads>0, mismatches=0,
  victims persist => scribbler => 0085 MSDC init hardening (reserved:
  controller reset + clear SA/CFG/CTRL/INT + DMA stop at attach).
- NEXT (after CI): 1) fetch + SHA256SUMS-verify artifact into
  research/art-0086/; 2) build the boot image:
  `python research\tmp-msdc-split\build-msdcroot0.py
  research\art-0086\kernel.development.sweet --cmdline "debug=0xc
  serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress
  rd=msdcroot0 unentitled_ios_sim_launch=1 launchd_unsecure_cache=1
  zlog1=kalloc.8192 zlog2=kalloc.4096 zlog3=kalloc.type.var.4096
  zlog4=kalloc.type.4096 zlog5=kalloc.16384 zlog6=kalloc.12288 -zc
  msdc_readverify=1" --out research\merlin-boot\shim-boot-merlin-msdc-0086-fv.img`
  3) user flash()es it (their normal flow), boots, ONE final-screen
  photo; 4) decode the FORENSICS + victim replay from that photo.

### LATEST-44 ADDENDUM (same day, ~15 min later): CI DONE, 0086 IMAGE BUILT

- CI run 40190497473 COMPLETED SUCCESS (~15 min); artifacts cross-checked
  against run id + head sha: xnu-kernel id 12596829718 (60,016,579 B,
  fresh; sibling id 12598525203 xnu-buildtree unused). Fetched into
  research/art-0086/ (flat extract; kernel.development.sweet 17,207,472 B).
- VERIFICATION: SHA256SUMS matches recomputed hash -
  kernel.sha256 = a34a07084ca8953469ee8635f859d5694bfbae3f6dd4c0bbc0c5e8a8da724ced.
  Binary.STRING probes all present: `MERLIN FORENSICS: msdc reads`,
  `MERLIN FORENSICS: victim`, `MERLIN zone-log: element history` =>
  0086 + 0084 both linked.
- BOOT IMAGE BUILT + SELF-VERIFIED:
  research/merlin-boot/shim-boot-merlin-msdc-0086-fv.img
  (16,989,139 B, sha256 33daf13f351c58273ff4f6f7f26cfc6a73f41c7063fb846cfa502169bcda1792),
  cmdline identical to the zlog5/zlog6 image + `-zc msdc_readverify=1`;
  shim slot + dtb byte-identical to the E1-base image (verifier output).
- USER ACTION (single loop, as always): flash the image (their normal
  flow), power on, ONE final-screen photo whatever it shows.
  DECODE GUIDE for the 0086 screens (each panic screen now re-prints
  the whole forensics, so the LAST screen is self-sufficient):
  - `MERLIN FORENSICS: msdc reads=N readverify mismatches=N last lba=N`
    reads=0 => driver never ran (panic pre-mount); reads>0 => mounted
    phase; mismatches>0 => the MSDC read path serves wrong bytes
    (driver guilty); mismatches=0 with survivors => scribbler class.
  - per-victim lines list up to the last 4 UAF elements with zone,
    size, off, val, elem - compare off/val against boots 6/10/11.
  - the 0084 zone-log block follows as before when the zone is traced.

## Agent handoff / active work (2026-10-25 LATEST-43: USER WORKFLOW CONSTRAINT = ONE PHOTO PER BOOT (no filming); 0086 FORENSICS-REPLAY PATCH DRAFTED + VALIDATED (final screen re-prints readverify verdict + victims); awaiting push+CI approval; B-test (fastboot boot from power-off) remains the free A/B)

- USER CONSTRAINT: filming multi-stage boots is not feasible for them
  ("that's gonna be really hard"). Agreed plan: every future boot stays a
  ONE-PHOTO decode; forensics must be portable to the FINAL screen.
- 0086 PATCH DRAFTED + VALIDATED (ios-merlin 449d9a4 + ios-sweet msdc-0079
  1a6efd8, NOT pushed - awaiting user approval for CI):
  xnu/patches/0086-merlin-forensics-replay.patch. Every zalloc_uaf_panic()
  now FIRST re-emits the accumulated forensics, so panic #2/#3/#N screens
  carry the whole picture (the 3-panic storm scrolls the first panic's
  0084 zone-log lines away today):
  (a) zalloc.c: static ring merlin_uaf_notes[4] + replay printer inserted
      before zalloc_uaf_panic; per UAF panic, BEFORE the 0084 zone-log
      block, prints
      `MERLIN FORENSICS: msdc reads=%lu readverify mismatches=%u last lba=%llu`
      + one `MERLIN FORENSICS: victim <heap+zone> size= off= val=0x%016llx
      elem=%p` per remembered hit (ring of the last 4 in chronological
      order). Helps the read[Any tracked zone] requirement for the replay;
      the zlogN tokens remain needed only for zone-log BACKTRACES.
  (b) sweet_ufs.c: msdc_rv_mismatches un-static'd (extern-visible), ADD
      uint64_t msdc_rv_last_lba (set in the mismatch branch) +
      unsigned long msdc_strategy_reads (counts readverify-path sector
      reads; msdc_read_sector entry). The `reads=` figure doubles as the
      driver-activity marker in both A/B arms.
  VALIDATION: generated by research/tmp-msdc-split/make-0086.py from the
  p0084/t1 post-0084 synth tree (difflib → guaranteed hunk counts);
  strict `git apply` clean; applied result BYTE-IDENTICAL to the
  directly-edited expected (t4). GOTCHAS recorded: (1) the scratch git
  apply must run `-c core.autocrlf=false` (global true CRLF-expanded
  t3, first run failed the byte-compare); (2) the generator's esc()
  must NOT convert `\\n` to real newlines (the C printf escapes) - the
  first patch draft was syntactically broken C (two printf literals
  contained raw newlines); sanity probes for the intact escapes are now
  part of the generator. zone_name/zone_heap_name are defined at
  zalloc.c:2491/2497 (before the 3064 insert point) = compile-safe.
- NEXT STEPS: (1) user runs experiment B (fastboot boot of the
  shim-boot-merlin-msdc-0084-rv-zlog5.img straight from power-off; ONE
  final-screen photo each outcome; flashed image stays on boot
  partition for A repeats). (2) on user push+CI approval: push
  msdc-0079 (1a6efd8) + workflow_dispatch; fetch artifact; build the
  same-image boot-11 (boot-10 cmdline) with the 0086 kernel; then boots
  become permanently one-photo decodable. (3) 0085 name remains
  RESERVED for the MSDC init hardening (controller reset + clear
  SA/CFG/CTRL/INT at attach) - write it if B shows UAF-free (handoff
  scribbler verdict) OR after forensics if still ambiguous.
- Decoding table for the NEXT one-photo results (method B or boot 11):
  final screen CALM console (no panic) = no storm under method B ->
  handoff-correlate; FORENSICS line reads=0 = driver never ran (panic
  pre-mount) vs reads>0 = mounted phase reached; mismatches>0 = driver
  read path serves wrong bytes; victim lines list every storm stage's
  element (the ORIGINAL's data + later storm victims).

## Agent handoff / active work (2026-10-25 LATEST-42: BOOT #10 METHOD-A RESULT = PANIC STORM (user counted 3 panic screens); ORIGINAL PANIC = data.kalloc.8192 off:704 DECIMAL - EXACTLY BOOT #6's SIGNATURE; elem-dump format decoded (decimal offsets, 1 KB buffer cap); caller digits unreliable; zone-log lines presumed scrolled - VIDEO STILL OWED)

- PHOTO (2026-10-25, user said "stage 3" = the 3rd panic screen of this
  boot = a panic STORM, consistent with the double-panic machinery):
  legible this time. Content: two element-dump blocks + `Original panic
  string:` + `panic(cpu 0 caller 0xffff...'07ab8a50'): [data.kalloc.
  8192]: element modified after free (off:704, val:0x070f37033a012300,
  sz:8192, ptr:0xffffffe29a172000)` + hangShake/banner line.
- FACTS decoded this session (from research/xnu-full zalloc.c:3069-3097):
  (1) The elem-dump print format is `"%5d: 0x%016lx"` = DECIMAL byte
      offset inside the element + hex word; the walk starts at offset 0
      and prints ONLY NONZERO words; frees bzero elements => the FIRST
      nonzero word off 704 = the scribbler's write START.
      CAREFUL: the buffer is 1024 bytes (~40-45 entries) - the visible
      dump EXHAUSTED the buffer at ~offset 1792; words beyond that are
      truncated-unknown, NOT zero. The corruption spans >= ~1.1 KB
      CONTIGUOUSLY (most words 704..1792 nonzero) = a multi-word stream,
      not one stray pointer. Boot #6's panic had the same format but the
      photos were unreadable; treat ANY earlier "0xff-heavy sparse" dump
      readings as the same class.
  (2) panic string owner = zalloc_uaf_panic ONLY (zalloc.c:3093, unique
      occurrence of "element modified after free"); `off`/`sz` are
      PRINTED DECIMAL (%d) — earlier NOTES' "off:704 hex?" ambiguity
      resolved.
  (3) val 0x070f37033a012300 (LE bytes 00 23 01 3a 03 37 0f 07) is
      STRUCTURED, not the sparse 0xFF-heaps of boots 7/9 — reads like an
      embedded constant/pointer fragment; no conclusion.
  (4) THE SIGNATURE = boot #6's EXACTLY (data.kalloc.8192, first
      nonzero at 704, sz 8192). Boot #10 (presumed = the zlog5 image,
      6 tracked zones, readverify on) did NOT dodge the corrupter and
      did NOT hop zones — it returned to the boot-6 victim. Boots 7/9
      hitting other zones = the same scribbler's victim selection
      varying with heap churn (fixed stale PA patch theory).
- CALLER CAVEAT: photo caller digits symbolicate to _zone_nofail_panic
  (0xfffffe0007ab8a50) — whose message is DIFFERENT ("Z_NOFAIL can't be
  satisfied"); the UAF panic function lives 0x100 lower (_zalloc_uaf_
  panic 0x...ab8950..0xab8a50, verified via python LC_SYMTAB parse of
  research/art-0084/kernel.development.sweet, 70,887 defined symbols).
  The recorded PC is untrustworthy (OCR low-digit fuzz AND panic-storm
  stack reuse); the STRING attribution is authoritative. Future nascent
  panic-caller digit reads: cross-check which candidate function's
  message format matches the text.
- zone-log trap status: NOT visible in the captured screen. The 0084
  gate is z->z_btlog != NULL and prints BEFORE the (panic)(...) call, so
  the FIRST panic's output (header + `zone-log #N ... bt:` lines, if
  data.kalloc.8192 was tracked this boot) sits ABOVE `Original panic
  string:` and scrolled off with the storm. ONLY the final screen was
  captured (user confirmed). => THE VIDEO ASK STANDS: film a full boot
  (method A flash-boot, phone standalone) from the first console lines
  through the panic(s); the video carries READVERIFY MISMATCH lines, the
  MERLIN MSDC init line, mount lines, ignition stages and the FIRST
  panic's zone-log output in one artifact. Second run = method B
  (fastboot boot directly from power-off) for the LK-handoff A/B.
- NEXT AFTER VIDEO: if mismatches seen -> 0085 read-engine fix; if zero
  mismatches + zone-log backtraces -> symbolicate the bt addrs vs the
  0084 symtab (parser already working this session); if zero mismatches
  + no zone-log -> write 0085 driver-init hardening (controller reset +
  clear SA/CFG/CTRL/INT at attach) against the stale-LK-handoff theory
  (LATEST-41) — patch text can be drafted while waiting.

## Agent handoff / active work (2026-10-25 LATEST-41: WORKFLOW FACT CORRECTED BY USER - ALL BOOTS 1-9 WERE `fastboot flash boot` (PERSISTENT), NOT `fastboot boot`; LK READS THE BOOT IMAGE FROM eMMC RIGHT BEFORE EVERY KERNEL BOOT; STALE-LK MSDC/DMA SCRIBBLER THEORY SHARPENS; NEW FREE A/B EXPERIMENT UNLOCKED)

- USER FACT (2026-10-25): boots are done via `fastboot flash boot
  <image>` and ALWAYS HAVE BEEN (boots 1-9; answer to explicit question).
  The NOTES' standing instruction `fastboot boot <image>` never actually
  happened - every "boot #N" observation = a power-on boot of the
  LAST-FLASHED boot-partition image. Consequences recut:
  (a) LK loads the 17 MB boot image FROM eMMC (MSDC) on every boot,
      immediately before handing off to the kernel. The MSDC controller +
      DMA engine therefore carry REAL block-read state (CMD17/18 work,
      image buffer SA, timing cfg) at kernel takeover on EVERY boot so far.
      (Ramdisk-less XNU took the controller over with a driver that has a
      PROVEN defect: DMA-stop timeout = continue-as-success, LATEST-38.)
  (b) The UAF victims' dumped bytes are 0xFF-heavy FLASH-LIKE content -
      exactly what LK's last eMMC reads carry. A stale/re-armed MSDC DMA
      writing to LK's stale buffer address explains: cross-zone victims
      (the stale PA region gets reused by different kalloc elements as
      the heap churns), persistence, and the wrong-diverging read bytes
      theory all at once.
  (c) The ~17 MiB raw flash to boot also cannot hit the userdata
      last-chunk sparse bug (small raw image, different fastboot path).
  (d) Persistent flash: the phone boots the test image standalone on
      every power-on (photo/video capture can be done untethered);
      each NEW test image needs a fresh flash; the boot partition no
      longer holds stock boot.img (restore path = MIUI fastboot ROM tgz
      boot.img; userdata already iOS so Android is unbootable anyway).
- NEW FREE A/B EXPERIMENT (same image, same cmdline, NO CI - do before
  building any 0085): (A) flashed-boot boot (current flow) vs (B)
  `fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0084-rv-zlog5.img`
  from a fastboot session entered STRAIGHT FROM POWER-OFF (button combo
  only - no prior flash/I/O in that LK session). UAF panic in A only ->
  the corrupter lives in the LK-eMMC-handoff state => 0085 driver-init
  hardening (full MSDC reset + clear SA/CFG/CTRL/INT before first use)
  becomes THE fix to write. UAF in both -> kernel-code bug, handoff
  largely exonerated. Neither -> environment/timing (revisit heat, event
  counting).
- BOOT #10 PROCEDURE UPDATED (flash-boot workflow):
  `fastboot flash boot research\merlin-boot\shim-boot-merlin-msdc-0084-rv-zlog5.img`
  -> power off -> power ON (standalone, no PC) -> FILM from the EARLIEST
  console lines (MERLIN MSDC first-sector line never captured yet; also
  any READVERIFY MISMATCH lines) through the panic. To re-test
  reproducibly just power off/on again (same image reboots itself).
- Summaries of boots #9/10 with the OLD method are still comparable
  against each other (same method), but any comparison with future
  `fastboot boot` runs must respect the method axis.

## Agent handoff / active work (2026-10-25 LATEST-40: BOOT #9 DECODED = SAME UAF CLASS IN data.kalloc.16384 (off:704, SAME OFF AS BOOT #6) - CORRUPTION ESCAPED THE 4 TRACKED ZONES; "handShake" LINE = BENIGN KDP PANIC-PRINTER NOISE (NOT A FIX TARGET); BOOT #10 BUILT WITH zlog5=kalloc.16384 + zlog6=kalloc.12288)

- USER QUESTION ANSWERED: "fix the handshake for have support of it?" =
  NOTHING TO FIX. `handShake structure not initialized` is XNU's panic
  REPORTING printer (kdp out_shmem.c) telling us the debug-console
  handshake stage is not configured; it appears in EVERY panic on these
  boots (documented benign in boot #5, LATEST-35). It is panic-printer
  noise printed WHILE dumping the real crisis, not a failure of the boot.

- BOOT #9 VERDICT (user photo, single frame of the tail): the UAF
  WRITE-AFTER-FREE CLASS PERSISTED ON THE 0084 KERNEL. Seen: two blocks
  of 0xFF-heavy element-dump words, `handShake structure not initialized`
  (+ the panic.apple.com banner), and `Original panic string:` +
  `panic(cpu 0 ...): [<da ta.>kalloc.<...>16384] : element modified after
  free (off:704, ..., sz:16384, ptr:0xffffffe2...e4d80)` (OCR-fuzzy;
  exact zone name + caller digits best-effort).
  FACTS: (1) third DIFFERENT zone family across boots - boot #6
  data.kalloc.8192 off:704, boot #7 kalloc.type.var.4096 off:768, boot #9
  ~data.kalloc.16384 off:704 (same off as #6!, whole sz-class grew) =
  a generalized scribbler landing in (semi-)randomly chosen freed kalloc
  elements; (2) NO zone-log history lines printed -> the victim zone was
  NOT among zlog1..4 (they covered only .8192/.4096 families; 16384 was
  not tracked) - the corrupter ESCAPED the instrumented set, trap not
  failed; (3) `Original panic string:` = double-panic bookkeeping (also
  seen boot #5); the two dump blocks = the primary + secondary panic
  dumps (or one dump + OCR fuzz) - unresolved; (4) NO CRASH/Jnl/READVERIFY
  lines visible = scrolled off; single frame cannot answer whether
  READVERIFY MISMATCH printed at all (its init line + MISMATCH lines
  would be far above the visible tail) - VIDEO during the next boot is
  REQUIRED to read the pre-panic sequence.

- zlog TOKEN SEMANTICS VERIFIED IN SOURCE (research/xnu-full
  osfmk/kern/zalloc.c): zone_setup_logging (:3256) tries zlog1..zlogN
  (MAX_ZONES_LOG_REQUESTS=10, :3236) with track_this_zone(zone_name,
  token) + track_kalloc_zones(z, token). track_kalloc_zones (:2899-2945)
  matches token `kalloc.<n>` against EVERY kheap kalloc zone whose
  elem_inner_size == n == strtoul(token tail) - so `kalloc.16384` covers
  BOTH data.kalloc.16384 and the default-heap kalloc.16384 (same
  mechanism that made zlog1=kalloc.8192 cover the .8192 pair), and
  `kalloc.type.<n>` / `kalloc.type.var.<n>` cover the KT zones by exact
  size. The "zlog prefix" comment (:3282-3294) is about the BOOT-ARG name
  (PE parsing quirk), NOT zone-name prefix match.track_this_zone is an
  exact full-name match (chars until BOTH end simultaneously; space<->dot
  equivalence). => to trap a new band, ADD ANOTHER zlogN=kalloc.<size>
  token. More than 10 needs no CI anyway (cmdline).

- BOOT #10 BUILT + SELF-VERIFIED (0084 kernel, NO CI needed):
  research/merlin-boot/shim-boot-merlin-msdc-0084-rv-zlog5.img
  (16,989,139 B; SHA256
  86f932ec7962c298d4a6934923acae039ff85b35b8c511b5fd8ca9dff9b92864).
  Cmdline = boot-9's (boot-6 args + zlog1..4 + -zc msdc_readverify=1)
  PLUS `zlog5=kalloc.16384 zlog6=kalloc.12288` - the band boot #9's
  victim came from plus the neighboring 12288 band (belt: if it hops
  again, add zlog7=<next band>; each hop = one cmdline edit + rebuild).
  unpack_bootv2 verify: cmdline OK; shim slot + dtb byte-identical to E1.
  SIX logged zones => expect a NOTICEABLY slower boot than #9.
- readverify SELF-CHECK: the 0084 re-read path (patch msdc_read_sector :
  31-66) is a 512 B stack copy + bounce-buffer re-read + memcmp - no
  allocations, no caller-buffer rewrites; it cannot be the UAF writer.
- NEXT USER STEP: capture a VIDEO of the screen from an early boot phase
  (before/at the MERLIN MSDC lines) and keep filming to the panic; then
      cold power-off; fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0084-rv-zlog5.img
  VERDICTS: (a) `zone-log #N: elem %p op %u bt:` lines at the panic ->
  symbolicate vs research/art-0084/kernel.development.sweet.link = the
  victim's alloc/free owners; (b) READVERIFY MISMATCH lines/flood ->
  the 0082 read path serves wrong bytes (fix the read engine, 0085);
  (c) full-video study shows ZERO mismatches AND the UAF still panics
  -> a rogue RAM writer: leading candidate = stale MSDC DMA state left
  by LK that gets re-armed (next patch = 0085 driver-init hardening:
  full controller reset + clear SA/CFG/CTRL before first use); (d) panic
  zone outside the 6 tracked families AGAIN -> add zlog7=kalloc.<size>
  (next band after reading the zone name) - cmdline-only, no CI.
- REMINDER: image.png at repo root is STILL the unrelated Blockman GO
  screenshot (untracked; do not commit). The boot #9 photo exists only in
  the chat - saving phone photos into research/merlin-boot/photos/ would
  help future decode sessions (research/ is gitignored; OCR-sourced facts
  above are already transcribed).

## Agent handoff / active work (2026-10-25 LATEST-39: 0084 CI BUILD DONE + VERIFIED; BOOT #9 IMAGE BUILT (msdc_readverify=1 + zlog x4 + -zc); READY FOR USER FASTBOOT BOOT + PHOTO)

- 0084 PUSH + CI COMPLETE: fork/msdc-0079 IS AT 00ce338 ON THE REMOTE
  (ls-remote-verified; LATEST-38's "NOT pushed, awaiting approval" was
  stale - the push happened after that note). Workflow_dispatch run
  40173186894 (run #17, head 00ce338, created 2026-10-25 07:33Z) completed
  SUCCESS. Real artifact cross-checked per the LATEST-36 gotcha:
  xnu-kernel id 12591790366 (60,018,920 B, workflow_run = 40173186894
  @00ce338, created 07:41:15Z). Also xnu-buildtree id 12590759940 (not
  needed).
- ARTIFACT FETCHED + VERIFIED: research/art-0084/ (zip extracted flat,
  NOT under an xnu-kernel/ subdir). kernel.development.sweet
  17,207,384 B (0083 build was 17,207,192 -> +192 B = the 0084 additions),
  SHA256 0fe6adc021c0346a2360c360949cad58b52640f7abf4dbb6a0a3c824c8239577
  == the artifact's own SHA256SUMS. New 0084 strings verified IN THE
  BINARY: "readverify enabled (double-read compare)", "READVERIFY
  MISMATCH lba", zone-log element-history prints,
  btlog_dump_element_history. kernel_end 0xfffffe00084cc000 (same as
  boot #6's kernel).
- BOOT #9 IMAGE BUILT + SELF-VERIFIED:
  research/merlin-boot/shim-boot-merlin-msdc-0084-rv-zlog.img
  (16,989,139 B; SHA256
  6409431794c59ec8148847ef41f5a6d2b5f539e5ec0a85809e6935722e0e1c2b).
  Payload 16,612,176 B = 0084 kernel + proven T/adt.bin + cmdline =
  the EXACT boot-6 args
  `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress
  rd=msdcroot0 unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`
  PLUS `zlog1=kalloc.8192 zlog2=kalloc.4096 zlog3=kalloc.type.var.4096
  zlog4=kalloc.type.4096 -zc msdc_readverify=1`.
  unpack_bootv2 verify: cmdline OK; shim slot + dtb byte-identical to
  the E1 image; built by research/tmp-msdc-split/build-msdcroot0.py
  (sources shim/dtb from the E1 image, so the uncommitted shim work did
  not affect it). NOTE: expect a SLOWER boot (4 zlog'd zones log every
  alloc/free + readverify re-reads and compares every sector).
- NEXT USER STEP (decisive discriminators, all print on the console):
  cold power-off; then
      fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0084-rv-zlog.img
  Photograph the settled/panic screen. Decode table:
  (a) `MERLIN MSDC: READVERIFY MISMATCH lba ...` => the 0082 CMD17 read
      path serves wrong bytes = boot-6 slide-overflow culprit -> fix the
      read engine (0085).
  (b) panic WITH `MERLIN zone-log: element history` + `zone-log #N: elem
      %p op %u bt: ...` lines => the UAF victim's alloc/free backtraces
      -> symbolicate against research/art-0084/
      kernel.development.sweet.link.
  (c) no READVERIFY MISMATCH + no kalloc panic + boot PROGRESSES past
      boot #6's slide wall => the earlier divergence was read/eMMC state,
      fixed side-effects; push on whatever the next wall is.
  (d) no READVERIFY MISMATCH + slide constant overflow persists =>
      eMMC content differs from the flashed image -> mtkclient read-back
      + sha256 of the 44 cache-file LBA ranges (extent map from the HFS+
      catalog; image-side digests already in research/tmp-msdc-split/img.sha).
- UNCOMMITTED STREAMS IN ios-merlin (NOT touched this session - likely
  another agent's in-flight work; keep out of commits until identified):
  shim/ramfb.{c,h} + shim/{console.h,loader.c,loader.h,shim.c,start.S}
  (+~490/-55 lines) = QEMU fw_cfg RAMFB support + loader changes;
  tools/patch-earlyfb.py = retarget the SWEET early console
  0x9c000000 -> merlin splash FB 0x7e605000 (3 movk sites + early_fb
  data word, all verified in that file's docstring); rebuilt fbcon-1x
  artifacts (tools/fbcon-1x.{S,ld,elf,o,init.bin,tx.bin},
  patch-fbcon1x.py tweak) + tools/qemu-ramfb*.elf/o + shim/out-qemu*/
  build dirs. No NOTES entry references this stream - ASK THE USER what
  it is before basing anything on it or reverting it.
- image.png at the repo root (untracked) is an UNRELATED Blockman GO
  game screenshot (no boot/panic content) - do not commit; left as-is.

## Agent handoff / active work (2026-10-24 LATEST-38: BOOT #6 = AMFI WALL CLEARED + SPRINGBOARD LAUNCHED (FIRST EVER); NEW WALL = SHARED-CACHE SLIDE OVERFLOW WITH IMAGE BYTES PROVEN GOOD -> SUSPECT = DEVICE READ PATH (0082 CMD17 DRIVER OR eMMC CONTENT); Jnl 0x19 = MISSING DKIOCSYNCHRONIZE (BENIGN); TERMINAL PANIC = GENUINE kalloc.8192 UAF; NEXT = 0084 READ-VERIFY + IOCTL PATCH)

- BOOT #6 (shim-boot-merlin-msdc-0083-simlaunch-unsec.img, boot-arg
  launchd_unsecure_cache=1) RESULT (user photo): THE ESCAPE HATCH WORKS.
  No "Unable to find AMFI" abort; launchd exec'd real iOS daemons
  (AppleCredentialManagerDaemon, CommCenter, fseventsd, mobiletimerd,
  imagent, Logd helper, xpcproxy - the "exec X" lines are SWEET 0042's
  logger) and **SpringBoard[26] launched and crashed - the first boot
  ever to reach SpringBoard**. Then processes died SIGBUS and the kernel
  panicked. Photo OCR is fuzzy on some hex digits (caveats below).
- FULL DECODE via dynamic workflow (run
  dwfrun-c906df4f-0fe8-40e1-9d9a-a9bea2867524; 4 source decoders + WSL
  cache-integrity verifier + citation-rechecking synthesizer;
  deliverable = "Boot #6 decode report" artifact). Findings:
- (1) SOURCE-PROVEN: `vm_shared_region_slide_page() offset overflow:
  pageIndex=9184, start_offset=8` = the v2 chained-fixup slider walking
  the rebase chain past the 4K page end (osfmk/vm/vm_shared_region.c:3088
  inside rebase_chain; v2-only path - v1/v3/v4 have separate code). On
  failure the kernel neither skips nor panics: the shared-region pager
  fails THAT page's fault with KERN_MEMORY_ERROR
  (vm_shared_region_pager.c:752-756) -> every process touching the page
  dies SIGBUS. SpringBoard's `code 0x10000000a` = EXC_BAD_ACCESS<<32 |
  KERN_MEMORY_ERROR(10), far inside the tag-32 (VM_MEMORY_SHARED_PMAP)
  shared-cache map; the crash lines themselves are SWEET patches
  0043-sweet-console-crash-log.patch:34,74 (printer: code/sub/slide/mh;
  photo "wih" = "mh" = task mach_header) + 0066-sweet-crash-fault-region
  .patch:13-18 (the map line). xpcproxy's `sub 0x3a6f727940` holds
  ASCII (":ory@") - a wild pointer from garbage data, same class.
- (2) IMAGE EXONERATED (byte-proven this session): all 44 dyld-cache
  files inside iosroot-v2.img are size+sha256-identical to the
  087-86593-047.dmg sources (full digests in
  research/tmp-msdc-split/img.sha; the (size,sha256) bijection consumes
  all 44 cache-sized iNodes, 0 mismatches). Kernel-exact simulation of
  the v2 chain walk (research/tmp-msdc-split/probe3.py, port of
  rebase_chain_64) over the ON-IMAGE bytes: pageIndex 9184 (and sweep
  9170-9200) in ALL FOUR slide-info mappings walk clean (342/110/321/351
  hops); on-image page_starts[9184] is 0x0 or 0x4 - NEVER the 2
  (=start_offset 8) the runtime consumed. A zero-filled page terminates
  in 1 hop (cannot trip the print). Only the two split-DATA files
  (.27/.41 dylddata, 187,105,280 B and 102,547,456 B) carry slide info
  (v2, 4K pages); TEXT subcaches have none.
  => THE BYTES THE KERNEL CONSUMED AT RUNTIME WERE NOT THE IMAGE'S BYTES.
- (3) THEREFORE (INFERENCE, not yet discriminated): the divergence is
  in the DEVICE read path - either (a) the 0082 MSDC CMD17 basic-DMA
  read served wrong bytes for some reads (e.g. a silent failure leaving
  stale bounce-buffer content), or (b) the eMMC content differs from the
  flashed image (fastboot OKAY is NOT data verification; flashes #1/#2
  demonstrably lost chunks, #3 was 47/47 OKAY but unverified).
- (4) SOURCE-PROVEN BENIGN: `Jnl: b(1, 0): flushing fs disk buffer
  returned 0x19` = ENOTTY (25; errno.h:117): the HFS journal's
  write_journal_header() issues DKIOCSYNCHRONIZE (hfs-627.100.6
  core/hfs_journal.c:482,498 - upstream Apple code, sha pinned by
  0026-stage-hfs.sh) and merlin_msdc_ioctl (0082 patch :563-596) does
  not implement it -> default ENOTTY. NOT an I/O failure; the journal
  continued. Fix = `case DKIOCSYNCHRONIZE: return 0;` (truthful: 0082
  writes are synchronous, on media before strategy returns). Also add
  DKIOCGETFEATURES (probed at journal open; ENOTTY -> no barrier ->
  full flush every header write = why the line repeated). The boots
  #4/#5 "lookup preboot : 25" same-errno theory is UNPROVEN (libignition
  is closed-source, no artifact in workspace). DKIOCGETMAXBLOCKCOUNTWRITE
  returning 0 is a separate oddity worth the next driver rev.
- (5) SOURCE-PROVEN: terminal `panic ... [data.kalloc.8192]: element
  modified after free (off:704 ...)` = the always-on arm64 kalloc
  zero-check (zalloc.c:3069-3097 zalloc_uaf_panic; frees bzero the
  element, so a non-zero word at off 704 = genuine WRITE-AFTER-FREE).
  The panic's caller is the DETECTOR, not the writer. EXCLUDED as
  writers: the 0082 driver's DMA (permanent 64KiB kmem bounce buffer,
  DMA never targets kalloc memory) and the SWEET crash reporter
  (allocates nothing, balanced refs). Writer unknown - most consistent
  with an independent kernel UAF or crash-storm fallout (kalloc.8192 =
  6145-8192 B kalloc_data buffers; hottest users this boot: AMFI
  entitlement XML copies (patch 0035), HFS journal buffers). Catch it:
  boot-args `zlog1=kalloc.8192 -zc` (cmdline-only, NO kernel rebuild:
  build-msdcroot0.py --cmdline).
- IMAGE-CONTAINER GOTCHA (integrity verifier): iosroot-v2.img can NO
  LONGER be mounted read-only by Linux hfsplus - the decoy tail moved
  the file end so the backup-volume-header slot the Linux driver checks
  (device_end-1024) lands in 0xFF decoy ("invalid secondary volume
  header"). XNU never needs the backup VH (boots fine). The verifier
  read the image side via 7-Zip 26.04's HFS+ handler instead (primary
  VH + catalog + forks; cross-validated against raw VH bytes). Future
  image-side checks: 7z, or repair the backup VH after padding.
- NEXT STEPS (recommended order):
  (0) FREE: if the panic screen still persists on the phone, one sharp
      photo of the panic block (off/val/ptr + dump lines and the CRASH
      lines' exact hex) - settles OCR-fuzzy digits (slide_amount
      4006251568 = 0xEECA8C30 is NOT 16K-aligned and would have been
      rejected at map time = misread; xpcproxy slide 0x167e10000
      exceeds the 32-bit sr_slide field).
  (1) THE DECISIVE EXPERIMENT - driver patch 0084: boot-arg
      `msdc_readverify=1` double-read+compare in strategy (re-read every
      completed read and memcmp against the served copy; print LBA +
      attempt count on mismatch) PLUS DKIOCSYNCHRONIZE /
      DKIOCGETFEATURES / MAXBLOCKCOUNTWRITE ioctl fixes. Needs fork push
      + CI build (user approval). Verdicts: mismatch prints -> DRIVER
      read bug (fix the CMD17 path); zero mismatches while the slide
      overflow recurs -> eMMC content wrong -> mtkclient read-back hash
      of the cache-file LBA ranges (extent map from the HFS+ catalog).
  (2) DONE - ZLOG BOOT IMAGE BUILT + SELF-VERIFIED:
      research/merlin-boot/shim-boot-merlin-msdc-0083-simlaunch-unsec-zlog.img
      (16,989,139 B, SHA256 47f84b16e0c13a3eb750244e92e44971b9bd790f440
      ba6e3f855fc10c1c60ef5). Same 0083 kernel (66750d31... re-verified
      pre-build), same shim slot + dtb byte-identical to E1, cmdline =
      the proven boot-6 args + `zlog1=kalloc.8192 -zc`. zlog1=kalloc.
      8192 tracks BOTH kalloc.8192 and data.kalloc.8192 (prefix match,
      zalloc.c:2929-2936); -zc = corruption_debug TUNABLE (:3233); btlog
      creation is boot-arg-driven, not config-gated (:3311-3316) ->
      DEVELOPMENT kernel logs alloc/free backtraces and zalloc_uaf_panic
      prints them. Boot it exactly like boot #6 and photograph.
- BOOT #7 = ZLOG BOOT (user photo 2026-10-24 ~20:53): panicked again,
  but DIFFERENT ZONE: `panic(cpu 0 caller 0xfffffe0007ab77e0):
  "kalloc.type.var.4096: element modified after free (off:768,
  val:0xfffd?debfe7bab5b, sz:4096, ptr:0xfffffe250f172000)"` (photo OCR:
  zone digits "var2.40961" = var.4096 + fuzz; val contains a non-hex
  "h" char). NO btlog output - zlog1=kalloc.8192 tracks only the 8192
  kalloc-heap zones and the corruption MOVED (boot #6: data.kalloc.8192
  off:704; boot #7: kalloc.type.var.4096 off:768 = the DEFAULT kalloc
  heap's 4096 band, kalloc.c:380-387 naming). The dump words are
  HIGH-ENTROPY ~75%-bits-set binary (0xfff7f3575fff7fe9,
  0xdeffdfbf7eeffd7b, ...) - NOT ARM64 code (no stp/ldp/sub-sp
  signatures), NOT ASCII; consistent with compressed/asset-class disk
  content. CONCLUSION (fact): generalized kernel-heap write-after-free
  across boots and zones. Screen showed no CRASH/Jnl/slide lines (ring
  scrolled; how far boot #7 got is UNKNOWN - if it panicked EARLY, the
  corrupter works under light I/O too).
- 0082 DRIVER AUDIT (this session, full source extracted to
  research/tmp-msdc-split/msdc-drv.c):
  - strategy/read/write offset accounting CORRECT: per-iteration
    want = MIN(count-done, 512-skip), memcpy bounded by vaddr+done+want
    <= vaddr+count and mo.dma+skip+want <= 512; GPT reads bounded
    (nent*esz <= sizeof(msdc_gpt) enforced). No caller-buffer overrun.
  - DMA cache handling CORRECT: flush_dcache64(pa, len, TRUE) on arm64
    = clean+INVALIDATE via FlushPoC_DcacheRegion + outer-cache dispatch
    (osfmk/arm/caches.c:61-96), called before AND after every DMA -
    stale-cache theory for boot #6's wrong bytes is DEAD. Late DMA arm
    is safe on eMMC (SD flow control: card stalls until host clocks).
  - REAL DEFECT #1: the DMA-stop wait (msdc_read_sector :282-287 and
    write path :360-365) BREAKS on timeout and CONTINUES AS SUCCESS -
    a hung DMA engine stays live while the driver serves data and
    programs the next transfer. Fix in 0084: timeout => EIO + full
    controller reset + print.
  - DEFECT #2 (known): missing DKIOCSYNCHRONIZE / DKIOCGETFEATURES
    ioctls (the Jnl 0x19 lines); DKIOCGETMAXBLOCKCOUNTWRITE returns 0.
  - Writer of the freed elements NOT found in-source (only DMA engine
    in the system is MSDC, SA always = bounce; kalloc panics remain
    consistent with a misbehaving DMA engine OR an unknown kernel bug;
    eMMC content mismatch CANNOT explain RAM writes).
- ZLOG4 TRAP IMAGE BUILT + SELF-VERIFIED:
  research/merlin-boot/shim-boot-merlin-msdc-0083-simlaunch-unsec-zlog4.img
  (16,989,139 B, SHA256 67ae7cccf35b1e79a58079b8df0a52afe5724339411
  0045608c968ada7df6527). Cmdline = boot-6 args + `zlog1=kalloc.8192
  zlog2=kalloc.4096 zlog3=kalloc.type.var.4096 zlog4=kalloc.type.4096
  -zc` - covers both hit zones plus neighbors (zlogN tokens verified
  against track_kalloc_zones zalloc.c:2905-2945: kalloc.<size> matches
  heap zones incl data.*; kalloc.type.var.<size> matches the KT_VAR
  band = boot #7's zone). If the corruption lands in ANY tracked zone,
  the panic dump prints the element's alloc/free BACKTRACES = the
  victim's owner + last freeer. NOTE: 4 hot zones logged => boot will
  run noticeably slower (btlog on every alloc/free) - that is expected.
  NEXT USER STEP: cold power-off, then
  fastboot boot research\merlin-boot\shim-boot-merlin-msdc-0083-simlaunch-unsec-zlog4.img
  photograph the panic block (backtrace lines under the element dump).
- BOOT #8 = ZLOG4 BOOT (user VIDEO 2026-10-24 ~21:43, full-screen pan):
  the element-modified-after-free panic class REPRODUCED; no
  zone-history/backtrace print appeared. SOURCE-EXPLAINED (not a trap
  failure): the stock panic path NEVER prints the btlog - zalloc_uaf_
  panic prints only the element dump (zalloc.c:3069-3096); the -zc+zlog
  comment block (zalloc.c:3150-3192) documents RECORDING only ("when
  the corruption is detected, EXAMINING the log will show...", via a
  debugger/MIG); btlog_get_records (btlog.c:1592+) returns deduplicated
  backtrace populations (leak reports), not per-element history, and
  allocates from ipc_kernel_map - unusable at panic. => A CMDLINE-ONLY
  TRAP CAN NEVER PRINT THE WRITER HISTORY; a kernel patch is required.
  (Zone name/digits in the video sit below readable resolution; same
  panic family, exact zone unconfirmed.)
- PATCH 0084 WRITTEN + VALIDATED (ios-merlin xnu/patches/0084-merlin-
  msdc-hardening.patch, 217 lines, LF; copied + committed LOCALLY to
  ios-sweet msdc-0079 as 00ce338 - NOT pushed, awaiting user approval):
  (a) driver (bsd/dev/sweet_ufs.c appended region): DKIOCSYNCHRONIZE
      returns 0 (truthful: polled CMD24 writes are on media before
      strategy returns - kills the Jnl 0x19 spam); DKIOCGETFEATURES=0;
      DKIOCGETMAXBLOCKCOUNTWRITE = BOUNCE/secsize (was 0); the DMA-stop
      timeout in BOTH read and write paths now prints and returns EIO
      instead of proceeding as success; boot-arg msdc_readverify=1
      double-reads every sector and memcpars - prints
      "READVERIFY MISMATCH lba ... off N: XX vs YY (total T)" - the
      decisive driver-vs-eMMC discriminator; init announces when on.
  (b) zalloc.c: zalloc_uaf_panic now dumps the corrupted element's
      zone-log history before panicking (when the zone is tracked).
  (c) btlog.c/btlog.h: new btlog_dump_element_history(btlog, element)
      walks BTLOG_LOG entries for that element under __btlog_lock,
      decodes each record (__bt_ref/__bt_op/btref_decode_unslide) and
      prints "zone-log #N: elem %p op %u bt: <up to 15 addrs>" (op:
      1=ZOP_ALLOC, 0=ZOP_FREE - zone_info.h:186-187).
  VALIDATION: dry-run apply on exact synthetic tree (536-line filler
  mapping derived from 0082 hunk2 @@ -533,4 +533,702 @@) = all hunks
  OK; on a +40-line shifted tree all 6 driver hunks apply at offset
  (the real upstream sweet_ufs.c length is unknown locally - offset
  tolerance proven for CI); applied output byte-identical to the edited
  sources; MSYS patch needs --binary locally (text-mode CRLF quirk,
  local-only - CI's Linux patch unaffected).
- NEXT STEPS:
  (1) USER APPROVAL PENDING: push ios-sweet msdc-0079 (00ce338 = 0083 +
      0084) + workflow_dispatch CI build; then fetch artifact and build
      the test image with cmdline: proven boot-6 args + `zlog1=kalloc.
      8192 zlog2=kalloc.4096 zlog3=kalloc.type.var.4096 zlog4=kalloc.
      type.4096 -zc msdc_readverify=1` (all four size families hit so
      far are covered; expect slower boot from 4 logged zones).
      VERDICTS: READVERIFY MISMATCH lines => driver read path serves
      wrong bytes (fix 0082 read engine); "zone-log ... bt:" lines at
      panic => the UAF victim's alloc/free owners (symbolicate vs the
      new kernel.development.sweet); neither + slide overflow persists
      => eMMC content differs from the image => mtkclient read-back.
  (2) The zlog4 cmdline-only image (built earlier tonight) remains
      bootable but CANNOT print history - superseded by (1).

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
- Artifacts: workflow deliverable "Boot #6 decode report" (markdown,
-  primary) + "Boot #6 signature decodes" (table), attached to run
-  dwfrun-c906df4f-0fe8-40e1-9d9a-a9bea2867524. research/tmp-msdc-split/
-  img.sha holds the 44 reference digests; probe3.py the chain simulator;
-  msdc-drv.c/-v2.c the extracted driver sources; p0084/ the patch
-  workdir (edited kernel files + synth trees).
