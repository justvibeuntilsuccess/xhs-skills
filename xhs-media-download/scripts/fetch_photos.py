#!/usr/bin/env python3
"""小红书 / RedNote 笔记照片下载器 — 默认产出**无损 PNG**。

用法:
    python3 fetch_photos.py <笔记链接或 24 位 id> [选项]

选项:
    --token TOK     只给了 id 时用这个补 xsec_token
    --outdir DIR    输出目录(默认 ./xhs_<id>)
    --mode png|jpg  png=无损(默认) | jpg=质量 97(体积小)
    --telegram      下载后以「文件」方式发到 Telegram(不压缩)
    --limit N       只取前 N 张

前提:
    - cookies 在 ~/xiaohongshu-mcp/data/cookies.json(读页面状态用;可用 XHS_COOKIES 覆盖)
    - 走页面路线时可设 XHS_PROXY(出口代理,如 socks5h://host:port);失败会自动改直连重试
    - Telegram 凭据读 ~/.hermes/.env 或 $HERMES_ENV_FILE
      (TELEGRAM_BOT_TOKEN / TELEGRAM_HOME_CHANNEL)
"""
import argparse, json, os, re, subprocess, sys

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow: /usr/bin/python3 -m pip install --user pillow")

HOME   = os.path.expanduser("~")
REPO   = os.path.join(HOME, "xiaohongshu-mcp")
MCP    = "http://127.0.0.1:18060/api/v1/feeds/detail"
COOKIE = os.environ.get("XHS_COOKIES") or os.path.join(REPO, "data", "cookies.json")
ENV    = os.environ.get("HERMES_ENV_FILE") or os.path.join(HOME, ".hermes", ".env")
UA     = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
PROXY  = os.environ.get("XHS_PROXY", "")   # 可选出口代理, 例如 socks5h://host:port (留空=直连)


def curl(args, timeout=90):
    """跑 curl 并把输出收回来(不要用 -o,需要写文件的场合自己传 -o 路径)

    注意:capture_output 必须始终为 True。早前写成 capture_output=binary,
    非二进制分支就把 stdout 漏给了终端 —— 整个 JSON 响应会直接刷屏。
    """
    cmd = ["curl", "-sS", "-m", str(timeout)] + args
    r = subprocess.run(cmd, capture_output=True)
    return (r.returncode,
            r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def resolve_link(link):
    """短链 / 分享文本 → (id, token, 规范 URL)"""
    m = re.search(r"https?://\S+", link)
    url = m.group(0).rstrip('",)') if m else link
    if "xhslink.com" in url or "xhslink.cn" in url:
        _, out, _ = curl(["-o", "/dev/null", "-w", "%{url_effective}", "-L", url])
        if out.startswith("http"):
            url = out
    nid = re.search(r"/(?:explore|discovery/item|item)/([0-9a-f]{24})", url) or re.search(r"\b([0-9a-f]{24})\b", url)
    tok = re.search(r"[?&]xsec_token=([^&\s]+)", url)
    return (nid.group(1) if nid else None), (tok.group(1) if tok else None), url


def cookie_header(site="rednote.com"):
    try:
        data = json.load(open(COOKIE, encoding="utf-8"))
    except Exception:
        return ""
    items = data if isinstance(data, list) else data.get("cookies", data)
    return "; ".join(f"{c['name']}={c['value']}" for c in items
                     if site in (c.get("domain") or "") and c.get("name"))


def slice_array(s, start):
    """从 '[' 开始做括号配对(跳过字符串内的括号)"""
    depth = 0; instr = False; esc = False
    for k in range(start, len(s)):
        ch = s[k]
        if instr:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': instr = False
        else:
            if ch == '"': instr = True
            elif ch == "[": depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return s[start:k + 1]
    return None


def from_mcp(nid, token):
    """路线 1:MCP 详情接口(给 WebP 图集;图文笔记=全部,视频笔记=仅封面)"""
    body = json.dumps({"feed_id": nid, "xsec_token": token})
    rc, out, _ = curl(["-X", "POST", MCP, "-H", "Content-Type: application/json", "-d", body])
    if rc != 0:
        return None
    try:
        note = json.loads(out)["data"]["data"]["note"]
    except Exception:
        return None
    urls = [(i.get("urlDefault") or i.get("urlPre")) for i in (note.get("imageList") or [])]
    meta = {"title": note.get("title") or "", "author": (note.get("user") or {}).get("nickname") or "",
            "type": note.get("type") or "", "source": "mcp"}
    return [u for u in urls if u], meta


def from_page(url):
    """路线 2:抓笔记页 HTML,解 imageList(给 JPEG 图集,并回吐新 token)"""
    hdr = cookie_header()
    for extra in (["--proxy", PROXY] if PROXY else [], []):
        rc, out, _ = curl(extra + ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {hdr}",
                                   "-H", "Referer: https://www.rednote.com/", url], timeout=60)
        if rc == 0 and len(out) > 5000 and '"imageList"' in out:
            break
    else:
        return None
    m = re.search(r'"imageList":\s*\[', out)
    if not m:
        return None
    try:
        il = json.loads(slice_array(out, out.index("[", m.start())))
    except Exception:
        return None
    urls = []
    for x in il:
        cand = x.get("urlDefault")
        for info in (x.get("infoList") or []):
            if info.get("imageScene") == "WB_DFT":
                cand = str(info.get("url") or "").replace("\\u002F", "/") or cand
        if cand:
            urls.append(cand)
    t = re.search(r'"title":"([^"]{0,120})"', out)
    u = re.search(r'"nickname":"([^"]{0,60})"', out)
    return urls, {"title": t.group(1) if t else "", "author": u.group(1) if u else "",
                  "type": "?", "source": "page"}


