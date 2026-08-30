
import json, os, sys, time, threading, urllib.request, urllib.error, base64, sqlite3
from pathlib import Path
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk

try:
    from usage_windows import normalize_claude_usage, normalize_codex_usage
except ImportError:
    from src.usage_windows import normalize_claude_usage, normalize_codex_usage

APP_NAME="AI Usage Widget"
APP_VERSION="1.2.0"
CLAUDE_URL="https://api.anthropic.com/api/oauth/usage"
CODEX_URL="https://chatgpt.com/backend-api/wham/usage"
CURSOR_BASE="https://cursor.com"
REFRESH_SECONDS=300

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray=None
    Image=ImageDraw=None

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
    try:return datetime.fromisoformat(v.replace("Z","+00:00")) if isinstance(v,str) else datetime.fromtimestamp(float(v),tz=timezone.utc)
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

def request_json(url,headers=None,method="GET",body=None,timeout=15):
    data=None
    if body is not None:data=json.dumps(body).encode("utf-8")
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode("utf-8")
            return r.status,json.loads(raw) if raw else {},None
    except urllib.error.HTTPError as e:
        try:err=e.read().decode("utf-8","replace")
        except Exception:err=str(e)
        return e.code,None,err
    except Exception as e:return None,None,str(e)

def get_claude():
    cred=Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home()/".claude"))/".credentials.json"
    try:
        c=json.loads(cred.read_text(encoding="utf-8")); token=(c.get("claudeAiOauth") or {}).get("accessToken")
    except Exception:return {"status":"error","message":"Nicht angemeldet"}
    if not token:return {"status":"error","message":"OAuth-Token fehlt"}
    st,d,_=request_json(CLAUDE_URL,{
        "Authorization":f"Bearer {token}","anthropic-beta":"oauth-2025-04-20",
        "User-Agent":"claude-code/2.1.207","Content-Type":"application/json"})
    if st!=200 or not isinstance(d,dict):return {"status":"error","message":f"HTTP {st or 'ERR'}"}
    return normalize_claude_usage(d)

def get_codex():
    p=Path(os.environ.get("CODEX_HOME") or (Path.home()/".codex"))/"auth.json"
    try:
        a=json.loads(p.read_text(encoding="utf-8")); t=a.get("tokens") or {}
        token=t.get("access_token"); aid=t.get("account_id"); iid=t.get("id_token")
    except Exception:return {"status":"error","message":"Nicht angemeldet"}
    if not token:return {"status":"error","message":"Access-Token fehlt"}
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
    appdata=env.get("APPDATA")
    base=Path(appdata) if appdata else home/"AppData"/"Roaming"
    return base/"Cursor"/"User"/"globalStorage"/"state.vscdb"

def cursor_session():
    db=cursor_db_path()
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=2)
    row=con.execute("SELECT value FROM ItemTable WHERE key=?",("cursorAuth/accessToken",)).fetchone()
    con.close()
    if not row:return None,None
    token=row[0]
    payload=jwt_payload(token)
    sub=payload.get("sub","")
    uid=sub.rsplit("|",1)[-1]
    cookie=f"{uid}%3A%3A{token}"
    return cookie,sub

