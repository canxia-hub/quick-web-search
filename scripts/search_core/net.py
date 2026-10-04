from __future__ import annotations
import ipaddress, json, os, socket, time
from urllib.parse import urlsplit, urljoin
import requests
from .models import SearchError
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
def public_url(url):
    p=urlsplit(url)
    if p.scheme not in {"http","https"} or not p.hostname or p.username or p.password:
        raise SearchError("invalid_url","Only credential-free HTTP(S) URLs are supported.")
    host=p.hostname.lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith((".local",".internal")):
        raise SearchError("private_url","Public page reader does not access local/internal hosts.")
    try:
        if not ipaddress.ip_address(host).is_global: raise SearchError("private_url","Non-public IP address rejected.")
    except ValueError: pass
    # Network egress proxy remains authoritative; do not bypass it for public requests.
    return url
def fetch(url, deadline, params=None, limit=3_000_000, local=False):
    if not local: public_url(url)
    s=requests.Session()
    if local: s.trust_env=False
    s.headers.update({"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8"})
    remaining=deadline-time.monotonic()
    if remaining<=0: raise SearchError("timeout","Request budget exhausted.")
    try:
        for hop in range(6):
            r=s.get(url,params=params if hop==0 else None,timeout=(min(3,remaining),min(9,remaining)),stream=True,allow_redirects=False)
            if r.is_redirect:
                url=urljoin(r.url,r.headers.get("Location",""));r.close()
                if not local: public_url(url)
                continue
            if r.status_code==429: raise SearchError("rate_limited","HTTP 429; no automatic retry flood.")
            if r.status_code in {401,403,412}: raise SearchError("blocked",f"HTTP {r.status_code}; authentication or site access restricted.")
            if r.status_code>=400: raise SearchError("http_error",f"HTTP {r.status_code}")
            chunks=[];size=0
            for part in r.iter_content(65536):
                if time.monotonic()>deadline: raise SearchError("timeout","Download budget exhausted.")
                size+=len(part)
                if size>limit: raise SearchError("too_large",f"Response exceeded {limit} bytes.")
                chunks.append(part)
            content=b"".join(chunks);ctype=r.headers.get("content-type","")
            encoding=r.encoding if r.encoding and r.encoding!="ISO-8859-1" else "utf-8"
            return {"url":r.url,"bytes":content,"text":content.decode(encoding,errors="replace"),"type":ctype,"status":r.status_code}
        raise SearchError("redirect_limit","Too many redirects.")
    except requests.Timeout as e: raise SearchError("timeout","HTTP request timed out.") from e
    except requests.RequestException as e: raise SearchError("network_error",type(e).__name__) from e
    finally: s.close()
