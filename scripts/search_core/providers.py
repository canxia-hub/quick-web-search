from __future__ import annotations
import json, re, time, subprocess, shutil
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from bs4 import BeautifulSoup
from .net import fetch
from .models import doc, SearchError, PLATFORMS, clean
from .models import canonical
from .browser import evaluate_page
from .ranking import relevance
GOOGLE_JS=r"""(() => ({blocked:/unusual traffic|异常流量|verify you are human/i.test(document.body.innerText),items:[...document.querySelectorAll('#search a')].filter(a=>a.querySelector('h3,[role="heading"],.n0jPhd')).map(a=>{let n=a;for(let i=0;i<4&&n.parentElement;i++)n=n.parentElement;return {title:a.querySelector('h3,[role="heading"],.n0jPhd').innerText,url:a.href,snippet:n.innerText.slice(0,1000)}})}))()"""
GOOGLE_READY="Boolean(document.querySelector('#search h3,#search .n0jPhd,#search [role=heading]')) || /did not match any documents|没有找到|unusual traffic|异常流量/.test(document.body.innerText)"
BILI_JS=r"""(() => ({blocked:/安全验证|验证码/.test(document.body.innerText),items:[...document.querySelectorAll('.bili-video-card')].map(n=>({title:n.querySelector('h3')?.innerText,url:n.querySelector('a[href*="/video/"]')?.href,author:n.querySelector('.bili-video-card__info--author')?.innerText,snippet:n.innerText.slice(0,700)})).filter(x=>x.url)}))()"""
BILI_READY="Boolean(document.querySelector('.bili-video-card h3')) || /安全验证|验证码|没有找到/.test(document.body.innerText)"
XHS_JS=r"""(() => ({login:/登录后查看搜索结果/.test(document.body.innerText),blocked:/安全验证|验证码/.test(document.body.innerText),items:[...document.querySelectorAll('section.note-item')].map(n=>({title:n.querySelector('.title')?.innerText,url:n.querySelector('a.cover')?.href,author:n.querySelector('.author')?.innerText,snippet:n.innerText.slice(0,700)})).filter(x=>x.url)}))()"""
XHS_READY="Boolean(document.querySelector('section.note-item')) || /登录后查看搜索结果|安全验证|验证码|暂时没有/.test(document.body.innerText)"
def normalize(items,provider,query,platform=None):
    return [d for x in items if x.get("url") and (d:=doc(x.get("title",""),x["url"],x.get("snippet",""),provider,query,platform,author=clean(x.get("author",""),120),published_at=x.get("published_at","")))]
def google(query,config,deadline,lease):
    params={"q":query}
    if config.get("page",1)>1:params["start"]=10*(config["page"]-1)
    if config.get("language") not in {None,"all"}:params["hl"]=config["language"]
    period={"day":"d","week":"w","month":"m","year":"y"}.get(config.get("time_range"))
    if period:params["tbs"]="qdr:"+period
    if config.get("categories")=="news":params["tbm"]="nws"
    data=evaluate_page("https://www.google.com/search?"+urlencode(params),GOOGLE_JS,config,deadline,lease,GOOGLE_READY)
    if not data:raise SearchError("empty","No rendered Google results.")
    if data.get("blocked"):raise SearchError("captcha","Google presented a verification page.")
    return normalize(data.get("items",[]),"google-browser",query)
def searx(query,config,deadline):
    base=config.get("searxng_url") or ""
    if not base:return []
    local=urlsplit(base).hostname in {"localhost","127.0.0.1","::1"}
    until=min(deadline,time.monotonic()+4)
    params={"q":query,"format":"json","language":config.get("language","all"),"categories":config.get("categories","general"),"pageno":config.get("page",1)}
    if config.get("time_range"):params["time_range"]=config["time_range"]
    data=json.loads(fetch(base.rstrip("/")+"/search",until,params=params,local=local)["text"])
    return normalize([{"title":x.get("title"),"url":x.get("url"),"snippet":x.get("content"),"published_at":x.get("publishedDate","")} for x in data.get("results",[])],"searxng",query)
def bing(query,config,deadline):
    payload=fetch("https://www.bing.com/search",min(deadline,time.monotonic()+4),params={"q":query,"count":12,"first":1+10*(config.get("page",1)-1)})
    soup=BeautifulSoup(payload["text"],"html.parser");items=[]
    for n in soup.select("li.b_algo"):
        a=n.select_one("h2 a");p=n.select_one(".b_caption p")
        if a:items.append({"title":a.get_text(" ",strip=True),"url":a.get("href"),"snippet":p.get_text(" ",strip=True) if p else ""})
    return [d for d in normalize(items,"bing-http",query) if relevance(query,d)>=.18]
def wechat(query,config,deadline):
    p=fetch("https://weixin.sogou.com/weixin",deadline,params={"type":2,"query":query,"page":config.get("page",1)})
    soup=BeautifulSoup(p["text"],"html.parser");items=[]
    for n in soup.select("ul.news-list > li"):
        a=n.select_one("h3 a");snippet=n.select_one(".txt-info");author=n.select_one('[class*="all-time"]');script=n.select_one(".s2 script")
        if a:
            x=doc(a.get_text(" ",strip=True),urljoin("https://weixin.sogou.com",a.get("href","")),snippet.get_text(" ",strip=True) if snippet else "","sogou-weixin",query,"wechat",author=clean(author.get_text() if author else "",120))
            if x:
                if script:
                    match=re.search(r"\b(\d{10})\b",script.get_text())
                    if match:
                        from datetime import datetime,timezone
                        x["published_at"]=datetime.fromtimestamp(int(match.group(1)),timezone.utc).isoformat()
                items.append(x)
    if not items and re.search(r"验证码|访问过于频繁|antispider",soup.get_text()):raise SearchError("captcha","Sogou verification page; no result claimed.")
    return items
