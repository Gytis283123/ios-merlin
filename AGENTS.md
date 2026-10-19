# Working on ios-merlin

- Read `NOTES.md` before starting; it contains the project goal, hardware
  facts (with sources), current blocker and the next concrete action.
- The user switches agents frequently. Update the active handoff in
  `NOTES.md` after each milestone and before stopping. Record artifact
  IDs, exact build/boot results and unfinished work. Distinguish
  observations from guesses.
- This project is LOCAL ONLY for now (user decision 2026-10-18): do not
  push to GitHub or create repos without being asked. Kernel compilation
  needs macOS; until this repo is pushed, kernels come from ios-sweet's
  CI (see tools/fetch-kernel-artifact.py and NOTES.md for the download).
- Device bring-up uses temporary `fastboot boot` images. Never flash;
  preserve bootloader, recovery, modem, persist and the partition
  backups, and confirm each destructive step with the user before running it.
- Keep device dumps, serial numbers and downloaded Apple artifacts out of
  git (`.gitignore` covers backup/, dtb/, recovery/, research/, out dirs).
- Commit completed changes; keep commits descriptive (patch/tool driven,
  one milestone per commit).
