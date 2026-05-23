"""
B站 UP主 翻唱视频发现 — Scrapling StealthyFetcher 版本
使用隐身浏览器加载 B站 space 页面，绕过 API 风控。

用法:
    "G:/Cover_vision/.venv/python.exe" tools/discover_stealth.py <UP主UID或space_url>
    "G:/Cover_vision/.venv/python.exe" tools/discover_stealth.py --uid 323418
    "G:/Cover_vision/.venv/python.exe" tools/discover_stealth.py https://space.bilibili.com/323418/video
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

COVER_KEYWORDS = ['翻唱', 'cover', 'Cover', 'COVER', '歌ってみた']


def discover_from_space(uid: str, filter_cover: bool = True, headless: bool = True):
    """使用 StealthyFetcher 加载 UP主 space 页面，提取视频列表"""
    space_url = f'https://space.bilibili.com/{uid}/video'

    print(f"[*] 启动隐身浏览器，加载: {space_url}")
    page = StealthyFetcher.fetch(
        space_url,
        headless=headless,
        network_idle=True,
        auto_save=True,
        timeout=60,
    )

    print("[*] 解析视频列表...")

    # B站 space 页面中视频卡片的选择器
    # 主结构: .video-list .video-item 或 .cube-list .video-card
    video_items = page.css('.video-list-item') or page.css('.video-card') or page.css('.cube-item')

    if not video_items:
        # 尝试更广泛的选择器
        video_items = page.css('[class*="video"]')

    videos = []
    for item in video_items:
        try:
            # 提取链接
            link_el = item.css('a[href*="/video/"]')
            if not link_el:
                continue
            href = link_el.attrib.get('href', '')
            if not href:
                continue

            bvid = href.split('/video/')[-1].rstrip('/')

            # 提取标题
            title_el = item.css('.title') or item.css('[class*="title"]')
            title = title_el.text().strip() if title_el else ''

            # 提取时长
            length_el = item.css('.length') or item.css('[class*="length"]') or item.css('.duration')
            length_text = length_el.text().strip() if length_el else '0:00'

            if not title:
                continue

            videos.append({
                'bvid': bvid,
                'title': title,
                'length': length_text,
                'url': f'https://www.bilibili.com/video/{bvid}',
            })
        except Exception:
            continue

    return videos


def discover_from_api_fallback(uid: str, cookies_file: str = None):
    """fallback: 如果浏览器方法不可用，尝试之前的 API 方法"""
    from discover import BiliSession, fetch_all_videos

    session = BiliSession(cookies_file)
    resp = session.session.get(
        'https://api.bilibili.com/x/space/acc/info',
        params={'mid': uid}, timeout=15
    )
    name = resp.json().get('data', {}).get('name', uid)
    print(f"[*] UP主: {name} (UID: {uid}) (API fallback)")

    videos_meta = fetch_all_videos(session, uid, filter_cover=True)
    return videos_meta, name


def main():
    parser = argparse.ArgumentParser(description='B站 UP主翻唱发现 — Scrapling版')
    parser.add_argument('target', nargs='?', help='UP主 UID 或 space URL')
    parser.add_argument('--uid', default=None, help='直接指定 UID')
    parser.add_argument('--output-dir', default=None)
    parser.add_argument('--all', action='store_true', help='不筛选翻唱关键词')
    parser.add_argument('--no-headless', action='store_true', help='显示浏览器窗口')
    parser.add_argument('--api-fallback', action='store_true',
                        help='直接使用 API 模式 (需要 cookies)')
    args = parser.parse_args()

    # 解析 UID
    uid = args.uid
    if not uid and args.target:
        uid_match = re.search(r'space\.bilibili\.com/(\d+)', args.target)
        if uid_match:
            uid = uid_match.group(1)
        elif args.target.isdigit():
            uid = args.target
        else:
            uid = args.target

    if not uid:
        parser.error("需要提供 UID 或 space URL")

    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / 'w' / 'C_bilibili' / 'urls'
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.api_fallback:
        print("[*] 使用 API fallback 模式")
        videos_meta, name = discover_from_api_fallback(uid)
        videos = videos_meta
    else:
        print("[*] 使用 Scrapling StealthyFetcher 模式")
        videos = discover_from_space(uid, filter_cover=not args.all, headless=not args.no_headless)

        # 获取 UP主 名称
        name = f'UP_{uid}'

    print(f"\n[*] 共找到 {len(videos)} 条视频")

    if not videos:
        print("[!] 未找到视频。可以尝试:")
        print("    1. --no-headless 查看浏览器实际加载的页面")
        print("    2. --api-fallback 切换到 API 模式")
        sys.exit(1)

    # 写入 URL 列表
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    url_file = output_dir / f'{safe_name}.txt'
    with open(url_file, 'w', encoding='utf-8') as f:
        for v in videos:
            f.write(f"# {v.get('title', '')} | {v.get('length', '')}\n")
            url = v.get('url', v.get('bvid', ''))
            if url and not url.startswith('http'):
                url = f'https://www.bilibili.com/video/{url}'
            f.write(f'{url}\n')

    print(f"[+] URL 列表: {url_file} ({len(videos)} 条)")

    json_file = output_dir / f'{safe_name}_meta.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"[+] 元数据: {json_file}")


if __name__ == '__main__':
    main()
