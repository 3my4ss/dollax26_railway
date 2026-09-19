================================================================================
  پنل Dollax — راهنمای راهاندازی و دیپلوی روی Railway (فارسی)
================================================================================

Dollax یک پنل مدیریت کوچک و self-hosted برای اجرای یک proxy با پروتکل
VLESS روی WebSocket روی TLS است. با Python (FastAPI) و SQLite نوشته شده و
یک رابط وب در اختیارتان میگذارد که با آن inbound (نقطه ورود) و client
(کاربر) بسازید؛ برای هر client یک لینک vless:// آماده کپی ساخته میشود.

این پنل مخصوص اجرا روی Railway و دامنه HTTPS آن طراحی شده. Railway در لبه
شبکهاش TLS را terminate میکند؛ یعنی هم مرورگر شما و هم کلاینت VLESS از
طریق wss://… به Railway وصل میشوند و Railway وبسوکت ساده را به کانتینر
روی $PORT پاس میدهد. این دقیقاً همان چیزی است که یک inbound با
VLESS+WS+TLS انتظار دارد.


--------------------------------------------------------------------------------
۱. محتویات این پوشه
--------------------------------------------------------------------------------

main.py            اپ FastAPI — روتها، auth، API جیسون، نقطه ورود relay WS
db.py              اسکیمای SQLite، migrationها، هش پسورد، شمارش ترافیک
pages.py           پوستههای HTML سمت سرور (صفحه لاگین + پوسته داشبورد)
protocol.py        پارس هدر VLESS، ساخت لینک vless://، relay بین WS و TCP
requirements.txt   وابستگیهای پایتون
Dockerfile         فایل build کانتینر که Railway استفاده میکند
railway.json       تنظیمات دیپلوی Railway (healthcheck + restart policy)
.env.example       نمونهی متغیرهای محیطی
static/
  style.css        استایل داشبورد و لاگین (۷ تم، از طریق data-theme)
  app.js           داشبورد SPA (Overview / Inbounds / Clients / Settings)
README.txt         همین فایل (انگلیسی + فارسی)


--------------------------------------------------------------------------------
۲. متغیرهای محیطی
--------------------------------------------------------------------------------

اینها را در Railway -> سرویس شما -> Variables تنظیم کنید (یا برای تست محلی
در فایل .env).

  ADMIN_USERNAME       خیر (پیشفرض "dollax26")
                       فقط یکبار، در اولین اجرا اگر جدول admins خالی باشد
                       ساخته میشود.

  ADMIN_PASSWORD       بله، حتماً عوضش کنید
                       پسورد اکانت ادمین اول. اگر روی مقدار admin بماند،
                       در لاگ هشدار میدهد.

  SECRET_KEY           بله، در production
                       امضای کوکی سشن. اگر تنظیم نشود، هر بار پروسه یک کلید
                       تصادفی جدید میسازد و با هر ریاستارت/ریدیپلوی همه از
                       حساب خارج میشوند. با این دستور بسازید:
                         python3 -c "import secrets; print(secrets.token_urlsafe(48))"

  PUBLIC_BASE_URL      توصیهشده
                       آدرس عمومی کامل دیپلوی، مثلاً
                       https://dollax-production.up.railway.app. برای ساخت
                       درست لینکهای vless:// و بهعنوان Host/SNI پیشفرض
                       استفاده میشود. بعداً از صفحه Settings هم قابل
                       تغییر است.

  DATA_DIR             خیر (پیشفرض "./data")
                       محل فایل dollax.db وقتی RAILWAY_VOLUME_MOUNT_PATH
                       تنظیم نشده باشد.

  RAILWAY_VOLUME_MOUNT_PATH
                       وقتی Volume وصل کنید خود Railway تنظیم میکند
                       اولویتش از DATA_DIR بالاتر است. به بخش ۴ نگاه کنید
                       — حتماً باید Volume وصل کنید، وگرنه با هر ریدیپلوی
                       ادمین و همهی clientها پاک میشوند.

  PORT                 خود Railway تنظیم میکند
                       برنامه میخواندش. تغییرش ندهید.


