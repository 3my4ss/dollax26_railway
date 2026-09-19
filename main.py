import os, secrets, ipaddress, json, logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import db
from pages import dashboard_html, login_html
from protocol import new_uuid, vless_link, relay_vless, parse_vless_header

log = logging.getLogger("dollax")

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY is not set - using a random per-process key. "
                "Every restart/redeploy will invalidate all sessions. Set SECRET_KEY in your environment.")

app = FastAPI(title="Dollax Panel", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup():
    db.init_db()
    if os.getenv("ADMIN_PASSWORD", "admin") == "admin":
        log.warning("ADMIN_PASSWORD is left at the default value 'admin'. Change it in your environment and redeploy.")

def authed(request): return bool(request.session.get("user"))
def guard(request): return None if authed(request) else RedirectResponse("/login", status_code=303)
def as_int(v, default=0, lo=0, hi=None):
    try: n=int(v)
    except Exception: n=default
    n=max(lo,n)
    return min(n,hi) if hi is not None else n
def as_float(v, default=0, lo=0):
    try: n=float(v)
    except Exception: n=default
    return max(lo,n)
def expiry(days):
    days=as_int(days)
    return (datetime.now(timezone.utc)+timedelta(days=days)).isoformat() if days else ""
def effective_host(request):
    base=db.setting("public_base_url","").strip().rstrip("/")
    if base:
        return urlparse(base).hostname or base
    return (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(":")[0]
def inbound_dict(r):
    d=dict(r); d["enabled"]=bool(d["enabled"]); return d
def client_dict(r, request):
    d=dict(r); d["enabled"]=bool(d["enabled"]); d["clean_ips"]=db.json_list(d.get("clean_ips"));
    ib=None
    with db.conn() as c: ib=c.execute("SELECT * FROM inbounds WHERE id=?",(d["inbound_id"],)).fetchone()
    if not ib: return d
    address=d["clean_ips"][0] if d["clean_ips"] else (ib["address"] or effective_host(request))
    d["link"]=vless_link(d["uuid"],address,ib["port"],ib["path"],ib["host_header"] or effective_host(request),ib["sni"] or effective_host(request),d["name"])
    d["links"]=[vless_link(d["uuid"],ip,ib["port"],ib["path"],ib["host_header"] or effective_host(request),ib["sni"] or effective_host(request),f"{d['name']} {i+1}") for i,ip in enumerate(d["clean_ips"])]
    if not d["links"]: d["links"]=[d["link"]]
    d["inbound_name"]=ib["name"]
    return d

@app.get("/health")
async def health(): return {"ok":True,"service":"dollax-panel"}
@app.get("/login", response_class=HTMLResponse)
async def login(): return login_html()
@app.post("/login")
async def do_login(request: Request):
    form=await request.form(); username=str(form.get("username","")).strip(); password=str(form.get("password","") )
    with db.conn() as c: row=c.execute("SELECT * FROM admins WHERE username=?",(username,)).fetchone()
    if not row or not db.verify_password(password,row["password_hash"]):
        return HTMLResponse(login_html("Invalid credentials"),status_code=401)
    request.session["user"]=username; return RedirectResponse("/",status_code=303)
@app.post("/logout")
async def logout(request: Request): request.session.clear(); return RedirectResponse("/login",status_code=303)
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    r=guard(request)
    return r or dashboard_html(db.setting("panel_name","Dollax Panel"))

@app.get("/api/summary")
async def summary(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c:
        ib=c.execute("SELECT COUNT(*) n FROM inbounds").fetchone()["n"]
        cl=c.execute("SELECT COUNT(*) n FROM clients").fetchone()["n"]
        active=c.execute("SELECT COUNT(*) n FROM clients WHERE enabled=1").fetchone()["n"]
    return {"inbounds":ib,"clients":cl,"active_clients":active,"transport":"WSS","tcp_proxy":False}

@app.get("/api/inbounds")
async def list_inbounds(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c: rows=c.execute("SELECT * FROM inbounds ORDER BY created DESC").fetchall()
    return [inbound_dict(x) for x in rows]

@app.post("/api/inbounds")
async def create_inbound(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    d=await request.json(); name=str(d.get("name") or "VLESS WS").strip()[:80]
    protocol=str(d.get("protocol") or "vless").lower(); network=str(d.get("network") or "ws").lower(); security=str(d.get("security") or "tls").lower()
    if (protocol,network,security)!=("vless","ws","tls"):
        return JSONResponse({"error":"This Railway build exposes VLESS + WebSocket + TLS/WSS only. Choose VLESS / WebSocket / TLS."},status_code=400)
    path=str(d.get("path") or "").strip() or "/ws/"+secrets.token_urlsafe(10).replace("-","_")
    if not path.startswith("/"): path="/"+path
    if len(path)>180 or "?" in path or "#" in path or " " in path: return JSONResponse({"error":"Invalid WebSocket path."},status_code=400)
    address=str(d.get("address") or "").strip()[:253]; port=as_int(d.get("port",443),443,1,65535)
    host=str(d.get("host_header") or "").strip()[:253]; sni=str(d.get("sni") or "").strip()[:253]
    if not host: host=effective_host(request)
    if not sni: sni=host
    limit_gb=as_float(d.get("limit_gb"),0); limit_bytes=int(limit_gb*1024**3)
    clients=as_int(d.get("client_limit"),0,0,10000); ip_limit=as_int(d.get("ip_limit"),0,0,1000); conn=as_int(d.get("connection_limit"),0,0,100000)
    days=as_int(d.get("expires_days"),0,0,3650)
    iid=secrets.token_hex(12)
    try:
        with db.conn() as c:
            c.execute("""INSERT INTO inbounds(id,name,protocol,network,security,address,port,path,host_header,sni,alpn,fingerprint,limit_bytes,expires_at,ip_limit,connection_limit,client_limit,note,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (iid,name,protocol,network,security,address,port,path,host,sni,str(d.get("alpn") or "http/1.1")[:100],str(d.get("fingerprint") or "chrome")[:40],limit_bytes,expiry(days),ip_limit,conn,clients,str(d.get("note") or "")[:500],db.now()))
            c.commit()
    except Exception: return JSONResponse({"error":"Path already exists."},status_code=409)
    return {"ok":True,"id":iid}

@app.patch("/api/inbounds/{iid}")
async def update_inbound(request: Request,iid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    d=await request.json()
    with db.conn() as c:
        row=c.execute("SELECT * FROM inbounds WHERE id=?",(iid,)).fetchone()
        if not row: return JSONResponse({"error":"Inbound not found"},status_code=404)
        vals={
          "name":str(d.get("name",row["name"])).strip()[:80] or row["name"],
          "path":str(d.get("path",row["path"])).strip() or row["path"],
          "address":str(d.get("address",row["address"])).strip()[:253],
          "port":as_int(d.get("port",row["port"]),row["port"],1,65535),
          "host_header":str(d.get("host_header",row["host_header"])).strip()[:253],
          "sni":str(d.get("sni",row["sni"])).strip()[:253],
          "note":str(d.get("note",row["note"])).strip()[:500],
          "enabled":1 if d.get("enabled",row["enabled"]) else 0,
        }
        try:
            c.execute("UPDATE inbounds SET name=?,path=?,address=?,port=?,host_header=?,sni=?,note=?,enabled=? WHERE id=?",(*vals.values(),iid)); c.commit()
        except Exception: return JSONResponse({"error":"Path already exists."},status_code=409)
    return {"ok":True}

@app.delete("/api/inbounds/{iid}")
async def delete_inbound(request: Request,iid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c: cur=c.execute("DELETE FROM inbounds WHERE id=?",(iid,)); c.commit()
    return {"ok":cur.rowcount>0}

@app.get("/api/inbounds/{iid}/clients")
async def inbound_clients(request: Request,iid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c:
        if not c.execute("SELECT id FROM inbounds WHERE id=?",(iid,)).fetchone(): return JSONResponse({"error":"Inbound not found"},status_code=404)
        rows=c.execute("SELECT * FROM clients WHERE inbound_id=? ORDER BY created DESC",(iid,)).fetchall()
    return [client_dict(x,request) for x in rows]

@app.get("/api/clients")
async def list_clients(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c: rows=c.execute("SELECT * FROM clients ORDER BY created DESC").fetchall()
    return [client_dict(x,request) for x in rows]

@app.post("/api/inbounds/{iid}/clients")
@app.post("/api/clients")
async def create_client(request: Request,iid:str|None=None):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    d=await request.json(); iid=iid or str(d.get("inbound_id") or ""); name=str(d.get("name") or "Client").strip()[:80]
    clean=db.clean_ips(d.get("clean_ips",[]))
    with db.conn() as c:
        ib=c.execute("SELECT * FROM inbounds WHERE id=?",(iid,)).fetchone()
        if not ib: return JSONResponse({"error":"Inbound not found"},status_code=404)
        count=c.execute("SELECT COUNT(*) n FROM clients WHERE inbound_id=?",(iid,)).fetchone()["n"]
        if ib["client_limit"] and count>=ib["client_limit"]: return JSONResponse({"error":"This inbound reached its client limit."},status_code=409)
        cid=secrets.token_hex(12); uid=new_uuid()
        c.execute("""INSERT INTO clients(id,inbound_id,name,uuid,limit_bytes,expires_at,ip_limit,connection_limit,speed_limit_mbps,clean_ips,note,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
          (cid,iid,name,uid,int(as_float(d.get("limit_gb"),0)*1024**3),expiry(d.get("expires_days",0)),as_int(d.get("ip_limit"),0,0,1000),as_int(d.get("connection_limit"),0,0,100000),as_float(d.get("speed_limit_mbps"),0),json.dumps(clean),str(d.get("note") or "")[:500],db.now())); c.commit()
        row=c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone()
    return {"ok":True,"client":client_dict(row,request)}

@app.patch("/api/clients/{cid}")
async def update_client(request: Request,cid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    d=await request.json()
    with db.conn() as c:
        row=c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone()
        if not row: return JSONResponse({"error":"Client not found"},status_code=404)
        c.execute("""UPDATE clients SET name=?,limit_bytes=?,expires_at=?,ip_limit=?,connection_limit=?,speed_limit_mbps=?,clean_ips=?,note=?,enabled=? WHERE id=?""",
          (str(d.get("name",row["name"])).strip()[:80] or row["name"],int(as_float(d.get("limit_gb"),row["limit_bytes"]/1024**3)*1024**3),expiry(d.get("expires_days",0)) if "expires_days" in d else row["expires_at"],as_int(d.get("ip_limit",row["ip_limit"]),row["ip_limit"],0,1000),as_int(d.get("connection_limit",row["connection_limit"]),row["connection_limit"],0,100000),as_float(d.get("speed_limit_mbps",row["speed_limit_mbps"]),row["speed_limit_mbps"]),json.dumps(db.clean_ips(d.get("clean_ips",db.json_list(row["clean_ips"])))),str(d.get("note",row["note"])).strip()[:500],1 if d.get("enabled",row["enabled"]) else 0,cid)); c.commit()
        row=c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone()
    return {"ok":True,"client":client_dict(row,request)}

@app.delete("/api/clients/{cid}")
async def delete_client(request: Request,cid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c: cur=c.execute("DELETE FROM clients WHERE id=?",(cid,)); c.commit()
    return {"ok":cur.rowcount>0}

@app.post("/api/clients/{cid}/regenerate")
async def regenerate_client(request: Request,cid:str):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    with db.conn() as c:
        row=c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone()
        if not row:return JSONResponse({"error":"Client not found"},status_code=404)
        uid=new_uuid(); c.execute("UPDATE clients SET uuid=? WHERE id=?",(uid,cid)); c.commit(); row=c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone()
    return {"ok":True,"client":client_dict(row,request)}

@app.get("/api/settings")
async def settings(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    return {"panel_name":db.setting("panel_name","Dollax Panel"),"public_base_url":db.setting("public_base_url","")}
@app.patch("/api/settings")
async def update_settings(request: Request):
    if not authed(request): return JSONResponse({"error":"unauthorized"},status_code=401)
    d=await request.json();
    if "panel_name" in d: db.set_setting("panel_name",str(d["panel_name"])[:80])
    if "public_base_url" in d: db.set_setting("public_base_url",str(d["public_base_url"]).strip().rstrip("/"))
    return {"ok":True}

@app.websocket("/{full_path:path}")
async def ws_dynamic(ws: WebSocket, full_path: str):
    path="/"+full_path
    with db.conn() as c: ib=c.execute("SELECT * FROM inbounds WHERE path=? AND enabled=1",(path,)).fetchone()
    if not ib or ib["protocol"]!="vless" or ib["network"]!="ws" or ib["security"]!="tls":
        await ws.close(code=1008); return
    await ws.accept()
    try: first=await ws.receive_bytes()
    except Exception: await ws.close(code=1002); return
    parsed=parse_vless_header(first)
    if not parsed: await ws.close(code=1002); return
    uid=parsed[0]
    with db.conn() as c: client=c.execute("SELECT * FROM clients WHERE inbound_id=? AND uuid=? AND enabled=1",(ib["id"],str(uid))).fetchone()
    if not client: await ws.close(code=1008); return
    original=ws.receive_bytes; used=[False]
    async def replay():
        if not used[0]: used[0]=True; return first
        return await original()
    ws.receive_bytes=replay
    await relay_vless(ws,str(uid))
