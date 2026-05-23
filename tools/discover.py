"""
B站 UP主 翻唱视频发现工具
通过 B站 API + wbi 签名获取指定 UP主的所有翻唱视频，输出 yt-dlp 批量下载 URL 列表。

用法:
    "G:/Cover_vision/.venv/python.exe" tools/discover.py <UP主用户名> [--output-dir w/C_bilibili/urls]
    "G:/Cover_vision/.venv/python.exe" tools/discover.py --uid <UID> [--output-dir w/C_bilibili/urls]
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]

MUSIC_COVER_TID = 31
MUSIC_CATEGORY_TIDS = {28, 29, 30, 31, 59, 193, 194}

UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)

COVER_KEYWORDS = ['翻唱', 'cover', 'Cover', 'COVER', '歌ってみた']


def load_cookies_file(path: str) -> dict:
    """从文件加载 cookies (key=value 每行)"""
    cookies = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, _, value = line.partition('=')
                cookies[key.strip()] = value.strip()
    return cookies


class BiliSession:
    """带 cookies 和 wbi 签名的 B站 API 会话"""

    def __init__(self, cookies_file: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': UA,
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Origin': 'https://space.bilibili.com',
        })
        self.mixin_key = None

        if cookies_file:
            cookies = load_cookies_file(cookies_file)
            for key, value in cookies.items():
                self.session.cookies.set(key, value, domain='.bilibili.com')
        self._init_cookies()
        self._init_wbi()

    def _init_cookies(self):
        """补充获取 B站首页 cookies (已有的登录态不会覆盖)"""
        time.sleep(3)  # 初始化前先等一会，避免触发限流
        self.session.get('https://www.bilibili.com/', timeout=20)
        time.sleep(2)

    def _init_wbi(self):
        """获取 wbi 签名密钥"""
        time.sleep(1)
        resp = self.session.get(
            'https://api.bilibili.com/x/web-interface/nav', timeout=15
        )
        data = resp.json()
        if 'data' not in data or 'wbi_img' not in data['data']:
            raise RuntimeError(f"nav 接口无 wbi_img: {data}")
        wbi_img = data['data']['wbi_img']
        img_key = wbi_img['img_url'].split('/')[-1].split('.')[0]
        sub_key = wbi_img['sub_url'].split('/')[-1].split('.')[0]
        raw = img_key + sub_key
        self.mixin_key = ''.join(raw[MIXIN_KEY_ENC_TAB[i]] for i in range(32))

    def _get_with_retry(self, url, params=None, max_tries=3):
        """带重试的 GET 请求，处理 -799 限流"""
        for i in range(max_tries):
            if params is not None:
                resp = self.signed_get(url, params, timeout=20)
            else:
                resp = self.session.get(url, timeout=20)
            data = resp.json()
            if data['code'] == -799:
                wait = (i + 1) * 10
                print(f"    限流中，等待 {wait}s...")
                time.sleep(wait)
                continue
            return data
        return data

    def sign(self, params: dict) -> dict:
        params['wts'] = int(time.time())
        params = dict(sorted(params.items()))
        query_str = urllib.parse.urlencode(params)
        w_rid = hashlib.md5((query_str + self.mixin_key).encode()).hexdigest()
        params['w_rid'] = w_rid
        return params

    def signed_get(self, url: str, params: dict, **kwargs) -> requests.Response:
        return self.session.get(url, params=self.sign(params), **kwargs)


def resolve_uid(session: BiliSession, username: str) -> str:
    """将用户名解析为 UID，尝试多种方法"""
    # 方法1: wbi 签名搜索
    try:
        params = {
            'keyword': username,
            'search_type': 'bili_user',
        }
        resp = session.signed_get(
            'https://api.bilibili.com/x/web-interface/wbi/search/all/v2',
            params, timeout=15
        )
        data = resp.json()
        if data['code'] == 0:
            for item in data['data'].get('result', []):
                if item.get('type') == 'bili_user' or item.get('uname'):
                    uname = item.get('uname', '')
                    if uname == username:
                        return str(item['mid'])
    except Exception:
        pass

    # 方法2: 无签名搜索（带完整 cookies）
    try:
        resp = session.session.get(
            'https://api.bilibili.com/x/web-interface/search/type',
            params={'search_type': 'bili_user', 'keyword': username},
            timeout=15
        )
        data = resp.json()
        if data['code'] == 0 and data['data'].get('result'):
            for user in data['data']['result']:
                if user['uname'] == username:
                    return str(user['mid'])
            return str(data['data']['result'][0]['mid'])
    except Exception:
        pass

    raise ValueError(f"无法解析用户名: {username}，请直接提供 UID (--uid)")


def fetch_all_videos(session: BiliSession, uid: str, filter_cover: bool = True):
    """获取某 UP 主的所有翻唱视频"""
    page = 1
    total_videos = []

    while True:
        resp = session.signed_get(
            'https://api.bilibili.com/x/space/wbi/arc/search',
            {'mid': uid, 'ps': 50, 'pn': page, 'order': 'pubdate'},
            timeout=20
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
            length_str = v['length']

            parts = length_str.split(':')
            total_seconds = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0
            if total_seconds < 60:
                continue
            if tid not in MUSIC_CATEGORY_TIDS:
                continue
            if filter_cover and tid != MUSIC_COVER_TID:
                has_kw = any(kw.lower() in title.lower() for kw in COVER_KEYWORDS)
                if not has_kw:
                    continue

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
    parser.add_argument('user', nargs='?', help='UP主用户名')
    parser.add_argument('--uid', default=None, help='直接指定 UID (跳过名称解析)')
    parser.add_argument('--output-dir', default=None)
    parser.add_argument('--all', action='store_true', help='不筛选翻唱关键词')
    parser.add_argument('--cookies', default=None,
                        help='cookies 文件路径 (默认: tools/bili_cookies.txt)')
    args = parser.parse_args()

    if not args.user and not args.uid:
        parser.error("必须提供 UP主用户名 或 --uid")

    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / 'w' / 'C_bilibili' / 'urls'
    output_dir.mkdir(parents=True, exist_ok=True)

    # cookies 文件查找顺序
    cookies_file = None
    for candidate in [
        args.cookies,
        project_root / 'tools' / 'bili_cookies.txt',
    ]:
        if candidate and Path(candidate).exists():
            cookies_file = str(Path(candidate))
            break

    if cookies_file:
        print(f"[*] 使用 cookies: {cookies_file}")
    else:
        print("[!] 未找到 cookies 文件，将以游客身份访问（可能受限）")

    print("[*] 初始化 B站会话...")
    session = BiliSession(cookies_file)

    if args.uid:
        uid = args.uid
    else:
        print(f"[*] 搜索用户: {args.user}")
        uid = resolve_uid(session, args.user)

    resp = session.session.get(
        'https://api.bilibili.com/x/space/acc/info',
        params={'mid': uid}, timeout=15
    )
    data = resp.json()
    if data['code'] != 0:
        print(f"[!] 获取用户信息失败: {data}")
        sys.exit(1)
    name = data['data']['name']
    print(f"[*] UP主: {name} (UID: {uid})")

    print("[*] 获取视频列表...")
    videos = fetch_all_videos(session, uid, filter_cover=not args.all)

    print(f"\n[*] 共找到 {len(videos)} 条匹配视频")
    if not videos:
        sys.exit(1)

    videos.sort(key=lambda x: x['created'], reverse=True)

    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    url_file = output_dir / f'{safe_name}.txt'
    with open(url_file, 'w', encoding='utf-8') as f:
        for v in videos:
            url = f'https://www.bilibili.com/video/{v["bvid"]}'
            f.write(f'# {v["title"]} | {v["length"]} | play:{v["play"]}\n')
            f.write(f'{url}\n')

    print(f"[+] URL 列表: {url_file} ({len(videos)} 条)")

    json_file = output_dir / f'{safe_name}_meta.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"[+] 元数据: {json_file}")


if __name__ == '__main__':
    main()
