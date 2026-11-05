
import json, os, sys, time, threading, urllib.request, urllib.error, base64, sqlite3, ssl, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk

try:
    from usage_windows import (
        normalize_claude_desktop,
        normalize_claude_usage,
        normalize_codex_usage,
        normalize_cursor_usage,
    )
    from local_auth import claude_credentials_payload, is_jwt, read_cursor_auth_json, unwrap_cursor_secret
except ImportError:
    from src.usage_windows import (
        normalize_claude_desktop,
        normalize_claude_usage,
        normalize_codex_usage,
        normalize_cursor_usage,
    )
    from src.local_auth import claude_credentials_payload, is_jwt, read_cursor_auth_json, unwrap_cursor_secret

try:
    import certifi
except Exception:
    certifi=None

APP_NAME="AI Usage Widget"
APP_VERSION="1.2.0"
CLAUDE_URL="https://api.anthropic.com/api/oauth/usage"
CLAUDE_PROFILE_URL="https://api.anthropic.com/api/oauth/profile"
CLAUDE_TOKEN_URL="https://platform.claude.com/v1/oauth/token"
CLAUDE_CLIENT_ID="9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CODEX_URL="https://chatgpt.com/backend-api/wham/usage"
CURSOR_BASE="https://cursor.com"
CURSOR_API2="https://api2.cursor.sh"
CURSOR_DASHBOARD=CURSOR_API2+"/aiserver.v1.DashboardService"
REFRESH_SECONDS=300
APP_WIDTH=450
_CLAUDE_OAUTH_CACHE={}
_CLAUDE_OAUTH_LOCK=threading.Lock()
_CURSOR_REFRESH=None
WIDGET_PORT=38471
SECONDARY_TEXT="systemSecondaryLabelColor" if sys.platform=="darwin" else "#555"

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray=None
    Image=ImageDraw=None

if sys.platform=="darwin":
    try:
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
        from Foundation import NSObject
    except Exception:
        NSObject=None
else:
    NSObject=None


if NSObject:
    class MacStatusTarget(NSObject):
        def toggle_(self,sender):
            self.widget.toggle()

        def refresh_(self,sender):
            self.widget.refresh()

        def topmost_(self,sender):
            self.widget.topmost()
            self.widget.root.after(30,lambda:sender.setState_(1 if bool(self.widget.root.attributes("-topmost")) else 0))

        def quit_(self,sender):
            self.widget.quit()


    class MacStatusBar:
        """Native NSStatusItem used instead of pystray on macOS."""

        def __init__(self,widget):
            self.widget=widget
            self.target=MacStatusTarget.alloc().init()
            self.target.widget=widget
            self.status_bar=NSStatusBar.systemStatusBar()
            self.status_item=self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)
            self.status_item.button().setTitle_("AI")
            self.status_item.button().setToolTip_(APP_NAME)

            self.menu=NSMenu.alloc().initWithTitle_(APP_NAME)
            self._add("Show / Hide","toggle:")
            self._add("Refresh now","refresh:")
            self.topmost_item=self._add("Always on top","topmost:")
            self.menu.addItem_(NSMenuItem.separatorItem())
            self._add("Quit","quit:")
            self.status_item.setMenu_(self.menu)

        def _add(self,title,action):
            item=NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title,action,"")
            item.setTarget_(self.target)
            self.menu.addItem_(item)
            return item

        @property
        def title(self):
            return self.status_item.button().toolTip()

        @title.setter
        def title(self,value):
            self.status_item.button().setToolTip_(value)

        def stop(self):
            if self.status_item:
                self.status_bar.removeStatusItem_(self.status_item)
                self.status_item=None

def num(v):
    try:return float(v)
    except Exception:return None
def clamp(v):
    n=num(v); return None if n is None else max(0,min(100,n))
def remain(used):
    n=clamp(used); return None if n is None else 100-n
def pt(v):
    n=clamp(v); return "—" if n is None else f"{n:.0f}%"
def money_minor(v,exp=2):
    try:return f"${float(v)/(10**int(exp)):,.2f}"
    except Exception:return "—"
def parse_reset(v):
    if not v:return None
    try:
        if isinstance(v,str):
            text=v.strip()
            if text.isdigit():
                stamp=float(text)
                if stamp>1e12:stamp/=1000
                return datetime.fromtimestamp(stamp,tz=timezone.utc)
            return datetime.fromisoformat(text.replace("Z","+00:00"))
        stamp=float(v)
        if stamp>1e12:stamp/=1000
        return datetime.fromtimestamp(stamp,tz=timezone.utc)
    except Exception:return None
def reset_text(v):
    dt=parse_reset(v)
    if not dt:return None
    sec=max(0,int((dt-datetime.now(timezone.utc)).total_seconds()))
    d,sec=divmod(sec,86400); h,sec=divmod(sec,3600); m=sec//60
    cd=f"{d}d {h}h" if d else (f"{h}h {m}m" if h else f"{m}m")
    return f"Reset in {cd} · {dt.astimezone().strftime('%d.%m.%Y %H:%M')}"
def jwt_payload(token):
    try:
        p=token.split(".")[1]; p+="="*((4-len(p)%4)%4)
        return json.loads(base64.urlsafe_b64decode(p).decode("utf-8"))
    except Exception:return {}

def account_email(data):
    if not isinstance(data,dict):return None
    account=data.get("account") if isinstance(data.get("account"),dict) else {}
    for source in (account,data):
        for key in ("emailAddress","email_address","email"):
            value=source.get(key)
            if isinstance(value,str) and "@" in value:return value.strip()
    return None

def account_display(data):
    email=data.get("email")
    if email:return email
    account_id=data.get("account_id")
    if account_id:return f"ID: {account_id}"
    if data.get("status")=="ok":return "Signed in · address unavailable"
    return data.get("message") or "Not signed in"