def get_cursor():
    try:cookie,sub=cursor_session()
    except Exception as e:return {"status":"error","message":str(e)}
    if not cookie:return {"status":"error","message":"Kein Cursor-Login"}
    hdr={"Cookie":f"WorkosCursorSessionToken={cookie}","User-Agent":"Mozilla/5.0"}
    st,d,_=request_json(CURSOR_BASE+"/api/usage-summary",hdr)
    if st!=200 or not isinstance(d,dict):return {"status":"error","message":f"HTTP {st or 'ERR'}"}
    plan=((d.get("individualUsage") or {}).get("plan")) or {}
    result={"status":"ok","cursor_models_used":plan.get("autoPercentUsed"),"other_models_used":plan.get("apiPercentUsed"),
            "total_used":plan.get("totalPercentUsed"),"reset":d.get("billingCycleEnd"),"models":[],"model_source":None}

    # 1) Reliable per-model request counts for current billing cycle.
    # /api/usage?user=<sub> is observed in the Cursor dashboard.
    if sub:
        from urllib.parse import quote
        st2,u,_=request_json(CURSOR_BASE+"/api/usage?user="+quote(sub,safe=""),hdr)
        if st2==200 and isinstance(u,dict):
            models=[]
            for name,val in u.items():
                if name in ("startOfMonth","globalRequests") or not isinstance(val,dict):continue
                nr=val.get("numRequests")
                if isinstance(nr,(int,float)) and nr>0:
                    models.append({"model":name,"requests":nr,"weighted":None,"charged_cents":None,"token_cents":None})
            if models:
                result["models"]=models
                result["model_source"]="request-counts"

    # 2) Rich event stream: weighted usage + charged/token cents.
    # Personal accounts use teamId=0, no userId. This is undocumented, so cleanly fall back above.
    eh={**hdr,"Origin":"https://cursor.com","Content-Type":"application/json"}
    agg={}
    pages=0
    try:
        for page in range(1,6):  # bounded: max 500 recent events
            st3,e,_=request_json(CURSOR_BASE+"/api/dashboard/get-filtered-usage-events",eh,"POST",
                                 {"teamId":0,"page":page,"pageSize":100})
            if st3!=200 or not isinstance(e,dict):break
            events=e.get("usageEventsDisplay") or []
            if not events:break
            pages+=1
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
            total=e.get("totalUsageEventsCount")
            if isinstance(total,int) and page*100>=total:break
        if agg:
            result["models"]=list(agg.values())
            result["model_source"]="events"
            result["events_pages"]=pages
    except Exception:
        pass

    # Sort by best available "consumption" measure.
    def score(x):
        return (x.get("weighted") or 0, x.get("charged_cents") or 0, x.get("requests") or 0)
    result["models"].sort(key=score,reverse=True)
    return result

class Bar(tk.Canvas):
    def __init__(self,parent,width=340,height=8):
        super().__init__(parent,width=width,height=height,highlightthickness=0,bg="#f4f4f4"); self.w=width; self.h=height
    def set(self,r):
        self.delete("all"); self.create_rectangle(0,0,self.w,self.h,fill="#e5e7eb",outline="")
        n=clamp(r)
        if n is None:return
        col="#22c55e" if n>=30 else ("#f59e0b" if n>=10 else "#ef4444")
        self.create_rectangle(0,0,self.w*n/100,self.h,fill=col,outline="")

