#!/usr/bin/env python3
"""Unified Agent-facing search/read/research/batch/health. Legacy commands remain available."""
from __future__ import annotations
import argparse,json,os,sys,time
from pathlib import Path
from search_core.engine import search,research,load_config,run_jobs,save_package
from search_core.browser import listing
from search_core.models import SearchError
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",help="Optional JSON config path (no secrets required).")
    p.add_argument("--no-browser",action="store_true",help="Use public HTTP only.")
    p.add_argument("--cancel-file",help="Stop own workers and retain collected results when this marker exists.")
    p.add_argument("--language",help="Provider language hint, e.g. zh-CN or en.")
    p.add_argument("--time-range",choices=["day","week","month","year"],help="Provider recency filter; timestamps still require verification.")
    p.add_argument("--category",choices=["general","news"],help="Web provider search category.")
    p.add_argument("--page",type=int,default=1,help="Provider result page 1-10; native Xiaohongshu requires scrolling instead.")
    sub=p.add_subparsers(dest="action",required=True)
    for action in ["search","research","auto"]:
        q=sub.add_parser(action);q.add_argument("query");q.add_argument("--sources",help="web,wechat,bilibili,xiaohongshu,github")
        q.add_argument("--limit",type=int,default=12);q.add_argument("--budget",type=float,default=None);q.add_argument("--fresh",action="store_true")
        q.add_argument("--queries",nargs="+",help="Agent-written query variants; original retained.")
        q.add_argument("--sites",nargs="+",help="Strict result hostname filters.")
        q.add_argument("--output",help="Directory for report.json/checkpoint.json/report.md")
        q.add_argument("--resume",help="Earlier research checkpoint.json; same question only.")
    q=sub.add_parser("read");q.add_argument("url");q.add_argument("--budget",type=float,default=20);q.add_argument("--max-chars",type=int,default=18000);q.add_argument("--title",default="",help="Exact discovered article title for fresh Sogou normal-click navigation.")
    q=sub.add_parser("batch");q.add_argument("input",help="JSON array of query strings.");q.add_argument("--budget",type=float,default=60);q.add_argument("--output")
    sub.add_parser("health")
    args=p.parse_args();config=load_config(args.config)
    if args.no_browser:config["browser"]=False
    if args.cancel_file:config["cancel_file"]=args.cancel_file
    if args.language:config["language"]=args.language
    if args.time_range:config["time_range"]=args.time_range
    if args.category:config["categories"]=args.category
    if not 1<=args.page<=10:p.error("--page must be 1-10")
    config["page"]=args.page
    try:
        if args.action=="health":
            try:targets=listing(config,time.monotonic()+3);browser={"status":"ready","pages":len(targets)}
            except SearchError as e:browser={"status":e.code,"message":str(e)}
            from search_core.net import fetch
            from urllib.parse import urlsplit
            try:fetch(config["searxng_url"]+"/config",time.monotonic()+2,local=urlsplit(config["searxng_url"]).hostname in {"127.0.0.1","localhost","::1"});searx="ready"
            except Exception as e:searx=getattr(e,"code","unavailable")
            result={"schema_version":"2.0","status":"ok","config":config,"browser":browser,"searxng":searx,"capabilities":{"public_web":"HTTP + existing-browser fallback","wechat":"public Sogou","bilibili":"API + browser cards/subtitles when accessible","xiaohongshu":"login-dependent native + public indexed discovery","github":"API + existing gh","pdf":"optional pypdf","rss":"legacy rss_fetch.py preserved"},"cost":"no new search/crawl API charges; current Agent inference unchanged"}
        elif args.action=="read":
            budget=max(.1,min(300,args.budget));records,cancelled=run_jobs([{"kind":"read","url":args.url,"title_hint":args.title,"max_chars":max(100,min(50000,args.max_chars))}],config,time.monotonic()+budget)
            rec=records[0];result=rec["value"] if rec["status"]=="ok" else {"status":rec["status"],"url":args.url,"content_level":"none","error":rec["value"].get("error"),"evidence":[]}
        elif args.action=="batch":
            queries=json.loads(Path(args.input).read_text(encoding="utf-8"))
            if not isinstance(queries,list) or any(not isinstance(q,str) or not q.strip() for q in queries):raise ValueError("Batch must be nonempty query strings.")
            until=time.monotonic()+max(.1,min(900,args.budget));results=[]
            for query in queries[:20]:
                if time.monotonic()>=until:break
                results.append(search(query,config,budget=min(30,until-time.monotonic())))
            result={"status":"ok" if len(results)==len(queries) else "partial","results":results,"completed":len(results),"requested":len(queries)}
            if args.output:Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        else:
            sources=args.sources.split(",") if args.sources else None
            if sources and any(s not in {"web","wechat","bilibili","xiaohongshu","github"} for s in sources):raise ValueError("Unsupported source.")
            mode=args.action
            if mode=="auto":
                import re
                mode="research" if re.search(r"深入|研究|报告|对比|系统梳理|research|compare",args.query,re.I) else "search"
            budget=max(.1,min(900,args.budget if args.budget is not None else 300 if mode=="research" else 30))
            variants=list(dict.fromkeys([args.query]+(args.queries or []))) if args.queries else None
            if args.resume:
                old=json.loads(Path(args.resume).read_text(encoding="utf-8"))
                if old.get("query")!=args.query:raise ValueError("Resume query must match checkpoint question.")
            if mode=="research":result=research(args.query,config,sources,max(1,min(50,args.limit)),budget,args.output,args.resume,variants,args.fresh)
            else:
                result=search(args.query,config,sources=sources,limit=max(1,min(50,args.limit)),budget=budget,fresh=args.fresh,queries=variants,sites=args.sites)
                if args.output:save_package(result,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get("status") in {"ok","partial","empty"} else 2
    except (ValueError,OSError,SearchError) as e:
        print(json.dumps({"status":"error","code":getattr(e,"code","invalid_request"),"error":str(e)},ensure_ascii=False));return 2
if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8");raise SystemExit(main())
