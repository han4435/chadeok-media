"""Fetch Wikimedia Commons files listed in a JSON request file.
Request format: [{"name": "gv80", "title": "File name.jpg", "width": 2400}, {"name": "s_tucson", "search": "Hyundai Tucson 2027"}, ...]
URL items ({"name","url","max_files"}) download manufacturer press files (ZIP unpacked) for editorial news use.
Search items save 480px previews <name>_NN.jpg of allowed-license results.
Writes <out>/<name>.jpg and <out>/meta.json (license, author, source page) for each.
Only files whose license is CC BY / CC BY-SA / CC0 / Public domain are saved."""
import json, sys, os, re, time, urllib.request, urllib.parse
req, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 chadeok-media-fetch/1.0"}
OK = re.compile(r"^(CC BY(-SA)? [0-9.]+|CC0|Public domain|PD.*)$", re.I)
def get(url, referer=None):
    h = dict(UA)
    if referer: h["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
        return r.read()
meta = {}
def search(item):
    q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search",
        "gsrsearch": item["search"] + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": item.get("limit", 20),
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 480,
        "iiextmetadatafilter": "LicenseShortName|Artist|DateTimeOriginal"})
    pages = json.loads(get("https://commons.wikimedia.org/w/api.php?" + q)).get("query", {}).get("pages", {})
    res = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        ii = p["imageinfo"][0]; em = ii.get("extmetadata", {})
        lic = em.get("LicenseShortName", {}).get("value", "").strip()
        if not OK.match(lic) or ii.get("width", 0) < item.get("min_width", 1600):
            continue
        n = len(res) + 1; fn = f"{item['name']}_{n:02d}.jpg"
        try:
            open(os.path.join(out, fn), "wb").write(get(ii["thumburl"])); time.sleep(0.5)
        except Exception as e:
            fn = "ERROR " + str(e)
        res.append({"thumb": fn, "title": p["title"], "license": lic,
                    "artist": re.sub(r"<[^>]+>", "", em.get("Artist", {}).get("value", "")).strip()[:60],
                    "date": re.sub(r"<[^>]+>", "", em.get("DateTimeOriginal", {}).get("value", ""))[:10],
                    "size": f"{ii.get('width')}x{ii.get('height')}"})
    return res
def fetch_url(item):
    """Download a file from a manufacturer press site (editorial use). ZIPs are unpacked;
    images are resized to max 2400px wide and saved as <name>_NN.jpg (first max_files)."""
    import io, zipfile
    from PIL import Image
    data = get(item["url"], item.get("referer"))
    files = []
    def save(buf, label):
        n = len(files) + 1
        if n > item.get("max_files", 40): return
        try:
            im = Image.open(io.BytesIO(buf)).convert("RGB")
        except Exception:
            return
        if im.width > 2400: im = im.resize((2400, round(im.height * 2400 / im.width)))
        fn = f"{item['name']}_{n:02d}.jpg"; im.save(os.path.join(out, fn), quality=90)
        files.append({"file": fn, "source_name": label, "size": f"{im.width}x{im.height}"})
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        for zi in sorted(z.infolist(), key=lambda x: x.filename):
            if re.search(r"\.(jpe?g|png|webp)$", zi.filename, re.I) and not zi.filename.startswith("__MACOSX"):
                save(z.read(zi), zi.filename)
    else:
        save(data, item["url"].split("/")[-1][:80])
    head = "" if files else data[:400].decode("utf-8", "replace")
    return {"head_if_no_images": head, "url": item["url"], "usage": item.get("usage", "press/editorial only"), "bytes": len(data), "files": files}
def fetch_page(item):
    """Collect image URLs from a press-release page (og:image + <img> tags) and download them."""
    import io
    from PIL import Image
    base = item["page"]; html = get(base).decode("utf-8", "replace")
    cands = re.findall(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
    cands += re.findall(r'(?:src|data-src|href)=["\']([^"\']+\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']', html, re.I)
    seen, urls = set(), []
    for u in cands:
        u = urllib.parse.urljoin(base, u.replace("&amp;", "&"))
        if u in seen or re.search(item.get("skip", r"logo|icon|sprite|favicon|btn_|thumb_s"), u, re.I): continue
        seen.add(u); urls.append(u)
    files = []
    for u in urls:
        if len(files) >= item.get("max_files", 12): break
        try:
            im = Image.open(io.BytesIO(get(u, base))).convert("RGB")
        except Exception:
            continue
        if im.width < item.get("min_width", 1000): continue
        if im.width > 2400: im = im.resize((2400, round(im.height * 2400 / im.width)))
        fn = f"{item['name']}_{len(files)+1:02d}.jpg"; im.save(os.path.join(out, fn), quality=90)
        files.append({"file": fn, "src": u, "size": f"{im.width}x{im.height}"})
        time.sleep(0.3)
    return {"page": base, "candidates": len(urls), "files": files, "first_urls": urls[:15]}
for item in json.load(open(req)):
    if "page" in item:
        try: meta[item["name"]] = fetch_page(item)
        except Exception as e: meta[item["name"]] = {"page": item["page"], "error": str(e)}
        continue
    if "url" in item:
        try: meta[item["name"]] = fetch_url(item)
        except Exception as e: meta[item["name"]] = {"url": item["url"], "error": str(e)}
        continue
    if "search" in item:
        try: meta[item["name"]] = {"search": item["search"], "results": search(item)}
        except Exception as e: meta[item["name"]] = {"search": item["search"], "error": str(e)}
        continue
    t = item["title"] if item["title"].startswith("File:") else "File:" + item["title"]
    q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "titles": t,
        "iiprop": "url|size|extmetadata", "iiurlwidth": item.get("width", 2400),
        "iiextmetadatafilter": "LicenseShortName|Artist|LicenseUrl"})
    try:
        page = next(iter(json.loads(get("https://commons.wikimedia.org/w/api.php?" + q))["query"]["pages"].values()))
        ii = page["imageinfo"][0]; em = ii.get("extmetadata", {})
        lic = em.get("LicenseShortName", {}).get("value", "")
        artist = re.sub(r"<[^>]+>", "", em.get("Artist", {}).get("value", "")).strip()
        rec = {"title": t, "license": lic, "artist": artist, "page": ii.get("descriptionurl"),
               "width": ii.get("width"), "height": ii.get("height")}
        if not OK.match(lic.strip()):
            rec["skipped"] = "license not allowed"
        else:
            data = get(ii.get("thumburl") or ii["url"])
            open(os.path.join(out, item["name"] + ".jpg"), "wb").write(data)
            rec["bytes"] = len(data)
    except Exception as e:
        rec = {"title": t, "error": str(e)}
    meta[item["name"]] = rec
    time.sleep(1)
json.dump(meta, open(os.path.join(out, "meta.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(meta, ensure_ascii=False, indent=1))
