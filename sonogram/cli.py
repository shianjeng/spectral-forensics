"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import io as sio
from . import render, transform, video


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sonogram",
        description="把一首歌渲染成声纹海报或频谱视频。",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("input", help="输入音频文件 (wav/mp3/flac/m4a...)")
    common.add_argument("-o", "--output", help="输出路径")
    common.add_argument("--sr", type=int, default=22050, help="重采样率 (默认 22050)")
    common.add_argument("--offset", type=float, default=0.0, help="起始时间(秒)")
    common.add_argument("--duration", type=float, default=None, help="截取时长(秒)")
    common.add_argument("--transform", choices=["stft", "mel", "cqt"], default="mel")
    common.add_argument("--n-fft", type=int, default=2048)
    common.add_argument("--hop", type=int, default=512)
    common.add_argument("--window", default="hann",
                        help="窗函数: hann / hamming / blackmanharris ...")
    common.add_argument("--n-mels", type=int, default=128)
    common.add_argument("--top-db", type=float, default=80.0)
    common.add_argument("--palette", default="ember",
                        help="ember / abyss / mono / bloom 或任意 matplotlib 色板名")

    sp = sub.add_parser("poster", parents=[common], help="渲染静态声纹海报")
    sp.add_argument("--title", default=None, help="海报标题 (默认用文件名)")
    sp.add_argument("--width", type=float, default=12.0)
    sp.add_argument("--height", type=float, default=8.0)
    sp.add_argument("--dpi", type=int, default=200)
    sp.add_argument("--no-axes", action="store_true", help="去掉坐标轴和文字，纯图")

    sv = sub.add_parser("video", parents=[common], help="渲染频谱视频 (需要 ffmpeg)")
    sv.add_argument("--fps", type=int, default=30)
    sv.add_argument("--size", default="1280x720")
    sv.add_argument("--bars", type=int, default=96)
    sv.add_argument("--smoothing", type=float, default=0.6)

    sc = sub.add_parser("compare", parents=[common],
                        help="同一段音频用多组 n_fft 对比，展示时频不确定性")
    sc.add_argument("--n-ffts", default="512,2048,8192")

    sr_ = sub.add_parser("reassign", parents=[common],
                         help="重分配谱：突破不确定性下限的锐化谱图")
    sr_.add_argument("--mag-top-db", type=float, default=60.0,
                     help="低于此动态范围的格点丢弃（相位不可靠）")
    sr_.add_argument("--grid", default="1400x600", help="重采样网格 时间x频率")
    sr_.add_argument("--linear-freq", action="store_true", help="频率轴用线性而非对数")
    sr_.add_argument("--side-by-side", action="store_true",
                     help="同时输出普通谱做对照（同窗同网格）")
    sr_.add_argument("--title", default=None)

    se = sub.add_parser("edit", parents=[common],
                        help="在频域编辑再变回音频（保留原相位，几乎无损）")
    se.add_argument("--reject", help="剔除频段，格式 LO:HI（Hz）")
    se.add_argument("--keep", help="只保留频段，格式 LO:HI（Hz）")
    se.add_argument("--denoise", action="store_true", help="谱减降噪")
    se.add_argument("--reduction-db", type=float, default=12.0)
    se.add_argument("--threshold-db", type=float, default=8.0)
    se.add_argument("--mask", help="用一张灰度图当掩码（在画图软件里涂抹频谱）")
    se.add_argument("--invert-mask", action="store_true")
    se.add_argument("--preview", help="同时输出编辑前后的谱图对比 PNG")

    ss = sub.add_parser("sonify", help="把一张照片编码成声音（Griffin-Lim 重建）")
    ss.add_argument("image", help="输入图片")
    ss.add_argument("-o", "--output", help="输出 wav 路径")
    ss.add_argument("--sr", type=int, default=22050)
    ss.add_argument("--n-fft", type=int, default=2048)
    ss.add_argument("--hop", type=int, default=256)
    ss.add_argument("--frames", type=int, default=900, help="时间方向的帧数（决定时长）")
    ss.add_argument("--fmin", type=float, default=150.0)
    ss.add_argument("--fmax", type=float, default=6000.0)
    ss.add_argument("--iters", type=int, default=64, help="Griffin-Lim 迭代次数")
    ss.add_argument("--preview", help="同时输出重建音频的谱图 PNG")

    sa = sub.add_parser("audit", help="检测有损转码：FLAC 是不是 mp3 转来的")
    sa.add_argument("input", help="音频文件或目录")
    sa.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    sa.add_argument("--json", action="store_true", help="输出 JSON 而非表格")
    sa.add_argument("--only-suspect", action="store_true",
                    help="只列出可疑和存疑的文件")
    sa.add_argument("--seconds", type=float, default=120.0, help="每个文件分析时长")
    sa.add_argument("--no-stereo-check", action="store_true",
                    help="跳过强度立体声检测（更快）")
    sa.add_argument("--verbose", action="store_true", help="逐条打印判据")

    return p


