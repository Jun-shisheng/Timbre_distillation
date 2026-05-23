"""
音频分段工具 — 将清洗后的干声按静音检测切分为 3-15s 训练就绪片段

用法:
    conda activate G:\Cover_vision\.venv
    python tools/segment_audio.py <input_dir> --output-dir w/C_bilibili/segments
"""

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def segment_file(
    input_path: Path,
    output_dir: Path,
    min_duration: float = 3.0,
    max_duration: float = 15.0,
    top_db: int = 35,
    min_silence: float = 0.3,
    sample_rate: int = 48000,
):
    """将单个音频文件切分为多个短片段"""
    y, sr = librosa.load(str(input_path), sr=sample_rate, mono=True)

    if len(y) == 0:
        return 0

    # 静音检测 → 非静音区间
    intervals = librosa.effects.split(
        y, top_db=top_db,
        frame_length=2048, hop_length=512
    )

    # 合并间隔小于 min_silence 的区间
    merged = []
    for start, end in intervals:
        start_s = librosa.samples_to_time(start, sr=sr)
        end_s = librosa.samples_to_time(end, sr=sr)
        if merged and start_s - merged[-1][1] < min_silence:
            merged[-1] = (merged[-1][0], end_s)
        else:
            merged.append((start_s, end_s))

    base_name = input_path.stem
    safe_name = ''.join(c if c.isalnum() or c in '._-' else '_' for c in base_name)
    up_dir = output_dir / safe_name
    up_dir.mkdir(parents=True, exist_ok=True)

    seg_count = 0
    for seg_start, seg_end in merged:
        duration = seg_end - seg_start

        # 过短丢弃
        if duration < min_duration:
            continue

        # 过长则拆分为 max_duration 段
        sub_segments = []
        pos = seg_start
        while pos < seg_end:
            end_pos = min(pos + max_duration, seg_end)
            if end_pos - pos >= min_duration:
                sub_segments.append((pos, end_pos))
            pos = end_pos

        for sub_start, sub_end in sub_segments:
            start_sample = librosa.time_to_samples(sub_start, sr=sr)
            end_sample = librosa.time_to_samples(sub_end, sr=sr)
            chunk = y[start_sample:end_sample]

            if len(chunk) < int(min_duration * sr):
                continue

            out_path = up_dir / f'seg_{seg_count:04d}.wav'
            sf.write(str(out_path), chunk, sr)
            seg_count += 1

    return seg_count


def main():
    parser = argparse.ArgumentParser(description='音频静音分段工具')
    parser.add_argument('input_dir', help='输入目录 (清洗后的干声)')
    parser.add_argument('--output-dir', default=None,
                        help='输出目录 (默认: w/C_bilibili/segments)')
    parser.add_argument('--min-dur', type=float, default=3.0,
                        help='最小片段时长秒 (默认: 3.0)')
    parser.add_argument('--max-dur', type=float, default=15.0,
                        help='最大片段时长秒 (默认: 15.0)')
    parser.add_argument('--top-db', type=int, default=35,
                        help='静音阈值 dB (默认: 35, 越小越敏感)')
    parser.add_argument('--sample-rate', type=int, default=48000,
                        help='采样率 (默认: 48000)')
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"[!] 输入目录不存在: {input_dir}")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / 'w' / 'C_bilibili' / 'segments'
    output_dir.mkdir(parents=True, exist_ok=True)

    wav_files = list(input_dir.rglob('*.wav'))
    if not wav_files:
        print(f"[!] 未找到 WAV 文件: {input_dir}")
        sys.exit(1)

    print(f"[*] 输入: {input_dir}")
    print(f"[*] 输出: {output_dir}")
    print(f"[*] 参数: min={args.min_dur}s, max={args.max_dur}s, top_db={args.top_db}, sr={args.sample_rate}")
    print(f"[*] 共 {len(wav_files)} 个 WAV 文件\n")

    total_segments = 0
    for i, wav_path in enumerate(wav_files, 1):
        print(f"[{i}/{len(wav_files)}] {wav_path.name} ... ", end='', flush=True)
        try:
            n = segment_file(
                wav_path, output_dir,
                min_duration=args.min_dur,
                max_duration=args.max_dur,
                top_db=args.top_db,
                sample_rate=args.sample_rate,
            )
            print(f"{n} segments")
            total_segments += n
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\n[+] 总计: {total_segments} 个训练片段 → {output_dir}")


if __name__ == '__main__':
    main()