def bili(query,config,deadline,lease):
    api_error=None
    try:
        p=fetch("https://api.bilibili.com/x/web-interface/search/type",min(deadline,time.monotonic()+2),params={"search_type":"video","keyword":query,"page":config.get("page",1)})
        data=json.loads(p["text"])
        if data.get("code")==0:
            return normalize([{"title":x.get("title"),"url":x.get("arcurl"),"snippet":x.get("description"),"author":x.get("author")} for x in data.get("data",{}).get("result",[])],"bilibili-api",query,"bilibili"),[]
        api_error={"code":"site_error","message":"Bilibili API code "+str(data.get("code"))}
    except SearchError as e:api_error={"code":e.code,"message":str(e)}
    if not config.get("browser",True):raise SearchError(api_error["code"],api_error["message"])
    data=evaluate_page("https://search.bilibili.com/all?"+urlencode({"keyword":query,"page":config.get("page",1)}),BILI_JS,config,deadline,lease,BILI_READY)
    if data.get("blocked"):raise SearchError("captcha","Bilibili browser verification required.")
    return normalize(data.get("items",[]),"bilibili-browser",query,"bilibili"),[api_error] if api_error else []
def xhs(query,config,deadline,lease):
    if config.get("page",1)>1:raise SearchError("unsupported_pagination","Native Xiaohongshu uses scrolling, not page numbers; use indexed pagination or native browser scrolling after login.")
    if not config.get("browser",True):raise SearchError("browser_required","Xiaohongshu requires browser access or indexed discovery.")
    data=evaluate_page("https://www.xiaohongshu.com/search_result?"+urlencode({"keyword":query,"source":"web_search_result_notes"}),XHS_JS,config,deadline,lease,XHS_READY)
    if data.get("login"):raise SearchError("login_required","Xiaohongshu search requires login in the selected existing browser profile.")
    if data.get("blocked"):raise SearchError("captcha","Xiaohongshu presented verification.")
    return normalize(data.get("items",[]),"xiaohongshu-browser",query,"xiaohongshu")
def github(query,config,deadline):
    p=None
    try:p=fetch("https://api.github.com/search/repositories",min(deadline,time.monotonic()+4),params={"q":query,"per_page":12,"page":config.get("page",1)})
    except SearchError:
        gh=shutil.which("gh") or str(Path.home()/"AppData/Local/openclaw/never-gh")
        windows=Path(r"C:\Program Files\GitHub CLI\gh.exe")
        if windows.exists():gh=str(windows)
        try:
            r=subprocess.run([gh,"api","search/repositories?"+urlencode({"q":query,"per_page":12,"page":config.get("page",1)})],capture_output=True,timeout=max(.1,min(5,deadline-time.monotonic())))
            if r.returncode:raise SearchError("github_error","Existing gh authentication/API unavailable.")
            p={"text":r.stdout.decode("utf-8")}
        except (OSError,subprocess.TimeoutExpired) as e:raise SearchError("github_error",type(e).__name__) from e
    data=json.loads(p["text"]);return normalize([{"title":x["full_name"],"url":x["html_url"],"snippet":x.get("description",""),"author":x.get("owner",{}).get("login",""),"published_at":x.get("pushed_at","")} for x in data.get("items",[])],"github-api",query,"github")
def collect(source,query,config,deadline,lease):
    errors=[];items=[]
    if source=="wechat":items=wechat(query,config,deadline)
    elif source=="bilibili":items,errors=bili(query,config,deadline,lease)
    elif source=="xiaohongshu":
        try:items=xhs(query,config,deadline,lease)
        except SearchError as e:
            errors.append({"code":e.code,"message":str(e)})
            if config.get("browser",True) and deadline-time.monotonic()>2:
                try:
                    candidates=google(query+" site:xiaohongshu.com",config,deadline,lease)
                    items=[d for d in candidates if d["platform"]=="xiaohongshu"]
                    for d in items:d["discovery_only"]=True
                except SearchError as fallback:errors.append({"code":fallback.code,"message":str(fallback)})
    elif source=="github":
        focused=query
        if re.search(r"installation|documentation|docs|安装|文档",query,re.I):
            entity=re.search(r"[A-Z][A-Za-z0-9_.-]{2,}",query)
            if entity:focused=entity.group()
        try:items=github(focused,config,deadline)
        except SearchError as e:errors.append({"code":e.code,"message":str(e)})
        if not items and config.get("browser",True) and deadline-time.monotonic()>1:
            try:items=[d for d in google(focused+" site:github.com",config,deadline,lease) if d["platform"]=="github"]
            except SearchError as e:errors.append({"code":e.code,"message":str(e)})
    elif source=="web":
        enabled=config.get("web_providers",["searxng","bing","google"])
        if any(p not in {"searxng","bing","google"} for p in enabled):raise SearchError("invalid_config","Unknown web provider.")
        for provider in [p for name,p in [("searxng",searx),("bing",bing)] if name in enabled]:
            try:
                candidates=provider(query,config,deadline)
                if candidates:items.extend(candidates);break
            except SearchError as e:errors.append({"code":e.code,"message":str(e)})
        # Sparse/suspicious HTTP results must not prevent independent recall.
        if "google" in enabled and config.get("browser",True) and (len(items)<3 or max((relevance(query,d) for d in items),default=0)<.4) and deadline-time.monotonic()>1:
            try:items.extend(google(query,config,deadline,lease))
            except SearchError as e:errors.append({"code":e.code,"message":str(e)})
    else:raise SearchError("unknown_source",source)
    for d in items:d["retrieval_page"]=config.get("page",1)
    return {"items":items,"errors":errors}