class UsageWindowRow(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.columnconfigure(1,weight=1)
        self.label=ttk.Label(self,text="",font=("Segoe UI",10,"bold"))
        self.label.grid(row=0,column=0,sticky="w")
        self.badge=ttk.Label(self,text="—",font=("Segoe UI",10,"bold"))
        self.badge.grid(row=0,column=1,sticky="e")
        self.stats=ttk.Label(self,text="",foreground="#555")
        self.stats.grid(row=1,column=0,columnspan=2,sticky="w",pady=(2,1))
        self.reset=ttk.Label(self,text="",foreground="#666")
        self.reset.grid(row=2,column=0,columnspan=2,sticky="w",pady=(0,4))
        self.bar=Bar(self)
        self.bar.grid(row=3,column=0,columnspan=2,sticky="ew")

    def set(self,window):
        used=window.get("used_percent")
        remaining=remain(used)
        self.label.config(text=window.get("label") or "Limit")
        self.badge.config(text=f"{pt(remaining)} frei" if remaining is not None else "—")
        extra=""
        if window.get("used_minor") is not None or window.get("limit_minor") is not None:
            exponent=window.get("exponent",2)
            extra=f" · {money_minor(window.get('used_minor'),exponent)}/{money_minor(window.get('limit_minor'),exponent)}"
        self.stats.config(text=f"{pt(used)} verbraucht · {pt(remaining)} verbleibend{extra}")
        self.reset.config(text=reset_text(window.get("resets_at")) or "Reset: vom Anbieter nicht gemeldet")
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
            ttk.Label(self.body,text=data.get("message","Keine Daten"),foreground="#666").pack(fill="x")
            return None
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
        self.inner=ttk.Frame(self.canvas)
        self.window=self.canvas.create_window((0,0),window=self.inner,anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left",fill="both",expand=True)
        self.scrollbar.pack(side="right",fill="y")
        self.inner.bind("<Configure>",self._content_changed)
        self.canvas.bind("<Configure>",lambda event:self.canvas.itemconfigure(self.window,width=event.width))
        self.canvas.bind("<Enter>",lambda _event:self.canvas.bind_all("<MouseWheel>",self._wheel))
        self.canvas.bind("<Leave>",lambda _event:self.canvas.unbind_all("<MouseWheel>"))

    def _content_changed(self,_event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

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
        bits=[f"{share:.1f}% Anteil"]
        if weighted is not None: bits.append(f"Usage {weighted:.1f}")
        if requests is not None: bits.append(f"{int(requests)} Req.")
        if cost is not None and cost > 0: bits.append(f"${cost/100:.2f}")
        self.stats.config(text=" · ".join(bits))
        # Here the bar represents consumption share, so larger = more consumption.
        self.bar.delete("all")
        self.bar.create_rectangle(0,0,self.bar.w,self.bar.h,fill="#e5e7eb",outline="")
        n=max(0,min(100,share))
        col="#22c55e" if n<30 else ("#f59e0b" if n<60 else "#ef4444")
        self.bar.create_rectangle(0,0,self.bar.w*n/100,self.bar.h,fill=col,outline="")

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
        self.table_btn=ttk.Button(buttons,text="Modelldetails ▾",command=self.flip_table)
        self.table_btn.pack(side="left",padx=(0,4))
        self.usage_btn=ttk.Button(buttons,text="Modellverbrauch ▾",command=self.flip_usage)
        self.usage_btn.pack(side="left")

        self.overall=ttk.Label(self,text="",foreground="#555"); self.overall.grid(row=1,column=0,sticky="w",pady=(3,6))
        ttk.Label(self,text="Cursor Models").grid(row=2,column=0,sticky="w")
        self.cmstat=ttk.Label(self,text="",font=("Segoe UI",9,"bold")); self.cmstat.grid(row=3,column=0,sticky="e")
        self.cmb=Bar(self); self.cmb.grid(row=4,column=0,sticky="ew",pady=(2,6))
        ttk.Label(self,text="Other Models").grid(row=5,column=0,sticky="w")
        self.omstat=ttk.Label(self,text="",font=("Segoe UI",9,"bold")); self.omstat.grid(row=6,column=0,sticky="e")
        self.omb=Bar(self); self.omb.grid(row=7,column=0,sticky="ew",pady=(2,6))
        self.reset=ttk.Label(self,text="",foreground="#666"); self.reset.grid(row=8,column=0,sticky="w")

        self.table_frame=ttk.Frame(self)
        self.tree=ttk.Treeview(self.table_frame,columns=("model","requests","weighted","cost"),show="headings",height=7)
        for key,title,width in [("model","Modell",160),("requests","Requests",65),("weighted","Usage",65),("cost","Kosten*",75)]:
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
        self.table_btn.config(text="Modelldetails ▴" if self.table_expanded else "Modelldetails ▾")
        self.relayout()

    def flip_usage(self):
        self.usage_expanded=not self.usage_expanded
        self.usage_btn.config(text="Modellverbrauch ▴" if self.usage_expanded else "Modellverbrauch ▾")
        self.relayout()

    def set(self,d):
        cmu=d.get("cursor_models_used"); omu=d.get("other_models_used"); tot=d.get("total_used")
        cmr=remain(cmu); omr=remain(omu)
        self.cmstat.config(text=f"{pt(cmu)} verbraucht · {pt(cmr)} frei"); self.cmb.set(cmr)
        self.omstat.config(text=f"{pt(omu)} verbraucht · {pt(omr)} frei"); self.omb.set(omr)
        self.overall.config(text=f"Gesamtindikator: {pt(tot)} verbraucht · {pt(remain(tot))} verbleibend" if tot is not None else "Zwei getrennte Nutzungspools")
        self.reset.config(text=reset_text(d.get("reset")) or "Reset: nicht gemeldet")

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

        if d.get("model_source")=="events":
            self.table_note.config(text=f"* letzte {d.get('events_pages',0)*100} Usage-Events (max. 500); Usage = gewichtete Cursor-Billing-Units.")
        elif d.get("model_source")=="request-counts":
            self.table_note.config(text="* Request-Anzahlen für den aktuellen Abrechnungszeitraum.")
        else:
            self.table_note.config(text="Keine Modellaufschlüsselung verfügbar.")

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
            basis_name="gewichteter Usage" if use_weighted else "Requests"
            self.usage_note.config(text=f"Anteil jedes Modells am erfassten Cursor-Verbrauch, berechnet aus {basis_name}. Die Prozentwerte sind keine separaten Monatslimits.")
        else:
            ttk.Label(self.usage_inner,text="Keine Modelldaten verfügbar.",foreground="#777").pack(anchor="w")
            self.usage_note.config(text="")

        vals=[v for v in (cmr,omr) if v is not None]
        return min(vals) if vals else None

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title(APP_NAME); self.root.geometry("470x500"); self.root.resizable(False,False)
        self.root.attributes("-topmost",False); self.root.protocol("WM_DELETE_WINDOW",self.hide); self.root.withdraw()
        self.stop=False; self.tray=None; self.data={}
        self.scroller=VerticalScrollFrame(self.root); self.scroller.pack(fill="both",expand=True)
        self.outer=ttk.Frame(self.scroller.inner,padding=14); self.outer.pack(fill="both",expand=True)
        top=ttk.Frame(self.outer); top.pack(fill="x")
        ttk.Label(top,text="AI Usage",font=("Segoe UI",15,"bold")).pack(side="left")
        self.updated=ttk.Label(top,text="",foreground="#777"); self.updated.pack(side="right")
        self.claude=UsageCard(self.outer,"Claude"); self.claude.pack(fill="x",pady=(8,3))
        self.codex=UsageCard(self.outer,"ChatGPT / Codex"); self.codex.pack(fill="x",pady=3)
        self.cursor=CursorCard(self.outer,self.resize_for_details); self.cursor.pack(fill="x",pady=3)
        self.note=ttk.Label(self.outer,text="",foreground="#777",wraplength=430); self.note.pack(fill="x",pady=(4,0))
        self.setup_tray(); threading.Thread(target=self.loop,daemon=True).start()
    def resize_for_details(self,expanded):
        self.root.after(10,self.resize_for_usage)
    def place_bottom_right(self):
        self.root.update_idletasks(); w=self.root.winfo_width(); h=self.root.winfo_height()
        sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{max(12,sw-w-16)}+{max(12,sh-h-72)}")
    def setup_tray(self):
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
        menu=pystray.Menu(pystray.MenuItem("Anzeigen / Ausblenden",self.toggle,default=True),pystray.MenuItem("Jetzt aktualisieren",self.refresh),
                         pystray.MenuItem("Always on top",self.topmost,checked=lambda i:bool(self.root.attributes("-topmost"))),pystray.Menu.SEPARATOR,pystray.MenuItem("Beenden",self.quit))
        self.tray=pystray.Icon("ai_usage_v9",img,"AI Usage",menu)
        if sys.platform=="darwin":
            # The native macOS backend must be attached from the main thread.
            self.tray.run_detached()
        else:
            threading.Thread(target=self.tray.run,daemon=True).start()
    def toggle(self,*_):self.root.after(0,self._toggle)
    def _toggle(self):
        if self.root.state()=="withdrawn":self.place_bottom_right();self.root.deiconify();self.root.lift()
        else:self.root.withdraw()
    def hide(self):self.root.withdraw()
    def topmost(self,*_):self.root.after(0,lambda:self.root.attributes("-topmost",not bool(self.root.attributes("-topmost"))))
    def refresh(self,*_):threading.Thread(target=self.poll,daemon=True).start()
    def quit(self,*_):
        self.stop=True
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
        if x.get("email"):notes.append(f"ChatGPT/Codex-Konto: {x['email']}")
        ur=self.cursor.set(u) if u.get("status")=="ok" else None
        if u.get("status")!="ok":notes.append("Cursor: "+u.get("message","Keine Daten"))
        self.note.config(text=" · ".join(notes)); self.updated.config(text=datetime.now().strftime("%H:%M"))
        self.root.after_idle(self.resize_for_usage)
        if self.tray:self.tray.title=f"Claude {pt(cr)} frei · ChatGPT/Codex {pt(xr)} frei · Cursor knappster Pool {pt(ur)} frei"
    def resize_for_usage(self):
        self.root.update_idletasks()
        expanded=self.cursor.table_expanded or self.cursor.usage_expanded
        requested=self.outer.winfo_reqheight()+28
        limit=max(500,self.root.winfo_screenheight()-100)
        height=min(limit,max(760 if expanded else 500,requested))
        self.root.geometry(f"470x{height}")
        self.place_bottom_right()
    def run(self):self.root.mainloop()

if __name__=="__main__":App().run()
