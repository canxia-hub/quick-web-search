"""Small RFC6455 CDP client; attaches only to explicitly configured loopback.
Never starts/kills Chrome, reads cookies, or closes existing user tabs.
"""
from __future__ import annotations
import base64, hashlib, json, os, socket, struct, time
from urllib.parse import urlsplit
from .net import fetch, public_url
from .models import SearchError
class Wire:
    def __init__(self,url,deadline):
        p=urlsplit(url)
        if p.scheme!="ws" or p.hostname not in {"127.0.0.1","localhost","::1"}:
            raise SearchError("browser_config","CDP must use an explicitly trusted loopback ws endpoint.")
        self.deadline=deadline;self.seq=0
        self.sock=socket.create_connection((p.hostname,p.port or 80),timeout=max(.1,min(3,deadline-time.monotonic())))
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {p.path} HTTP/1.1\r\nHost: {p.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        response=b""
        while b"\r\n\r\n" not in response: response+=self.sock.recv(1)
        expected=base64.b64encode(hashlib.sha1((key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not response.startswith(b"HTTP/1.1 101") or expected not in response:
            self.sock.close();raise SearchError("browser_connect","CDP websocket handshake rejected.")
    def exact(self,n):
        self.sock.settimeout(max(.1,self.deadline-time.monotonic()));data=b""
        while len(data)<n:
            part=self.sock.recv(n-len(data))
            if not part: raise SearchError("browser_connect","CDP connection closed.")
            data+=part
        return data
    def send(self,payload,opcode=1):
        data=payload.encode() if isinstance(payload,str) else payload;n=len(data);mask=os.urandom(4)
        header=bytes([0x80|opcode,0x80|(n if n<126 else 126 if n<65536 else 127)])
        if n>=126:header+=struct.pack("!H" if n<65536 else "!Q",n)
        self.sock.sendall(header+mask+bytes(b^mask[i%4] for i,b in enumerate(data)))
    def receive(self):
        pieces=b""
        while True:
            a,b=self.exact(2);size=b&127
            if size==126:size=struct.unpack("!H",self.exact(2))[0]
            elif size==127:size=struct.unpack("!Q",self.exact(8))[0]
            if size>10_000_000: raise SearchError("browser_response","Oversized CDP frame.")
            mask=self.exact(4) if b&128 else None;data=self.exact(size)
            if mask:data=bytes(v^mask[i%4] for i,v in enumerate(data))
            op=a&15
            if op==8:raise SearchError("browser_connect","CDP websocket closed.")
            if op==9:self.send(data,10);continue
            if op==10:continue
            pieces+=data
            if a&128:return json.loads(pieces)
    def call(self,method,params=None):
        self.seq+=1;seq=self.seq;self.send(json.dumps({"id":seq,"method":method,"params":params or {}}))
        while time.monotonic()<self.deadline:
            msg=self.receive()
            if msg.get("id")==seq:
                if "error" in msg:raise SearchError("browser_protocol",msg["error"].get("message","CDP error"))
                return msg.get("result",{})
        raise SearchError("timeout","Browser operation budget exhausted.")
    def close(self):self.sock.close()

def endpoint(config):
    url=config.get("cdp_url") or os.getenv("SEARCH_CDP_URL","http://127.0.0.1:18800")
    p=urlsplit(url)
    if p.scheme!="http" or p.hostname not in {"localhost","127.0.0.1","::1"} or p.username or p.password:
        raise SearchError("browser_config","Only configured loopback HTTP CDP endpoints are supported.")
    return url.rstrip("/")
def listing(config,deadline):
    try:return json.loads(fetch(endpoint(config)+"/json/list",deadline,local=True)["text"])
    except Exception as e:raise SearchError("browser_required","Start the existing OpenClaw browser profile with the native browser tool, then retry.") from e
def close_target(config,target):
    try:
        until=time.monotonic()+2
        version=json.loads(fetch(endpoint(config)+"/json/version",until,local=True)["text"])
        w=Wire(version["webSocketDebuggerUrl"],until)
        try:w.call("Target.closeTarget",{"targetId":target})
        finally:w.close()
    except Exception:pass
def evaluate_page(url,expression,config,deadline,lease=None,ready=None,*,click_title=None):
    public_url(url);targets=listing(config,deadline);owned=False;target=None
    for t in targets:
        if click_title is None and t.get("type")=="page" and t.get("url")==url:target=t;break
    if target is None:
        version=json.loads(fetch(endpoint(config)+"/json/version",deadline,local=True)["text"])
        w=Wire(version["webSocketDebuggerUrl"],deadline)
        try:tid=w.call("Target.createTarget",{"url":url})["targetId"]
        finally:w.close()
        owned=True
        if lease:lease(tid)
        for _ in range(30):
            targets=listing(config,deadline);target=next((t for t in targets if t["id"]==tid),None)
            if target:break
            if time.monotonic()>=deadline:raise SearchError("timeout","Browser target creation timed out.")
            time.sleep(.05)
    if not target:raise SearchError("browser_connect","No CDP page target.")
    w=None
    try:
        w=Wire(target["webSocketDebuggerUrl"],deadline)
        w.call("Runtime.enable")
        def evaluate(expr):
            # Navigation can replace the execution context between target creation and extraction.
            for attempt in range(30):
                if time.monotonic()>=deadline:raise SearchError("timeout","Page execution context did not become ready.")
                try:
                    result=w.call("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True})
                    if result.get("exceptionDetails"):raise SearchError("browser_script",str(result["exceptionDetails"].get("exception",{}).get("description") or result["exceptionDetails"].get("text","Extraction failed"))[:160])
                    return result.get("result",{}).get("value")
                except SearchError as e:
                    if e.code!="browser_protocol" or not any(t in str(e) for t in ["execution context","Cannot find context"]):raise
                    time.sleep(.08)
            raise SearchError("browser_context","Page execution context repeatedly replaced.")
        # Do not evaluate extractors against an initial about:blank document.
        while time.monotonic()<deadline:
            if evaluate("Boolean(document.body) && location.href !== 'about:blank'"):break
            time.sleep(.08)
        if click_title is not None:
            # Use an owned search tab and the site's normal mouse navigation;
            # never synthesize redirect signatures or alter existing user tabs.
            title=json.dumps(click_title,ensure_ascii=False)
            locate=r"""(() => {const normalized=s=>s.normalize('NFKC').replace(/\s+/g,'');
                const matches=[...document.querySelectorAll('ul.news-list h3 a')].filter(a=>normalized(a.innerText)===normalized(__TITLE__));
                if(matches.length!==1)return {count:matches.length};
                const a=matches[0];a.target='_self';a.scrollIntoView({block:'center'});
                const r=a.getBoundingClientRect();return {count:1,x:r.x+r.width/2,y:r.y+r.height/2};
            })()""".replace("__TITLE__",title)
            while time.monotonic()<deadline:
                if evaluate("Boolean(document.querySelector('ul.news-list h3 a')) || (document.readyState==='complete' && /验证码|访问过于频繁|antispider/.test(document.body?.innerText||''))"):break
                time.sleep(.15)
            point=evaluate(locate)
            if not point or point.get("count")!=1:
                if evaluate("/验证码|访问过于频繁|antispider/.test(document.body?.innerText||'')"):
                    raise SearchError("captcha","Sogou requires manual verification; no verification was attempted.")
                raise SearchError("article_match_unavailable","Requested article title not uniquely present on fresh Sogou results; no different article substituted.")
            for event in ("mousePressed","mouseReleased"):
                w.call("Input.dispatchMouseEvent",{"type":event,"x":point["x"],"y":point["y"],"button":"left","clickCount":1})
        if ready:
            while time.monotonic()<deadline:
                if evaluate(ready):break
                time.sleep(.15)
        value=evaluate(expression)
        return value
    finally:
        if w:w.close()
        if owned:close_target(config,target["id"])