def _config(args) -> transform.SpectroConfig:
    return transform.SpectroConfig(
        kind=args.transform, n_fft=args.n_fft, hop_length=args.hop,
        window=args.window, n_mels=args.n_mels, top_db=args.top_db,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # audit 接受目录、sonify 接受图片，都不走单文件解码这条路
    if args.command == "audit":
        return _run_audit(args)
    if args.command == "sonify":
        return _run_sonify(args)

    try:
        audio = sio.load(args.input, sr=args.sr,
                         offset=args.offset, duration=args.duration)
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    stem = Path(args.input).stem

    if args.command == "poster":
        spec = transform.compute(audio, _config(args))
        out = args.output or f"{stem}_sonogram.png"
        tempo = sio.estimate_tempo(audio)
        subtitle = (f"{spec.config.describe(audio.sr)} · "
                    f"{audio.duration:.0f}s · {tempo:.0f} BPM")
        path = render.poster(
            spec, out,
            title=args.title if args.title is not None else stem,
            subtitle=subtitle, palette=args.palette,
            width=args.width, height=args.height, dpi=args.dpi,
            show_axes=not args.no_axes,
        )
        print(f"已生成海报: {path}  ({spec.shape[0]}×{spec.shape[1]})")

    elif args.command == "video":
        if not video.ffmpeg_available():
            print("错误: 未找到 ffmpeg", file=sys.stderr)
            return 1
        spec = transform.compute(audio, _config(args))
        w, _, h = args.size.partition("x")
        out = args.output or f"{stem}_sonogram.mp4"
        path = video.render_video(
            audio, spec, out, fps=args.fps,
            width=int(w), height=int(h), n_bars=args.bars,
            palette=args.palette, smoothing=args.smoothing,
        )
        print(f"已生成视频: {path}")

    elif args.command == "compare":
        n_ffts = [int(x) for x in args.n_ffts.split(",")]
        specs, labels = [], []
        for n in n_ffts:
            cfg = transform.SpectroConfig(
                kind=args.transform, n_fft=n, hop_length=max(64, n // 4),
                window=args.window, n_mels=args.n_mels, top_db=args.top_db,
            )
            s = transform.compute(audio, cfg)
            specs.append(s)
            labels.append(f"n_fft={n}  Δt={cfg.time_resolution(audio.sr)*1000:.0f}ms  "
                          f"Δf={cfg.freq_resolution(audio.sr):.1f}Hz")
        out = args.output or f"{stem}_compare.png"
        path = render.comparison(specs, labels, out, palette=args.palette)
        print(f"已生成对比图: {path}")

    elif args.command == "reassign":
        from .reassign import rasterize, reassign as do_reassign, sharpness

        cfg = _config(args)
        if cfg.kind != "stft":
            cfg = transform.SpectroConfig(
                kind="stft", n_fft=args.n_fft, hop_length=args.hop,
                window=args.window, top_db=args.top_db,
            )
        nt, _, nf = args.grid.partition("x")
        nt, nf = int(nt), int(nf)
        log_freq = not args.linear_freq

        rea = rasterize(do_reassign(audio, cfg, mag_top_db=args.mag_top_db),
                        n_time=nt, n_freq=nf, log_freq=log_freq,
                        top_db=args.top_db)
        out = args.output or f"{stem}_reassigned.png"

        if args.side_by_side:
            base = rasterize(do_reassign(audio, cfg, mag_top_db=args.mag_top_db,
                                         enabled=False),
                             n_time=nt, n_freq=nf, log_freq=log_freq,
                             top_db=args.top_db)
            path = render.comparison(
                [base, rea],
                [f"standard STFT  n_fft={cfg.n_fft}  (identical grid)",
                 "reassigned  (identical window & grid)"],
                out, palette=args.palette,
            )
            print(f"已生成对照图: {path}")
            print(f"锐度 (谱集中度): 普通 {sharpness(base):.3f} → "
                  f"重分配 {sharpness(rea):.3f}")
        else:
            path = render.poster(
                rea, out,
                title=args.title if args.title is not None else stem,
                subtitle=f"reassigned · n_fft={cfg.n_fft} · hop={cfg.hop_length} "
                         f"· {cfg.window} · {audio.duration:.0f}s",
                palette=args.palette,
            )
            print(f"已生成重分配谱: {path}  (锐度 {sharpness(rea):.3f})")

    elif args.command == "edit":
        return _run_edit(args, audio, stem)

    return 0


def _band(arg: str) -> tuple[float, float]:
    lo, _, hi = arg.partition(":")
    return float(lo), float(hi)


def _run_edit(args, audio, stem: str) -> int:
    """edit 子命令：频域编辑 → 保相位重建。"""
    import numpy as np

    from .invert import (analyze, apply_mask, band_mask, mask_from_image,
                         spectral_gate, write_wav)

    cfg = transform.SpectroConfig(
        kind="stft", n_fft=args.n_fft, hop_length=args.hop,
        window=args.window, top_db=args.top_db,
    )
    spec = analyze(audio, cfg)
    mask = np.ones_like(spec.magnitude)
    applied: list[str] = []

    if args.reject:
        lo, hi = _band(args.reject)
        mask = mask * band_mask(spec, lo, hi, keep=False)
        applied.append(f"剔除 {lo:.0f}–{hi:.0f} Hz")
    if args.keep:
        lo, hi = _band(args.keep)
        mask = mask * band_mask(spec, lo, hi, keep=True)
        applied.append(f"只保留 {lo:.0f}–{hi:.0f} Hz")
    if args.denoise:
        mask = mask * spectral_gate(spec, reduction_db=args.reduction_db,
                                    threshold_db=args.threshold_db)
        applied.append(f"降噪 −{args.reduction_db:.0f} dB")
    if args.mask:
        mask = mask * mask_from_image(args.mask, spec.magnitude.shape,
                                      invert=args.invert_mask)
        applied.append(f"图像掩码 {args.mask}")

    if not applied:
        print("没有指定任何编辑操作（--reject / --keep / --denoise / --mask）。",
              file=sys.stderr)
        return 1

    y = apply_mask(spec, mask, length=len(audio.y))
    out = args.output or f"{stem}_edited.wav"
    path = write_wav(out, y, audio.sr)
    print(f"已生成音频: {path}   [{' + '.join(applied)}]")

    if args.preview:
        from .io import Audio
        before = transform.compute(audio, cfg)
        after = transform.compute(
            Audio(y=y.astype("float32"), sr=audio.sr, path=Path(out)), cfg)
        p = render.comparison([before, after], ["before", "after"],
                              args.preview, palette=args.palette)
        print(f"已生成对比图: {p}")
    return 0


def _run_sonify(args) -> int:
    """sonify 子命令：图片 → 幅度谱 → Griffin-Lim → 音频。"""
    from .invert import (image_to_magnitude, spectral_convergence, synthesize,
                         write_wav)

    cfg = transform.SpectroConfig(kind="stft", n_fft=args.n_fft,
                                  hop_length=args.hop)
    mag = image_to_magnitude(args.image, args.sr, cfg, n_frames=args.frames,
                             fmin=args.fmin, fmax=args.fmax)
    y = synthesize(mag, args.sr, cfg, n_iter=args.iters)

    out = args.output or f"{Path(args.image).stem}_sonified.wav"
    path = write_wav(out, y, args.sr)
    sc = spectral_convergence(mag, y, cfg)
    print(f"已生成音频: {path}  ({len(y)/args.sr:.1f}s, "
          f"谱收敛误差 {sc:.3f}，越小越接近目标幅度谱)")

    if args.preview:
        from .io import Audio
        a = Audio(y=y.astype("float32"), sr=args.sr, path=Path(out))
        sp = transform.compute(a, transform.SpectroConfig(
            kind="stft", n_fft=args.n_fft, hop_length=args.hop // 2, top_db=70))
        p = render.poster(sp, args.preview, title=Path(args.image).stem,
                          subtitle=f"Griffin-Lim {args.iters} iters  ·  spectral convergence {sc:.3f}",
                          palette="mono")
        print(f"已生成谱图: {p}")
    return 0


def _run_audit(args) -> int:
    """audit 子命令：扫描文件或整个音乐库。"""
    import json as _json

    from .audit import audit_path

    results = audit_path(
        args.input, recursive=args.recursive,
        max_seconds=args.seconds,
        check_stereo=not args.no_stereo_check,
    )
    if args.only_suspect:
        results = [r for r in results if r.verdict in ("suspect", "likely", "unknown")]

    if args.json:
        print(_json.dumps([r.as_dict() for r in results],
                          ensure_ascii=False, indent=2))
        return 0

    if not results:
        print("没有找到音频文件。")
        return 0

    mark = {"clean": "✓", "likely": "?", "suspect": "⚠",
            "lossy": "·", "unknown": "!"}
    flagged = ("suspect", "likely")
    width = min(46, max(len(Path(r.path).name) for r in results))

    for r in results:
        name = Path(r.path).name
        if len(name) > width:
            name = name[:width - 1] + "…"
        cut = f"{r.cutoff_khz:.1f}k" if r.cutoff_khz else "  —  "
        conf = f"{r.confidence:.0%}" if r.verdict in flagged else "    "
        tail = f"→ {r.guess}" if r.verdict in flagged else ""
        print(f"{mark[r.verdict]} {name:<{width}}  cut={cut:>6}  {conf:>4}  {tail}")
        if args.verbose:
            for n in r.notes:
                print(f"    · {n}")

    n_sus = sum(1 for r in results if r.verdict == "suspect")
    n_lik = sum(1 for r in results if r.verdict == "likely")
    print(f"\n共 {len(results)} 个文件，{n_sus} 个可疑，{n_lik} 个存疑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