def request_json(url,headers=None,method="GET",body=None,timeout=15):
    data=None
    if body is not None:data=json.dumps(body).encode("utf-8")
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    try:
        context=ssl.create_default_context(cafile=certifi.where()) if certifi else None
        with urllib.request.urlopen(req,timeout=timeout,context=context) as r:
            raw=r.read().decode("utf-8")
            return r.status,json.loads(raw) if raw else {},None
    except urllib.error.HTTPError as e:
        try:err=e.read().decode("utf-8","replace")
        except Exception:err=str(e)
        return e.code,None,err
    except Exception as e:return None,None,str(e)

def request_form_json(url,fields,timeout=30):
    from urllib.parse import urlencode
    req=urllib.request.Request(url,data=urlencode(fields).encode("utf-8"),headers={
        "Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"},method="POST")
    try:
        context=ssl.create_default_context(cafile=certifi.where()) if certifi else None
        with urllib.request.urlopen(req,timeout=timeout,context=context) as r:
            raw=r.read().decode("utf-8")
            return r.status,json.loads(raw) if raw else {},None
    except urllib.error.HTTPError as e:
        try:err=e.read().decode("utf-8","replace")
        except Exception:err=str(e)
        return e.code,None,err
    except Exception as e:return None,None,str(e)

def refresh_claude_oauth(oauth):
    refresh_token=_CLAUDE_OAUTH_CACHE.get("refresh_token") or oauth.get("refreshToken")
    if not refresh_token:return None
    with _CLAUDE_OAUTH_LOCK:
        refresh_token=_CLAUDE_OAUTH_CACHE.get("refresh_token") or refresh_token
        fields={"grant_type":"refresh_token","refresh_token":refresh_token,"client_id":CLAUDE_CLIENT_ID}
        st,data,_=request_form_json(CLAUDE_TOKEN_URL,fields)
        if st!=200 or not isinstance(data,dict) or not data.get("access_token"):
            st,data,_=request_json(CLAUDE_TOKEN_URL,{
                "Content-Type":"application/json","Accept":"application/json"},"POST",fields)
        if st!=200 or not isinstance(data,dict) or not data.get("access_token"):return None
        _CLAUDE_OAUTH_CACHE["access_token"]=data["access_token"]
        _CLAUDE_OAUTH_CACHE["refresh_token"]=data.get("refresh_token") or refresh_token
        return data["access_token"]

def claude_headers(token):
    return {"Authorization":f"Bearer {token}","anthropic-beta":"oauth-2025-04-20",
            "User-Agent":"claude-code/2.1.207","Content-Type":"application/json"}


