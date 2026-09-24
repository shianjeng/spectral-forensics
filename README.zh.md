# spectral-forensics

[![tests](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml/badge.svg)](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

[English](README.md) · **中文** · [日本語](README.ja.md)

**那个 FLAC，其实是 mp3 换了个壳吧？** 所有有损编码器都会把某个截止频率以上的内容整块丢掉，这道“悬崖”在转回无损格式之后依然存在。这个工具扫描整个音乐库，告诉你哪些文件值得查看——并且明明白白地写出它自己抓不到什么。

**[→ 在浏览器里直接试](https://shianjeng.github.io/spectral-forensics/?lang=zh)**——拖入一个文件，就能看到判定结果和它的时频图（STFT 或重分配）。不上传任何东西。

![transcode cliffs](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/audit_cliffs.png)

上：同一段 12 秒的音频，左边是真无损 FLAC，右边经过了 128 kbps mp3 往返。16.7 kHz 以上的内容被丢掉了，转回 FLAC 也找不回来。下：同一段音频用 LAME 分别以 96、128、192 kbps 编码，再转回 FLAC。在各自的截止频率以下，曲线与真无损的那条无法区分；截止频率以上，每个编码器的砖墙都正好立在 `spf audit` 报告的位置。用 `python examples/make_audit_figure.py` 可以重新生成（需要带 libmp3lame 的 ffmpeg）。

这个检测器只是同一套频谱机制上的四样东西之一。另外三样：在频域里编辑声音再逆变换回波形、把时频图锐化到超越时频不确定性下限，以及渲染声纹海报和频谱视频。

---

## 安装

```bash
pip install spectral-forensics
```

需要 Python 3.11 或更新版本。安装后的命令是 `spf`（全名 `spectral-forensics`）。`ffmpeg` 是可选的——输出视频以及解码某些 mp3/m4a 文件时才需要。查看当前环境：

```bash
spf check
```

如果需要示例和测试，从源码安装：

```bash
git clone https://github.com/shianjeng/spectral-forensics.git
cd spectral-forensics
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python examples/make_demo_audio.py      # 下文用到的演示音轨
```

---

## 功能一览

| 命令 | 用途 |
|---|---|
| `audit` | 在整个音乐库里检测有损转码 |
| `edit` | 在频域编辑，保留原始相位重建音频 |
| `sonify` | 把图片编码进频谱，再合成成音频 |
| `reassign` | 重分配谱——分辨率超越 Δt·Δf ≥ 1 |
| `poster` | 静态声纹海报（STFT / mel / CQT） |
| `video` | 频谱视频，并混入原始音轨 |
| `compare` | 不同窗长并排对比 |
| `check` | 报告运行环境：Python 版本、ffmpeg、哪些功能可用 |

---

## 1. 真的是无损吗？

```bash
spf audit ~/Music --recursive --verbose
```

```
✓ 01 - genuine.flac         cut= 22.1k
⚠ 02 - suspicious.flac      cut= 16.0k   90%  → mp3 ~128 kbps
? 03 - borderline.flac      cut= 18.8k   55%  → mp3 ~192 kbps
· 04 - honest.mp3           cut= 16.0k
```

### 不用安装，直接试

[shianjeng.github.io/spectral-forensics](https://shianjeng.github.io/spectral-forensics/?lang=zh)用 Web Audio API 在浏览器里运行同样的截止频率、陡峭度和强度立体声检测。文件在本机解码和分析，不会离开你的电脑。

判定结果下面是时频图，mp3 的低通在上面表现为一块平直的“天花板”。可以选 STFT 或重分配（第 3 节），窗长 512 / 2048 / 8192 采样点，频率轴对数或线性，四种配色，动态范围可调，并标出检测到的截止频率。鼠标悬停可以读出时间、频率和电平，点击就从那个位置开始播放。

什么都没载入时，页面处于归零状态：判定显示“尚未载入”，各项数值都是“—”，两张图只有空坐标轴。拖入一个文件，或者从三个示例中选一个：经过 128 kbps mp3 往返的片段、编码前的那个真无损 FLAC，以及用来对比窗长的合成信号（扫频、纯音与脉冲）。每个来源只解码一次，切回去不用等；点**清除**就回到归零状态。长时频谱上会叠加一条绿色的真无损 FLAC 参考线。在 mp3 示例上，两条曲线一直重合到 16.7 kHz，之后只有一条还在继续——整个论点就在这一张图里。鼠标悬停可以读出任意频率上两条曲线各自的电平。横向拖动可以放大某一频段，拖出一个框则连电平一起放大，双击复位；点“截止附近”会直接放大到悬崖那一段。拖动图下方的手柄可以调整图的高度。纵轴会按可见范围内的数据自动适配，曲线不会被截掉。

每个示例都有自己的链接：[`?sample=mp3`](https://shianjeng.github.io/spectral-forensics/?sample=mp3&lang=zh)、[`?sample=genuine`](https://shianjeng.github.io/spectral-forensics/?sample=genuine&lang=zh)、[`?sample=synth`](https://shianjeng.github.io/spectral-forensics/?sample=synth&lang=zh)。页面支持英文、中文和日文（`?lang=en`、`zh`、`ja`）。字体由仓库自己提供，所以除了 GitHub Pages 本身，页面不会发出任何网络请求。

JavaScript 版不只是参照 Python 版写的，而是用测试保证两者一致。`tests/test_web_parity.py` 把同样的信号喂给两边，断言它们落在同一个 FFT 频点上，并且对自带示例给出相同的判定。`tests/test_web_spectrogram.py` 逐个频点把 STFT 与`librosa.stft` 比对，把每个重分配点与 `librosa.reassigned_spectrogram` 比对。示例音频用 `python examples/make_web_samples.py` 重新生成。

移植这件事立刻就回本了：JavaScript 版在一个 16 kHz 砖墙上和 Python 版结论不同，而**错的是 Python 版**。`librosa.stft` 默认会在两端补零，补零边界上的台阶是宽带的，所以第一帧和最后一帧的频谱是满的。在短片段上，这两帧在 95 百分位里的分量足以把截止频率完全掩盖。改成 `center=False` 就修好了，结果也不再依赖片段长度。

采用三条相互独立的证据，因为任何一条单独使用都会误报——老录音和纯原声的素材本来就缺高频：

1. **截止频率**——仍然带有真实能量的最高频率，取自 95 百分位的长时频谱。用百分位而不用平均值，是因为安静段落会把平均值拖进底噪，而单纯取最大值又会被个别瞬态牵着走。
2. **陡峭度**——从截止频率往上 1 kHz 之内，电平还会再下降多少。编码器的砖墙会下降 20 dB 以上，自然滚降不会。
3. **强度立体声**——有损编码器会在高频把左右声道合并成“单声道加声像权重”，所以侧信号`(L−R)/2` 会在某个频率以上消失。这条线索与低通无关，而且很难伪造。

判定分三档：`⚠ 可疑`（有低通**并且**有砖墙，通常正好落在已知编码器的截止频率上）、`? 存疑`（有低通，但没有其他证据佐证）和 `✓ 干净`。设中间这一档，是为了让本来就发闷的录音被标出来去听一听，而不是直接被定罪。

它也能抓反过来的情况：标称 320 kbps、频谱却只达到 128 kbps 水平的 mp3，是从低码率源重新编码出来的。

### 验证

用 ffmpeg 构造的真值——同一个音源以几种截止频率编码，再转回 FLAC：

| 文件 | 真实截止 | 检测结果 | 判定 |
|---|---|---|---|
| `original.wav` | 无 | 22.1 kHz | ✓ 干净 |
| `genuine.flac` | 无 | 22.1 kHz | ✓ 干净 |
| `cut_15000.flac` | 15.0 kHz | 15.3 kHz | ⚠ → ~112 kbps |
| `cut_16000.flac` | 16.0 kHz | 16.0 kHz | ⚠ → ~128 kbps |
| `cut_17500.flac` | 17.5 kHz | 17.4 kHz | ⚠ → ~160 kbps |
| `cut_19000.flac` | 19.0 kHz | 18.8 kHz | ⚠ → ~192 kbps |

### 与现有工具的比较

[Spek](https://www.spek.cc/) 给你画出时频图，判断留给你自己——看单个文件很好用，面对四万首的音乐库就无能为力了。*fakin' the funk?!* 能自动判断，但闭源且只支持 Windows。这个项目提供一个开源命令行工具：扫描整个目录树、报告推断码率、导出可分享的 HTML 报告，并且——这是大多数工具略过的部分——写明它自己会在哪里失手。

### 批量报告

```bash
spf audit ~/Music --recursive --html report.html
```

一个自包含的 HTML 文件：每个被标记的音轨都附带自己的长时频谱，并标出检测到的截止频率。证据跟着判定一起走，而不是在终端里滚出屏幕。

### 20 kHz 的问题

陡峭的滚降不等于压缩的证据。母带处理链和某些 ADC 的抗混叠滤波器也会做低通，其中一个位置就在 20 kHz 附近——而 LAME 在 320 kbps 时也把截止频率放在那里。在频域里，这两者是同一幅画面。

在不同频率上放砖墙的合成无损文件上实测：

| 低通 | 判定 |
|---|---|
| 21.5 kHz | ✓ 干净 |
| 21.0 kHz | ✓ 干净 |
| 20.5 kHz | ? 存疑 |
| 20.0 kHz | ? 存疑 |
| 19.0 kHz | ⚠ 可疑 |
| 16.0 kHz | ⚠ 可疑 |

两条规则保证它说实话。距离奈奎斯特频率 1.2 kHz 以内的一律算全频带，所以 21 kHz 的 ADC 滤波器根本不会被计分。而在 19.8 到 21.6 kHz 之间，“正好落在已知编码器截止频率上”的加分被取消，判定最高只到 `存疑`——除非有与低通无关的证据（强度立体声）佐证。上面的真值表不受这两条规则影响：每个真正转码过的文件仍然都被抓到了。

这个问题要归功于一位读者：对方指出 ADC 也会做砖墙滤波。这个提醒是对的，这层推理确实需要写明；对方举的那个具体情况（21 kHz）其实已经处理了，但顺着查下去，发现真正的漏洞在 20 kHz。

### 已知局限

**完全不做**硬低通的编码器——较高码率下 ffmpeg 自带的 AAC、Opus——能绕过截止频率检测，在一次实测中工具把这样的文件判成了干净。目前随附的、与低通无关的检测（强度立体声）对单声道素材无能为力。频谱空洞和 MDCT 周期性检测器都做过原型，但**在测试素材上无法把两类区分开**，所以没有随附。请把 `✓` 理解为“没有低通的证据”，而不是来源的证明。

---

## 2. 可逆编辑

时频图不再是流水线的终点，而是变成可以编辑的介质。两条重建路径，对应两种不同的情况：

**保留相位**（`edit`）——只改幅度，保留原始相位，直接做逆 STFT。所有遮罩操作都走这条路。用恒等遮罩时，往返误差在数值精度以内：

```
||y' − y|| / ||y||  =  1.3e-08      (−158 dB)
```

```bash
spf edit track.wav --reject 2000:4000          # 去掉一个频段
spf edit track.wav --keep 80:250               # 只留下低音
spf edit track.wav --denoise
spf edit track.wav --mask painted.png          # 在任何图片编辑器里画遮罩
```

在三音混合信号上测量频段抑制：目标频段下降超过 30 dB，相邻频段的能量与原来相差不到 5%。

降噪是基于**最小统计**底噪估计的频谱门限——对每个频点，取整个文件上的一个低百分位，前提是每个频点总有安静的时候。在加了噪声的演示音轨上实测，如实列出：

| 输入信噪比 | 处理后 | Δ |
|---|---|---|
| 17.0 dB | 16.9 dB | −0.2 |
| 9.1 dB | 11.8 dB | **+2.7** |
| 3.1 dB | 6.5 dB | **+3.4** |

有真实噪声时有帮助，没有时反而略有损害——门限本身带来的失真超过了它去掉的东西。平稳素材（一个从不停止的音）会直接打破最小统计的前提，因为这个音会把自己估计成底噪；这时请明确指定一段噪声区域。

**Griffin-Lim**（`sonify`）——当幅度是凭空构造的，就没有相位可以保留。Griffin-Lim 在“是一个真实信号”和“具有这个幅度”两个约束之间交替投影，直到得出一个自洽的相位。它只收敛到局部解，所以那种金属质感是算法固有的，不是 bug。

```bash
spf sonify photo.jpg --preview roundtrip.png
```

![source photo](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/source_photo.png)

输入：一张普通的灰度图。

![photo round trip](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/photo_roundtrip.png)

往返后的输出：图片被编码成幅度谱，合成为 10 秒的 wav，再只凭音频重新分析。山脊、月亮和星星都挺过了这一趟。频谱收敛度在 1 / 8 / 32 / 64 次迭代时依次为0.345 → 0.241 → 0.207 → 0.196。

---

## 3. 重分配谱

在普通时频图里，一个纯音总是画成一条“带”。这个宽度是窗强加的，不是信号本身的——它直接来自

```
Δt = n_fft / sr     Δf = sr / n_fft     Δt · Δf = 1
```

但一个 STFT 频点携带的不只是幅度，还有相位。对相位求偏导，就能找回频点内部的能量实际在哪里：

```
瞬时频率   ω̂ = ω − ∂φ/∂t
群延迟     t̂ = t + ∂φ/∂ω
```

把每个频点的能量从它的格子挪到 `(t̂, ω̂)`，画面就会比不确定性下限更锐利。这并不违反它：这个下限约束的是**单个时频原子的宽度**，而不是**估计其能量位置的精度**——正是同一个区别，让显微镜里的质心定位能突破衍射极限。

```bash
spf reassign track.flac --hop 256 --side-by-side
```

![reassigned vs standard](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/reassign_compare.png)

同一段音频、同样的窗、同样的网格。上：常规 STFT。下：重分配之后。谐波收拢成发丝般的细线，底鼓的音高滑动——在上图里看不见——变成一条可以读的曲线。

```
sharpness (spectral concentration): standard 5.116 → reassigned 5.389
```

有一个测试用数字而不是肉眼来陈述这个结论：对 22.05 kHz 下 `n_fft=2048`（Δf = 10.8 Hz）的1 kHz 纯音，按幅度加权的重分配频率估计的离散度**不到一个 FFT 频点**。

局限：重分配依赖相位导数有意义，所以相互重叠的分音和低信噪比区域会散开。低于 `--mag-top-db` 的部分直接丢弃，而不是当作噪声画出来。

![reassigned poster](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/poster_reassigned.png)

---

## 4. 声纹海报、视频、窗长对比

```bash
spf poster  track.mp3 --transform cqt --palette bloom
spf video   track.mp3 --size 1920x1080 --fps 30 --bars 128
spf compare track.mp3 --n-ffts 512,2048,8192
```

![window comparison](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/compare_nfft.png)

短窗能分辨每一下鼓点，却把和弦抹成一片；长窗能把谐波钉在几 Hz 之内，却把每个瞬态抹开到372 ms。自始至终 Δt·Δf = 1——没有哪个设置能两头都赢。

视频帧用纯 NumPy 栅格化，经 `stdin` 直接送进 `ffmpeg`：不用每帧调用 matplotlib，没有中间 PNG，在 1280×720 / 30 fps 下比实时还快。

配色（`ember`、`abyss`、`mono`、`bloom`）的亮度在感知上单调递增。刻意不提供 `jet`——它不均匀的亮度会凭空造出数据里没有的条带。

---

## 目录结构

```
spectral_forensics/
├── io.py          解码 → 单声道 → 重采样（m4a 退回 ffmpeg）
├── transform.py   STFT / mel / CQT      （numpy 进，numpy 出）
├── reassign.py    相位导数重分配 + 栅格化
├── invert.py      遮罩、频谱门限、Griffin-Lim、图片 → 音频
├── audit.py       截止频率 / 陡峭度 / 强度立体声 取证
├── render.py      矩阵 → 图像        （不含音频代码）
├── video.py       ffmpeg 管道
└── cli.py         argparse 入口

docs/              浏览器演示——静态文件，GitHub Pages 原样提供
├── analysis.js    audit + STFT + 重分配，从上面的 Python 移植
├── app.js         页面本身
├── i18n.js        英文 / 中文 / 日文文案
├── fonts/         Geist、Geist Mono、Instrument Serif（SIL OFL 1.1）
└── samples/       由 examples/make_web_samples.py 生成
```

`transform.py` 从不导入 matplotlib，`render.py` 从不导入 librosa，所以两半都可以单独使用。

## 测试

```bash
pytest -q     # 67 passed
```

每次推送，CI 都会在 Python 3.11 到 3.14 上跑一遍测试，每周一再跑一次。每周跑是因为依赖没有锁定版本：上游的变化应该先在 CI 里暴露，而不是先在某个人的安装里暴露。

除了“不崩溃”之外，测试断言的内容：各种窗长下 Δt·Δf = 1；1 kHz 纯音的峰值落在一个 FFT 频点之内；在同一网格上重分配确实让线性调频信号变锐利；12/16/19 kHz 的合成砖墙截止被还原到 500 Hz 以内；平缓的 6 dB/oct 滚降**不会**被当成编码器截止；STFT→ISTFT 往返精确；频段抑制不影响相邻频段；Griffin-Lim 误差随迭代次数单调下降；以及浏览器演示的 JavaScript 逐个频点与 Python 和 librosa 一致。

浏览器相关的测试在 Node 下运行 JavaScript，没有 Node 时会跳过。这在本地很方便，在 CI 里却很危险：一个没装 Node 的运行器会报绿，实际上什么都没测。所以 CI 会安装 Node 并设置 `SPF_REQUIRE_NODE=1`，把跳过变成失败。CI 还会对 `docs/` 里的每个脚本执行 `node --check`，因为页面没有构建步骤来提前拦住语法错误。

还有冒烟测试会实际执行每个子命令。之所以需要它们，是因为 `--help` 通过什么也证明不了——argparse 从不调用处理函数，所以一个处理函数被删掉的子命令，顺利通过了 `--help` 检查，就这样坏着发布了出去。

### CI 抓到的问题

两个真实的缺陷，在开发机上都看不出来：

- **`audit` 因 `NameError` 崩溃。** 它的处理函数在之前一次编辑中丢了 `def` 那一行，函数体变成了另一个函数里执行不到的代码。命令行冒烟测试现在覆盖了这一点。
- **Griffin-Lim 在 librosa 0.x 上出错。** 代码传的是 librosa 1.0 的 `rng` 参数，而 `pyproject.toml`声明的是 `librosa>=0.10`，在那些版本里同一个参数叫 `random_state`。在声明范围内安装的人都会遇到`TypeError`。3.11 那个任务解析到了较旧的 librosa，把它暴露了出来；现在改为运行时检测该用哪个关键字。

两者有一个值得点明的共同形态：声明的支持范围比代码实际支持的范围更宽——而这正是单一开发环境看不见的缺口。

## 参考文献

这里的算法不是我的；实现和验证是。

- K. Kodera, R. Gendrin, C. de Villedary (1978). *Analysis of time-varying signals with small BT values.* IEEE Trans. ASSP **26**(1), 64–76. ——重分配的最初构想。
- F. Auger, P. Flandrin (1995). *Improving the readability of time-frequency and time-scale representations by the reassignment method.* IEEE Trans. Signal Processing **43**(5), 1068–1089. ——本实现遵循的一般框架。
- D. Griffin, J. Lim (1984). *Signal estimation from modified short-time Fourier transform.* IEEE Trans. ASSP **32**(2), 236–243. ——`sonify` 使用的相位重建。
- R. Martin (2001). *Noise power spectral density estimation based on optimal smoothing and minimum statistics.* IEEE Trans. Speech and Audio Processing **9**(5), 504–512. ——`edit --denoise` 使用的底噪估计。
- J. Brown (1991). *Calculation of a constant Q spectral transform.* JASA **89**(1), 425–434. ——`--transform cqt` 的基础。

## 路线图

- 心理声学掩蔽叠加层——把物理上存在但听不见的部分调暗，这正是编码器决定丢掉的东西
- 一个能通过验证的、与低通无关的转码检测器
- 交互式绘制界面，不必再经由 PNG 遮罩往返

## 许可证

MIT。演示音轨由 `examples/make_demo_audio.py` 生成；请不要把商业录音提交到这个仓库。
