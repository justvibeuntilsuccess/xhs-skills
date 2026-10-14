# xhs-skills

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/justvibeuntilsuccess/xhs-skills/blob/main/README.md)
[![zh-cn](https://img.shields.io/badge/lang-zh--cn-green.svg)](https://github.com/justvibeuntilsuccess/xhs-skills/blob/main/README.zh-cn.md)

Two agent skills for downloading images from **Xiaohongshu / RedNote (international site)**, extracted from a setup that actually works end to end:

| skill | what it does |
|---|---|
| [`xhs-media-download`](xhs-media-download/SKILL.md) | Give it a note link → saves every photo in the note at the **highest quality the CDN serves**, as **lossless PNG** (optionally delivered to Telegram). Also does batch downloads of one author's latest N notes. |
| [`xhs-comment-images`](xhs-comment-images/SKILL.md) | Pulls **every photo posted in the comments** (all pages scrolled + all replies expanded) and delivers them as a single zip. |

Both are written in the Hermes skill format (`SKILL.md` + `scripts/`), but the findings and gotchas inside are agent-agnostic — the same steps work in any other agent, or as plain scripts.

## Install

```bash
mkdir -p ~/.hermes/skills/media
cp -r xhs-media-download xhs-comment-images ~/.hermes/skills/media/
```

Not using Hermes? Read the procedure in each `SKILL.md`, or call the scripts directly:

```bash
python3 xhs-media-download/scripts/fetch_photos.py "<note link>" --telegram
python3 xhs-media-download/scripts/fetch_user_photos.py --from-note "<any note link>" --limit 20 --zip
```

## Requirements

- **Python 3 + Pillow + curl** (`python3 -m pip install --user pillow`)
- **A logged-in [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) instance**: the scripts call its local `http://127.0.0.1:18060/api/v1` API and read the QR-login cookies from `~/xiaohongshu-mcp/data/cookies.json` (cookies stay on your machine; nothing is sent anywhere else)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_HOME_CHANNEL` only if you want the `--telegram` delivery

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `XHS_COOKIES` | `~/xiaohongshu-mcp/data/cookies.json` | Path to the cookies file |
| `XHS_PROXY` | empty (direct) | Optional egress proxy, e.g. `socks5h://host:port`. The image CDN is neither login- nor IP-gated, so most runs **don't need** a proxy — it only matters when fetching note HTML / profile data, where some egresses get downgraded to the guest shell. |
| `HERMES_ENV_FILE` | `~/.hermes/.env` | File holding the Telegram credentials |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_HOME_CHANNEL` | — | Only needed for `--telegram` |

## Findings worth knowing up front (all measured)

- **For originals you need the app's own share text**: the `xsec_token` inside the link is mandatory. A bare, hand-typed URL returns `302` with no data (measured).
- **Never synthesise an image variant URL**: every rendition on the CDN has its own signed path (timestamp + hash). Recombining one rendition's suffix with another's hash, switching `_3` to `_1`/`_2`, or dropping the `!...` suffix all return **403**. Use only URLs a response handed you.
- **Don't rank renditions by file size**: WebP is simply the more efficient codec. Measured on the same picture, `webp_3` (164 KB) vs `jpg_3` (190 KB) differed by a pixel-difference mean of 1.8/255 — a smaller WebP is not a worse image.
- **The comment API cannot be hand-signed**: its `X-s` / `X-t` signatures are bound to the URL and the time and cannot be replayed. Let the page make its own calls and hook `fetch`/`XHR` instead (`hook_capture.js` does exactly that).
- **Comment pagination needs real `mouseWheel` events** — setting `scrollTop` never fires the loader. And **viewport height is a hidden gate**: at ~577 px only page 1 loads; at 1100 px the list keeps growing.
- **`www.xiaohongshu.com` serves a guest shell to non-China egresses** (measured 48 KB), while the international host `www.rednote.com` returns the full state (351 KB) — use `rednote.com` outside China.

## Disclaimer

For personal research and backing up content you can already see. Respect Xiaohongshu's terms of service and robots rules, keep request rates low (the scripts already sleep between requests and pages), and **do not** republish, resell or bulk-scrape what you download. Image copyright belongs to the original authors.

MIT (see the `license` field in each `SKILL.md`).
