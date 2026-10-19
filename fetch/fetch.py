"""Fetch Wikimedia Commons files listed in a JSON request file.
Request format: [{"name": "gv80", "title": "File name.jpg", "width": 2400}, {"name": "s_tucson", "search": "Hyundai Tucson 2027"}, ...]
Search items save 480px previews <name>_NN.jpg of allowed-license results.
Writes <out>/<name>.jpg and <out>/meta.json (license, author, source page) for each.
Only files whose license is CC BY / CC BY-SA / CC0 / Public domain are saved."""
import json, sys, os, re, time, urllib.request, urllib.parse
req, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
UA = {"User-Agent": "chadeok-media-fetch/1.0 (github.com/han4435/chadeok-media)"}
OK = re.compile(r"^(CC BY(-SA)? [0-9.]+|CC0|Public domain|PD.*)$", re.I)
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
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
for item in json.load(open(req)):
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
