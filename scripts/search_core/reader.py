from __future__ import annotations
import io,json,re,time
from urllib.parse import urlsplit, urljoin, urlencode, parse_qsl
from bs4 import BeautifulSoup
from .net import fetch,public_url
from .models import now,digest,clean,canonical,SearchError,platform_for
from .browser import evaluate_page
READ_JS=r"""(() => {let node=document.querySelector('#js_content,article,[role="main"],main,.note-content,.video-desc-container');let text=(node||document.body)?.innerText||'';let wechat=location.hostname==='mp.weixin.qq.com',stamp=Number(window.ct),xhs=location.hostname==='www.xiaohongshu.com',id=location.pathname.split('/').pop(),n=xhs?window.__INITIAL_STATE__?.note?.noteDetailMap?.[id]?.note:null;return {title:document.querySelector('h1')?.innerText||document.title,text:text.slice(0,50000),url:location.href,login:/登录后查看|请先登录|扫码登录/.test(document.body.innerText)&&!node,blocked:/访问过于频繁|安全验证|verify you are human|环境异常|VerifyCode|此验证码用于|antispider|当前笔记暂时无法浏览|你访问的页面不存在/.test(document.body?.innerText||''),author:(wechat?document.querySelector('#js_name')?.innerText:'')||n?.user?.nickname||document.querySelector(xhs?'.author-container .username':'meta[name="author"]')?.[xhs?'innerText':'content']||'',published_at:wechat&&stamp>0&&stamp<32503680000?new Date(stamp*1000).toISOString():n?.time?new Date(n.time).toISOString():document.querySelector('meta[property="article:published_time"]')?.content||'',published_at_text:wechat?document.querySelector('#publish_time')?.innerText||'':xhs?document.querySelector('.note-content .date')?.innerText||'':'',content_scope:wechat?(document.querySelector('#activity-name')?'article_text':'post_text'):xhs?'note_text':'',note_id:n?.noteId||'',media_type:n?.type||'',image_count:n?.imageList?.length||0,selected:!!node}})()"""
def segments(text,kind):
    paragraphs=[p.strip() for p in re.split(r"\n\s*\n|\n",text) if len(p.strip())>=15]
    return [{"text":p[:1600],"locator":f"{kind}:paragraph:{i+1}","hash":digest(p)} for i,p in enumerate(paragraphs[:80])]
def xhs_metadata(soup,url):
    """Read only the requested public note's metadata; never execute page scripts."""
    author=soup.select_one(".author-container .username,.author-wrapper .username")
    date=soup.select_one(".note-content .date")
    info={"author":clean(author.get_text() if author else "",120),
          "published_at_text":clean(date.get_text() if date else "",100),
          "content_scope":"note_text"}
    match_id=re.search(r"/(?:explore|discovery/item|search_result)/([a-f0-9]{24})",urlsplit(url).path)
    if not match_id:return info
    for script in soup.select("script"):
        match=re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*})\s*;?\s*$",script.get_text(),re.S)
        if not match:continue
        # Replace the JS undefined token outside JSON strings, without eval.
        encoded=re.sub(r'"(?:\\.|[^"\\])*"|\bundefined\b',lambda m:"null" if m.group()=="undefined" else m.group(),match.group(1))
        try:state=json.loads(encoded)
        except ValueError:continue
        note=state.get("note",{}).get("noteDetailMap",{}).get(match_id.group(1),{}).get("note",{})
        if not note:continue
        info["author"]=clean(note.get("user",{}).get("nickname") or info["author"],120)
        stamp=note.get("time")
        if isinstance(stamp,(int,float)) and 0<stamp<32503680000000:
            from datetime import datetime,timezone
            info["published_at"]=datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat()
        info["note_id"]=note.get("noteId",match_id.group(1))
        info["media_type"]=note.get("type","")
        info["image_count"]=len(note.get("imageList",[]))
        break
    return info

def wechat_metadata(soup,url):
    author=soup.select_one("#js_name")
    date=soup.select_one("#publish_time")
    info={"author":clean(author.get_text() if author else "",120),
          "published_at_text":clean(date.get_text() if date else "",100),
          "content_scope":"article_text" if soup.select_one("#activity-name") else "post_text"}
    for script in soup.select("script"):
        match=re.search(r"\bct\s*=\s*['\"]?(\d{10})['\"]?",script.get_text())
        if match:
            from datetime import datetime,timezone
            info["published_at"]=datetime.fromtimestamp(int(match.group(1)),timezone.utc).isoformat()
            break
    return info

