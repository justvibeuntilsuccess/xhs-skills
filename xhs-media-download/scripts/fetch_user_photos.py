#!/usr/bin/env python3
"""批量下载某个博主**最新 N 篇**笔记的照片(默认无损 PNG)。

用法:
    python3 fetch_user_photos.py --user-id <24位id> --user-token <tok> [选项]
    python3 fetch_user_photos.py --from-note "<任意一篇笔记的链接>"   # 自动推导 user id + token

选项:
    --limit N        取最新 N 篇(默认 20)
    --outdir DIR     输出目录(默认 ./xhs_user_<id>)
    --mode png|jpg   png=无损(默认) | jpg=质量 97
    --telegram       下载后把图片一张一个「文件」发 Telegram
    --zip            改为把图片打包成 ≤45MB 的分卷 zip 再发(图多时用这个)

要点(实测 2026-10-11):
    * 笔记 id 的前 8 位十六进制 = 发布时间的 unix 秒数 → 用它排序最能代表“最新”,
      不会被博主的置顶帖干扰(主页返回里置顶帖会排在第一位,顺序不单调)。
    * 主页接口响应是双层嵌套:data.data.{userBasicInfo,interactions,feeds}。
    * 每篇笔记的详情要单独请求,中间 sleep 避免风控;每篇的原始响应先落盘再解析。
"""
import argparse, json, os, re, subprocess, sys, time, zipfile

from PIL import Image

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "xiaohongshu-mcp")
BASE = "http://127.0.0.1:18060/api/v1"
COOKIE = os.environ.get("XHS_COOKIES") or os.path.join(REPO, "data", "cookies.json")
ENV = os.environ.get("HERMES_ENV_FILE") or os.path.join(HOME, ".hermes", ".env")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
PROXY = os.environ.get("XHS_PROXY", "")   # 可选出口代理; 留空=直连
ZIP_LIMIT = 45 * 1024 * 1024


def curl(args, timeout=120):
    r = subprocess.run(["curl", "-sS", "-m", str(timeout)] + args, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def api(path, payload):
    rc, out, err = curl(["-X", "POST", f"{BASE}{path}", "-H", "Content-Type: application/json",
                         "-d", json.dumps(payload)], timeout=180)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def cookie_header(site="rednote.com"):
    try:
        data = json.load(open(COOKIE, encoding="utf-8"))
    except Exception:
        return ""
    items = data if isinstance(data, list) else data.get("cookies", data)
    return "; ".join(f"{c['name']}={c['value']}" for c in items
                     if site in (c.get("domain") or "") and c.get("name"))


def user_candidates_from_note(url):
    """抓笔记页,列出页面里所有的 (userId, xsecToken) 候选对。

    页面里同时有「登录用户自己」和「笔记作者」的用户对象,不能只取第一个 ——
    必须枚举出全部候选,再由调用方逐个拿主页接口试,哪个能返回笔记就是对的。
    """
    hdr = cookie_header()
    html = ""
    for extra in (["--proxy", PROXY] if PROXY else [], []):
        rc, out, _ = curl(extra + ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {hdr}",
                                   "-H", "Referer: https://www.rednote.com/", url], timeout=60)
        if rc == 0 and len(out) > 5000:
            html = out
            break
    cands = []
    for m in re.finditer(r'\{[^{}]*"userId":\s*"([0-9a-f]{24})"[^{}]*?"xsecToken":\s*"([^"]+)"[^{}]*?\}', html):
        uid, tok = m.group(1), m.group(2)
        nick = re.search(r'"nickname":\s*"([^"]{0,40})"', m.group(0))
        if all(uid != c[0] for c in cands):
            cands.append((uid, tok, nick.group(1) if nick else ""))
    return cands


def note_time(nid):
    try:
        return int(nid[:8], 16)
    except Exception:
        return 0


def download(url, stem):
    ext = ".webp" if "webp" in url.split("!")[-1] else ".jpg"
    raw = stem + ext
    rc, _, err = curl(["-o", raw, "-H", f"User-Agent: {UA}",
                       "-H", "Referer: https://www.rednote.com/", url], timeout=90)
    if rc != 0 or not os.path.exists(raw) or os.path.getsize(raw) < 2000:
        return None
    return raw