def download(url, dest_noext):
    ext = ".webp" if "webp" in url.split("!")[-1] else ".jpg"
    raw = dest_noext + ext
    rc, _, err = curl(["-o", raw, "-H", f"User-Agent: {UA}",
                       "-H", "Referer: https://www.rednote.com/", url], timeout=90)
    if rc != 0 or not os.path.exists(raw) or os.path.getsize(raw) < 2000:
        return None, err
    return raw, None


def send_documents(paths, caption):
    env = {}
    for line in open(ENV, encoding="utf-8", errors="replace"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat:
        return "跳过: ~/.hermes/.env 里没有 TELEGRAM_BOT_TOKEN / TELEGRAM_HOME_CHANNEL"
    results = []
    for i, p in enumerate(paths):
        args = ["-X", "POST", f"https://api.telegram.org/bot{token}/sendDocument",
                "--form-string", f"chat_id={chat}",
                "-F", f"document=@{p};filename={os.path.basename(p)}"]
        if i == 0 and caption:
            args += ["--form-string", f"caption={caption}"]
        rc, out, _ = curl(args, timeout=180)
        try:
            d = json.loads(out); doc = d["result"]["document"]
            results.append(f"  [{i+1}] ok  {doc['file_name']}  {doc['file_size']} 字节  (message_id {d['result']['message_id']})")
        except Exception:
            results.append(f"  [{i+1}] 失败: {out[:120]}")
    return "\n".join(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("link")
    ap.add_argument("--token", default=None)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--mode", choices=["png", "jpg"], default="png")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    nid, tok, url = resolve_link(a.link)
    tok = a.token or tok
    if not nid:
        sys.exit("× 解析不出笔记 id —— 把 App 里「分享 → 复制链接」的整段文字发过来")
    if not tok:
        sys.exit("× 链接里没有 xsec_token(裸链接实测 302 拿不到数据)—— 请用 App 分享出来的链接")

    got = from_mcp(nid, tok) or from_page(url)
    if not got or not got[0]:
        sys.exit("× 拿不到图集:检查 MCP 容器 / cookies / sidecar 是否在跑")
    urls, meta = got
    if a.limit:
        urls = urls[:a.limit]

    outdir = a.outdir or os.path.join(os.getcwd(), f"xhs_{nid}")
    os.makedirs(outdir, exist_ok=True)
    print(f"笔记: {meta.get('title','(无标题)')}  |  作者: {meta.get('author','?')}  |  类型: {meta.get('type','?')}  |  来源: {meta.get('source')}")
    print(f"共 {len(urls)} 张 → {outdir}\n")

    saved = []
    for i, u in enumerate(urls, 1):
        stem = os.path.join(outdir, f"{nid}_{i:02d}")
        raw, err = download(u, stem)
        if not raw:
            print(f"  [{i}] 下载失败: {err}");  continue
        im = Image.open(raw).convert("RGB")
        if a.mode == "png":
            out = stem + ".png";  im.save(out, "PNG", optimize=True)
        else:
            out = stem + ".jpg";  im.save(out, "JPEG", quality=97, subsampling=0)
        saved.append(out)
        print(f"  [{i}] {im.size[0]}x{im.size[1]}  {os.path.getsize(raw)//1024:>5} KB 源 → {os.path.getsize(out)//1024:>5} KB {a.mode.upper()}")
    print(f"\n完成: {len(saved)}/{len(urls)} 张")

    if a.telegram and saved:
        cap = f"{meta.get('title','')} — {meta.get('author','')}".strip(" —")
        cap += f"\n以文件发送({'无损 PNG' if a.mode=='png' else 'JPEG q97'}),聊天里点开看原样"
        print("发送 Telegram:")
        print(send_documents(saved, cap))


if __name__ == "__main__":
    main()