def extract_html(text,url,max_chars):
    soup=BeautifulSoup(text,"html.parser")
    note_info=xhs_metadata(soup,url) if platform_for(url)=="xiaohongshu" else wechat_metadata(soup,url) if urlsplit(url).hostname=="mp.weixin.qq.com" else {}
    for n in soup.select("script,style,nav,footer,header,form,iframe,noscript"):n.decompose()
    chosen=soup.select_one("#js_content,article,[role=main],main,.note-content,.video-desc-container")
    if chosen is None:
        # A longest content container is a heuristic, never proof of complete article.
        candidates=soup.select("div.content,div.article,div.post-content")
        chosen=max(candidates,key=lambda n:len(n.get_text()),default=None)
    meta=soup.select_one('meta[name=author]')
    pub=soup.select_one('meta[property="article:published_time"],meta[name="pubdate"],meta[itemprop="datePublished"]')
    title=soup.select_one("h1") or soup.title
    body=(chosen or soup.body or soup).get_text("\n",strip=True)
    blocked=bool(re.search(r"环境异常|访问过于频繁|验证你是人类|verify you are human|enable JavaScript|登录后查看|VerifyCode|此验证码用于|antispider|当前笔记暂时无法浏览|你访问的页面不存在",body,re.I))
    return {"title":clean(title.get_text() if title else "",350),"text":body[:max_chars],"author":meta.get("content","") if meta else "",
            "published_at":pub.get("content","") if pub else "","selected":chosen is not None,"blocked":blocked,"url":url,"truncated":len(body)>max_chars,**note_info}
BILI_READ_JS=r"""(async()=>{
 const bv=__BV__,part=__PART__,diagnostics=[];
 async function request(url,credentials='include'){
  try {const r=await fetch(url,{credentials,signal:AbortSignal.timeout(3500)}),text=await r.text();
   if(!r.ok)return {error:'http_'+r.status};
   try{return JSON.parse(text)}catch{return {error:'invalid_json'}};
  }catch(e){return {error:e.name==='TimeoutError'?'timeout':'request_failed'};}
 }
 let d=window.__INITIAL_STATE__?.videoData,metadata_source='embedded-video-state';
 if(d?.bvid!==bv||!d?.pages?.length){
  const v=await request('https://api.bilibili.com/x/web-interface/view?bvid='+bv);
  if(v.error||v.code!==0)return {error:'view_unavailable',diagnostics:[v.error||'code_'+v.code]};
  d=v.data;metadata_source='api-view';
 }
 const page=d.pages?.find(x=>x.page===part);
 const meta={title:d.title,description:d.desc||'',author:d.owner?.name||'',published_at:d.pubdate,
  bvid:bv,part,part_title:page?.part||'',cid:page?.cid,metadata_source,diagnostics,subtitles:[]};
 if(!page?.cid)return {...meta,error:'part_unavailable'};
 let p;
 for(const endpoint of ['wbi/v2','v2']){
  const candidate=await request('https://api.bilibili.com/x/player/'+endpoint+'?bvid='+bv+'&cid='+page.cid);
  if(!candidate.error&&candidate.code===0){p=candidate;break;}
  diagnostics.push('player_'+endpoint+':'+(candidate.error||'code_'+candidate.code));
 }
 if(!p)return {...meta,subtitle_status:'player_unavailable'};
 const tracks=p.data?.subtitle?.subtitles||[];
 if(!tracks.length)return {...meta,subtitle_status:p.data?.need_login_subtitle?'login_required':'no_accessible_track'};
 const s=tracks.find(x=>/^(ai-)?zh/.test(x.lan||''))||tracks[0];
 let subtitle_url;
 try{subtitle_url=new URL(s.subtitle_url,location.href)}catch{return {...meta,subtitle_status:'invalid_track_url'};}
 if(subtitle_url.protocol!=='https:'||!/^(?:[^.]+\.)*(?:hdslb\.com|bilibili\.com)$/.test(subtitle_url.hostname))
  return {...meta,subtitle_status:'invalid_track_url'};
 const body=await request(subtitle_url.href,'omit');
 if(body.error||!Array.isArray(body.body))return {...meta,subtitle_status:'track_fetch_failed',diagnostics:[...diagnostics,body.error||'invalid_track_body']};
 const subtitles=body.body.filter(x=>typeof x.content==='string'&&x.content.trim()&&Number.isFinite(x.from)&&Number.isFinite(x.to)&&x.from>=0&&x.to>=x.from);
 return {...meta,subtitles,subtitle_status:subtitles.length?'available':'empty_track',subtitle_language:s.lan||'',subtitle_label:s.lan_doc||''};
})()"""
def bili_transcript(url,config,deadline,lease):
    bv=re.search(r"BV[a-zA-Z0-9]+",url)
    if not bv:return {"error":"video_id_missing"}
    value=dict(parse_qsl(urlsplit(url).query)).get("p","1")
    if not value.isdigit() or int(value)<1:return {"error":"invalid_part"}
    expr=BILI_READ_JS.replace("__BV__",json.dumps(bv.group())).replace("__PART__",str(int(value)))
    return evaluate_page(url,expr,config,deadline,lease,"Boolean(window.__INITIAL_STATE__?.videoData?.pages?.length) || (document.readyState==='complete' && /安全验证|验证码|视频不见了|出错啦/.test(document.body?.innerText||''))")

