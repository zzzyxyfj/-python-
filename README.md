#
# wechat-article-dl · 微信公众号文章下载器
#
# 扒取微信公众号文章并转为本地 Markdown 文件，保留原始微信图床图片链接，
# 自动清理文末打赏、广告、公众号推荐等非正文内容，支持 HTML 表格转 Markdown 表格。
#

## 项目简介

一个轻量级 Python 脚本，只需一个 URL 即可将微信公众号文章完整转为本地 Markdown 文件。

**核心能力：**
- 模拟微信内置浏览器环境抓取文章，绕过反爬限制
- 自动去除文末的打赏、广告、公众号关注引导、往期推荐等非正文内容
- 保留微信图床链接，图片不下载到本地，文章体积小、加载快
- 原文中的 HTML 表格自动转为 Markdown 表格
- 生成的 Markdown 文件结构清晰，可直接用于个人知识库、博客发布等场景

## 功能特性

| 特性 | 说明 |
| --- | --- |
| 一键抓取 | 输入 URL，输出 Markdown，没有中间步骤 |
| 反爬对抗 | 模拟 MicroMessenger 浏览器 UA，成功率高 |
| 元数据提取 | 标题、作者、发布时间自动填入 Markdown 头信息 |
| 图片保留 | 使用微信原始图床链接，不下载、不转存 |
| 内容洁净 | 自动清除免责声明、打赏、广告、星标引导、往期推荐等页面噪声 |
| 表格支持 | 原文的 HTML `<table>` 正确转为 Markdown `| ... |` 格式 |
| 标题层级 | 保留原文的标题层级结构，转为 `#` / `##` / `###` |
| 加粗/链接 | 保留 `**加粗**` 和 `[链接](url)` 格式 |

## 环境要求

- Python 3.8+
- 依赖: `lxml`

```bash
pip install lxml
```

## 快速开始

```bash
python wechat_article_dl.py "https://mp.weixin.qq.com/s/xxx"
```

脚本会自动以文章标题生成 `.md` 文件，保存在当前目录。

**指定输出路径：**

```bash
python wechat_article_dl.py "https://mp.weixin.qq.com/s/xxx" -o 我的文章.md
```

## 运行示例

```bash
$ python wechat_article_dl.py "https://mp.weixin.qq.com/s/-6IxxxO-zwixxxxSB4A"
正在抓取: https://mp.weixin.qq.com/s/-6IxxxxGXO-zwi6IxxxA
标题: Title...
作者: xxxx
发布: 2026-06-16 07:30:00
正文: 131016 字符
清理后: 121442 字符

[OK] 已保存: Title...md
```

**输出文件预览：**

```markdown
---
title: xxxxx...
author: xxxx
source: 微信公众号
url: https://mp.weixin.qq.com/s/...
publish_time: 2026-06-16 07:30:00
---

# 文章标题

> **作者：** xxxx
> **来源：** 微信公众号
> **发布时间：** 2026-06-16 07:30:00

---

![](https://mmbiz.qpic.cn/...)

| 功能 | 描述 |
| --- | --- |
| **AI Agent 自动化** | 基于 LangChain4j... |
| **多模型支持** | 兼容 OpenAI... |

正文内容...
```

## 工作原理

### 抓取阶段
使用 `urllib.request` 携带微信内置浏览器的 User-Agent 头，请求文章页面 HTML。微信的反爬机制对 MicroMessenger UA 相对宽松，成功率高。

### 提取阶段
1. **元数据** — 正则提取标题 (`<h1 class="rich_media_title">`)、作者 (`#js_name`)、发布时间（Unix 时间戳，三路兜底提取）
2. **正文** — 定位 `<div id="js_content">`，通过栈式括号匹配提取嵌套 div 内的纯正文 HTML

### 清理阶段
四级清理流水线：
1. 按块级标签分割 HTML，逐段匹配推广关键词（免责声明、VX 联系方式、关注引导、星标引导等）并删除
2. 从前往后扫描 `<a linktype="image" data-linktype="1">` 推荐文章卡片标记，找到第一张卡片后截断尾部
3. 关键词尾部截断（"往期推荐""推荐阅读"等）
4. 截断最后一个 `</section>` 之后的装饰性内容（纯图片、空段落等）

*清理规则集中在 `BLOCK_KW` 列表中，可根据需要自行增删。*

### 转换阶段
1. 图片 `data-src` → `src`，保留原始微信 `mmbiz.qpic.cn` 链接
2. 移除秀米编辑器专有属性（`powered-by`、`opera-tn-ra-cell` 等）和空标签
3. 递归遍历 lxml 树，将各标签转为对应 Markdown 语法：
   - `table` → `| ... | ... |` Markdown 表格
   - `h1`~`h6` → `#` ~ `######`
   - `strong`/`b` → `**粗体**`
   - `a` → `[链接](url)`
   - `img` → `![](url)`
   - `ul`/`ol` → `-` / `1.` 列表
   - `section`/`div`/`p` → 段落
4. 最后 polish 扫尾：合并多余空行、清理残留的推广碎片文本

## 推广关键词自定义

编辑脚本中的 `BLOCK_KW` 列表即可：

```python
BLOCK_KW = [
    "免责声明",
    r"VX[：:\s]",
    "工具获取",
    "往期精彩",
    # ... 按需增删
]
```

每个条目是一个正则表达式，匹配到的短段落（长度 < 150 字符）将被删除。

## 局限性说明

- 依赖微信的反爬策略当前行为；若微信调整 UA 检测逻辑，可能需要更新 `HEADERS`
- 仅支持公开可访问的微信公众号文章（需在微信内可正常打开）
- 若文章页触发滑块验证码，脚本无法自动通过，需更换 IP 后重试
- 秀米等第三方编辑器的复杂排版（如多列布局、特殊分割线）可能无法完美还原为 Markdown
- 保留的图片链接依赖微信图床，长期有效性由微信控制

## 文件结构

```
wechat-article-dl/
├── wechat_article_dl.py   # 主脚本
├── README.md              # 本文件
└── *.md                   # 输出的 Markdown 文件
```

## License

MIT
