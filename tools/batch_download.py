"""
yt-dlp 批量音频下载封装
读取 URL 列表文件，并发下载纯音频，自动去重。

用法:
    conda activate G:\Cover_vision\.venv
    python tools/batch_download.py <url_file_or_dir> [--output-dir w/C_bilibili/raw_audio]

可以传入单个 .txt URL 列表文件，或一个包含多个 .txt 文件的目录。
"""

import argparse
import subprocess
import sys
from pathlib import Path


def download_urls(url_file: Path, output_dir: Path, archive_file: Path, concurrency: int = 8):
    """对单个 URL 列表文件执行 yt-dlp 下载"""
    name = url_file.stem
    up_output_dir = output_dir / name
    up_output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        'yt-dlp',
        '--batch-file', str(url_file),
        '--output', str(up_output_dir / '%(title).100s [%(id)s].%(ext)s'),
        '--format', 'ba',                       # 最佳纯音频
        '--extract-audio',                       # 提取音频
        '--audio-format', 'wav',                 # 输出 WAV (无损，方便后续 UVR5 处理)
        '--concurrent-fragments', str(concurrency),
        '--download-archive', str(archive_file),
        '--no-playlist',
        '--no-overwrites',
        '--sleep-requests', '1',                 # 请求间隔
        '--sleep-interval', '3',                 # 下载间隔
        '--max-sleep-interval', '10',
        '--retries', '5',
        '--fragment-retries', '5',
        '--user-agent',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        '--add-header', 'Referer:https://www.bilibili.com/',
    ]

    print(f"[*] 下载: {name} ({url_file})")
    print(f"[*] 输出: {up_output_dir}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description='yt-dlp 批量音频下载')
    parser.add_argument('input', help='URL 列表文件 (.txt) 或包含多个 .txt 的目录')
    parser.add_argument('--output-dir', default=None,
                        help='输出根目录 (默认: w/C_bilibili/raw_audio)')
    parser.add_argument('--concurrency', type=int, default=8,
                        help='并发下载线程 (默认: 8)')
    args = parser.parse_args()

    input_path = Path(args.input)
    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / 'w' / 'C_bilibili' / 'raw_audio'
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_file = output_dir / '.yt_dlp_archive.txt'

    # 收集 URL 文件
    if input_path.is_dir():
        url_files = sorted(input_path.glob('*.txt'))
    elif input_path.is_file() and input_path.suffix == '.txt':
        url_files = [input_path]
    else:
        print(f"[!] 无效输入: {input_path}")
        sys.exit(1)

    if not url_files:
        print("[!] 未找到 .txt URL 文件")
        sys.exit(1)

    print(f"[*] 共 {len(url_files)} 个 URL 列表")
    print(f"[*] 输出根目录: {output_dir}")
    print(f"[*] 归档文件: {archive_file}")
    print()

    total_errors = 0
    for i, url_file in enumerate(url_files, 1):
        print(f"[{i}/{len(url_files)}] ", end='')
        ret = download_urls(url_file, output_dir, archive_file, args.concurrency)
        if ret != 0:
            total_errors += 1
            print(f"  [!] 下载出错 (exit code: {ret})")

    print(f"\n[*] 完成。错误数: {total_errors}/{len(url_files)}")


if __name__ == '__main__':
    main()
