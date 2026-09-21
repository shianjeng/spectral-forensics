# spectral-forensics

*Installs as the `sonogram` command.*

[![tests](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml/badge.svg)](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Not another audio visualiser. A spectral **inspection and editing** toolkit:
sharpen a spectrogram past the uncertainty limit, tell whether a "lossless"
file was ever an mp3, and edit sound in the frequency domain — including
turning a photograph into something you can hear.

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
| `poster` | Static sonogram (STFT / mel / CQT) |
| `video` | Spectrum video with the original audio muxed in |
| `edit` | Edit in the frequency domain, reconstruct with the original phase |
| `sonify` | Encode an image into a spectrum and resynthesise it as audio |
| `compare` | Side-by-side window-length comparison |

## Install

```bash
git clone https://github.com/shianjeng/spectral-forensics.git
cd spectral-forensics && pip install -e .
```

`ffmpeg` is required for video output and for decoding mp3/m4a.

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
sonogram reassign track.flac --hop 256 --side-by-side
```

```
锐度 (谱集中度): 普通 5.116 → 重分配 5.389
```

A test in `tests/test_audit_reassign.py` states the claim numerically: for a
1 kHz tone with `n_fft=2048` at 22.05 kHz (Δf = 10.8 Hz), the
magnitude-weighted spread of reassigned frequency estimates stays **under
one FFT bin**.

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
sonogram audit ~/Music --recursive --verbose
```

```
✓ 01 - genuine.flac         cut= 22.1k
⚠ 02 - suspicious.flac      cut= 16.0k   90%  → mp3 ~128 kbps 或 AAC ~128 kbps
    · 截止处 1 kHz 内再跌 74 dB，呈砖墙特征
? 03 - borderline.flac      cut= 18.8k   55%  → mp3 ~192 kbps
· 04 - honest.mp3           cut= 16.0k
    · 声明 320 kbps，频谱只支持 mp3 ~128 kbps

共 4 个文件，1 个可疑，1 个存疑。
```

Three independent pieces of evidence, because any one alone produces false
positives (old recordings and solo acoustic material genuinely lack high
frequencies):

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

Verdicts come in three tiers: `⚠ suspect` (lowpass **and** a brick wall,
usually landing on a known encoder cutoff), `? likely` (a lowpass with no
corroborating evidence), and `✓ clean`.

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
MDCT-periodicity detectors were prototyped and **did not separate the
classes on the test material**, so they are not shipped. Read a `✓` as "no
lowpass evidence", not as proof of provenance.

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
sonogram edit track.wav --reject 2000:4000          # drop a band
sonogram edit track.wav --keep 80:250               # isolate the bass
sonogram edit track.wav --denoise
sonogram edit track.wav --mask painted.png          # paint in any image editor
```

Band rejection measured on a three-tone mixture: target band down more than
30 dB, neighbouring bands within 5 % of their original energy.

Denoising is spectral gating with a **minimum-statistics** noise floor — for
each frequency bin, a low percentile across the whole file, on the
assumption that every bin falls quiet at some point. Honest numbers on a
noisy version of the demo track:

| Input SNR | After | Δ |
|---|---|---|
| 17.0 dB | 16.9 dB | −0.2 |
| 9.1 dB | 11.8 dB | **+2.7** |
| 3.1 dB | 6.5 dB | **+3.4** |

It helps when there is real noise and mildly hurts when there is not — the
gate's own distortion outweighs what it removes. Stationary material (a tone
that never stops) breaks the minimum-statistics assumption outright; pass an
explicit noise region instead.

**Griffin-Lim** (`sonify`) — when the magnitude is invented, no phase exists
to keep. Griffin-Lim alternates projections between "is a real signal" and
"has this magnitude" until a self-consistent phase falls out. It only
converges to a local solution, so a metallic quality is inherent, not a bug.

```bash
sonogram sonify photo.jpg --preview roundtrip.png
```

![photo round trip](examples/photo_roundtrip.png)

*A picture, encoded as a magnitude spectrum, resynthesised into a 10-second
wav, then re-analysed. The ridge, moon and stars survive the trip.*
Spectral convergence falls 0.345 → 0.241 → 0.207 → 0.196 at 1 / 8 / 32 / 64
iterations.

---

## 4. Posters, video, window comparison

```bash
sonogram poster  track.mp3 --transform cqt --palette bloom
sonogram video   track.mp3 --size 1920x1080 --fps 30 --bars 128
sonogram compare track.mp3 --n-ffts 512,2048,8192
```

![window comparison](examples/compare_nfft.png)

Short windows resolve every drum hit and smear the chords; long windows pin
the harmonics to a few Hz and smear every transient across 372 ms. Δt·Δf = 1
throughout — no setting wins both.

Video frames are rasterised in pure NumPy and piped straight into `ffmpeg`
over `stdin`: no matplotlib per frame, no intermediate PNGs.

Palettes (`ember`, `abyss`, `mono`, `bloom`) are perceptually monotonic.
`jet` is deliberately absent — its non-uniform lightness invents banding
that is not in the data.

---

## Layout

```
sonogram/
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
pytest -q     # 33 passed
```

Covers: Δt·Δf = 1 across window lengths; a 1 kHz tone peaking within one
bin; reassignment measurably sharpening a chirp on an identical grid;
synthetic brick-wall cutoffs at 12/16/19 kHz recovered to within 500 Hz; a
gentle 6 dB/oct rolloff *not* being flagged as an encoder cutoff; an exact
STFT→ISTFT round trip; band rejection leaving neighbouring bands intact; and
Griffin-Lim error decreasing monotonically with iteration count. Plus CLI
smoke tests that actually execute every subcommand — `--help` passing is not
evidence that a command runs.

## Roadmap

- Psychoacoustic masking overlay — dim what is physically present but
  inaudible, which is exactly what the encoder decided to throw away
- A lowpass-independent transcode detector that survives validation
- Interactive painting UI instead of round-tripping through a PNG mask

## Licence

MIT. The demo track is generated by `examples/make_demo_audio.py`; do not commit
commercial recordings to this repository.
