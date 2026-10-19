# XNU for merlin

Built on GitHub's macOS arm64 runners by `.github/workflows/xnu.yml`, using
[blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) (MIT) at a pinned commit.

- `MACOS_VERSION=13.5` -> xnu-8796 (same generation as iOS 16.6/16.7, the last iOS for iPhone 8).
- `patches/*.patch` are copied into the build script's patch dir and applied to the xnu tree with `git apply`.
- Output: `kernel.<config>.sweet` (the machine config stays SWEET for now - see NOTES.md; merlin identity comes from the ADT, and the MERLIN machine config lands with the first MTK driver work).

Fetch the latest build: `gh run download -R dipa-studio/ios-merlin -n xnu-kernel -D xnu/out`
(one this repo has been pushed; until then see `tools/fetch-kernel-artifact.py`
and NOTES.md for pulling ios-sweet's artifacts, which boot identically).
