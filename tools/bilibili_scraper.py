"""
B站翻唱素材采集 — yt-dlp + cookies 全自动流水线
基于 yt-dlp B站空间解析，绕过 API 风控。

用法:
    "G:/Cover_vision/.venv/python.exe" tools/bilibili_scraper.py \
        --uid 37754047 --name "咻咻满" \
        --download

步骤:
    1. discover: 列出 UP主全部视频
    2. filter: 按标题关键词筛选翻唱视频
    3. download: 提取纯音频 (WAV 48K)
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

COVER_KEYWORDS = ['翻唱', 'cover', 'Cover', 'COVER', '歌ってみた', '翻', '唱']
DEFAULT_COOKIES = Path(__file__).resolve().parent / 'bili_cookies.txt'


def make_netscape_cookies(cookies_file: Path) -> Path:
    """将 key=value 格式 cookies 转为 Netscape 格式，yt-dlp 需要"""
    nc_path = cookies_file.with_suffix('.netscape.txt')
    with open(cookies_file, 'r', encoding='utf-8') as f_in:
        with open(nc_path, 'w') as f_out:
            f_out.write('# Netscape HTTP Cookie File\n')
            for line in f_in:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                key, _, value = line.partition('=')
                if key and value:
                    f_out.write(
                        f'.bilibili.com\tTRUE\t/\tFALSE\t0\t{key.strip()}\t{value.strip()}\n'
                    )
    return nc_path


def discover(uid: str, cookies: Path) -> list[dict]:
    """使用 yt-dlp 获取 UP主全部视频列表"""
    nc = make_netscape_cookies(cookies)
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--cookies', str(nc),
        '--flat-playlist',
        '--playlist-end', '9999',
        '--dump-json',
        f'https://space.bilibili.com/{uid}/video',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            videos.append({
                'bvid': d.get('id', ''),
                'title': d.get('title', ''),
                'duration': d.get('duration') or 0,
                'url': d.get('url', '') or f'https://www.bilibili.com/video/{d.get("id","")}',
            })
        except json.JSONDecodeError:
            continue
    return videos


def filter_covers(videos: list[dict]) -> list[dict]:
    """按标题关键词 + 时长筛选翻唱视频。
    注意: flat-playlist 模式下 title/duration 可能为空，此时不做筛选。"""
    if not videos:
        return []
    # 如果 flat 模式没有 title，跳过筛选，全量保留
    if not videos[0].get('title'):
        return videos

    filtered = []
    for v in videos:
        title = v.get('title', '')
        duration = v.get('duration') or 0

        if duration and duration < 60:
            continue
        has_kw = any(kw.lower() in title.lower() for kw in COVER_KEYWORDS)
        if not has_kw:
            continue
        filtered.append(v)
    return filtered or videos  # 如果全部被筛掉，保留全部


def download_audio(uid: str, name: str, videos: list[dict], cookies: Path, output_base: Path = None):
    """使用 yt-dlp 批量下载纯音频"""
    if output_base is None:
        output_base = Path(__file__).resolve().parent.parent / 'w' / 'C_bilibili'

    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    raw_dir = output_base / 'raw_audio' / safe_name
    raw_dir.mkdir(parents=True, exist_ok=True)

    archive_file = raw_dir / 'downloaded.txt'
    nc = make_netscape_cookies(cookies)

    # 写入 URL 列表
    url_file = raw_dir / 'urls.txt'
    with open(url_file, 'w', encoding='utf-8') as f:
        for v in videos:
            f.write(f'{v["url"]}\n')

    print(f'[*] 下载 {len(videos)} 首翻唱 → {raw_dir}')
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--cookies', str(nc),
        '--batch-file', str(url_file),
        '--output', str(raw_dir / '%(title).80s [%(id)s].%(ext)s'),
        '--format', 'ba',
        '--extract-audio',
        '--audio-format', 'wav',
        '--concurrent-fragments', '4',
        '--download-archive', str(archive_file),
        '--no-playlist',
        '--no-overwrites',
        '--sleep-requests', '2',
        '--sleep-interval', '5',
        '--retries', '5',
    ]
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description='B站翻唱素材采集')
    parser.add_argument('--uid', required=True, help='UP主 UID')
    parser.add_argument('--name', default='', help='UP主名称 (可选)')
    parser.add_argument('--cookies', default=str(DEFAULT_COOKIES),
                        help=f'cookies 文件 (默认: {DEFAULT_COOKIES})')
    parser.add_argument('--discover-only', action='store_true', help='仅发现，不下载')
    parser.add_argument('--download', action='store_true', help='发现 + 下载')
    parser.add_argument('--all', action='store_true', help='下载全部视频，不过滤翻唱')
    parser.add_argument('--output-base', default=None, help='输出根目录')
    args = parser.parse_args()

    cookies = Path(args.cookies)
    if not cookies.exists():
        print(f'[!] cookies 文件不存在: {cookies}')
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    output_base = Path(args.output_base) if args.output_base else project_root / 'w' / 'C_bilibili'
    urls_dir = output_base / 'urls'
    urls_dir.mkdir(parents=True, exist_ok=True)

    print(f'[*] UP主 UID: {args.uid}')
    print(f'[*] 发现视频列表...')
    all_videos = discover(args.uid, cookies)
    print(f'[*] 全部视频: {len(all_videos)} 个')

    covers = all_videos if args.all else filter_covers(all_videos)
    print(f'[*] 翻唱视频: {len(covers)} 个')

    if not covers:
        print('[!] 未找到翻唱视频。尝试 --all 下载全部')
        return

    # 获取 UP主名称（从第一个视频的返回结果，或者从用户空间查）
    name = args.name
    if not name:
        name = f'UP_{args.uid}'

    # 保存 URL 列表
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    url_file = urls_dir / f'{safe_name}.txt'
    with open(url_file, 'w', encoding='utf-8') as f:
        for v in covers:
            f.write(f'# {v["title"]} | {v["duration"]}s\n')
            f.write(f'{v["url"]}\n')
    print(f'[+] URL 列表: {url_file}')

    # 保存元数据
    meta_file = urls_dir / f'{safe_name}_meta.json'
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(covers, f, ensure_ascii=False, indent=2)

    if args.download:
        print()
        download_audio(args.uid, name, covers, cookies, output_base)
        print(f'\n[+] 下载完成: {output_base / "raw_audio" / safe_name}')

    if args.discover_only or not args.download:
        print('\n[*] 预览 (前10条):')
        for v in covers[:10]:
            print(f'  {v["bvid"]} | {v["title"][:50]} | {v["duration"]}s')


if __name__ == '__main__':
    main()