--------------------------------------------------------------------------------
۳. اجرای محلی (اختیاری، پیش از دیپلوی)
--------------------------------------------------------------------------------

  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt

  export ADMIN_USERNAME=admin
  export ADMIN_PASSWORD=change-me-now
  export SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  export DATA_DIR=./data

  uvicorn main:app --reload --port 8000

آدرس http://localhost:8000 را باز کنید و با یوزر/پسورد بالا لاگین کنید.

توجه: پنل بهصورت محلی کار میکند، ولی لینکهای vless:// که میسازد به هر
چیزی که PUBLIC_BASE_URL روی آن تنظیم شده (یا Host درخواست) اشاره میکنند.
برای تست واقعی VPN محلی، باید یک TLS terminator جلوی برنامه بگذارید —
Railway این کار را برای شما انجام میدهد، ولی محلی نیاز به چیزی مثل Caddy
یا Cloudflare Tunnel دارید.


--------------------------------------------------------------------------------
۴. دیپلوی روی Railway — گام به گام
--------------------------------------------------------------------------------

گام ۱ — Push روی GitHub

  git init
  git add .
  git commit -m "Initial commit"
  git remote add origin git@github.com:YOU/dollax-railway.git
  git push -u origin main

گام ۲ — ساخت پروژه Railway

  ۱. به https://railway.app بروید، لاگین کنید، New Project بزنید.
  ۲. Deploy from GitHub repo را انتخاب و ریپو را انتخاب کنید.
  ۳. Railway خودش Dockerfile را تشخیص میدهد و از روی آن build میکند.
     نیازی به تنظیم Nixpacks یا start command نیست.

گام ۳ — اتصال Volume (اجباری)

  کانتینرهای Railway موقتیاند. بدون Volume، فایل dollax.db با هر ریدیپلوی
  پاک میشود و ادمین و همهی clientها از بین میروند.

  ۱. سرویس -> Settings -> Volumes -> New Volume.
  ۲. مسیر mount: /data
  ۳. Railway خودش RAILWAY_VOLUME_MOUNT_PATH=/data را ست میکند.
     دست نزنید.

  برنامه طوری نوشته شده که این متغیر را بخواند، پس کار دیگری لازم نیست.

گام ۴ — تنظیم متغیرهای محیطی

  در سرویس -> Variables، حداقل اینها را اضافه کنید:

    ADMIN_USERNAME  = youradminname
    ADMIN_PASSWORD  = a-long-strong-password
    SECRET_KEY      = <خروجی دستور python از بخش ۲>
    PUBLIC_BASE_URL = https://<your-railway-domain>   # میتوانید بعد از گام ۵ پر کنید

  میتوانید PUBLIC_BASE_URL را فعلاً خالی بگذارید و بعد از گام ۵ ست کنید.

گام ۵ — تولید دامنه عمومی

  ۱. سرویس -> Settings -> Networking -> Generate Domain.
  ۲. Railway چیزی مثل dollax-production.up.railway.app میدهد و گواهی TLS
     را خودش میسازد.
  ۳. آن دامنه را کپی کنید، به Variables برگردید و
     PUBLIC_BASE_URL=https://dollax-production.up.railway.app را ست کنید.
  ۴. Railway با تغییر Variables خودش ریدیپلوی میکند.

گام ۶ — بررسی دیپلوی

  - https://<your-domain>/health را باز کنید -> باید
    {"ok": true, "service": "dollax-panel"} برگرداند.
  - https://<your-domain>/ -> به /login ریدایرکت میشود.
  - با ADMIN_USERNAME / ADMIN_PASSWORD که ست کردید لاگین کنید.

  اگر /health کار نکرد یا لاگها crash loop نشان دادند، بخش ۷ را ببینید.