def tg_creds():
    env = {}
    for line in open(ENV, encoding="utf-8", errors="replace"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_HOME_CHANNEL")


def send_document(path, caption=None, as_filename=None):
    token, chat = tg_creds()
    if not token or not chat:
        return "× ~/.hermes/.env 缺 TELEGRAM_BOT_TOKEN / TELEGRAM_HOME_CHANNEL"
    name = as_filename or os.path.basename(path)
    args = ["-X", "POST", f"https://api.telegram.org/bot{token}/sendDocument",
            "--form-string", f"chat_id={chat}", "-F", f"document=@{path};filename={name}"]
    if caption:
        args += ["--form-string", f"caption={caption}"]
    rc, out, _ = curl(args, timeout=600)
    try:
        d = json.loads(out); doc = d["result"]["document"]
        return f"ok  {doc['file_name']}  {doc['file_size']} 字节  (msg {d['result']['message_id']})"
    except Exception:
        return f"失败: {out[:160]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id")
    ap.add_argument("--user-token")
    ap.add_argument("--from-note")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--outdir")
    ap.add_argument("--mode", choices=["png", "jpg"], default="png")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--zip", action="store_true")
    a = ap.parse_args()

    cands = []
    if a.from_note:
        cands = user_candidates_from_note(a.from_note)
        if not cands:
            sys.exit("× 从链接里推导不出任何 (user id, token) 对(链接要带 xsec_token)")
        print(f"链接里找到 {len(cands)} 个用户候选,逐个试主页接口…")
    if a.user_id and a.user_token:
        cands.insert(0, (a.user_id, a.user_token, ""))
    if not cands:
        sys.exit("× 需要 --user-id + --user-token,或 --from-note <链接>")

    feeds, inner, uid, utok = [], {}, None, None
    for c_uid, c_tok, c_nick in cands[:5]:
        prof = api("/user/profile", {"user_id": c_uid, "xsec_token": c_tok, "tab": "note"})
        got = ((prof or {}).get("data") or {}).get("data") or {}
        n = len(got.get("feeds") or [])
        print(f"  试 {c_uid} ({c_nick}) → {n} 篇")
        if n:
            feeds, inner, uid, utok = got["feeds"], got, c_uid, c_tok
            break
    if not feeds:
        sys.exit("× 所有候选都拿不到主页笔记:检查 token 是否有效 / 出口是否正常")
    bi = inner.get("userBasicInfo") or {}
    print(f"博主: {bi.get('nickname') or ''} ({bi.get('redId','')}) | 主页返回 {len(feeds)} 篇")

    feeds = sorted(feeds, key=lambda f: note_time(f.get("id", "")), reverse=True)[:a.limit]
    print(f"取最新 {len(feeds)} 篇:\n")
    for i, f in enumerate(feeds, 1):
        nc = f.get("noteCard") or {}
        ts = time.strftime("%Y-%m-%d", time.localtime(note_time(f["id"])))
        print(f"  {i:>2}. {ts}  {str(nc.get('displayTitle') or '(无题)')[:38]}")

    outdir = a.outdir or os.path.join(os.getcwd(), f"xhs_user_{uid}")
    os.makedirs(outdir, exist_ok=True)
    manifest, images = [], []

    for i, f in enumerate(feeds, 1):
        nid, tok = f["id"], f.get("xsecToken")
        raw_path = os.path.join(outdir, f".note_{nid}.json")
        rc, out, _ = curl(["-X", "POST", f"{BASE}/feeds/detail", "-H", "Content-Type: application/json",
                           "-d", json.dumps({"feed_id": nid, "xsec_token": tok}), "-o", raw_path], timeout=180)
        try:
            note = json.load(open(raw_path, encoding="utf-8"))["data"]["data"]["note"]
        except Exception:
            print(f"  [{i:>2}] 详情失败,跳过 {nid}");  continue
        urls = [u for u in ((x.get("urlDefault") or x.get("urlPre")) for x in (note.get("imageList") or [])) if u]
        title = note.get("title") or ""
        done = 0
        for j, u in enumerate(urls, 1):
            stem = os.path.join(outdir, f"{nid}_{j:02d}")
            raw = download(u, stem)
            if not raw:
                continue
            im = Image.open(raw).convert("RGB")
            if a.mode == "png":
                out = stem + ".png";  im.save(out, "PNG", optimize=True)
            else:
                out = stem + ".jpg";  im.save(out, "JPEG", quality=97, subsampling=0)
            images.append({"note_id": nid, "title": title, "file": out,
                           "raw": raw, "dim": f"{im.size[0]}x{im.size[1]}"})
            done += 1
        manifest.append({"note_id": nid, "title": title, "time": note_time(nid), "images": done})
        print(f"  [{i:>2}] {done} 张  {str(title)[:34]}")
        time.sleep(1.5)

    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(x["file"]) for x in images)
    print(f"\n完成: {len(images)} 张图,合计 {total/1024/1024:.1f} MB → {outdir}")

    if a.telegram and not a.zip:
        print("\n逐个发 Telegram(文件模式):")
        for k, x in enumerate(images, 1):
            cap = f"{x['title']} — {x['note_id'][:8]} ({k}/{len(images)})" if k == 1 else None
            print(f"  [{k}] {send_document(x['file'], cap)}")
    elif a.zip:
        zips, cur, cur_size, idx = [], [], 0, 1
        for x in images:
            sz = os.path.getsize(x["file"])
            if cur and cur_size + sz > ZIP_LIMIT:
                zips.append((cur, idx)); idx += 1; cur, cur_size = [], 0
            cur.append(x["file"]); cur_size += sz
        if cur:
            zips.append((cur, idx))
        print(f"\n打包: {len(zips)} 个 zip(上限 45MB)")
        for files, n in zips:
            zp = os.path.join(outdir, f"xhs_{uid}_part{n}.zip")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for fp in files:
                    z.write(fp, os.path.basename(fp))
            mb = os.path.getsize(zp)/1024/1024
            print(f"  part{n}: {len(files)} 张, {mb:.1f} MB")
            if a.telegram:
                print("    →", send_document(zp, f"最新笔记照片(无损 PNG) 第 {n}/{len(zips)} 卷"))


if __name__ == "__main__":
    main()
