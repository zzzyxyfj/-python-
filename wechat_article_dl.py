#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号文章下载器
====================
功能：扒取微信公众号文章并转为本地 Markdown 文件。
- 保留微信图床图片链接（data-src -> src）
- 保持内容一致性，优化排版结构
- 自动将 HTML 表格转为 Markdown 表格
- 自动去除文末打赏、广告、公众号推荐、往期推荐等非正文内容

依赖：pip install lxml

用法：
  python wechat_article_dl.py <文章URL> [-o 输出路径]
  示例:
  python wechat_article_dl.py "https://mp.weixin.qq.com/s/-6IwGXO-zwi6I8kWojSB4A"
"""

import html as html_mod
import os
import re
import sys
import time
from urllib.request import Request, urlopen

try:
    from lxml import html as lxml_html
except ImportError:
    print("错误：需要 lxml 库。请执行: pip install lxml")
    sys.exit(1)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1461"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.weixin.qq.com/",
}


def fetch(url, timeout=30):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=timeout) as r:
        b = r.read()
    text = b.decode("utf-8", errors="replace")
    if "环境异常" in text:
        print("请求被微信反爬机制拦截。")
    return text


def get_meta(html_text):
    meta = {}
    m = re.search(r'<h1[^>]*class="rich_media_title[^"]*"[^>]*>([\s\S]*?)</h1>', html_text)
    meta["title"] = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "无标题"
    m = re.search(r'id="js_name"[^>]*>([\s\S]*?)</span>', html_text)
    meta["author"] = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "未知作者"
    pub = ""
    m = re.search(r'publish_time%22%3A(\d{10})', html_text)
    if m:
        pub = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(m.group(1))))
    if not pub:
        m = re.search(r'publish_time["\']?\s*[:=]\s*["\']?(\d{10})', html_text)
        if m:
            pub = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(m.group(1))))
    if not pub:
        m = re.search(r'id="publish_time"[^>]*>([^<]+)<', html_text)
        if m:
            pub = m.group(1).strip()
    meta["publish_time"] = pub
    return meta


def get_content(html_text):
    start = html_text.find('id="js_content"')
    if start < 0:
        print("错误：未找到 js_content。")
        return ""
    tag_open = html_text.find(">", start)
    if tag_open < 0:
        return ""
    depth = 1
    pos = tag_open + 1
    while depth > 0 and pos < len(html_text):
        n_open = html_text.find("<div", pos)
        n_close = html_text.find("</div>", pos)
        if n_close < 0:
            break
        if 0 <= n_open < n_close:
            depth += 1
            pos = n_open + 5
        else:
            depth -= 1
            pos = n_close + 6
    return html_text[tag_open + 1: pos - 6]


BLOCK_KW = [
    "免责声明",
    "由于传播.*?本公众号.*?后果",
    "如有侵权.*?告知.*?删除",
    "所有工具安全性自测",
    r"VX[：:\s]",
    "只对常读和星标的公众号",
    "设为星标",
    "^朋友们现在",
    "NightCTI",
    "工具获取",
    "往期精彩",
    "回复关键字",
    "点击关注",
    r"否则.*?看不到了",
    "进入公众号",
    r"\d+\u3011.*?获取下载链接",
]
_BLOCK_RE = [re.compile(p) for p in BLOCK_KW]


def _is_block(text):
    for r in _BLOCK_RE:
        if r.search(text):
            return True
    return False


def clean(html_text):
    """清理推广内容：逐段删除 + 尾部卡片截断 + 尾部装饰截断。"""
    # 1) 逐段删除含推广词的短段落
    parts = []
    for block in re.split(r'(<(?:section|p|div|span)[^>]*>|</(?:section|p|div|span)>)', html_text):
        text = re.sub(r"<[^>]+>", "", block).strip()
        if text and len(text) < 150 and _is_block(text):
            continue
        parts.append(block)
    html_text = "".join(parts)

    # 2) 截断尾部推荐卡片（linktype="image"）
    card_pat = re.compile(r'<a[^>]*linktype="image"[^>]*data-linktype="1"[^>]*>')
    cut_at = len(html_text)
    for m in card_pat.finditer(html_text):
        cut_at = m.start()
        break
    if cut_at < len(html_text):
        return html_text[:cut_at]

    # 3) 关键词尾部截断
    for kw in ["往期推荐", "推荐阅读", "更多推荐", "精彩回顾"]:
        idx = html_text.rfind(kw)
        if idx > len(html_text) * 0.3:
            return html_text[:idx]

    # 4) 截断尾部装饰性内容
    last_sec = html_text.rfind("</section>")
    if last_sec > len(html_text) * 0.5:
        trail = html_text[last_sec + 10:]
        if len(re.findall(r'<(?:section|section )', trail)) < 2:
            html_text = html_text[:last_sec + 10]
    return html_text


def simplify(html_text):
    """data-src -> src；去除编辑器残留属性。"""
    def fix_img(m):
        t = m.group(0)
        ds = m.group(1)
        t = re.sub(r'data-src="[^"]*"', 'src="' + ds + '"', t, count=1)
        for a in ["data-imgfileid", "data-ratio", "data-s", "data-type",
                   "data-w", "data-aistatus", "data-croporisrc",
                   "data-cropx1", "data-cropx2", "data-cropy1", "data-cropy2",
                   "data-backw", "data-backh"]:
            t = re.sub(r'\s' + a + '="[^"]*"', "", t)
        return t
    html_text = re.sub(r'<img[^>]*data-src="([^"]+)"[^>]*>', fix_img, html_text)
    for a in ["powered-by", "opera-tn-ra-cell", "data-tool"]:
        html_text = re.sub(r'\s' + a + '="[^"]*"', "", html_text)
    html_text = re.sub(r'\s+title=""', "", html_text)
    for t in ["section", "p", "span", "div"]:
        html_text = re.sub(r'<' + t + r'[^>]*>\s*</' + t + r'>', "", html_text)
    return html_text


def _collect_rows(node):
    """从 table 节点收集所有行的单元格数据。"""
    rows = []
    for child in node:
        tag = child.tag if isinstance(child.tag, str) else None
        if tag in ("thead", "tbody", "tfoot"):
            for row in child:
                if row.tag == "tr":
                    cells = []
                    for cell in row:
                        if cell.tag in ("th", "td"):
                            cells.append(_render(cell).strip())
                    if cells:
                        rows.append(cells)
        elif tag == "tr":
            cells = []
            for cell in child:
                if cell.tag in ("th", "td"):
                    cells.append(_render(cell).strip())
            if cells:
                rows.append(cells)
    return rows


def _build_markdown_table(rows):
    """将行数据渲染为 Markdown 表格。"""
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    lines = ["\n"]
    # header 行
    lines.append("| " + " | ".join(rows[0]) + " |\n")
    # 分隔行
    lines.append("|" + "|".join([" --- " for _ in range(ncols)]) + "|\n")
    # 数据行
    for row in rows[1:]:
        # 补齐列数
        padded = list(row) + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(padded) + " |\n")
    lines.append("\n")
    return "".join(lines)


def _render(node):
    """递归将 lxml 节点转为 Markdown。"""
    tag = node.tag if isinstance(node.tag, str) else None
    if tag is None:
        return (node.text or "").strip()

    # --- 表格 ---
    if tag == "table":
        rows = _collect_rows(node)
        return _build_markdown_table(rows)
    if tag in ("thead", "tbody", "tfoot", "tr", "col", "colgroup"):
        # 这些由 table 处理器统一处理，跳过
        return ""
    if tag in ("th", "td"):
        # 由 table 处理器收集，但如果独立出现则渲染内容
        raw = "".join(_render(c) for c in node)
        return raw.strip()

    # --- 图片 ---
    if tag == "img":
        src = node.get("src") or node.get("data-src") or ""
        if src:
            return "\n![](" + html_mod.unescape(src) + ")\n"
        return ""
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "\n---\n"

    # --- 文本 ---
    texts = []
    if node.text:
        t = node.text.strip()
        if t:
            texts.append(t)
    for child in node:
        ct = _render(child)
        if ct.strip():
            texts.append(ct)
        if child.tail:
            tt = child.tail.strip()
            if tt:
                texts.append(tt)
    raw = "".join(texts)

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return "\n" + "#" * int(tag[1]) + " " + raw.strip() + "\n"
    if tag in ("strong", "b"):
        r = raw.strip()
        return "**" + r + "**" if r else ""
    if tag in ("em", "i"):
        r = raw.strip()
        return "*" + r + "*" if r else ""
    if tag == "a":
        href = node.get("href", "")
        r = raw.strip()
        if href and r:
            return "[" + r + "](" + html_mod.unescape(href) + ")"
        return r
    if tag == "code":
        r = raw.strip()
        return "`" + r + "`" if r else ""
    if tag == "pre":
        return "\n```\n" + raw.strip() + "\n```\n"
    if tag == "blockquote":
        r = raw.strip()
        if r:
            return "\n> " + r.replace(chr(10), "\n> ") + "\n"
        return ""
    if tag in ("ul", "ol"):
        lines = ["\n"]
        for i, li in enumerate(node):
            if li.tag == "li":
                t = _render(li).strip()
                p = "- " if tag == "ul" else str(i + 1) + ". "
                if t:
                    lines.append(p + t + "\n")
        return "".join(lines) + "\n"
    if tag in ("section", "div", "p", "span"):
        raw = raw.strip()
        if raw and tag in ("p", "section", "div"):
            return "\n" + raw + "\n"
        return raw
    return raw


def to_md(html_text):
    html_text = html_text.strip()
    try:
        tree = lxml_html.fromstring(html_text)
        return _render(tree).strip()
    except Exception:
        t = re.sub(r"<br\s*/?>", "\n", html_text)
        t = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r"\n![](\1)\n", t)
        t = re.sub(r"<[^>]+>", "", t)
        return re.sub(r"\n{3,}", "\n\n", t).strip()


def polish(md):
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"\n---\n---\n", "\n---\n", md)
    md = re.sub(r'^\s*进入公众号\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'^\s*\d+\u3011.*?获取下载链接\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'^\s*NightCTI\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'\*\*夜组安全\*\*.*?\uff0c\s*\n', '', md)
    md = re.sub(r'^\s*##\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'^\s*功能\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'^\s*描述\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip() + "\n"


def run(url, output_path=None):
    print("正在抓取:", url)
    raw = fetch(url)
    meta = get_meta(raw)
    print("标题:", meta["title"])
    print("作者:", meta["author"])
    print("发布:", meta["publish_time"])
    content = get_content(raw)
    if not content:
        return ""
    print("正文: %d 字符" % len(content))
    content = clean(content)
    print("清理后: %d 字符" % len(content))
    content = simplify(content)
    md = to_md(content)
    md = polish(md)
    header = (
        "---\n"
        "title: " + meta["title"] + "\n"
        "author: " + meta["author"] + "\n"
        "source: 微信公众号\n"
        "url: " + url + "\n"
        "publish_time: " + meta["publish_time"] + "\n"
        "download_time: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n"
        "---\n\n"
        "# " + meta["title"] + "\n\n"
        "> **作者：** " + meta["author"] + "  \n"
        "> **来源：** 微信公众号  \n"
        "> **发布时间：** " + meta["publish_time"] + "  \n"
        "> **原文链接：** [" + url + "](" + url + ")\n"
        "\n---\n\n"
    )
    if not output_path:
        safe = re.sub(r'[\\/:*?"<>|]', "_", meta["title"])
        safe = re.sub(r"\s+", "_", safe)[:80]
        output_path = safe + ".md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + md)
    print("\n[OK] 已保存:", os.path.abspath(output_path))
    return os.path.abspath(output_path)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="微信公众号文章下载器")
    p.add_argument("url", help="文章 URL")
    p.add_argument("-o", "--output", help="输出路径")
    args = p.parse_args()
    run(args.url, args.output)