class WidgetDataServer:
    """Expose non-sensitive usage percentages to the local WidgetKit extension."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path!="/usage":
                self.send_error(404)
                return
            body=json.dumps(self.server.snapshot_provider()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self,format,*args):
            pass

    def __init__(self,snapshot_provider):
        self.server=None
        try:
            self.server=ThreadingHTTPServer(("127.0.0.1",WIDGET_PORT),self.Handler)
            self.server.daemon_threads=True
            self.server.snapshot_provider=snapshot_provider
            threading.Thread(target=self.server.serve_forever,daemon=True).start()
        except OSError:
            self.server=None

    def stop(self):
        if self.server:
            threading.Thread(target=self.server.shutdown,daemon=True).start()

def claude_credentials():
    return claude_credentials_payload()

def get_claude_desktop():
    """Read Claude Desktop's non-sensitive, locally cached plan utilization."""
    data_dir=Path(os.environ.get("CLAUDE_DESKTOP_DATA_DIR") or
                  (Path.home()/"Library"/"Application Support"/"Claude"))
    try:
        history=json.loads((data_dir/"plan-usage-history.json").read_text(encoding="utf-8"))
        samples=history.get("samples") or []
        sample=max((item for item in samples if isinstance(item,dict)),key=lambda item:item.get("t",0))
        captured=float(sample.get("t"))/1000
        values=sample.get("u") or {}
    except Exception:
        return {"status":"error","message":"Claude Desktop: no usage data"}
    result=normalize_claude_desktop(values)
    if result.get("status")!="ok":
        return {"status":"error","message":"Claude Desktop: no quota data","windows":[]}
    age=max(0,time.time()-captured)
    if age>1800:
        captured_text=datetime.fromtimestamp(captured,tz=timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
        result.update(
            stale=True,
            captured_at=captured,
            source="claude-desktop-cache",
            message=f"Saved Claude status from {captured_text}",
        )
    return result

def merge_claude_usage(live,desktop):
    if live.get("status")!="ok":return desktop
    if desktop.get("status")!="ok":return live
    windows=[dict(window) for window in desktop.get("windows") or []]
    positions={window.get("id"):index for index,window in enumerate(windows)}
    live_windows=live.get("windows") or []
    live_ids={window.get("id") for window in live_windows}
    stale_desktop_windows=bool(desktop.get("stale") and any(
        window.get("id") not in live_ids for window in desktop.get("windows") or []))
    for window in live_windows:
        window_id=window.get("id")
        if window_id in positions:windows[positions[window_id]]=dict(window)
        else:
            positions[window_id]=len(windows)
            windows.append(dict(window))
    result=dict(live); result["windows"]=windows; result["source"]="oauth+claude-desktop"
    if stale_desktop_windows:
        result.update(
            stale=True,
            captured_at=desktop.get("captured_at"),
            message=desktop.get("message") or "Partially saved Claude status",
        )
    valid=[window for window in windows if num(window.get("used_percent")) is not None]
    if valid:
        tightest=max(valid,key=lambda window:window["used_percent"])
        result.update(label=tightest.get("label"),used=tightest.get("used_percent"),reset=tightest.get("resets_at"))
    return result

def get_claude():
    c=claude_credentials()
    if not isinstance(c,dict):return get_claude_desktop()
    oauth=c.get("claudeAiOauth") or {}
    token=_CLAUDE_OAUTH_CACHE.get("access_token") or oauth.get("accessToken")
    if not token and (oauth.get("refreshToken") or _CLAUDE_OAUTH_CACHE.get("refresh_token")):
        token=refresh_claude_oauth(oauth)
    if not token:return get_claude_desktop()
    headers=claude_headers(token)
    pst,profile,_=request_json(CLAUDE_PROFILE_URL,headers)
    if pst in (401,403):
        token=refresh_claude_oauth(oauth)
        if token:
            headers=claude_headers(token)
            pst,profile,_=request_json(CLAUDE_PROFILE_URL,headers)
    email=account_email(profile) if pst==200 else None
    st,d,_=request_json(CLAUDE_URL,headers)
    desktop=get_claude_desktop()
    result=normalize_claude_usage(d) if st==200 and isinstance(d,dict) else desktop
    if result.get("status")=="ok":result=merge_claude_usage(result,desktop)
    else:result=desktop
    if email:result["email"]=email
    return result

def get_codex():
    p=Path(os.environ.get("CODEX_HOME") or (Path.home()/".codex"))/"auth.json"
    try:
        a=json.loads(p.read_text(encoding="utf-8")); t=a.get("tokens") or {}
        token=t.get("access_token"); aid=t.get("account_id"); iid=t.get("id_token")
    except Exception:return {"status":"error","message":"Not signed in"}
    if not token:return {"status":"error","message":"Access token missing"}
    h={"Authorization":f"Bearer {token}","User-Agent":"codex-cli"}
    if aid:h["ChatGPT-Account-Id"]=aid
    st,d,_=request_json(CODEX_URL,h)
    if st!=200 or not isinstance(d,dict):return {"status":"error","message":f"HTTP {st or 'ERR'}"}
    result=normalize_codex_usage(d)
    email=jwt_payload(iid).get("email") if iid else None
    if email:result["email"]=email
    return result

def cursor_db_path(platform_name=None, env=None, home=None):
    platform_name=platform_name or sys.platform
    env=os.environ if env is None else env
    home=Path.home() if home is None else Path(home)
    if platform_name=="darwin":
        return home/"Library"/"Application Support"/"Cursor"/"User"/"globalStorage"/"state.vscdb"
    if platform_name=="linux":
        return home/".config"/"Cursor"/"User"/"globalStorage"/"state.vscdb"
    appdata=env.get("APPDATA")
    base=Path(appdata) if appdata else home/"AppData"/"Roaming"
    return base/"Cursor"/"User"/"globalStorage"/"state.vscdb"

def sqlite_readonly(path):
    """Open Cursor's state DB even when the IDE holds a Windows file lock or the path contains spaces."""
    path=Path(path)
    uri=path.resolve().as_uri()+"?mode=ro&immutable=1"
    try:
        con=sqlite3.connect(uri,uri=True,timeout=2)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.Error:
        pass
    try:
        con=sqlite3.connect(str(path),timeout=2)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.Error:
        pass
    import shutil, tempfile
    tmp=Path(tempfile.mkdtemp(prefix="ai-usage-cursor-"))/"state.vscdb"
    shutil.copyfile(path,tmp)
    for suffix in ("-wal","-shm"):
        extra=Path(str(path)+suffix)
        if extra.exists():shutil.copyfile(extra,Path(str(tmp)+suffix))
    return sqlite3.connect(str(tmp),timeout=2)

def cursor_user_id(sub):
    if not isinstance(sub,str) or not sub:return ""
    if "|" in sub:
        parts=sub.split("|")
        for part in parts:
            if part.startswith("user_"):return part
        return parts[-1]
    return sub

def cursor_api2_headers(token):
    return {"Authorization":f"Bearer {token}","Content-Type":"application/json",
            "Connect-Protocol-Version":"1","User-Agent":"Mozilla/5.0"}

def cursor_plan_result(plan, reset=None, email=None, account_id=None):
    result={"status":"ok","cursor_models_used":plan.get("autoPercentUsed"),"other_models_used":plan.get("apiPercentUsed"),
            "total_used":plan.get("totalPercentUsed"),"reset":reset,"models":[],"model_source":None}
    if result["cursor_models_used"] is None and result["other_models_used"] is None:
        used=num(plan.get("used")); limit=num(plan.get("limit"))
        if used is not None and limit not in (None,0):
            result["total_used"]=max(0,min(100,used/limit*100))
    if email:result["email"]=email
    elif account_id:result["account_id"]=account_id
    return result

def models_from_aggregations(data):
    rows=data.get("aggregations") if isinstance(data,dict) else None
    if not isinstance(rows,list):return []
    models=[]
    for row in rows:
        if not isinstance(row,dict):continue
        name=row.get("modelIntent") or row.get("model") or "Unknown"
        cents=num(row.get("totalCents"))
        models.append({"model":name,"requests":num(row.get("eventCount")) or 0,"weighted":cents,
                       "charged_cents":cents,"token_cents":cents})
    return [item for item in models if item["model"] and (item["weighted"] or item["requests"])]

def models_from_legacy_usage(data):
    models=[]
    for name,val in (data or {}).items():
        if name in ("startOfMonth","globalRequests") or not isinstance(val,dict):continue
        nr=val.get("numRequests")
        if isinstance(nr,(int,float)) and nr>0:
            models.append({"model":name,"requests":nr,"weighted":None,"charged_cents":None,"token_cents":None})
    return models

def models_from_events(events):
    agg={}
    for ev in events:
        if not isinstance(ev,dict):continue
        m=ev.get("model") or "Unknown"
        a=agg.setdefault(m,{"model":m,"requests":0,"weighted":0.0,"charged_cents":0.0,"token_cents":0.0})
        a["requests"]+=1
        rc=num(ev.get("requestsCosts"))
        if rc is not None:a["weighted"]+=rc
        cc=num(ev.get("chargedCents"))
        if cc is not None:a["charged_cents"]+=cc
        tc=num((ev.get("tokenUsage") or {}).get("totalCents"))
        if tc is not None:a["token_cents"]+=tc
    return list(agg.values())

def sort_cursor_models(models):
    models.sort(key=lambda x:(x.get("weighted") or 0, x.get("charged_cents") or 0, x.get("requests") or 0),reverse=True)
    return models

def finalize_cursor_result(result):
    normalized=normalize_cursor_usage(result)
    if normalized.get("windows"):
        result["windows"]=normalized["windows"]
    return result

def cursor_auth_from_token(token, cached_email=None):
    payload=jwt_payload(token)
    sub=payload.get("sub","")
    uid=cursor_user_id(sub)
    cookie=f"{uid}%3A%3A{token}" if uid and token else None
    email=account_email(payload) or cached_email
    if isinstance(email,str) and "@" not in email:email=None
    return cookie,sub,email,token

def refresh_cursor_oauth(refresh_token):
    if not refresh_token:return None
    st,data,_=request_json(CURSOR_API2+"/oauth/token",{
        "Content-Type":"application/json","User-Agent":"Mozilla/5.0"},"POST",
        {"grant_type":"refresh_token","refresh_token":refresh_token})
    if st!=200 or not isinstance(data,dict) or data.get("shouldLogout"):return None
    return data.get("access_token") or data.get("accessToken")

def cursor_session():
    global _CURSOR_REFRESH
    _CURSOR_REFRESH=None
    access=refresh=cached_email=None
    try:
        con=sqlite_readonly(cursor_db_path())
        try:
            rows={key:value for key,value in con.execute(
                "SELECT key, value FROM ItemTable WHERE key IN (?,?,?)",
                ("cursorAuth/accessToken","cursorAuth/refreshToken","cursorAuth/cachedEmail"))}
        finally:
            con.close()
        access=unwrap_cursor_secret(rows.get("cursorAuth/accessToken"))
        refresh=unwrap_cursor_secret(rows.get("cursorAuth/refreshToken"))
        cached_email=rows.get("cursorAuth/cachedEmail")
    except Exception:
        access=None
    if not access or not is_jwt(access):
        json_access,json_refresh=read_cursor_auth_json()
        if json_access:
            access=json_access
            refresh=refresh or json_refresh
    if not access:return None,None,None,None
    _CURSOR_REFRESH=refresh
    return cursor_auth_from_token(access,cached_email)

def get_cursor():
    try:cookie,sub,token_email,token=cursor_session()
    except Exception:return {"status":"error","message":"Could not read the local Cursor session"}
    if not token:return {"status":"error","message":"Cursor is not signed in"}
    hdr={"User-Agent":"Mozilla/5.0"}
    if cookie:hdr["Cookie"]=f"WorkosCursorSessionToken={cookie}"
    api2=cursor_api2_headers(token)

    st,period,_=request_json(CURSOR_DASHBOARD+"/GetCurrentPeriodUsage",api2,"POST",{})
    if st in (401,403) and _CURSOR_REFRESH:
        token=refresh_cursor_oauth(_CURSOR_REFRESH)
        if token:
            cookie,sub,token_email,token=cursor_auth_from_token(token,token_email)
            hdr={"Cookie":f"WorkosCursorSessionToken={cookie}","User-Agent":"Mozilla/5.0"}
            api2=cursor_api2_headers(token)
            st,period,_=request_json(CURSOR_DASHBOARD+"/GetCurrentPeriodUsage",api2,"POST",{})
    result=None
    plan=period.get("planUsage") if st==200 and isinstance(period,dict) else None
    if isinstance(plan,dict) and (plan or period.get("billingCycleEnd")):
        result=cursor_plan_result(plan, period.get("billingCycleEnd"))
    if result is None:
        st,d,_=request_json(CURSOR_BASE+"/api/usage-summary",hdr)
        if st!=200 or not isinstance(d,dict):return {"status":"error","message":f"HTTP {st or 'ERR'}"}
        result=cursor_plan_result(((d.get("individualUsage") or {}).get("plan")) or {}, d.get("billingCycleEnd"))

    ist,identity,_=request_json(CURSOR_BASE+"/api/auth/me",{**hdr,"Accept":"application/json"})
    email=account_email(identity) if ist==200 else token_email
    if email:result["email"]=email
    elif sub:result["account_id"]=sub

    st_agg,aggregated,_=request_json(CURSOR_DASHBOARD+"/GetAggregatedUsageEvents",api2,"POST",{})
    models=models_from_aggregations(aggregated) if st_agg==200 else []
    if models:
        result["models"]=sort_cursor_models(models)
        result["model_source"]="aggregations"
        return finalize_cursor_result(result)

    if sub:
        from urllib.parse import quote
        st2,u,_=request_json(CURSOR_BASE+"/api/usage?user="+quote(sub,safe=""),hdr)
        if st2==200 and isinstance(u,dict):
            models=models_from_legacy_usage(u)
            if models:
                result["models"]=sort_cursor_models(models)
                result["model_source"]="request-counts"

    eh={**hdr,"Origin":"https://cursor.com","Content-Type":"application/json"}
    try:
        pages=0; events=[]
        for page in range(1,6):
            st3,payload,_=request_json(CURSOR_DASHBOARD+"/GetFilteredUsageEvents",api2,"POST",{"page":page,"pageSize":100})
            if st3!=200 or not isinstance(payload,dict):
                st3,payload,_=request_json(CURSOR_BASE+"/api/dashboard/get-filtered-usage-events",eh,"POST",
                                           {"teamId":0,"page":page,"pageSize":100})
            if st3!=200 or not isinstance(payload,dict):break
            batch=payload.get("usageEventsDisplay") or []
            if not batch:break
            pages+=1
            events.extend(batch)
            total=payload.get("totalUsageEventsCount")
            if isinstance(total,int) and page*100>=total:break
        models=models_from_events(events)
        if models:
            result["models"]=sort_cursor_models(models)
            result["model_source"]="events"
            result["events_pages"]=pages
    except Exception:
        pass
    return finalize_cursor_result(result)

class Bar(tk.Canvas):
    def __init__(self,parent,width=340,height=8):
        super().__init__(parent,width=width,height=height,highlightthickness=0,bg="#f4f4f4")
        self.w=width; self.h=height; self.value=None; self.color=None
        self.bind("<Configure>",lambda event:self._draw(event.width))
    def set(self,r):
        self.value=clamp(r)
        self.color=None
        self._draw()
    def set_fraction(self,value,color):
        self.value=clamp(value)
        self.color=color
        self._draw()
    def _draw(self,width=None):
        width=max(1,width or self.winfo_width() or self.w)
        self.delete("all"); self.create_rectangle(0,0,width,self.h,fill="#e5e7eb",outline="")
        if self.value is None:return
        col=self.color or ("#22c55e" if self.value>=30 else ("#f59e0b" if self.value>=10 else "#ef4444"))
        self.create_rectangle(0,0,width*self.value/100,self.h,fill=col,outline="")

class UsageWindowRow(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.columnconfigure(1,weight=1)
        self.label=ttk.Label(self,text="",font=("Segoe UI",10,"bold"))
        self.label.grid(row=0,column=0,sticky="w")
        self.badge=ttk.Label(self,text="—",font=("Segoe UI",11,"bold"))
        self.badge.grid(row=0,column=1,sticky="e")
        self.stats=ttk.Label(self,text="",foreground=SECONDARY_TEXT)
        self.stats.grid(row=1,column=0,columnspan=2,sticky="w",pady=(2,1))
        self.reset=ttk.Label(self,text="",foreground=SECONDARY_TEXT)
        self.reset.grid(row=2,column=0,columnspan=2,sticky="w",pady=(0,4))
        self.bar=Bar(self)
        self.bar.grid(row=3,column=0,columnspan=2,sticky="ew")

    def set(self,window):
        used=window.get("used_percent")
        remaining=remain(used)
        self.label.config(text=window.get("label") or "Limit")
        self.badge.config(text=f"{pt(remaining)} free" if remaining is not None else "—")
        extra=""
        if window.get("used_minor") is not None or window.get("limit_minor") is not None:
            exponent=window.get("exponent",2)
            extra=f" · {money_minor(window.get('used_minor'),exponent)}/{money_minor(window.get('limit_minor'),exponent)}"
        self.stats.config(text=f"{pt(used)} used · {pt(remaining)} remaining{extra}")
        self.reset.config(text=reset_text(window.get("resets_at")) or "Reset: not reported by provider")
        self.bar.set(remaining)
        return remaining


class UsageCard(ttk.Frame):
    def __init__(self,parent,name):
        super().__init__(parent,padding=(14,8))
        self.name=name
        self.title=ttk.Label(self,text=name,font=("Segoe UI",14,"bold"))
        self.title.pack(fill="x",anchor="w")
        self.body=ttk.Frame(self)
        self.body.pack(fill="x",pady=(5,0))

    def set_data(self,data):
        for child in self.body.winfo_children():
            child.destroy()
        windows=data.get("windows") or []
        if not windows and data.get("used") is not None:
            windows=[{"id":"legacy","label":data.get("label","Limit"),"used_percent":data.get("used"),"resets_at":data.get("reset")}]
        if not windows:
            ttk.Label(self.body,text=data.get("message","No data"),foreground=SECONDARY_TEXT).pack(fill="x")
            return None
        if data.get("stale"):
            ttk.Label(self.body,text=data.get("message") or "Saved status",
                      foreground=SECONDARY_TEXT).pack(fill="x",pady=(0,5))
        remaining=[]
        for index,window in enumerate(windows):
            if index:
                ttk.Separator(self.body,orient="horizontal").pack(fill="x",pady=(8,7))
            row=UsageWindowRow(self.body)
            row.pack(fill="x")
            value=row.set(window)
            if value is not None:
                remaining.append(value)
        return min(remaining) if remaining else None


class VerticalScrollFrame(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,highlightthickness=0,bg=parent.cget("bg"))
        self.scrollbar=ttk.Scrollbar(self,orient="vertical",command=self.canvas.yview)
        self.scrollbar_visible=False
        self.inner=ttk.Frame(self.canvas)
        self.window=self.canvas.create_window((0,0),window=self.inner,anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left",fill="both",expand=True)
        self.inner.bind("<Configure>",self._content_changed)
        self.canvas.bind("<Configure>",self._canvas_changed)
        self.canvas.bind("<Enter>",lambda _event:self.canvas.bind_all("<MouseWheel>",self._wheel))
        self.canvas.bind("<Leave>",lambda _event:self.canvas.unbind_all("<MouseWheel>"))

    def _content_changed(self,_event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after_idle(self._update_scrollbar)

    def _canvas_changed(self,event):
        self.canvas.itemconfigure(self.window,width=event.width)
        self.after_idle(self._update_scrollbar)

    def _update_scrollbar(self):
        bounds=self.canvas.bbox("all")
        needs_scroll=bool(bounds and bounds[3]-bounds[1]>self.canvas.winfo_height()+1)
        if needs_scroll and not self.scrollbar_visible:
            self.scrollbar.pack(side="right",fill="y")
            self.scrollbar_visible=True
        elif not needs_scroll and self.scrollbar_visible:
            self.scrollbar.pack_forget()
            self.scrollbar_visible=False

    def _wheel(self,event):
        if event.delta:
            step=int(-event.delta/120)
            self.canvas.yview_scroll(step if step else (-1 if event.delta>0 else 1),"units")

class ModelUsageRow(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.columnconfigure(0,weight=1)
        self.name=ttk.Label(self,text="",font=("Segoe UI",9,"bold"))
        self.name.grid(row=0,column=0,sticky="w")
        self.stats=ttk.Label(self,text="",foreground="#555")
        self.stats.grid(row=0,column=1,sticky="e")
        self.bar=Bar(self,width=330,height=7)
        self.bar.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(2,7))
    def set(self,name,share,requests,weighted,cost):
        self.name.config(text=name)
        bits=[f"{share:.1f}% share"]
        if weighted is not None: bits.append(f"Usage {weighted:.1f}")
        if requests is not None: bits.append(f"{int(requests)} Req.")
        if cost is not None and cost > 0: bits.append(f"${cost/100:.2f}")
        self.stats.config(text=" · ".join(bits))
        # Here the bar represents consumption share, so larger = more consumption.
        n=max(0,min(100,share))
        col="#22c55e" if n<30 else ("#f59e0b" if n<60 else "#ef4444")
        self.bar.set_fraction(n,col)

class CursorCard(ttk.Frame):
    def __init__(self,p,on_toggle):
        super().__init__(p,padding=(14,8))
        self.on_toggle=on_toggle
        self.table_expanded=False
        self.usage_expanded=False
        self.columnconfigure(0,weight=1)

        head=ttk.Frame(self); head.grid(row=0,column=0,sticky="ew"); head.columnconfigure(0,weight=1)
        ttk.Label(head,text="Cursor",font=("Segoe UI",14,"bold")).grid(row=0,column=0,sticky="w")
        buttons=ttk.Frame(head); buttons.grid(row=0,column=1,sticky="e")
        self.table_btn=ttk.Button(buttons,text="Model details ▾",command=self.flip_table)
        self.table_btn.pack(side="left",padx=(0,4))
        self.usage_btn=ttk.Button(buttons,text="Model usage ▾",command=self.flip_usage)
        self.usage_btn.pack(side="left")

        self.overall=ttk.Label(self,text="",foreground=SECONDARY_TEXT); self.overall.grid(row=1,column=0,sticky="w",pady=(3,6))
        self.cm_label=ttk.Label(self,text="Cursor Models · Monthly")
        self.cm_label.grid(row=2,column=0,sticky="w")
        self.cmstat=ttk.Label(self,text="",font=("Segoe UI",10,"bold")); self.cmstat.grid(row=3,column=0,sticky="e")
        self.cmb=Bar(self); self.cmb.grid(row=4,column=0,sticky="ew",pady=(2,6))
        self.om_label=ttk.Label(self,text="Other Models · Monthly")
        self.om_label.grid(row=5,column=0,sticky="w")
        self.omstat=ttk.Label(self,text="",font=("Segoe UI",10,"bold")); self.omstat.grid(row=6,column=0,sticky="e")
        self.omb=Bar(self); self.omb.grid(row=7,column=0,sticky="ew",pady=(2,6))
        self.reset=ttk.Label(self,text="",foreground=SECONDARY_TEXT); self.reset.grid(row=8,column=0,sticky="w")

        self.table_frame=ttk.Frame(self)
        self.tree=ttk.Treeview(self.table_frame,columns=("model","requests","weighted","cost"),show="headings",height=7)
        for key,title,width in [("model","Model",160),("requests","Requests",65),("weighted","Usage",65),("cost","Cost*",75)]:
            self.tree.heading(key,text=title)
            self.tree.column(key,width=width,anchor="w" if key=="model" else "e")
        sb=ttk.Scrollbar(self.table_frame,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self.table_note=ttk.Label(self,text="",foreground="#777",wraplength=420)

        self.usage_frame=ttk.Frame(self)
        self.usage_canvas=tk.Canvas(self.usage_frame,height=285,highlightthickness=0)
        self.usage_scroll=ttk.Scrollbar(self.usage_frame,orient="vertical",command=self.usage_canvas.yview)
        self.usage_inner=ttk.Frame(self.usage_canvas)
        self.usage_window=self.usage_canvas.create_window((0,0),window=self.usage_inner,anchor="nw")
        self.usage_canvas.configure(yscrollcommand=self.usage_scroll.set)
        self.usage_inner.bind("<Configure>",lambda e:self.usage_canvas.configure(scrollregion=self.usage_canvas.bbox("all")))
        self.usage_canvas.bind("<Configure>",lambda e:self.usage_canvas.itemconfigure(self.usage_window,width=e.width))
        self.usage_canvas.pack(side="left",fill="both",expand=True)
        self.usage_scroll.pack(side="right",fill="y")
        self.usage_note=ttk.Label(self,text="",foreground="#777",wraplength=420)

    def relayout(self):
        self.table_frame.grid_remove(); self.table_note.grid_remove()
        self.usage_frame.grid_remove(); self.usage_note.grid_remove()
        row=9
        if self.table_expanded:
            self.table_frame.grid(row=row,column=0,sticky="ew",pady=(8,2)); row+=1
            self.table_note.grid(row=row,column=0,sticky="w"); row+=1
        if self.usage_expanded:
            self.usage_frame.grid(row=row,column=0,sticky="ew",pady=(8,2)); row+=1
            self.usage_note.grid(row=row,column=0,sticky="w")
        self.on_toggle(self.table_expanded or self.usage_expanded)

    def flip_table(self):
        self.table_expanded=not self.table_expanded
        self.table_btn.config(text="Model details ▴" if self.table_expanded else "Model details ▾")
        self.relayout()

    def flip_usage(self):
        self.usage_expanded=not self.usage_expanded
        self.usage_btn.config(text="Model usage ▴" if self.usage_expanded else "Model usage ▾")
        self.relayout()

    def set(self,d):
        cmu=d.get("cursor_models_used"); omu=d.get("other_models_used"); tot=d.get("total_used")
        cmr=remain(cmu); omr=remain(omu)
        if cmu is None:
            self.cm_label.grid_remove(); self.cmstat.grid_remove(); self.cmb.grid_remove()
        else:
            self.cm_label.grid(); self.cmstat.grid(); self.cmb.grid()
            self.cmstat.config(text=f"{pt(cmu)} used · {pt(cmr)} free"); self.cmb.set(cmr)
        if omu is None:
            self.om_label.grid_remove(); self.omstat.grid_remove(); self.omb.grid_remove()
        else:
            self.om_label.grid(); self.omstat.grid(); self.omb.grid()
            self.omstat.config(text=f"{pt(omu)} used · {pt(omr)} free"); self.omb.set(omr)
        pool_count=sum(value is not None for value in (cmu,omu))
        if tot is not None:
            overall=f"Monthly included usage · {pt(tot)} used · {pt(remain(tot))} remaining"
        elif pool_count==2:
            overall="Two monthly included pools · unused usage does not roll over"
        elif pool_count==1:
            overall="Monthly included pool · unused usage does not roll over"
        else:
            overall="No monthly pool reported"
        self.overall.config(text=overall)
        cycle=reset_text(d.get("reset"))
        self.reset.config(text=cycle or ("Resets with the Cursor billing cycle" if pool_count else "Reset: not reported"))

        models=d.get("models") or []
        for i in self.tree.get_children(): self.tree.delete(i)
        for m in models:
            req=m.get("requests") or 0
            w=m.get("weighted")
            cc=m.get("charged_cents"); tc=m.get("token_cents")
            cost=cc if cc not in (None,0) else tc
            self.tree.insert("","end",values=(
                m.get("model","Unknown"),
                int(req) if isinstance(req,(int,float)) and float(req).is_integer() else req,
                f"{w:.1f}" if isinstance(w,(int,float)) else "—",
                f"${cost/100:.2f}" if isinstance(cost,(int,float)) and cost>0 else "—"))

        if d.get("model_source")=="aggregations":
            self.table_note.config(text="* Current billing-cycle totals from Cursor. Cost is the billed share in cents converted to dollars.")
        elif d.get("model_source")=="events":
            self.table_note.config(text=f"* latest {d.get('events_pages',0)*100} usage events (max. 500); usage = weighted Cursor billing units.")
        elif d.get("model_source")=="request-counts":
            self.table_note.config(text="* Request counts for the current billing period.")
        else:
            self.table_note.config(text="No model breakdown available.")

        for child in self.usage_inner.winfo_children(): child.destroy()
        if models:
            weighted_total=sum((m.get("weighted") or 0) for m in models)
            use_weighted=weighted_total>0
            total=weighted_total if use_weighted else sum((m.get("requests") or 0) for m in models)
            ranked=[]
            for m in models:
                basis=(m.get("weighted") or 0) if use_weighted else (m.get("requests") or 0)
                share=(basis/total*100) if total else 0
                ranked.append((share,m))
            ranked.sort(key=lambda x:x[0],reverse=True)
            for share,m in ranked:
                cc=m.get("charged_cents"); tc=m.get("token_cents")
                cost=cc if cc not in (None,0) else tc
                row=ModelUsageRow(self.usage_inner); row.pack(fill="x")
                row.set(m.get("model","Unknown"),share,m.get("requests"),m.get("weighted"),cost)
            basis_name="weighted usage" if use_weighted else "requests"
            self.usage_note.config(text=f"Share of each model in the captured Cursor usage, calculated from {basis_name}. These percentages are not separate monthly limits.")
        else:
            ttk.Label(self.usage_inner,text="No model data available.",foreground="#777").pack(anchor="w")
            self.usage_note.config(text="")

        vals=[v for v in (cmr,omr) if v is not None]
        return min(vals) if vals else None

class AccountsPanel(ttk.Frame):
    def __init__(self,parent,on_toggle):
        super().__init__(parent)
        self.on_toggle=on_toggle; self.expanded=False; self.data={}
        self.toggle_button=ttk.Button(self,text="Accounts ▾",command=self.toggle)
        self.toggle_button.pack(anchor="w")
        self.body=ttk.Frame(self)
        self.rows={}
        for key,title in (("claude","Claude"),("codex","ChatGPT"),("cursor","Cursor")):
            row=ttk.Frame(self.body); row.pack(fill="x",pady=1)
            ttk.Label(row,text=title,width=10).pack(side="left")
            value=ttk.Label(row,text="—",foreground=SECONDARY_TEXT,wraplength=330)
            value.pack(side="left",fill="x",expand=True); self.rows[key]=value
    def toggle(self):
        self.expanded=not self.expanded
        self.toggle_button.config(text="Accounts ▴" if self.expanded else "Accounts ▾")
        if self.expanded:self.body.pack(fill="x",pady=(3,0))
        else:self.body.pack_forget()
        self.on_toggle(self.expanded)
    def set_data(self,data):
        self.data=data
        for key,label in self.rows.items():label.config(text=account_display(data.get(key) or {}))

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title(APP_NAME); self.root.geometry(f"{APP_WIDTH}x470"); self.root.resizable(False,False)
        self.root.attributes("-topmost",False)
        self.root.protocol("WM_DELETE_WINDOW",self.quit if sys.platform=="darwin" else self.hide)
        self.stop=False; self.tray=None; self.data={}; self.widget_server=WidgetDataServer(self.widget_snapshot)
        self.scroller=VerticalScrollFrame(self.root); self.scroller.pack(fill="both",expand=True)
        self.outer=ttk.Frame(self.scroller.inner,padding=14); self.outer.pack(fill="both",expand=True)
        self.claude=UsageCard(self.outer,"Claude"); self.claude.pack(fill="x",pady=(0,3))
        self.codex=UsageCard(self.outer,"ChatGPT"); self.codex.pack(fill="x",pady=3)
        self.cursor=CursorCard(self.outer,self.resize_for_details); self.cursor.pack(fill="x",pady=3)
        self.accounts=AccountsPanel(self.outer,self.resize_for_details); self.accounts.pack(fill="x",pady=(5,0))
        self.note=ttk.Label(self.outer,text="",foreground=SECONDARY_TEXT,wraplength=APP_WIDTH-40)
        self.setup_tray(); self.place_bottom_right(); self.root.deiconify(); threading.Thread(target=self.loop,daemon=True).start()
    def resize_for_details(self,expanded):
        self.root.after(10,self.resize_for_usage)
    def place_bottom_right(self):
        self.root.update_idletasks(); w=self.root.winfo_width(); h=self.root.winfo_height()
        sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{max(12,sw-w-16)}+{max(12,sh-h-72)}")
    def setup_tray(self):
        if sys.platform=="darwin":
            # macOS uses the Dock app and WidgetKit extension; avoid crowding the menu bar.
            self.tray=None
            return
        if not pystray:self.root.deiconify();self.place_bottom_right();return
        img=Image.new("RGBA",(64,64),(20,22,28,255))
        d=ImageDraw.Draw(img)
        d.rounded_rectangle((3,3,61,61),12,fill=(20,22,28,255),outline=(255,255,255,255),width=3)
        # Large, high-contrast AI letters that remain legible in a tray or menu bar.
        try:
            from PIL import ImageFont
            font=ImageFont.truetype("arialbd.ttf",28)
        except Exception:
            font=None
        text="AI"
        box=d.textbbox((0,0),text,font=font)
        tw,th=box[2]-box[0],box[3]-box[1]
        d.text(((64-tw)/2,(64-th)/2-2),text,fill=(255,255,255,255),font=font)
        menu=pystray.Menu(pystray.MenuItem("Show / Hide",self.toggle,default=True),pystray.MenuItem("Refresh now",self.refresh),
                         pystray.MenuItem("Always on top",self.topmost,checked=lambda i:bool(self.root.attributes("-topmost"))),pystray.Menu.SEPARATOR,pystray.MenuItem("Quit",self.quit))
        self.tray=pystray.Icon("ai_usage_v9",img,"AI Usage",menu)
        threading.Thread(target=self.tray.run,daemon=True).start()
    def toggle(self,*_):self.root.after(0,self._toggle)
    def _toggle(self):
        if self.root.state() in ("withdrawn","iconic"):
            self.place_bottom_right();self.root.deiconify();self.root.lift();self.root.focus_force()
        elif sys.platform=="darwin":self.root.iconify()
        else:self.root.withdraw()
    def hide(self):self.root.withdraw()
    def topmost(self,*_):self.root.after(0,lambda:self.root.attributes("-topmost",not bool(self.root.attributes("-topmost"))))
    def refresh(self,*_):threading.Thread(target=self.poll,daemon=True).start()
    def widget_snapshot(self):
        claude=self.data.get("claude") or {}
        codex=self.data.get("codex") or {}
        cursor=self.data.get("cursor") or {}
        def public_reset(value):
            # Provider APIs use both ISO-8601 strings and Unix timestamps. Keep
            # the WidgetKit wire format stable so one numeric reset cannot make
            # Swift discard the complete snapshot.
            return None if value is None else str(value)
        cursor_remaining=[remain(cursor.get(key)) for key in ("cursor_models_used","other_models_used")]
        cursor_remaining=[value for value in cursor_remaining if value is not None]
        cursor_windows=[]
        for window_id,label,key in (
            ("cursor-models","Cursor Models · Monthly","cursor_models_used"),
            ("cursor-other-models","Other Models · Monthly","other_models_used"),
        ):
            if cursor.get(key) is not None:
                cursor_windows.append({"id":window_id,"label":label,"usedPercent":clamp(cursor.get(key)),"resetsAt":public_reset(cursor.get("reset")),"type":"monthly"})
        def public_windows(data):
            return [{
                "id":window.get("id","limit"),
                "label":window.get("label","Limit"),
                "usedPercent":clamp(window.get("used_percent")),
                "resetsAt":public_reset(window.get("resets_at")),
                "type":window.get("type","other"),
            } for window in data.get("windows") or [] if clamp(window.get("used_percent")) is not None]
        return {
            "updated":datetime.now(timezone.utc).isoformat(),
            "claudeRemaining":remain(claude.get("used")),
            "codexRemaining":remain(codex.get("used")),
            "cursorRemaining":min(cursor_remaining) if cursor_remaining else None,
            "providers":[
                {"id":"claude","title":"Claude · saved" if claude.get("stale") else "Claude","windows":public_windows(claude)},
                {"id":"chatgpt","title":"ChatGPT","windows":public_windows(codex)},
                {"id":"cursor","title":"Cursor","windows":cursor_windows},
            ],
        }
    def quit(self,*_):
        self.stop=True
        self.widget_server.stop()
        if self.tray:self.tray.stop()
        self.root.after(0,self.root.destroy)
    def loop(self):
        self.poll()
        while not self.stop:
            for _ in range(REFRESH_SECONDS):
                if self.stop:return
                time.sleep(1)
            self.poll()
    def poll(self):
        self.data={"claude":get_claude(),"codex":get_codex(),"cursor":get_cursor()}; self.root.after(0,self.render)
    def render(self):
        c,x,u=self.data["claude"],self.data["codex"],self.data["cursor"]; notes=[]
        cr=self.claude.set_data(c)
        xr=self.codex.set_data(x)
        ur=self.cursor.set(u) if u.get("status")=="ok" else None
        if u.get("status")!="ok":notes.append("Cursor: "+u.get("message","No data"))
        self.accounts.set_data(self.data)
        note_text=" · ".join(notes)
        self.note.config(text=note_text)
        if note_text and not self.note.winfo_manager():self.note.pack(fill="x",pady=(4,0))
        elif not note_text:self.note.pack_forget()
        self.root.after_idle(self.resize_for_usage)
        if self.tray:self.tray.title=f"Claude {pt(cr)} free · ChatGPT {pt(xr)} free · Cursor tightest pool {pt(ur)} free"
    def resize_for_usage(self):
        self.root.update_idletasks()
        expanded=self.cursor.table_expanded or self.cursor.usage_expanded
        requested=self.outer.winfo_reqheight()+4
        limit=max(360,self.root.winfo_screenheight()-100)
        height=min(limit,max(560 if expanded else 360,requested))
        self.root.geometry(f"{APP_WIDTH}x{height}")
        self.place_bottom_right()
    def run(self):self.root.mainloop()

if __name__=="__main__":App().run()
