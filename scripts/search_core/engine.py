from __future__ import annotations
import collections, json, multiprocessing as mp, os, re, time, signal
from pathlib import Path
from .models import now,SearchError,trace,PLATFORMS
from .providers import collect
from .reader import read_url
from .ranking import merge_rank
from .cache import Cache
from .browser import close_target,listing
DEFAULTS={"searxng_url":os.getenv("SEARXNG_BASE_URL","http://127.0.0.1:8888"),"browser":True,"cdp_url":os.getenv("SEARCH_CDP_URL","http://127.0.0.1:18800"),"workers":2,"language":"all","cache_ttl":900,"cache_entries":64}
def load_config(path=None):
    config=dict(DEFAULTS)
    candidate=Path(path) if path else Path.home()/".openclaw"/"search-v2.json"
    if candidate.exists():config.update(json.loads(candidate.read_text(encoding="utf-8")))
    config["workers"]=max(1,min(3,int(config.get("workers",2))))
    config["cache_ttl"]=max(0,min(86400,int(config.get("cache_ttl",900))))
    config["cache_entries"]=max(1,min(256,int(config.get("cache_entries",64))))
    return config
def choose_sources(query,sources=None):
    if sources:return list(dict.fromkeys(sources))
    if re.search(r"公众号|微信|B站|哔哩|小红书|视频.*(?:教程|工作流)|视频制作",query,re.I):return ["wechat","bilibili","xiaohongshu","web"]
    if re.search(r"github|开源|SDK|API|代码|源码|software|library",query,re.I):return ["web","github"]
    return ["web"]
def expand(query,mode):
    original=query.strip()
    # Preserve user entities and constraints; never reduce Chinese queries to "ai".
    variants=[original]
    if mode=="research":
        if re.search(r"视频.*(?:教程|流程)|视频制作",original):
            variants += [original+" 分镜 一致性 剪辑",original+" 实操 完整流程"]
        else:variants += [original+" 官方 文档",original+" 实践 局限"]
    return list(dict.fromkeys(variants))
def worker(conn,job,config,deadline):
    def lease(target):conn.send({"type":"lease","target":target})
    try:
        if job["kind"]=="read":value=read_url(job["url"],config,deadline,lease,job.get("max_chars",18000),job.get("title_hint",""))
        else:value=collect(job["source"],job["query"],config,deadline,lease)
        conn.send({"type":"result","value":value})
    except BaseException as e:
        try:conn.send({"type":"error","code":getattr(e,"code","provider_error"),"message":str(e)[:220]})
        except (BrokenPipeError,OSError):pass
    finally:conn.close()
def run_jobs(jobs,config,deadline):
    """Bounded isolated workers. Deadlines/cancel terminate only our worker processes."""
    context=mp.get_context("spawn");pending=collections.deque(jobs);active=[];results=[];cancelled=False
    def finish(slot,status,value=None):
        proc,conn,job,leases=slot
        if proc.is_alive():proc.terminate()
        proc.join(timeout=.2);conn.close()
        for target in leases:close_target(config,target)
        results.append({"job":job,"status":status,"value":value or {}})
    try:
        while (pending or active) and time.monotonic()<deadline:
            if config.get("cancel_file") and Path(config["cancel_file"]).exists():cancelled=True;break
            while pending and len(active)<config["workers"] and time.monotonic()<deadline:
                job=pending[0]
                # One normal Sogou redirect flow at a time in the shared profile.
                sogou=lambda j:j["kind"]=="read" and j.get("url","").startswith("https://weixin.sogou.com/link")
                if sogou(job) and any(sogou(slot[2]) for slot in active):break
                job=pending.popleft();parent,child=context.Pipe(duplex=False)
                job["_expires"]=min(deadline,time.monotonic()+float(config.get("read_job_budget",24) if job["kind"]=="read" else config.get("search_job_budget",18)))
                proc=context.Process(target=worker,args=(child,job,config,job["_expires"]));proc.daemon=True;proc.start();child.close()
                active.append((proc,parent,job,set()))
            for slot in active[:]:
                proc,conn,job,leases=slot
                if time.monotonic()>=job["_expires"]:
                    finish(slot,"timeout",{"error":"Per-source work budget exhausted."});active.remove(slot);continue
                try:
                    while conn.poll():
                        event=conn.recv()
                        if event["type"]=="lease":leases.add(event["target"])
                        elif event["type"]=="result":finish(slot,"ok",event["value"]);active.remove(slot);break
                        else:finish(slot,event["code"],{"error":event["message"]});active.remove(slot);break
                except EOFError:
                    if slot in active:finish(slot,"worker_failed",{"error":"Worker exited without a result."});active.remove(slot)
            if active:time.sleep(.02)
    except KeyboardInterrupt:cancelled=True
    finally:
        for slot in active:finish(slot,"cancelled" if cancelled else "timeout",{"error":"Worker work budget ended; already received results preserved."})
        for job in pending:results.append({"job":job,"status":"cancelled" if cancelled else "not_started","value":{}})
    return results,cancelled
