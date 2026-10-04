from __future__ import annotations
import re, math
from collections import Counter
from urllib.parse import urlsplit
from .models import canonical, digest
STOP={"the","a","an","and","of","in","for","to","on","with","is","how","what","latest","find","search","please"}
INTENTS={"video":["视频","影片","漫剧","短剧","video","film"],"workflow":["工作流","流程","全流程","实操","workflow","pipeline"],"tutorial":["教程","教学","指南","入门","tutorial","guide"]}
def tokens(query):
    query=re.sub(r"site:\S+","",query.lower())
    words=[x for x in re.findall(r"[a-z0-9][a-z0-9.+_-]*",query) if x not in STOP]
    for word in re.findall(r"[\u4e00-\u9fff]+",query):
        if len(word)>1:words.extend(word[i:i+2] for i in range(len(word)-1))
    return list(dict.fromkeys(words))
def relevance(query,d):
    text=(d.get("title","")+" "+d.get("snippet","")).lower(); terms=tokens(query)
    lexical=sum(1 for t in terms if t in text)/max(1,len(terms))
    groups=[group for group,aliases in INTENTS.items() if any(a in query.lower() for a in aliases)]
    group_score=sum(any(a in text for a in INTENTS[g]) for g in groups)/max(1,len(groups))
    if groups and not any(any(a in text for a in INTENTS[g]) for g in groups):return 0.0
    score=.65*lexical+.35*group_score if groups else lexical
    # Tutorial queries prefer direct procedural titles to promotional resource/earnings pitches.
    if "tutorial" in groups:
        if re.search(r"财富密码|变现|赚钱|涨粉|带货|免费下载|知识宝库|资源库",d.get("title","")):score-=.16
        if re.search(r"全流程|完整流程|实操|指南|保姆级|从脚本|从零",d.get("title","")):score+=.05
    return round(max(0,min(1,score)),4)
def source_hint(d, official_domains):
    host=urlsplit(d["url"]).hostname or ""
    if any(host==x or host.endswith("."+x) for x in official_domains):return "official_verified_domain"
    if host.endswith(".gov") or ".gov." in host:return "government_domain_hint"
    if d["platform"]=="github":return "repository" # Not automatically official for a product.
    if d["platform"] in {"wechat","bilibili","xiaohongshu"}:return "creator_content"
    return "unknown"
def merge_rank(query,docs,limit,platforms,sites=None,official_domains=None):
    merged={};removed=Counter();sites=sites or [];official_domains=official_domains or []
    for d in docs:
        if not d or not d.get("url") or not d.get("title"):removed["invalid"]+=1;continue
        d["canonical_url"]=canonical(d["url"]);host=urlsplit(d["url"]).hostname or ""
        if sites and not any(host==s or host.endswith("."+s) for s in sites):removed["site_mismatch"]+=1;continue
        score=relevance(query,d)
        if score<.12:removed["irrelevant"]+=1;continue
        d["relevance"]=score;d["source_type"]=source_hint(d,official_domains)
        key=d["canonical_url"]
        if d["platform"]=="wechat" and host=="weixin.sogou.com":
            # Redirect tokens vary per query; title+author dedup is restricted to this provider.
            key="wechat:"+digest(d["title"]+"|"+d.get("author",""))
        if key in merged:
            old=merged[key];old["provenance"].extend(p for p in d["provenance"] if p not in old["provenance"])
            if len(d.get("snippet",""))>len(old.get("snippet","")):old["snippet"]=d["snippet"]
            removed["duplicates"]+=1
        else:merged[key]=d
    ranked=sorted(merged.values(),key=lambda d:(d["relevance"],len(d.get("provenance",[]))),reverse=True)
    # Reserve a slot per actually discovered requested platform, then fill by relevance.
    result=[]
    buckets={p:[d for d in ranked if d["platform"]==p] for p in platforms}
    reserve=max(1,min(3,limit//max(1,len([v for v in buckets.values() if v]))))
    for index in range(reserve):
        for p in platforms:
            if len(buckets[p])>index and len(result)<limit:result.append(buckets[p][index])
    result.extend(d for d in ranked if d not in result)
    return result[:limit],dict(removed),len(merged)
