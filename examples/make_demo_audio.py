"""生成一段无版权的合成音频作为示例（和弦进行 + 鼓点 + 旋律）。"""
from pathlib import Path

import numpy as np
import soundfile as sf

sr = 44100; bpm = 100; beat = 60 / bpm; bars = 8
dur = bars * 4 * beat
t = np.linspace(0, dur, int(sr * dur), endpoint=False)
y = np.zeros_like(t)

def note(f, start, length, amp=0.2, harmonics=5):
    n0, n1 = int(start * sr), int((start + length) * sr)
    n1 = min(n1, len(t)); 
    if n1 <= n0: return
    tt = np.arange(n1 - n0) / sr
    env = np.exp(-2.5 * tt / max(length, 1e-6)) * (1 - np.exp(-tt / 0.008))
    s = sum(np.sin(2*np.pi*f*k*tt) / k**1.6 for k in range(1, harmonics+1))
    y[n0:n1] += amp * env * s

def kick(start):
    n0 = int(start*sr); n1 = min(n0 + int(0.25*sr), len(t))
    tt = np.arange(n1-n0)/sr
    f = 120*np.exp(-28*tt) + 45
    y[n0:n1] += 0.55*np.exp(-12*tt)*np.sin(2*np.pi*np.cumsum(f)/sr)

def hat(start):
    n0 = int(start*sr); n1 = min(n0 + int(0.06*sr), len(t))
    tt = np.arange(n1-n0)/sr
    y[n0:n1] += 0.10*np.exp(-70*tt)*np.random.randn(n1-n0)

hz = lambda n: 440.0 * 2 ** ((n - 69) / 12)
chords = [[57,60,64,67],[53,57,60,64],[55,59,62,65],[52,55,59,62]]
mel = [76,79,81,84,83,79,76,74]

for b in range(bars):
    ch = chords[b % 4]; t0 = b * 4 * beat
    for m in ch: note(hz(m-12), t0, 4*beat, amp=0.13, harmonics=6)
    note(hz(mel[b % len(mel)]), t0 + beat, 1.6*beat, amp=0.22, harmonics=4)
    note(hz(mel[(b+3) % len(mel)]), t0 + 2.5*beat, 1.2*beat, amp=0.18, harmonics=4)
    for k in range(4):
        if k in (0, 2): kick(t0 + k*beat)
        hat(t0 + k*beat); hat(t0 + (k+0.5)*beat)

y /= np.max(np.abs(y)) * 1.05
sf.write(str(Path(__file__).parent / "demo_track.wav"), y.astype(np.float32), sr)
print(f"{dur:.1f}s written")