def search(query,config,mode="search",sources=None,limit=12,budget=30,fresh=False,queries=None,sites=None,deadline=None):
    started=time.monotonic();deadline=deadline or started+budget;sources=choose_sources(query,sources);queries=queries or expand(query,mode)
    inferred=re.findall(r"site:([a-zA-Z0-9.-]+)",query)
    sites=list(dict.fromkeys((sites or [])+inferred))
    jobs=[{"kind":"search","source":source,"query":q} for q in queries for source in sources]
    cache=Cache(Path.home()/".openclaw"/"cache"/"search-v2",config["cache_ttl"],config["cache_entries"])
    cached=[];todo=[]
    for job in jobs:
        key=json.dumps({"job":job,"config":{k:v for k,v in config.items() if k not in {"workers"}}},sort_keys=True)
        job["cache_key"]=key
        value=None if fresh else cache.get(key)
        if value:cached.append({"job":job,"status":"cached","value":value})
        else:todo.append(job)
    outcomes,cancelled=run_jobs(todo,config,deadline)
    outcomes=cached+outcomes;docs=[];traces=[]
    for record in outcomes:
        job=record["job"];value=record["value"];status=record["status"];items=value.get("items",[]);docs.extend(items)
        warnings=value.get("errors",[])
        codes=[x.get("code") for x in warnings]
        display=("limited" if items and ("login_required" in codes or "captcha" in codes) else "ok" if items else codes[-1] if codes else "empty") if status in {"ok","cached"} else status
        traces.append(trace(job["source"],job["query"],display,len(items),errors=warnings,error=value.get("error"),cached=status=="cached"))
        if items and status=="ok" and not warnings:cache.put(job["cache_key"],value)
    ranked,removed,total=merge_rank(query,docs,limit,sources,sites,config.get("official_domains",[]))
    warnings=[t for t in traces if t["status"] not in {"ok","empty"}]
    status="cancelled" if cancelled else "partial" if warnings and ranked else "ok" if ranked else "blocked" if warnings else "empty"
    return {"schema_version":"2.0","mode":mode,"query":query,"status":status,"results":ranked,"total_unique_candidates":total,
            "coverage":{s:sum(d["platform"]==s for d in ranked) for s in sources},"traces":traces,"removed":removed,
            "queries":queries,"sources":sources,"ranking":"lexical-intent-diversified (no embeddings)","fetched_at":now(),
            "seconds":round(time.monotonic()-started,3),"budget_seconds":budget,"warnings":warnings}
