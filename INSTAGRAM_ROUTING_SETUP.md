# Instagram Routing Setup

## 🎯 مشکل
اینستاگرام در ایران فیلتر است و Passwall2's transparent proxy به دلیل fake DNS نمی‌تواند آن را به درستی route کند.

## ✅ راه‌حل پیاده‌سازی شده

### 1️⃣ تنظیمات Router (OpenWrt با Passwall2)

**Load Balancing با Health Check:**
```bash
ssh root@192.168.1.1

# تنظیمات فعلی:
- Iranian sites → Direct routing
- Company (*.kixy.com) → SSH tunnel port 1032
- Other traffic → Auto load-balanced (tunnels 1032/1033)
  - Strategy: leastload (کم‌ترین بار)
  - Health check: هر 60 ثانیه
```

**پورت‌های SOCKS Proxy:**
- `192.168.1.1:1081` - Passwall2 SOCKS proxy (عمومی)
- `192.168.1.1:1032` - SSH tunnel 1 SOCKS (شرکت)
- `192.168.1.1:1033` - SSH tunnel 2 SOCKS (عمومی)

### 2️⃣ Chrome Extension Integration

**Automatic Instagram Routing:**

Extension به صورت خودکار Instagram را از طریق router SOCKS proxy می‌فرستد:

```javascript
// در background.js - PAC Script
if (shExpMatch(host, "*.instagram.com") ||
    shExpMatch(host, "*.cdninstagram.com") ||
    shExpMatch(host, "*.fbcdn.net")) {
    return "SOCKS5 192.168.1.1:1081";
}
```

**دامنه‌های پوشش داده شده:**
- `*.instagram.com` - سایت اصلی اینستاگرام
- `*.cdninstagram.com` - CDN اینستاگرام
- `*.fbcdn.net` - Facebook CDN (برای محتوای مشترک)

## 🧪 تست

### تست از Terminal:
```bash
# Instagram (باید 200 برگردونه):
curl -x socks5h://192.168.1.1:1081 -I https://www.instagram.com

# سایت شرکت (باید 302 برگردونه):
curl -x socks5h://192.168.1.1:1032 -I https://noc.kixy.com

# Google (auto-balanced):
curl -I https://www.google.com
```

### تست از Chrome:
1. Extension را reload کنید
2. به instagram.com بروید
3. باید بدون مشکل باز شود

## 📊 معماری Routing

```
┌─────────────────┐
│  Chrome Browser │
└────────┬────────┘
         │
    PAC Script
         │
    ┌────┴─────────────────────────────┐
    │                                  │
┌───▼─────────────┐          ┌────────▼──────────┐
│ Instagram       │          │ Other Sites       │
│ *.instagram.com │          │                   │
└───┬─────────────┘          └────────┬──────────┘
    │                                 │
    │ SOCKS5                          │ PAC Rules
    │ 192.168.1.1:1081               │
    │                                 │
┌───▼─────────────────────────────────▼──┐
│     OpenWrt Router (Passwall2)         │
│  ┌──────────────────────────────────┐  │
│  │  Load Balancer (leastload)       │  │
│  │  - Health check every 60s        │  │
│  └──┬────────────────────────┬──────┘  │
│     │                        │         │
│  ┌──▼─────────┐      ┌───────▼──┐     │
│  │ SSH Tunnel │      │ SSH Tunnel│     │
│  │ Port 1032  │      │ Port 1033 │     │
│  └────────────┘      └───────────┘     │
└────────────────────────────────────────┘
         │                    │
         └────────┬───────────┘
                  │
           ┌──────▼────────┐
           │   Internet    │
           └───────────────┘
```

## 🔧 تغییرات انجام شده

### Router (Passwall2 UCI Config):
```bash
# Balancing node
uci set passwall2.balanced_tunnel.balancing_strategy='leastload'
uci set passwall2.balanced_tunnel.use_health_check='1'

# Shunt routing
uci set passwall2.iran_shunt_node.company_sites='company_sites'
uci set passwall2.iran_shunt_node.default_node='balanced_tunnel'

# Company routing
uci set passwall2.company_sites.domain_list='domain:.kixy.com'
uci set passwall2.company_sites.node='ssh_7Hd5rcr0'
```

### Chrome Extension (background.js):
- اضافه شده: Instagram routing به SOCKS proxy در خط ~832
- قبل از GeoSite bypass اجرا می‌شود تا اولویت داشته باشد

## ⚠️ نکات مهم

1. **Router باید در دسترس باشد:** `192.168.1.1` باید قابل دسترسی باشد
2. **SSH Tunnels باید running باشند:** پورت‌های 1032 و 1033
3. **Passwall2 SOCKS باید فعال باشد:** پورت 1081 listen می‌کند

## 🔍 Troubleshooting

### اگر Instagram کار نکرد:

1. **چک کردن SOCKS proxy:**
   ```bash
   ssh root@192.168.1.1 "netstat -lntp | grep 1081"
   ```

2. **تست مستقیم SOCKS:**
   ```bash
   curl -x socks5h://192.168.1.1:1081 -I https://www.instagram.com
   ```

3. **چک کردن Passwall2 status:**
   ```bash
   ssh root@192.168.1.1 "/etc/init.d/passwall2 status"
   ```

4. **Reload Extension:**
   - Chrome → Extensions → Reload
   - یا `chrome.runtime.reload()` در console

## 📝 دستورات مفید

```bash
# نمایش تنظیمات shunt node
ssh root@192.168.1.1 "uci show passwall2.iran_shunt_node"

# نمایش balancing config
ssh root@192.168.1.1 "uci show passwall2.balanced_tunnel"

# Restart Passwall2
ssh root@192.168.1.1 "/etc/init.d/passwall2 restart"

# مشاهده logs
ssh root@192.168.1.1 "logread | grep passwall2 | tail -20"
```

## 🎉 نتیجه

✅ Instagram به صورت خودکار از طریق router SOCKS proxy route می‌شود  
✅ سایت‌های شرکت از tunnel اختصاصی استفاده می‌کنند  
✅ بقیه ترافیک با load balancing بهینه می‌شود  
✅ کاربر نیازی به تنظیمات دستی ندارد
