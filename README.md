# spectral-forensics

[![tests](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml/badge.svg)](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Not another audio visualiser. A spectral **inspection and editing** toolkit:
sharpen a spectrogram past the uncertainty limit, tell whether a "lossless"
file was ever an mp3, and edit sound in the frequency domain — including
turning a photograph into something you can hear.

*Installs as `spf` (or the full `spectral-forensics`).*

![reassigned vs standard](examples/reassign_compare.png)

*Same audio, same window, same grid. Top: conventional STFT. Bottom: after
reassignment. The harmonics collapse to hairlines and the kick drum's pitch
glide — invisible above — becomes a readable curve.*

---

## What it does

| Command | Purpose |
|---|---|
| `reassign` | Reassigned spectrogram — resolution beyond Δt·Δf ≥ 1 |
| `audit` | Detect lossy transcodes in a music library |
| `edit` | Edit in the frequency domain, reconstruct with the original phase |
| `sonify` | Encode an image into a spectrum and resynthesise it as audio |
| `poster` | Static sonogram (STFT / mel / CQT) |
| `video` | Spectrum video with the original audio muxed in |
| `compare` | Side-by-side window-length comparison |

## Install

```bash
git clone https://github.com/shianjeng/spectral-forensics.git
cd spectral-forensics
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Python 3.11 or newer. `ffmpeg` is optional but needed for video output and for
decoding mp3/m4a/alac fallback paths:

```bash
sudo apt install ffmpeg     # Debian / Ubuntu
brew install ffmpeg         # macOS
```

The demo track used throughout this README is synthesised, not sampled:

```bash
python examples/make_demo_audio.py
```

### Dependencies at a glance

- **Required** (core commands): Python 3.11+, package dependencies from
  `pyproject.toml`
- **Optional**: `ffmpeg` for `spf video` and codec fallback decoding
  (`mp3/m4a/alac` in environments where the default decoder cannot open them)

Quick environment check:

```bash
spf check
spf check --json
```

---

## 1. Reassigned spectrogram

A pure tone always draws as a *band* in a normal spectrogram. That width is
imposed by the window, not by the signal — a direct consequence of

```
Δt = n_fft / sr     Δf = sr / n_fft     Δt · Δf = 1
```

But an STFT bin carries more than a magnitude: it carries a phase. Taking
partial derivatives of that phase recovers where the energy inside the bin
actually sits:

```
instantaneous frequency   ω̂ = ω − ∂φ/∂t
group delay               t̂ = t + ∂φ/∂ω
```

Move each bin's energy from its cell to `(t̂, ω̂)` and the picture becomes
sharper than the uncertainty bound. This is not a violation: the bound
constrains the *width of a single time–frequency atom*, not the *precision
with which you can estimate the location of its energy* — the same
distinction that lets centroid localisation beat the diffraction limit in
microscopy.

```bash
spf reassign track.flac --hop 256 --side-by-side
```

```
sharpness (spectral concentration): standard 5.116 → reassigned 5.389
```

A test states the claim numerically rather than leaving it to the eye: for a
1 kHz tone with `n_fft=2048` at 22.05 kHz (Δf = 10.8 Hz), the
magnitude-weighted spread of reassigned frequency estimates stays **under one
FFT bin**.

Where it fails: reassignment relies on the phase derivative being
meaningful, so overlapping partials and low-SNR regions scatter. Anything
below `--mag-top-db` is discarded rather than plotted as noise.

![reassigned poster](examples/poster_reassigned.png)

---

## 2. Transcode audit

A real problem for anyone with a music library: **is this FLAC actually a
re-wrapped mp3?** Lossy encoders discard everything above a cutoff. Convert
the result back to FLAC and the container changes, but the cliff stays.

```bash
spf audit ~/Music --recursive --verbose
```

```
✓ 01 - genuine.flac         cut= 22.1k
⚠ 02 - suspicious.flac      cut= 16.0k   90%  → mp3 ~128 kbps
? 03 - borderline.flac      cut= 18.8k   55%  → mp3 ~192 kbps
· 04 - honest.mp3           cut= 16.0k
```

Three independent pieces of evidence, because any one alone produces false
positives — old recordings and solo acoustic material genuinely lack high
frequencies:

1. **Cutoff frequency** — the highest frequency still carrying real energy,
   from a 95th-percentile long-term spectrum. A percentile rather than a
   mean, because quiet passages drag the mean into the noise floor, while a
   plain maximum chases single transients.
2. **Steepness** — how much further the level falls within 1 kHz above the
   cutoff. An encoder's brick wall drops 20 dB or more; natural rolloff does
   not.
3. **Intensity stereo** — lossy codecs collapse L/R into mono-plus-weight at
   high frequencies, so the side signal `(L−R)/2` vanishes above some
   frequency. Independent of the lowpass, and hard to fake.

Verdicts come in three tiers: `⚠ suspect` (a lowpass **and** a brick wall,
usually landing on a known encoder cutoff), `? likely` (a lowpass with no
corroborating evidence), and `✓ clean`. The middle tier exists so that
genuinely dull recordings are flagged for a listen rather than accused.

It also catches the reverse: an mp3 declaring 320 kbps whose spectrum only
supports 128 kbps was re-encoded from a low-bitrate source.

### Validation

Ground truth built with ffmpeg — one source encoded at several cutoffs, then
converted back to FLAC:

| File | True cutoff | Detected | Verdict |
|---|---|---|---|
| `original.wav` | none | 22.1 kHz | ✓ clean |
| `genuine.flac` | none | 22.1 kHz | ✓ clean |
| `cut_15000.flac` | 15.0 kHz | 15.3 kHz | ⚠ → ~112 kbps |
| `cut_16000.flac` | 16.0 kHz | 16.0 kHz | ⚠ → ~128 kbps |
| `cut_17500.flac` | 17.5 kHz | 17.4 kHz | ⚠ → ~160 kbps |
| `cut_19000.flac` | 19.0 kHz | 18.8 kHz | ⚠ → ~192 kbps |

### Known limitation

Encoders that apply **no** hard lowpass — ffmpeg's native AAC at higher
bitrates, Opus — slip past the cutoff test, and in a bench run the tool
called such a file clean. The lowpass-independent test currently shipped
(intensity stereo) does not help for mono material. Spectral-hole and
MDCT-periodicity detectors were prototyped and **did not separate the classes
on the test material**, so they are not shipped. Read a `✓` as "no lowpass
evidence", not as proof of provenance.

---

## 3. Invertible editing

The spectrogram stops being the end of the pipeline and becomes an editable
medium. Two reconstruction paths, for two different situations:

**Phase-preserving** (`edit`) — only the magnitude is changed, the original
phase is kept, and the inverse STFT runs directly. Every masking operation
goes this way. With an identity mask the round trip is exact to within
numerical precision:

```
||y' − y|| / ||y||  =  1.3e-08      (−158 dB)
```

```bash
spf edit track.wav --reject 2000:4000          # drop a band
spf edit track.wav --keep 80:250               # isolate the bass
spf edit track.wav --denoise
spf edit track.wav --mask painted.png          # paint in any image editor
```

Band rejection measured on a three-tone mixture: target band down more than
30 dB, neighbouring bands within 5 % of their original energy.

Denoising is spectral gating with a **minimum-statistics** noise floor — for
each frequency bin, a low percentile across the whole file, on the assumption
that every bin falls quiet at some point. Honest numbers on a noisy version
of the demo track:

| Input SNR | After | Δ |
|---|---|---|
| 17.0 dB | 16.9 dB | −0.2 |
| 9.1 dB | 11.8 dB | **+2.7** |
| 3.1 dB | 6.5 dB | **+3.4** |

It helps when there is real noise and mildly hurts when there is not — the
gate's own distortion outweighs what it removes. Stationary material (a tone
that never stops) breaks the minimum-statistics assumption outright, since
the tone estimates itself as the noise floor; pass an explicit noise region
instead.

**Griffin-Lim** (`sonify`) — when the magnitude is invented, no phase exists
to keep. Griffin-Lim alternates projections between "is a real signal" and
"has this magnitude" until a self-consistent phase falls out. It only
converges to a local solution, so a metallic quality is inherent, not a bug.

```bash
spf sonify photo.jpg --preview roundtrip.png
```

![source photo](examples/source_photo.png)

*Input: an ordinary greyscale picture.*

![photo round trip](examples/photo_roundtrip.png)

*Output, round-tripped: the picture encoded as a magnitude spectrum,
resynthesised into a 10-second wav, then re-analysed from the audio alone.
The ridge, moon and stars survive the trip.* Spectral convergence falls
0.345 → 0.241 → 0.207 → 0.196 at 1 / 8 / 32 / 64 iterations.

---

## 4. Posters, video, window comparison

```bash
spf poster  track.mp3 --transform cqt --palette bloom
spf video   track.mp3 --size 1920x1080 --fps 30 --bars 128
spf compare track.mp3 --n-ffts 512,2048,8192
```

![window comparison](examples/compare_nfft.png)

Short windows resolve every drum hit and smear the chords; long windows pin
the harmonics to a few Hz and smear every transient across 372 ms. Δt·Δf = 1
throughout — no setting wins both.

Video frames are rasterised in pure NumPy and piped straight into `ffmpeg`
over `stdin`: no matplotlib per frame, no intermediate PNGs, faster than
realtime at 1280×720 / 30 fps.

Palettes (`ember`, `abyss`, `mono`, `bloom`) are perceptually monotonic.
`jet` is deliberately absent — its non-uniform lightness invents banding that
is not in the data.

---

## Layout

```
spectral_forensics/
├── io.py          decode → mono → resample (ffmpeg fallback for m4a)
├── transform.py   STFT / mel / CQT      (numpy in, numpy out)
├── reassign.py    phase-derivative reassignment + rasterisation
├── invert.py      masking, spectral gating, Griffin-Lim, image → audio
├── audit.py       cutoff / steepness / intensity-stereo forensics
├── render.py      matrix → image        (no audio code)
├── video.py       ffmpeg pipe
└── cli.py         argparse entry point
```

`transform.py` never imports matplotlib and `render.py` never imports
librosa, so either half is usable alone.

## Tests

```bash
pytest -q     # 34 passed
```

## Development checks

Install dev toolchain:

```bash
pip install -e ".[dev]"
```

Run the standard local checks:

```bash
pytest -q
python -m build
ruff check .
mypy spectral_forensics tests
```

CI runs the suite on Python 3.11 and 3.12 on every push.

What the suite asserts, beyond "it doesn't crash": Δt·Δf = 1 across window
lengths; a 1 kHz tone peaking within one FFT bin; reassignment measurably
sharpening a chirp on an identical grid; synthetic brick-wall cutoffs at
12/16/19 kHz recovered to within 500 Hz; a gentle 6 dB/oct rolloff *not*
being flagged as an encoder cutoff; an exact STFT→ISTFT round trip; band
rejection leaving neighbouring bands intact; and Griffin-Lim error decreasing
monotonically with iteration count.

There are also CLI smoke tests that execute every subcommand. They exist
because `--help` passing proves nothing — argparse never invokes the handler,
so a subcommand whose handler had been deleted sailed through a `--help`
sweep and shipped broken.

### What CI caught

Two real defects, both invisible on the development machine:

- **`audit` crashed with `NameError`.** Its handler's `def` line was lost in
  an earlier edit, leaving the body as unreachable code inside another
  function. The CLI smoke tests now cover this.
- **Griffin-Lim broke on librosa 0.x.** The code passed librosa 1.0's `rng`
  argument while `pyproject.toml` declared `librosa>=0.10`, where the same
  argument is called `random_state`. Anyone installing within the declared
  range hit a `TypeError`. The 3.11 job resolved an older librosa and
  surfaced it; the seeding keyword is now detected at runtime.

Both share a shape worth naming: the declared support range was wider than
the code actually supported, which is exactly the gap a single development
environment cannot see.

## References

The algorithms here are not mine; the implementation and the validation are.

- K. Kodera, R. Gendrin, C. de Villedary (1978). *Analysis of time-varying
  signals with small BT values.* IEEE Trans. ASSP **26**(1), 64–76. — the
  original reassignment idea.
- F. Auger, P. Flandrin (1995). *Improving the readability of time-frequency
  and time-scale representations by the reassignment method.* IEEE Trans.
  Signal Processing **43**(5), 1068–1089. — the general framework this
  implementation follows.
- D. Griffin, J. Lim (1984). *Signal estimation from modified short-time
  Fourier transform.* IEEE Trans. ASSP **32**(2), 236–243. — the phase
  reconstruction used by `sonify`.
- R. Martin (2001). *Noise power spectral density estimation based on optimal
  smoothing and minimum statistics.* IEEE Trans. Speech and Audio Processing
  **9**(5), 504–512. — the noise floor used by `edit --denoise`.
- J. Brown (1991). *Calculation of a constant Q spectral transform.* JASA
  **89**(1), 425–434. — the basis of `--transform cqt`.

## Roadmap

- Psychoacoustic masking overlay — dim what is physically present but
  inaudible, which is exactly what the encoder decided to throw away
- A lowpass-independent transcode detector that survives validation
- Interactive painting UI instead of round-tripping through a PNG mask

## Licence

MIT. The demo track is generated by `examples/make_demo_audio.py`; do not
commit commercial recordings to this repository.