def research(query,config,sources=None,limit=18,budget=300,output=None,resume=None,queries=None,fresh=False):
    start=time.monotonic();deadline=start+budget;prior={}
    if resume:prior=json.loads(Path(resume).read_text(encoding="utf-8"))
    package=search(query,config,"research",sources,limit,min(budget,max(15,budget*.6)),fresh,queries,deadline=min(deadline,start+max(1,budget*.6)))
    if prior.get("results"):
        package["results"],package["resume_removed"],package["total_unique_candidates"]=merge_rank(query,prior["results"]+package["results"],limit,package["sources"],official_domains=config.get("official_domains",[]))
        package["coverage"]={s:sum(d["platform"]==s for d in package["results"]) for s in package["sources"]}
    reads=prior.get("documents",[]);seen={x["requested_url"] for x in reads if x.get("status")=="ok"}
    chosen=[];platform_seen=set()
    for d in package["results"]:
        if d["platform"] not in platform_seen:chosen.append(d);platform_seen.add(d["platform"])
    # Prefer complementary original hosts over rereading the same blocked redirect/service.
    from urllib.parse import urlsplit
    selected_hosts={urlsplit(d["url"]).hostname for d in chosen}
    for d in package["results"]:
        host=urlsplit(d["url"]).hostname
        if d not in chosen and host not in selected_hosts:chosen.append(d);selected_hosts.add(host)
    # Sogou links share one host, but can lead to different original creators.
    # Include one additional representative instead of making a blocked/short
    # first result stand for the whole WeChat source.
    another=next((d for d in package["results"] if d["platform"]=="wechat" and d not in chosen and d["url"] not in seen),None)
    if another and len(chosen)<6:chosen.append(another)
    jobs=[{"kind":"read","url":d["url"],"title_hint":d.get("title","")} for d in chosen[:6] if d["url"] not in seen]
    if package["status"]!="cancelled":
        records,cancelled=run_jobs(jobs,config,deadline)
        for rec in records:
            value=rec["value"]
            if rec["status"]=="ok":reads.append(value)
            else:reads.append({"requested_url":rec["job"]["url"],"url":rec["job"]["url"],"status":rec["status"],"content_level":"none","evidence":[],"warnings":[{"message":value.get("error","Read budget ended.")}]})
    else:cancelled=True
    package["mode"]="research";package["documents"]=reads;package["budget_seconds"]=budget;package["seconds"]=round(time.monotonic()-start,3)
    package["research_plan"]={"goal":query,"queries":package["queries"],"steps":["discover complementary sources","read representative original pages","identify evidence gaps/conflicts","Agent synthesizes cited claims"]}
    package["gaps"]=[{"source":s,"reason":"No validated result retrieved; see traces."} for s,n in package["coverage"].items() if not n]
    package["gaps"] += [{"url":d["url"],"reason":"Only metadata/snippet or failed read, not full content."} for d in reads if d.get("content_level") in {"none","metadata"}]
    for source in package["sources"]:
        if not any(d.get("status")=="ok" and d.get("platform")==source and d.get("content_level") in {"body","pdf_text","transcript"} for d in reads):
            package["gaps"].append({"source":source,"reason":"No full-content evidence acquired from this source in this run."})
    package["requires_agent_synthesis"]=True
    if cancelled:package["status"]="cancelled"
    elif package["gaps"] and package["results"]:package["status"]="partial"
    if output:save_package(package,output)
    return package
def save_package(package,directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    for name in ["report.json","checkpoint.json"]:
        temp=root/(name+".tmp");temp.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding="utf-8");temp.replace(root/name)
    lines=["# "+package["query"],"","检索证据包（不是自动生成的事实结论）；Agent须回读正文、逐声明引用，说明不足。","",f"状态：{package['status']}；耗时：{package['seconds']}s；排序：{package['ranking']}",""]
    for i,d in enumerate(package["results"],1):
        lines += [f"## [{i}] {d['title']}",f"来源：{d['platform']} / {d['provider']}；{d['url']}",d.get("snippet",""),""]
    lines += ["## 阅读证据",""]
    for d in package.get("documents",[]):
        lines += [f"### {d.get('title') or d['url']}",f"{d['url']} — {d['status']} / {d['content_level']}"]
        lines += [f"- {e['locator']}: {e['text'][:1600]}" for e in d.get("evidence",[])[:8]]
    lines += ["","## 缺口",*[f"- {json.dumps(g,ensure_ascii=False)}" for g in package.get("gaps",[])]]
    (root/"report.md").write_text("\n".join(lines),encoding="utf-8")
