# xhs-skills

两个用于**小红书 / RedNote（国际站）图片下载**的 agent skill，来自一套真实跑通的流程，都能直接拿去用：

| skill | 作用 |
|---|---|
| [`xhs-media-download`](xhs-media-download/SKILL.md) | 给一个笔记链接 → 把笔记里的照片按 CDN 提供的**最高清晰度**存成**无损 PNG**（可选发到 Telegram）；也支持批量下载某个博主最新 N 篇 |
| [`xhs-comment-images`](xhs-comment-images/SKILL.md) | 把**评论区**里所有人发的图全部抓下来（翻完所有分页 + 展开所有回复），打包成一个 zip |

两个 skill 都写成 Hermes 的 skill 格式（`SKILL.md` + `scripts/`），但里面的坑与结论与具体 agent 无关，换成别的 agent / 纯脚本流程一样适用。

## 装法

```bash
mkdir -p ~/.hermes/skills/media
cp -r xhs-media-download xhs-comment-images ~/.hermes/skills/media/
```

不用 Hermes 的话，直接读 `SKILL.md` 里的过程，或者单独调 `scripts/*.py`：

```bash
python3 xhs-media-download/scripts/fetch_photos.py "<笔记链接>" --telegram
python3 xhs-media-download/scripts/fetch_user_photos.py --from-note "<任意笔记链接>" --limit 20 --zip
```

## 前置条件

- **Python 3 + Pillow + curl**（`python3 -m pip install --user pillow`）
- **一个已登录的 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 实例**：脚本默认调它本地的 `http://127.0.0.1:18060/api/v1`，并从 `~/xiaohongshu-mcp/data/cookies.json` 读扫码登录后的 cookies（cookie 只在你本机使用，不会外传）
- 想用 Telegram 发送（`--telegram`）才需要 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_HOME_CHANNEL`

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `XHS_COOKIES` | `~/xiaohongshu-mcp/data/cookies.json` | cookies 文件路径 |
| `XHS_PROXY` | 空（直连） | 可选出口代理，如 `socks5h://host:port`。图片 CDN 本身不校验 IP、不需要登录，所以多数情况**不需要**代理；只有抓笔记页 HTML / 主页数据时某些出口会被降级成游客页，这时才用得上 |
| `HERMES_ENV_FILE` | `~/.hermes/.env` | 存放 Telegram 凭据的 env 文件 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_HOME_CHANNEL` | — | 仅 `--telegram` 时需要 |

## 几个值得先知道的结论（都实测过）

- **要原图就得用「App 分享 → 复制链接」的整段文字**：链接里的 `xsec_token` 是必需的，裸链接（手打 URL）实测 302 拿不到数据。
- **别自己拼图片变体 URL**：CDN 每个尺寸的路径都带独立签名，把某个尺寸的后缀拼到另一个的 hash 上、把 `_3` 改成 `_1`、或删掉 `!...` 后缀，都会 **403**。只用拿到的 URL。
- **不要用文件大小判断清晰度**：WebP 比 JPEG 更省字节，实测同一张图 `webp_3`（164 KB）和 `jpg_3`（190 KB）像素差只有 1.8/255 —— 更小的 WebP 不等于更差的图。
- **评论区那套不能自己签名**：评论接口的 `X-s` / `X-t` 等签名与 URL、时间绑定，无法重放；正确做法是让页面自己发请求，然后 hook `fetch`/`XHR` 抓返回（`hook_capture.js` 就是干这个的）。
- **评论区翻页必须派发真实的 `mouseWheel` 事件**，只改 `scrollTop` 永远不会触发加载；另外**视口高度是个隐藏开关**（~577 px 时只加载第一页，1100 px 才会继续加载）。
- **小红书的 `www.xiaohongshu.com` 对非中国出口会返回游客壳页**（实测 48 KB），而国际站 `www.rednote.com` 返回完整状态（351 KB）——所以非中国出口要打 `rednote.com`。

## 免责声明

仅供个人研究、备份自己可见的内容使用。请遵守小红书的用户协议与 robots 规则，控制请求频率（脚本里已内置 sleep 与分页节流），**不要**把抓下来的内容用于再发布、转卖或批量采集。图片版权属于原作者。

MIT（见各 `SKILL.md` 的 frontmatter）。
