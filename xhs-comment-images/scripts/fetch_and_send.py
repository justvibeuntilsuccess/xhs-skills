#!/usr/bin/env python3
"""Download comment photos at the CDN's best rendition -> lossless PNG -> one zip -> Telegram.

Usage:
    /usr/bin/python3 fetch_and_send.py pics.json [--outdir DIR] [--no-send] [--caption TEXT]

pics.json: list of {url, prv?, w?, h?, owner?} — the output of scripts/parse_bodies.js.
Verified 2026-10-12 (23 images, 31,388,970-byte zip, document.file_size matched exactly).

The caller still owns the last step: after a byte-matched send, delete the working dir and
pics.json (the operator's no-trace rule).
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, zipfile

from PIL import Image

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
PROXY = ["--proxy", os.environ["XHS_PROXY"]] if os.environ.get("XHS_PROXY") else []  # optional egress; comment images need none
MIN_BYTES = 500                                     # tiny stickers are real (~3.9 KB at 225x225)


def safe(s, n=24):
    return re.sub(r'[^\w\u4e00-\u9fff.-]+', '_', str(s or 'anon'))[:n]


def fetch(url, dest):
    for extra in (PROXY, []):
        for scheme in ('http://', 'https://'):
            p = subprocess.run(["curl", "-s", "-m", "90", "-o", dest, "-w", "%{http_code}"] + extra +
                               ["-H", "User-Agent: " + UA, "-H", "Referer: https://www.rednote.com/",
                                scheme + url.split('://', 1)[-1]], capture_output=True, text=True)
            if p.stdout.strip() == "200" and os.path.exists(dest) and os.path.getsize(dest) > MIN_BYTES:
                return True
    return False


def env_value(path, key, default=""):
    try:
        for line in open(path):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pics")
    ap.add_argument("--outdir", default=os.path.join(tempfile.gettempdir(), "comment_pics"))
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--caption", default="")
    args = ap.parse_args()

    items = json.load(open(args.pics))
    os.makedirs(args.outdir, exist_ok=True)
    rows, seen_md5 = [], {}
    for idx, it in enumerate(items, 1):
        name = "%02d_%s_%sx%s" % (idx, safe(it.get('owner')), it.get('w'), it.get('h'))
        webp, png = os.path.join(args.outdir, name + ".webp"), os.path.join(args.outdir, name + ".png")
        if not fetch(it['url'], webp):
            print("  %2d FAILED %s" % (idx, it['url'][:90]))
            continue
        im = Image.open(webp); im.load(); im.save(png, "PNG")
        md5 = hashlib.md5(open(png, 'rb').read()).hexdigest()
        seen_md5.setdefault(md5, []).append(name)
        rows.append((idx, name, png))
        print("  %2d ok  %-40s %8d -> %8d  %dx%d" % (idx, name[:40], os.path.getsize(webp),
                                                    os.path.getsize(png), *im.size))
    dupes = [v for v in seen_md5.values() if len(v) > 1]
    print("downloaded: %d/%d | unique images: %d | duplicate groups: %s" %
          (len(rows), len(items), len(seen_md5), dupes or 'none'))

    zp = os.path.join(args.outdir, "comment_photos.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for _, n, p in rows:
            z.write(p, n + ".png")
    with zipfile.ZipFile(zp) as z:
        print("zip: %s bytes | entries %d | integrity %s" %
              (os.path.getsize(zp), len(z.namelist()), "OK" if z.testzip() is None else "BAD"))
    if args.no_send:
        return

    envfile = os.environ.get('HERMES_ENV_FILE', os.path.expanduser('~/.hermes/.env'))
    tok = os.environ.get('TELEGRAM_BOT_TOKEN') or env_value(envfile, 'TELEGRAM_BOT_TOKEN')
    chat = (os.environ.get('TELEGRAM_HOME_CHANNEL') or os.environ.get('TELEGRAM_CHAT_ID')
            or env_value(envfile, 'TELEGRAM_HOME_CHANNEL'))
    if not tok or not chat:
        print('SEND SKIPPED: set TELEGRAM_BOT_TOKEN and TELEGRAM_HOME_CHANNEL (env or ~/.hermes/.env)')
        return
    size = os.path.getsize(zp)
    cap = args.caption or ("评论照片 %d 张（无损 PNG）" % len(rows))
    r = subprocess.run(["curl", "-s", "-m", "900", "-F", "chat_id=" + chat, "-F", "caption=" + cap,
                        "-F", "document=@" + zp,
                        "https://api.telegram.org/bot%s/sendDocument" % tok],
                       capture_output=True, text=True)
    j = json.loads(r.stdout or '{}')
    if not j.get("ok"):
        print("SEND FAILED:", json.dumps(j, ensure_ascii=False)[:400]); sys.exit(1)
    d = j["result"].get("document", {})
    print("SENT message_id=%s file_name=%s file_size=%s local=%s MATCH=%s" %
          (j["result"]["message_id"], d.get("file_name"), d.get("file_size"), size,
           d.get("file_size") == size))


if __name__ == "__main__":
    main()
