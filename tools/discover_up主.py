"""
B站 UP主 翻唱视频发现工具
通过 B站 API + wbi 签名获取指定 UP主的所有翻唱视频，输出 yt-dlp 批量下载 URL 列表。

用法:
    conda activate G:\Cover_vision\.venv
    python tools/discover_up主.py <UP主UID或用户名> [--output-dir w/C_bilibili/urls]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

# B站 wbi 签名置换表（固定，来自客户端）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]

# B站 翻唱区 TID
MUSIC_COVER_TID = 31
MUSIC_CATEGORY_TIDS = {28, 29, 30, 31, 59, 193, 194}

# 通用请求头
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.bilibili.com/',
}

# 翻唱关键词（用于标题筛选）
COVER_KEYWORDS = ['翻唱', 'cover', 'Cover', 'COVER', '翻', '唱', '歌ってみた']


class BiliWbiSigner:
    """B站 wbi 签名器"""

    def __init__(self):
        self.mixin_key = None
        self._fetch_keys()

    def _fetch_keys(self):
        """从 nav 接口获取 img_key 和 sub_key"""
        resp = requests.get(
            'https://api.bilibili.com/x/web-interface/nav',
            headers=HEADERS, timeout=15
        )
        data = resp.json()
        # nav 接口未登录时 code=-101 但仍返回 wbi_img
        if 'data' not in data or 'wbi_img' not in data['data']:
            raise RuntimeError(f"nav 接口无 wbi_img: {data}")
        wbi_img = data['data']['wbi_img']
        img_key = wbi_img['img_url'].split('/')[-1].split('.')[0]
        sub_key = wbi_img['sub_url'].split('/')[-1].split('.')[0]

        raw = img_key + sub_key
        self.mixin_key = ''.join(raw[MIXIN_KEY_ENC_TAB[i]] for i in range(32))

    def sign(self, params: dict) -> dict:
        """对请求参数进行 wbi 签名"""
        if not self.mixin_key:
            raise RuntimeError("wbi key 未获取")

        params['wts'] = int(time.time())
        params = dict(sorted(params.items()))
        query_str = urllib.parse.urlencode(params)
        w_rid = hashlib.md5((query_str + self.mixin_key).encode()).hexdigest()
        params['w_rid'] = w_rid
        return params


def resolve_uid(username_or_uid: str) -> str:
    """将用户名解析为 UID"""
    if username_or_uid.isdigit():
        return username_or_uid

    resp = requests.get(
        'https://api.bilibili.com/x/web-interface/search/type',
        params={'search_type': 'bili_user', 'keyword': username_or_uid},
        headers=HEADERS, timeout=15
    )
    data = resp.json()
    if data['code'] != 0 or not data['data'].get('result'):
        raise ValueError(f"未找到用户: {username_or_uid}")

    for user in data['data']['result']:
        if user['uname'] == username_or_uid:
            return str(user['mid'])
    return str(data['data']['result'][0]['mid'])


def fetch_all_videos(uid: str, signer: BiliWbiSigner, filter_cover: bool = True):
    """获取某 UP 主的所有翻唱视频"""
    page = 1
    total_videos = []
    session = requests.Session()
    session.headers.update(HEADERS)

    while True:
        params = signer.sign({
            'mid': uid,
            'ps': 50,
            'pn': page,
            'order': 'pubdate',
        })
        resp = session.get(
            'https://api.bilibili.com/x/space/wbi/arc/search',
            params=params, timeout=20
        )
        data = resp.json()
        if data['code'] != 0:
            print(f"  [!] API 错误 (page {page}): code={data['code']}, msg={data.get('message')}")
            break

        vlist = data['data']['list']['vlist']
        if not vlist:
            break

        for v in vlist:
            tid = v['tid']
            title = v['title']
            length_str = v['length']  # e.g. "3:45"

            # 时长过滤：>= 60s
            parts = length_str.split(':')
            total_seconds = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0
            if total_seconds < 60:
                continue

            # 分区过滤
            if tid not in MUSIC_CATEGORY_TIDS:
                continue

            # 关键词过滤
            if filter_cover:
                has_keyword = any(kw.lower() in title.lower() for kw in COVER_KEYWORDS)
                if not has_keyword and tid == MUSIC_COVER_TID:
                    pass  # 翻唱区默认通过

            total_videos.append({
                'bvid': v['bvid'],
                'title': title,
                'length': length_str,
                'play': v['play'],
                'created': v['created'],
                'tid': tid,
            })

        total_pages = data['data']['page']['count'] // 50 + 1
        print(f"  page {page}/{total_pages} — 已收集 {len(total_videos)} 条")
        page += 1
        time.sleep(0.5)

    return total_videos


def main():
    parser = argparse.ArgumentParser(description='B站 UP主翻唱视频发现工具')
    parser.add_argument('user', help='UP主 UID 或用户名')
    parser.add_argument('--output-dir', default=None,
                        help='输出目录 (默认: w/C_bilibili/urls)')
    parser.add_argument('--all', action='store_true',
                        help='不筛选翻唱关键词，拉取全部音乐区视频')
    args = parser.parse_args()

    # 确定输出目录
    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / 'w' / 'C_bilibili' / 'urls'
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] 初始化 wbi 签名器...")
    signer = BiliWbiSigner()

    print(f"[*] 解析用户: {args.user}")
    uid = resolve_uid(args.user)

    # 获取用户名
    resp = requests.get(
        'https://api.bilibili.com/x/space/acc/info',
        params={'mid': uid}, headers=HEADERS, timeout=15
    )
    name = resp.json()['data']['name']
    print(f"[*] UP主: {name} (UID: {uid})")

    print(f"[*] 获取视频列表...")
    videos = fetch_all_videos(uid, signer, filter_cover=not args.all)

    print(f"\n[*] 共找到 {len(videos)} 条匹配视频")

    if not videos:
        print("[!] 未找到符合条件的视频")
        sys.exit(1)

    # 按发布时间排序（新→旧）
    videos.sort(key=lambda x: x['created'], reverse=True)

    # 写入 URL 列表
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    url_file = output_dir / f'{safe_name}.txt'
    with open(url_file, 'w', encoding='utf-8') as f:
        for v in videos:
            url = f'https://www.bilibili.com/video/{v["bvid"]}'
            f.write(f'# {v["title"]} | {v["length"]} | play:{v["play"]}\n')
            f.write(f'{url}\n')

    print(f"[+] URL 列表已保存: {url_file}")
    print(f"[+] 视频数量: {len(videos)}")

    # 同时输出摘要 JSON
    json_file = output_dir / f'{safe_name}_meta.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"[+] 元数据已保存: {json_file}")


if __name__ == '__main__':
    main()
