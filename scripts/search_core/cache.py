import json, time
from pathlib import Path
from .models import digest
class Cache:
    def __init__(self,path,ttl=900,entries=64):
        self.path=Path(path);self.ttl=ttl;self.entries=entries
    def get(self,key):
        f=self.path/(digest(key)+".json")
        try:
            if time.time()-f.stat().st_mtime>self.ttl:return None
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError,ValueError):return None
    def put(self,key,value):
        try:
            self.path.mkdir(parents=True,exist_ok=True)
            f=self.path/(digest(key)+".json");tmp=f.with_suffix(".tmp")
            tmp.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8");tmp.replace(f)
            files=sorted(self.path.glob("*.json"),key=lambda f:f.stat().st_mtime,reverse=True)
            for old in files[self.entries:]:old.unlink(missing_ok=True)
        except OSError:pass