گام ۷ — ساخت اولین inbound

  ۱. در پنل تب Inbounds -> + New inbound.
  ۲. پر کنید:
       Name             مثلاً "Main inbound"
       Port             443 (لبه Railway همیشه از بیرون روی 443 صحبت میکند)
       WebSocket path   خالی بگذارید تا خودکار ساخته شود، مثل /ws/9f3aQ_2
       Address          خالی بگذارید تا از دامنه Railway استفاده شود
       Host header      دامنه Railway (اگر خالی بگذارید خودکار پر میشود)
       SNI              دامنه Railway (اگر خالی بگذارید خودکار پر میشود)
  ۳. Create inbound بزنید.

  پنل مسیر WS را ذخیره میکند و فقط درخواستهای WebSocket upgrade که مسیر
  آنها با یک inbound ثبتشده بخواند را relay میکند.

گام ۸ — ساخت client و گرفتن لینک

  ۱. تب Clients -> + New client.
  ۲. inbound ساختهشده را انتخاب، نام بدهید، و اختیاری ست کنید:
       Data limit        به GB (۰ = نامحدود)
       Expiry            به روز (۰ = هرگز)
       IP limit          (که از طریق traffic log اعمال میشوند)
       Connection limit  (که از طریق traffic log اعمال میشوند)
  ۳. Create client بزنید.
  ۴. در جدول clientها Copy link را بزنید. چیزی شبیه این خواهید گرفت:

     vless://<uuid>@dollax-production.up.railway.app:443
       ?encryption=none
       &security=tls
       &type=ws
       &host=dollax-production.up.railway.app
       &sni=dollax-production.up.railway.app
       &path=%2Fws%2F9f3aQ_2
       &fp=chrome
       #MyClient

     (اینجا شکسته شده؛ لینک واقعی یک خط است.)

گام ۹ — اتصال یک اپ کلاینت

  لینک vless:// را در هر کلاینت سازگار با VLESS وارد کنید:

    اندروید:  v2rayNG، NekoBox، Hiddify
    iOS:      Streisand، Shadowrocket، FoXray
    دسکتاپ:   v2rayN (ویندوز)، V2Box / Nekoray (لینوکس/مک)، Foxray

  کلاینت یک اتصال TLS به dollax-production.up.railway.app:443 باز میکند،
  WebSocket upgrade به /ws/9f3aQ_2 میزند، و شروع به فرستادن frameهای
  VLESS میکند. Railway TLS را terminate کرده و upgrade را به کانتینر شما
  میرساند، و main.py آن را روی /{full_path:path} میگیرد. relay:

    ۱. هدر VLESS (UUID + مقصد) را پارس میکند
    ۲. client را با UUID داخل inbound پیدا میکند
    ۳. enabled / expiry / quota را چک میکند
    ۴. یک اتصال TCP به مقصد باز میکند
    ۵. بایتها را دوطرفه پمپ میکند و up/down را جمع میزند

  ترافیک از طریق db.add_traffic() در دیتابیس نوشته میشود و در جدولهای
  Overview / Inbounds / Clients دیده میشود.


--------------------------------------------------------------------------------
۵. داستانِ «بدون TCP خام»
--------------------------------------------------------------------------------

Railway فقط HTTP(S)/WS را expose میکند و راهی برای داشتن listener خام TCP
ندارد. به همین دلیل:

  - پنل فقط VLESS + WS + TLS را قبول میکند. transportهای TCP خام و gRPC
    را عمداً رد میکند.
  - لبه Railway خودش TLS را terminate میکند. داخل کانتینر، برنامه فقط روی
    HTTP/WS ساده $PORT گوش میدهد.
  - لینک vless همیشه security=tls و type=ws تبلیغ میکند که دقیقاً همان
    چیزی است که کلاینت برای یک WS transport پشت Cloudflare/Railway انتظار
    دارد.

