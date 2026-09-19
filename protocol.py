import asyncio, base64, struct, uuid
from urllib.parse import urlencode, quote

def new_uuid():
    return str(uuid.uuid4())

def vless_link(client_uuid, address, port, path, host_header, sni, name):
    host_header = host_header or address
    sni = sni or host_header
    q = urlencode({
        "type": "ws", "security": "tls", "encryption": "none",
        "host": host_header, "sni": sni, "path": path
    }, quote_via=quote)
    return f"vless://{client_uuid}@{address}:{port}?{q}#{quote(name, safe='') }"

def parse_vless_header(data):
    if len(data) < 22 or data[0] != 0:
        return None
    try:
        uid = uuid.UUID(bytes=data[1:17])
    except Exception:
        return None
    addon_len = data[17]
    i = 18 + addon_len
    if len(data) < i + 4:
        return None
    command = data[i]
    port = struct.unpack(">H", data[i+1:i+3])[0]
    at = data[i+3]
    i += 4
    if command not in (1, 2):
        return None
    if at == 1:
        if len(data) < i+4: return None
        host = ".".join(map(str, data[i:i+4])); i += 4
    elif at == 2:
        if len(data) < i+1: return None
        n = data[i]; i += 1
        if len(data) < i+n: return None
        try: host = data[i:i+n].decode("utf-8", "strict")
        except UnicodeDecodeError: return None
        i += n
    elif at == 3:
        if len(data) < i+16: return None
        host = ":".join(data[i+j:i+j+2].hex() for j in range(0,16,2)); i += 16
    else:
        return None
    return uid, host, port, i

async def relay_vless(ws, client_uuid):
    first = await ws.receive_bytes()
    parsed = parse_vless_header(first)
    if not parsed:
        await ws.close(code=1002); return
    uid, host, port, offset = parsed
    if str(uid) != client_uuid:
        await ws.close(code=1008); return
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except Exception:
        await ws.close(code=1011); return
    try:
        await ws.send_bytes(b"\x00\x00\x00")
        initial = first[offset:]
        if initial:
            writer.write(initial); await writer.drain()
        async def ws_to_tcp():
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect": break
                    data = msg.get("bytes")
                    if data:
                        writer.write(data); await writer.drain()
            finally:
                try: writer.close()
                except Exception: pass
        async def tcp_to_ws():
            try:
                while True:
                    data = await reader.read(65536)
                    if not data: break
                    await ws.send_bytes(data)
            finally:
                try: await ws.close()
                except Exception: pass
        await asyncio.gather(ws_to_tcp(), tcp_to_ws())
    finally:
        try: writer.close()
        except Exception: pass