def read_url(url,config,deadline,lease=None,max_chars=18000,title_hint=""):
    public_url(url);started=time.monotonic();errors=[];payload=None;kind="body";provider="http";platform=platform_for(url)
    if platform=="bilibili" and config.get("browser",True):
        try:
            v=bili_transcript(url,config,deadline,lease)
            if v and v.get("error") in {"invalid_part","part_unavailable","video_id_missing"}:
                return {"url":url,"requested_url":url,"status":"empty","content_level":"none","text":"","evidence":[],"warnings":[{"code":v["error"],"message":"Requested video/part is unavailable; no other part substituted."}],"fetched_at":now(),"seconds":round(time.monotonic()-started,3)}
            if v and not v.get("error"):
                published_at=""
                if isinstance(v.get("published_at"),(int,float)):
                    from datetime import datetime,timezone
                    published_at=datetime.fromtimestamp(v["published_at"],timezone.utc).isoformat()
                extra={k:v[k] for k in ("bvid","cid","part","part_title","metadata_source","subtitle_status","subtitle_language","subtitle_label") if k in v}
                if v.get("subtitles"):
                    evidence=[];size=0;truncated=False
                    for x in v["subtitles"]:
                        content=clean(x.get("content",""),max_chars+1)
                        room=max_chars-size-(1 if evidence else 0)
                        if room<=0:truncated=True;break
                        if len(content)>room:content=content[:room];truncated=True
                        evidence.append({"text":content,"locator":f"video:{x.get('from',0):.2f}-{x.get('to',0):.2f}s","start":x.get("from"),"end":x.get("to")})
                        size+=len(content)+(1 if len(evidence)>1 else 0)
                        if truncated:break
                    full="\n".join(x["text"] for x in evidence)
                    truncated=truncated or len(evidence)<len(v["subtitles"])
                    return {**extra,"url":canonical(url),"requested_url":url,"title":v.get("title",""),"platform":platform,"content_level":"transcript","status":"ok","provider":"bilibili-browser-subtitle","author":v.get("author",""),"published_at":published_at,"fetched_at":now(),"text":full[:max_chars],"evidence":evidence,"content_hash":digest(json.dumps(evidence,ensure_ascii=False)),"truncated":truncated,"warnings":[{"code":"truncated","message":"Subtitle output capped by segment/character budget."}] if truncated else [],"seconds":round(time.monotonic()-started,3)}
                status=v.get("subtitle_status","player_unavailable")
                payload={**extra,"url":url,"title":v.get("title",""),"text":v.get("description",""),"author":v.get("author",""),"published_at":published_at,"selected":True}
                kind="metadata";provider="bilibili-browser-player"
                errors.append({"code":"login_required" if status=="login_required" else "subtitle_unavailable","message":"Bilibili player explicitly requires login for subtitles in this browser profile." if status=="login_required" else "No readable subtitle track returned ("+status+"); video was not transcribed."})
                if v.get("diagnostics"):errors.append({"code":"subtitle_diagnostic","message":"; ".join(v["diagnostics"])[:220]})
            elif v:errors.append({"code":v.get("error","subtitle_error"),"message":"Video metadata unavailable; see page access conditions."})
        except Exception as e:errors.append({"code":getattr(e,"code","subtitle_error"),"message":str(e)[:180]})
    if payload is None:
        try:
            raw=fetch(url,min(deadline,time.monotonic()+6),limit=8_000_000)
            if "application/pdf" in raw["type"] or urlsplit(raw["url"]).path.lower().endswith(".pdf"):
                try:
                    from pypdf import PdfReader
                    pdf=PdfReader(io.BytesIO(raw["bytes"]));evidence=[];size=0
                    for i,page in enumerate(pdf.pages[:50]):
                        if time.monotonic()>deadline:break
                        text=(page.extract_text() or "").strip();size+=len(text)
                        if text:evidence.append({"text":text[:4000],"locator":f"pdf:page:{i+1}"})
                        if size>=max_chars:break
                    payload={"title":urlsplit(url).path.rsplit("/",1)[-1],"text":"\n\n".join(e["text"] for e in evidence)[:max_chars],"url":raw["url"],"selected":True,"evidence":evidence,"truncated":size>=max_chars or len(pdf.pages)>50};kind="pdf_text"
                except ImportError as e:raise SearchError("missing_dependency","Install pypdf only if PDF reading is needed.") from e
            else:
                payload=extract_html(raw["text"],raw["url"],max_chars)
                if platform=="xiaohongshu" and payload.get("note_id") and payload.get("media_type")=="video":kind="metadata"
                # Sogou article links may use script redirects; browser executes the site's normal navigation.
        except Exception as e:errors.append({"code":getattr(e,"code","read_error"),"message":str(e)[:180]})
    if (not payload or payload.get("blocked") or len(payload.get("text",""))<150 and kind not in {"pdf_text","metadata"} and not payload.get("note_id") or "weixin.sogou.com/link" in payload.get("url","")) and config.get("browser",True) and deadline-time.monotonic()>1:
        try:
            query=dict(parse_qsl(urlsplit(url).query)).get("query","")
            use_click=urlsplit(url).hostname=="weixin.sogou.com" and urlsplit(url).path=="/link" and title_hint and query
            search_url="https://weixin.sogou.com/weixin?"+urlencode({"type":2,"query":query})
            ready="Boolean(document.body) && location.href!=='about:blank' && document.readyState==='complete'"
            if use_click:ready="location.hostname==='mp.weixin.qq.com' && document.readyState==='complete' && Boolean(document.querySelector('#js_content')?.innerText?.trim()) || /验证码|访问过于频繁|antispider|环境异常/.test(document.body?.innerText||'')"
            data=evaluate_page(search_url if use_click else url,READ_JS,config,deadline,lease,ready,click_title=title_hint if use_click else None)
            if data and not data.get("blocked") and not data.get("login") and (len(data.get("text",""))>=80 or platform=="bilibili" and data.get("title") or platform=="xiaohongshu" and data.get("note_id") and data.get("selected") and data.get("text")):
                data["text"]=data.get("text","")[:max_chars];payload=data;provider="existing-browser";kind="body"
            elif data and data.get("login"):errors.append({"code":"login_required","message":"Page needs login in the existing browser profile."})
            else:errors.append({"code":"blocked" if data and data.get("blocked") else "body_unavailable","message":"Browser returned an access/verification page." if data and data.get("blocked") else "Browser did not expose readable body; a page shell/short empty content is not proof of verification."})
        except Exception as e:errors.append({"code":getattr(e,"code","browser_error"),"message":str(e)[:180]})
    valid=bool(payload and not payload.get("blocked") and (len(payload.get("text",""))>=80 or platform=="xiaohongshu" and payload.get("note_id") and payload.get("selected") and payload.get("text") or kind=="pdf_text" and payload.get("evidence") or kind=="metadata" and payload.get("title")))
    if not valid:
        return {"url":url,"requested_url":url,"status":"blocked" if errors else "empty","content_level":"none","evidence":[],"text":"","warnings":errors,"fetched_at":now(),"seconds":round(time.monotonic()-started,3)}
    text=payload["text"];selected=payload.get("selected",False)
    if not selected and kind=="body":kind="page_text"
    if platform=="bilibili" and kind!="transcript":kind="metadata";errors.append({"code":"not_transcribed","message":"Page/description is not a transcription of the video."})
    if platform=="xiaohongshu" and ("/search_result" in payload.get("url","") or payload.get("media_type")=="video"):kind="metadata"
    if "weixin.sogou.com" in payload.get("url",""):kind="metadata";errors.append({"code":"redirect_unresolved","message":"Only Sogou search/redirect page obtained, not the WeChat article body."})
    if platform=="wechat" and payload.get("content_scope")=="post_text":
        kind="metadata"
        errors.append({"code":"post_text_only","message":"Only WeChat short/media-post text acquired; embedded media was not read or transcribed."})
    if platform=="xiaohongshu" and payload.get("content_scope")=="note_text":
        errors.append({"code":"note_text_only","message":"Note text acquired; images were not OCRed and video was not transcribed."})
    return {**{k:payload[k] for k in ("published_at_text","content_scope","note_id","media_type","image_count","bvid","cid","part","part_title","metadata_source","subtitle_status","subtitle_language","subtitle_label") if k in payload},"url":canonical(payload.get("url",url)),"requested_url":url,"title":payload.get("title",""),"platform":platform,"status":"ok","content_level":kind,"provider":provider,"author":payload.get("author",""),"published_at":payload.get("published_at",""),"fetched_at":now(),"text":text,"evidence":payload.get("evidence") or segments(text,kind) or ([{"text":text,"locator":"note:text","hash":digest(text)}] if platform=="xiaohongshu" and payload.get("note_id") and text else []),"content_hash":digest(text),"truncated":payload.get("truncated",False),"warnings":errors,"seconds":round(time.monotonic()-started,3)}