بنابراین مسیر این است:

  کلاینت VLESS -- wss://domain/ws/xyz --> لبه Railway (TLS off)
                                            |
                                            +--> کانتینر روی $PORT (WS ساده)
                                                   |
                                                   +--> protocol.relay_vless()
                                                          |
                                                          +--> مقصد host:port


--------------------------------------------------------------------------------
۶. شمارش ترافیک — چطور کار میکند و کجا ببینیم
--------------------------------------------------------------------------------

هر relay روی WS اینها را جمع میزند:

  up    — بایتهای فرستادهشده از client به مقصد
  down  — بایتهای فرستادهشده از مقصد به client

وقتی WS بسته میشود (قطع کلاینت، خطا، یا رد شدن از quota)، این اعداد در
traffic_log و clients.up / clients.down و inbounds.total_up /
inbounds.total_down نوشته میشوند.

میتوانید اینها را ببینید در:

  - Overview    -> کارتها مجموع ↑ و ↓ را نشان میدهند.
  - Inbounds    -> هر سطر "↑ … | ↓ …" آن inbound را نمایش میدهد.
  - Clients     -> هر سطر up/down همان client را نشان میدهد.
  - Client View -> یک دکمه Reset traffic دارد که clients.up و clients.down
                   را صفر میکند (مجموع inbound عمداً دستنخورده میماند).

محدودیتهای فعلی شمارش:

  - بایتها را بعد از برداشتن TLS میشمارد (داخل frame WS)، که برای VLESS
    درست است.
  - سربازِ framing خود WebSocket (چند بایت per message) شمرده نمیشود.
  - limit_bytes ذخیره میشود ولی در میانهی استریم اعمال نمیشود. برای
    اعمال، کافی است داخل pump() در protocol.relay_vless() از
    db.get_client_traffic(client_id) استفاده کنید و وقتی از limit_bytes
    گذشت ws.close(code=1008) بزنید.


--------------------------------------------------------------------------------
۷. عیبیابی
--------------------------------------------------------------------------------

«Invalid credentials» میبینید در حالی که مطمئنید پسورد درست است
  -> احتمالاً ADMIN_PASSWORD را بعد از اولین اجرا ست کردهاید. رکورد ادمین
     فقط یکبار وقتی جدول admins خالی است ساخته میشود. با Volume در دسترس،
     یا فایل dollax.db را از Volume پاک کنید و دوباره دیپلوی کنید، یا
     مستقیم رکورد را آپدیت کنید:

       python - <<'PY'
       import db
       with db.conn() as c:
           c.execute("UPDATE admins SET password_hash=? WHERE username=?",
                     (db.hash_password("new-password"), "youradminname"))
           c.commit()
       PY

با هر دیپلوی از حساب خارج میشوید
  -> SECRET_KEY ست نیست. ستش کنید و یک بار ریدیپلوی کنید. از این به بعد
     سشنها باقی میمانند.

برنامه بالا نمیآید، Railway crash loop نشان میدهد
  -> لاگهای دیپلوی را ببینید. رایجترین دلایل: نبود پوشه static/ (در
     Dockerfile رفع شده)، نبود python-multipart (در requirements.txt رفع
     شده)، یا خطا در db.init_db() چون /data قابل نوشتن نیست (باید Volume
     روی /data وصل باشد).

کلاینتها وصل میشوند ولی ترافیکی رد نمیشود / لینکها اشتباهاند
  -> PUBLIC_BASE_URL را در Settings چک کنید، و مطمئن شوید Host header و
     SNI همان inbound با دامنه واقعیتان میخوانند. اشتباه رایج این است که
     از دیپلوی قبلی یک دامنهی قدیمی روی inbound مانده باشد.

لینک در مرورگر کار میکند ولی در client نه
  -> بعضی کلاینتها به path حساسند. مطمئن شوید path در لینک vless
     URL-encoded است (پنل این کار را میکند) و با / شروع میشود (پنل این را
     هم اجبار میکند). اگر کلاینتی query string را حذف کند، WS upgrade به
     مسیر اشتباه میخورد و پنل سوکت را با کد 1008 میبندد.

