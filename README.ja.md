# spectral-forensics

[![tests](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml/badge.svg)](https://github.com/shianjeng/spectral-forensics/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

[English](README.md) · [中文](README.zh.md) · **日本語**

**その FLAC、実は mp3 を詰め替えただけでは？** 非可逆エンコーダーはどれも、
ある周波数（カットオフ）より上を捨てる。その「崖」はロスレス形式に変換し直しても
残る。このツールはライブラリ全体をスキャンして確認すべきファイルを挙げ、
さらに自分が見抜けないものについても正直に明記する。

**[→ ブラウザで試す](https://shianjeng.github.io/spectral-forensics/)**
— ファイルをドロップすると、判定とスペクトログラム（STFT または再割り当て）が
表示される。アップロードは一切しない。

![transcode cliffs](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/audit_cliffs.png)

*同じ音源を 3 種類のビットレートでエンコードし、FLAC に戻したもの。カットオフより
下では 4 本の曲線は見分けがつかない。その上では、各エンコーダーの「レンガの壁」が
検出器の示す位置にそびえている。`python examples/make_audit_figure.py` で再現できる。*

この検出器は、同じスペクトル解析の基盤の上に作った 4 つの機能のひとつにすぎない。
残りの 3 つは、周波数領域で音を編集して波形に戻すこと、時間–周波数の不確定性の
限界を超えてスペクトログラムを鮮明にすること、そしてポスターやスペクトル動画の
書き出しである。

---

## インストール

```bash
pip install spectral-forensics
```

Python 3.11 以上。コマンドは `spf`（正式名 `spectral-forensics` でも可）。
`ffmpeg` は任意で、動画出力と一部の mp3/m4a のデコードに必要になる。
手元の環境で何が使えるかは次で確認できる：

```bash
spf check
```

サンプルやテストも使うならソースから：

```bash
git clone https://github.com/shianjeng/spectral-forensics.git
cd spectral-forensics
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python examples/make_demo_audio.py      # 以下で使うデモ曲
```

---

## できること

| コマンド | 用途 |
|---|---|
| `audit` | 音楽ライブラリから非可逆トランスコードを検出する |
| `edit` | 周波数領域で編集し、元の位相で再構成する |
| `sonify` | 画像をスペクトルに埋め込み、音声として再合成する |
| `reassign` | 再割り当てスペクトログラム — Δt·Δf ≥ 1 を超える解像度 |
| `poster` | 静止画のソノグラム（STFT / mel / CQT） |
| `video` | 元の音声を多重化したスペクトル動画 |
| `compare` | 窓長ごとの並列比較 |
| `check` | 環境レポート：Python のバージョン、ffmpeg、使える機能 |

---

## 1. それ、本当にロスレス？

```bash
spf audit ~/Music --recursive --verbose
```

```
✓ 01 - genuine.flac         cut= 22.1k
⚠ 02 - suspicious.flac      cut= 16.0k   90%  → mp3 ~128 kbps
? 03 - borderline.flac      cut= 18.8k   55%  → mp3 ~192 kbps
· 04 - honest.mp3           cut= 16.0k
```

### インストールせずに試す

[shianjeng.github.io/spectral-forensics](https://shianjeng.github.io/spectral-forensics/)
では、カットオフ・急峻さ・インテンシティ・ステレオの 3 つのテストを Web Audio API で
ブラウザ内実行する。ファイルはローカルでデコード・解析され、マシンの外には出ない。

判定の下にはスペクトログラムがあり、mp3 のローパスは平らな「天井」として目に見える。
表示方法は STFT と再割り当て（3 章）から選べる。窓長は 512 / 2048 / 8192 サンプル、
周波数軸は対数と線形、配色は 4 種類から選択でき、ダイナミックレンジも調整できる。
検出したカットオフも線で示す。カーソルを重ねると時刻・周波数・レベルを読み取れ、
クリックするとその位置から再生する。

何も読み込んでいないとき、ページはゼロの状態にある。判定は「未読み込み」、数値は
すべて「—」、2 つのグラフは空の座標軸だけだ。ファイルをドロップするか、3 つの
サンプルから選ぶ：128 kbps の mp3 を経由したクリップ、そのエンコード前の本物の FLAC、
窓長の違いを見比べるための合成信号（スイープ・純音・クリック）。どれもデコードは
一度だけなので、戻るときは待ち時間がない。**クリア**を押すとゼロの状態に戻る。
長時間スペクトルには本物の FLAC が緑の参考線として重なる。mp3 のサンプルでは
2 本の曲線が 16.7 kHz まで一致し、そこから先は片方しか続かない。主張のすべてが
1 枚に収まっている。カーソルを重ねると任意の周波数で両方のレベルを読み取れる。

サンプルにはそれぞれ直接リンクがある：
[`?sample=mp3`](https://shianjeng.github.io/spectral-forensics/?sample=mp3&lang=ja)、
[`?sample=genuine`](https://shianjeng.github.io/spectral-forensics/?sample=genuine&lang=ja)、
[`?sample=synth`](https://shianjeng.github.io/spectral-forensics/?sample=synth&lang=ja)。
ページは英語・中国語・日本語に対応している（`?lang=en`、`zh`、`ja`）。フォントは
リポジトリから配信しているので、GitHub Pages 自体を除けば外部への通信は一切ない。

JavaScript 版は Python 版を参考にしただけではなく、Python 版と一致することを
テストで保証している。`tests/test_web_parity.py` は同一の信号を両方に与え、
同じ FFT ビンに着地すること、同梱サンプルで同じ判定になることを確かめる。
`tests/test_web_spectrogram.py` は STFT を `librosa.stft` とビン単位で、
再割り当ての各点を `librosa.reassigned_spectrogram` と一点ずつ照合する。
サンプルは `python examples/make_web_samples.py` で作り直せる。

移植はすぐに元が取れた。16 kHz のレンガの壁で JavaScript 版と Python 版の結果が食い違い、
**間違っていたのは Python 版の方**だった。`librosa.stft` はデフォルトで両端を
パディングし、パディング境界の段差は広帯域なので、最初と最後のフレームは全帯域の
スペクトルを持ってしまう。短いクリップではこの 2 フレームが 95 パーセンタイルに
十分効いてしまい、カットオフが完全に隠れる。`center=False` を渡して修正し、
結果がクリップ長に依存しなくなった。

証拠は互いに独立な 3 種類を使う。どれか 1 つだけでは誤検出が出るからだ —
古い録音やアコースティックのソロ演奏は、本当に高域を持っていないことがある：

1. **カットオフ周波数** — 実際にエネルギーが残っている最も高い周波数。
   95 パーセンタイルの長時間スペクトルから求める。平均ではなくパーセンタイルを
   使うのは、静かな区間が平均をノイズフロアまで引き下げる一方、単純な最大値は
   単発のトランジェントに引っぱられるからだ。
2. **急峻さ** — カットオフから 1 kHz 上までに、レベルがさらにどれだけ落ちるか。
   エンコーダーのレンガの壁は 20 dB 以上落ちるが、自然な減衰はそうならない。
3. **インテンシティ・ステレオ** — 非可逆コーデックは高域で L/R を
   モノラル＋定位情報にまとめるため、ある周波数より上でサイド信号 `(L−R)/2` が
   消える。ローパスとは独立で、偽装も難しい。

判定は 3 段階。`⚠ suspect`（ローパス**かつ**レンガの壁があり、たいてい既知の
エンコーダーのカットオフに一致する）、`? likely`（ローパスはあるが裏づけがない）、
そして `✓ clean`。中間の段階があるのは、もともと高域の乏しい録音を「告発」するのでは
なく、「一度聴いてみて」と知らせるためだ。

逆のケースも見抜く。320 kbps を名乗る mp3 のスペクトルが 128 kbps 相当しかなければ、
低ビットレートの音源から再エンコードされたものだ。

### 検証

ffmpeg で作った正解データ — 1 つの音源を複数のカットオフでエンコードし、
FLAC に戻したもの：

| ファイル | 真のカットオフ | 検出値 | 判定 |
|---|---|---|---|
| `original.wav` | なし | 22.1 kHz | ✓ clean |
| `genuine.flac` | なし | 22.1 kHz | ✓ clean |
| `cut_15000.flac` | 15.0 kHz | 15.3 kHz | ⚠ → ~112 kbps |
| `cut_16000.flac` | 16.0 kHz | 16.0 kHz | ⚠ → ~128 kbps |
| `cut_17500.flac` | 17.5 kHz | 17.4 kHz | ⚠ → ~160 kbps |
| `cut_19000.flac` | 19.0 kHz | 18.8 kHz | ⚠ → ~192 kbps |

### 既存ツールとの比較

[Spek](https://www.spek.cc/) はスペクトログラムを描いて判断を人に委ねる。
1 ファイルなら優秀だが、4 万曲のライブラリには使えない。*fakin' the funk?!* は
判断まで自動化するが、クローズドソースで Windows 専用だ。このプロジェクトは、
ツリー全体をスキャンし、推定ビットレートを報告し、共有できる HTML レポートを
書き出し、そして多くのツールが省く部分 — 自分の失敗パターン — を明記する
オープンソースの CLI である。

### 一括レポート

```bash
spf audit ~/Music --recursive --html report.html
```

単体で完結する HTML ファイル 1 つ。フラグが立った曲にはそれぞれ、検出した
カットオフ付きの長時間スペクトルが添えられる。証拠が判定と一緒に持ち運べるので、
ターミナルのスクロールに流れて消えることがない。

### 20 kHz 問題

急峻な減衰は圧縮の証拠にはならない。マスタリングのチェーンや一部の ADC の
アンチエイリアス・フィルターもローパスをかけ、その位置のひとつが 20 kHz 付近 —
LAME が 320 kbps でカットオフを置くのと同じ場所だ。周波数領域では、この 2 つは
まったく同じ絵になる。

さまざまな周波数にレンガの壁を入れた合成ロスレスファイルでの実測：

| ローパス | 判定 |
|---|---|
| 21.5 kHz | ✓ clean |
| 21.0 kHz | ✓ clean |
| 20.5 kHz | ? likely |
| 20.0 kHz | ? likely |
| 19.0 kHz | ⚠ suspect |
| 16.0 kHz | ⚠ suspect |

2 つのルールでこれを誠実に保っている。ナイキスト周波数から 1.2 kHz 以内は全帯域と
みなすので、21 kHz の ADC フィルターが点数になることはない。また 19.8〜21.6 kHz では
「既知のエンコーダーのカットオフに一致」の加点を与えず、ローパスとは独立な証拠 —
インテンシティ・ステレオ — が裏づけない限り、判定を `likely` で頭打ちにする。
上の正解データの表はこのルールの影響を受けない。本当にトランスコードされた
ファイルは、すべて引き続き検出される。

この問いを投げかけてくれたのは、「ADC もレンガの壁を作る」と指摘してくれた読者だ。
推論をきちんと書くべきだという指摘は正しかった。挙げられた具体例（21 kHz）はすでに
処理済みだったが、調べる過程で本当の穴が 20 kHz にあることが分かった。

### 既知の限界

ハードなローパスを**かけない**エンコーダー — 高ビットレートの ffmpeg ネイティブ AAC、
Opus — はカットオフのテストをすり抜け、ベンチマークではそうしたファイルを clean と
判定した。現在搭載しているローパス非依存のテスト（インテンシティ・ステレオ）は
モノラル素材には効かない。スペクトルの穴や MDCT の周期性を使う検出器も試作したが、
**テスト素材ではクラスを分離できなかった**ため搭載していない。`✓` は
「ローパスの証拠なし」と読むべきで、出自の証明ではない。

---

## 2. 可逆な編集

スペクトログラムはパイプラインの終点ではなく、編集できる媒体になる。
再構成の経路は 2 つあり、状況に応じて使い分ける：

**位相保存**（`edit`） — 振幅だけを変え、元の位相はそのまま残して、逆 STFT を直接かける。
マスク処理はすべてこの経路を通る。恒等マスクなら往復は数値精度の範囲で厳密だ：

```
||y' − y|| / ||y||  =  1.3e-08      (−158 dB)
```

```bash
spf edit track.wav --reject 2000:4000          # 帯域を除去
spf edit track.wav --keep 80:250               # ベースだけを抜き出す
spf edit track.wav --denoise
spf edit track.wav --mask painted.png          # 好きな画像エディタで描く
```

3 つの純音の混合で測った帯域除去：対象帯域は 30 dB 以上低下し、隣接帯域は
元のエネルギーの 5 % 以内に収まる。

ノイズ除去は**最小統計量**のノイズフロアを使ったスペクトル・ゲーティングだ。
各周波数ビンについてファイル全体での低いパーセンタイルを取る。どのビンもどこかで
静かになる、という仮定に基づいている。デモ曲にノイズを加えた版での正直な数字：

| 入力 SNR | 処理後 | Δ |
|---|---|---|
| 17.0 dB | 16.9 dB | −0.2 |
| 9.1 dB | 11.8 dB | **+2.7** |
| 3.1 dB | 6.5 dB | **+3.4** |

本当にノイズがあるときは効き、ないときはわずかに悪化する — ゲート自体の歪みが
取り除く分を上回るからだ。定常的な素材（鳴りやまない純音）は最小統計量の仮定を
根本から崩す。純音そのものがノイズフロアとして推定されてしまうので、その場合は
ノイズ区間を明示的に指定する。

**Griffin-Lim**（`sonify`） — 振幅を新たに作った場合、保存すべき位相はそもそも存在しない。
Griffin-Lim は「実信号であること」と「この振幅を持つこと」の間で射影を交互に繰り返し、
自己無撞着な位相を導き出す。収束するのは局所解だけなので、金属的な響きは仕様であって
バグではない。

```bash
spf sonify photo.jpg --preview roundtrip.png
```

![source photo](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/source_photo.png)

*入力：ごく普通のグレースケール画像。*

![photo round trip](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/photo_roundtrip.png)

*出力（往復後）：画像を振幅スペクトルとして埋め込み、10 秒の wav に再合成し、
その音声だけから再解析したもの。尾根も月も星も往復を生き延びている。*
スペクトル収束度は 1 / 8 / 32 / 64 回の反復で 0.345 → 0.241 → 0.207 → 0.196 と下がる。

---

## 3. 再割り当てスペクトログラム

通常のスペクトログラムでは、純音は必ず*帯*として描かれる。その幅は信号ではなく
窓が課したもので、次の関係の直接の帰結だ：

```
Δt = n_fft / sr     Δf = sr / n_fft     Δt · Δf = 1
```

しかし STFT のビンが持つのは振幅だけではない。位相もある。その位相の偏微分を取れば、
ビンの中でエネルギーが実際にどこにあるかが分かる：

```
瞬時周波数   ω̂ = ω − ∂φ/∂t
群遅延       t̂ = t + ∂φ/∂ω
```

各ビンのエネルギーをそのセルから `(t̂, ω̂)` へ移すと、絵は不確定性の限界より鮮明になる。
これは限界の破りではない。限界が縛っているのは*1 つの時間–周波数アトムの幅*であって、
*そのエネルギーの位置を推定する精度*ではない — 顕微鏡で重心の定位が回折限界を
超えられるのと同じ区別である。

```bash
spf reassign track.flac --hop 256 --side-by-side
```

![reassigned vs standard](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/reassign_compare.png)

*同じ音声、同じ窓、同じグリッド。上：通常の STFT。下：再割り当て後。倍音は髪の毛ほどの
細線に収束し、上では見えないキックドラムのピッチの下降が、読み取れる曲線になる。*

```
sharpness (spectral concentration): standard 5.116 → reassigned 5.389
```

この主張は目視任せにせず、テストで数値として確かめている。22.05 kHz で
`n_fft=2048`（Δf = 10.8 Hz）の 1 kHz の純音について、再割り当てした周波数推定値の
振幅重み付きの広がりは **1 FFT ビン未満**に収まる。

うまくいかない場合：再割り当ては位相の微分に意味があることを前提にしているので、
重なり合う部分音や低 SNR の領域では点が散らばる。`--mag-top-db` を下回る点は、
ノイズとして描くのではなく捨てる。

![reassigned poster](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/poster_reassigned.png)

---

## 4. ポスター、動画、窓長の比較

```bash
spf poster  track.mp3 --transform cqt --palette bloom
spf video   track.mp3 --size 1920x1080 --fps 30 --bars 128
spf compare track.mp3 --n-ffts 512,2048,8192
```

![window comparison](https://raw.githubusercontent.com/shianjeng/spectral-forensics/main/examples/compare_nfft.png)

短い窓はドラムの打撃を 1 つ残らず分解するが、和音はにじむ。長い窓は倍音を数 Hz の
精度で捉えるが、トランジェントはすべて 372 ms にわたってにじむ。どの窓でも
Δt·Δf = 1 — 両方を満たす設定は存在しない。

動画のフレームは純粋な NumPy でラスタライズし、`stdin` 経由で `ffmpeg` に直接流し込む。
フレームごとの matplotlib も中間 PNG もなく、1280×720 / 30 fps で実時間より速い。

配色（`ember`、`abyss`、`mono`、`bloom`）は知覚的に単調だ。`jet` はあえて外している —
明度が不均一なため、データにない縞模様を作り出してしまう。

---

## 構成

```
spectral_forensics/
├── io.py          デコード → モノラル化 → リサンプル（m4a は ffmpeg にフォールバック）
├── transform.py   STFT / mel / CQT      （numpy を受け取り numpy を返す）
├── reassign.py    位相微分による再割り当て + ラスタライズ
├── invert.py      マスク、スペクトル・ゲーティング、Griffin-Lim、画像 → 音声
├── audit.py       カットオフ / 急峻さ / インテンシティ・ステレオの鑑定
├── render.py      行列 → 画像          （音声処理のコードなし）
├── video.py       ffmpeg パイプ
└── cli.py         argparse のエントリポイント

docs/              ブラウザ版デモ — 静的ファイルで、GitHub Pages がそのまま配信する
├── analysis.js    audit + STFT + 再割り当て（上の Python からの移植）
├── app.js         ページ本体
├── i18n.js        英語 / 中国語 / 日本語の文言
├── fonts/         Geist、Geist Mono、Instrument Serif（SIL OFL 1.1）
└── samples/       examples/make_web_samples.py で生成
```

`transform.py` は matplotlib を import せず、`render.py` は librosa を import しない。
どちらの半分も単独で使える。

## テスト

```bash
pytest -q     # 67 passed
```

CI は push のたびに Python 3.11〜3.14 でテストを実行し、毎週月曜にも再実行する。
週次実行があるのは、依存関係のバージョンを固定していないからだ。上流の変化は、
誰かのインストールで表面化する前に CI で見つけたい。

「クラッシュしない」以上に、テストが確かめていること：窓長を変えても Δt·Δf = 1 で
あること、1 kHz の純音のピークが 1 FFT ビン以内に来ること、同一グリッド上で
再割り当てがチャープを測定可能なほど鮮明にすること、12/16/19 kHz の合成レンガの壁が
500 Hz 以内で復元されること、なだらかな 6 dB/oct の減衰がエンコーダーのカットオフと
*誤認されない*こと、STFT→ISTFT の往復が厳密であること、帯域除去が隣接帯域を
損なわないこと、Griffin-Lim の誤差が反復回数に対して単調に減ること、そして
ブラウザ版デモの JavaScript が Python 版および librosa とビン単位で一致すること。

ブラウザ版のテストは JavaScript を Node で実行し、Node がなければスキップする。
ローカルでは便利だが、CI では危険だ。Node のないランナーは何もテストせずに
緑を報告してしまう。そこで CI では Node をインストールしたうえで `SPF_REQUIRE_NODE=1` を
設定し、このスキップを失敗に変えている。さらに、ページには構文エラーを先に拾う
ビルド工程がないので、`docs/` のスクリプトすべてに `node --check` をかけている。

すべてのサブコマンドを実際に実行する CLI のスモークテストもある。`--help` が通っても
何の証明にもならないからだ — argparse はハンドラを呼ばないので、ハンドラが
削除されたサブコマンドが `--help` の一括チェックをすり抜け、壊れたまま出荷されたことがある。

### CI が見つけたもの

開発マシンでは見えなかった、実際の不具合が 2 つ：

- **`audit` が `NameError` でクラッシュした。** 以前の編集でハンドラの `def` 行が消え、
  本体が別の関数の中の到達不能なコードになっていた。現在は CLI のスモークテストが
  これをカバーしている。
- **librosa 0.x で Griffin-Lim が壊れていた。** コードは librosa 1.0 の `rng` 引数を
  渡していたが、`pyproject.toml` は `librosa>=0.10` を宣言しており、そちらでは同じ引数が
  `random_state` という名前だった。宣言した範囲内でインストールした人は `TypeError` に
  遭遇した。3.11 のジョブが古い librosa を解決したことで表面化し、現在はシード用の
  キーワードを実行時に判定している。

どちらにも名前をつけておく価値のある共通点がある。宣言したサポート範囲が、コードが
実際にサポートしている範囲より広かった — それこそ、単一の開発環境からは見えない隙間だ。

## 参考文献

アルゴリズムは私のものではない。実装と検証は私のものだ。

- K. Kodera, R. Gendrin, C. de Villedary (1978). *Analysis of time-varying
  signals with small BT values.* IEEE Trans. ASSP **26**(1), 64–76. —
  再割り当ての最初のアイデア。
- F. Auger, P. Flandrin (1995). *Improving the readability of time-frequency
  and time-scale representations by the reassignment method.* IEEE Trans.
  Signal Processing **43**(5), 1068–1089. — この実装が従う一般的な枠組み。
- D. Griffin, J. Lim (1984). *Signal estimation from modified short-time
  Fourier transform.* IEEE Trans. ASSP **32**(2), 236–243. — `sonify` が使う
  位相再構成。
- R. Martin (2001). *Noise power spectral density estimation based on optimal
  smoothing and minimum statistics.* IEEE Trans. Speech and Audio Processing
  **9**(5), 504–512. — `edit --denoise` が使うノイズフロア。
- J. Brown (1991). *Calculation of a constant Q spectral transform.* JASA
  **89**(1), 425–434. — `--transform cqt` の基礎。

## ロードマップ

- 心理音響マスキングのオーバーレイ — 物理的には存在するが聴こえない成分、
  つまりエンコーダーが捨てると決めたものそのものを暗く表示する
- 検証をくぐり抜けられる、ローパスに依存しないトランスコード検出器
- PNG マスクを往復させる代わりに、対話的に描ける UI

## ライセンス

MIT。デモ曲は `examples/make_demo_audio.py` で生成している。市販の録音を
このリポジトリにコミットしないこと。
