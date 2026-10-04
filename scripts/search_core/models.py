from __future__ import annotations
import hashlib, json, re, base64
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote, urljoin

PLATFORMS = {"wechat": "mp.weixin.qq.com", "bilibili": "bilibili.com", "xiaohongshu": "xiaohongshu.com", "github": "github.com"}
TRACKING = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","spm_id_from","from_spmid","vd_source","share_source","share_medium","share_plat","from","feature"}
def now(): return datetime.now(timezone.utc).isoformat()
def digest(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()
def clean(text, limit=1000):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()[:limit]
def canonical(url):
    url = urljoin("https://weixin.sogou.com", url) if url.startswith("/link") else url
    if url.startswith("//"): url="https:"+url
    p=urlsplit(url)
    if p.hostname and p.hostname.endswith("bing.com") and p.path=="/ck/a":
        u=dict(parse_qsl(p.query)).get("u","")
        if u.startswith("a1"):
            try: return canonical(base64.urlsafe_b64decode(u[2:]+"="*((-len(u[2:]))%4)).decode())
            except (ValueError,UnicodeError): pass
    if p.hostname and p.hostname.endswith("google.com") and p.path=="/url":
        dest=dict(parse_qsl(p.query)).get("q") or dict(parse_qsl(p.query)).get("url")
        if dest: return canonical(dest)
    host=(p.hostname or "").lower()
    path=p.path.rstrip("/") or "/"
    if host.endswith("bilibili.com"):
        match=re.search(r"/video/(BV[a-zA-Z0-9]+)",path)
        if match:
            part=dict(parse_qsl(p.query)).get("p","1")
            return "https://www.bilibili.com/video/"+match.group(1)+("?"+urlencode({"p":part}) if part!="1" else "")
    if host.endswith("xiaohongshu.com"):
        match=re.search(r"/(?:explore|discovery/item|search_result)/([a-f0-9]{24})",path)
        if match: return "https://www.xiaohongshu.com/explore/"+match.group(1)
    params=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k not in TRACKING and not k.startswith("utm_")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(sorted(params)), ""))
def platform_for(url):
    host=(urlsplit(url).hostname or "").lower()
    if host=="weixin.sogou.com": return "wechat"
    return next((p for p,domain in PLATFORMS.items() if host==domain or host.endswith("."+domain)), "web")
def doc(title,url,snippet,provider,query,platform=None,**extra):
    identity=canonical(url)
    # Signed note URLs are retrieval routes, not document identity. Keep the route
    # for reading while deduplicating by the stable note ID.
    url=url if platform_for(identity)=="xiaohongshu" else identity
    if urlsplit(url).scheme not in {"http","https"}: return None
    return {"id":digest(identity)[:16],"title":clean(title,350),"url":url,"canonical_url":identity,
            "snippet":clean(snippet,1200),"platform":platform or platform_for(url),
            "provider":provider,"query":query,"content_level":"snippet","fetched_at":now(),
            "source_type":"unknown","provenance":[{"provider":provider,"query":query,"url":url}],**extra}
def trace(source, query, status, count=0, **extra):
    return {"source":source,"query":query,"status":status,"count":count,**extra}
class SearchError(Exception):
    def __init__(self,code,message):
        self.code=code; super().__init__(message)
