# Changelog

Versions follow [semantic versioning](https://semver.org/). The web demo in
`docs/` is not part of the PyPI package; its changes are listed here because
they ship from the same repository.

## 0.4.2 — 2026-10-08

Detection is unchanged from 0.4.1: every file gets the same verdict.

### Fixed

- `spf --version` printed `0.4.0` on the 0.4.1 release. The version is now
  read from the installed package metadata, so it can no longer drift from
  `pyproject.toml`, and a test compares the two.

### Added

- Web demo: drop several files or a whole folder to audit them into one
  table. It can be filtered to suspect and likely files, stopped part-way,
  and exported as CSV with the same field names as `spf audit --json`.
  Clicking a row opens that file's full report below.
- Web demo: a spectrogram (STFT or reassigned) and a long-term spectrum
  that overlays a genuine FLAC as reference, with zoom and a resizable plot.
  The page starts empty, has one shareable link per example (`?sample=`),
  and is available in English, Chinese and Japanese.
- `README.zh.md` and `README.ja.md`.
- CI runs the test suite on the Python 3.15 preview as well. That job may
  fail without blocking anything; it shows early which dependency has not
  caught up.
- Dependabot watches the GitHub Actions versions and the dependency caps.
- Issue forms for bugs and for files that got the wrong verdict.

### Changed

- The README figure is drawn from real LAME encodes at 96, 128 and 192 kbps
  and uses the same report layout as the demo.
- GitHub Actions moved to checkout v7, setup-python v7, setup-node v7,
  upload-artifact v7 and download-artifact v8.

## 0.4.1 — 2026-09-22

### Changed

- Dependencies are capped below their next major version: pillow < 14,
  librosa < 2, numpy < 3, matplotlib < 4, soundfile < 1.
- CI tests Python 3.11 to 3.14 and also runs every Monday, so upstream
  changes are caught before users hit them.
- License metadata uses an SPDX expression (`MIT`) and `license-files`.
  Building now needs setuptools 77 or newer.

## 0.4.0 — 2026-09-22

First release on PyPI.

- `spf audit` checks whether a lossless file was transcoded from a lossy
  one. It measures the spectral cutoff, how steep the cliff is, and whether
  the side channel collapses (intensity stereo). Each file is rated suspect,
  likely or clean, and files already in a lossy container are marked lossy.
  It can also write an HTML report or JSON.
- Cutoffs between 19.8 and 21.6 kHz are rated likely at most, because
  mastering filters and 320 kbps mp3 look the same there.
- `spf check` reports the environment and optional dependencies.
- The browser demo runs the same audit with the Web Audio API.
- Fixed STFT padding.