ریدیپلویها پنل را پاک میکنند
  -> Volume وصل نیست. بخش ۴ گام ۳ را ببینید.


--------------------------------------------------------------------------------
۸. چکلیست امنیتی پیش از انتشار
--------------------------------------------------------------------------------

  [ ] ADMIN_PASSWORD را از پیشفرض عوض کرده و قوی انتخاب کردهاید.
  [ ] یک SECRET_KEY ثابت ست کردهاید (نه تصادفیِ هر اجرا).
  [ ] Volume روی Railway وصل کردهاید تا دادهها با ریدیپلوی پاک نشوند.
  [ ] PUBLIC_BASE_URL را روی دامنه واقعی ست کردهاید.
  [ ] توجه دارید که هیچ rate-limit و هیچ 2FA روی لاگین وجود ندارد. یک
      پسورد ادمین قوی و یکتا خط دفاع اول است. اگر بیشتر میخواهید، دامنه
      Railway را پشت Cloudflare بگذارید و rate limiting / WAF آنجا اضافه
      کنید.
  [ ] توجه دارید که UI برای چند ادمین وجود ندارد؛ فقط همان یک اکانت که در
      اولین بوت ساخته شده. برای rotate پسورد از آن یکخطی بخش ۷ استفاده
      کنید.


--------------------------------------------------------------------------------
۹. محدودیتهای شناختهشده (طراحیِ همین نسخه)
--------------------------------------------------------------------------------

  - فقط VLESS + WebSocket + TLS. create_inbound هر ترکیب دیگری را رد میکند
    چون Railway نمیتواند TCP خام را route کند.
  - UDP پشتیبانی نمیشود. protocol.parse_vless_header() بایت کامند 2 (UDP)
    را میپذیرد ولی relay آن را عیناً مثل TCP رفتار میکند. framing واقعی
    UDP-over-VLESS پیادهسازی نشده، پس برای QUIC/HTTP3 یا بازیها روی آن
    حساب نکنید.
  - محدودیت داده در میانهی اتصال اعمال نمیشود. در لحظه اتصال چک میشود
    ولی یک اتصال بلندمدت که از ابتدا داخل quota بود میتواند از آن رد شود.
    برای اعمال، تغییری ۵ خطی در protocol.relay_vless() کافی است.
  - هیچ محافظتی در برابر brute-force روی /login نیست.
  - چند ادمین / نقشها وجود ندارد. یک ادمین، یک نقش.
  - فونتهای سفارشی Cloudflare Worker اصلی (Triakis, Incorrigible, Sheed,
    Kamran, Vesterbro) اینجا embed نشدهاند. بهجای آن از Inter + Vazirmatn
    استفاده شده تا CSS کوچک بماند. اگر نسخه اصلی را میخواهید، بلوکهای
    @font-face با base64 را در بالای static/style.css پیست کنید و دو تگ
    <link> گوگلفونتس را از pages.py حذف کنید.


--------------------------------------------------------------------------------
۱۰. توسعه دادن پنل
--------------------------------------------------------------------------------

  - تمها / style: از کنسول مرورگر
    document.documentElement.dataset.theme = "cyan" را ست کنید — هر ۷ تم در
    static/style.css سیمکشی شدهاند. برای تبدیل به toggle UI، فیلد به
    Settings اضافه کنید که با db.set_setting("theme", …) ذخیره شود.

  - Clean IPs برای هر client: clients.clean_ips یک لیست JSON است که از قبل
    از طریق client_dict() سیمکشی شده، پس با اضافه کردن یک editor برای این
    فیلد، لینکهای چندنودی ظاهر میشوند.

  - اعمال واقعی quota: داخل حلقهی pump() در protocol.relay_vless()
    db.get_client_traffic(client_id) را صدا بزنید و وقتی از limit_bytes
    گذشت ws.close(code=1008) کنید.


================================================================================
  END OF FILE
================================================================================
