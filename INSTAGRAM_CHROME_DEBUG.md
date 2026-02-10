# 🔧 Instagram در Chrome کار نمی‌کنه - راهنمای Debug

## ✅ تست شده و کار می‌کنه:
```bash
curl -x socks5h://192.168.1.1:1081 -I https://www.instagram.com
# نتیجه: HTTP/2 200 ✅
```

## ❌ مشکل: Chrome نمی‌تونه به Instagram وصل بشه

---

## 🔍 راه‌حل‌های احتمالی

### روش ۱: Reload کردن Extension (سریع‌ترین)

1. برو به `chrome://extensions/`
2. پیدا کن **Holocron**
3. کلیک کن روی **دکمه Reload** (🔄)
4. برو به `instagram.com`
5. اگر کار نکرد، به روش ۲ برو

---

### روش ۲: چک کردن PAC Script

1. باز کن `test_instagram_pac.html` در Chrome
2. کلیک کن روی همه دکمه‌های Test
3. ببین کدوم قسمت خطا می‌ده:

**اگر "Test Instagram Access" خطا داد:**
- Extension فعال نیست یا PAC script apply نشده

**اگر "Test SOCKS Connection" خطا داد:**
- Router در دسترس نیست یا SOCKS proxy down هست

---

### روش ۳: Debug با Chrome Console

1. باز کن هر صفحه‌ای (مثلاً `google.com`)
2. فشار بده **F12** (DevTools)
3. برو به tab **Console**
4. Copy کن محتوای `debug_instagram_pac.js`
5. Paste کن در console و Enter
6. خروجی رو بخون:

**اگر گفت "PAC script mode is NOT active":**
- Extension proxy رو فعال نکرده
- احتمالاً connection به tunnel موفق نبوده

**اگر گفت "Instagram routing NOT found":**
- کد جدید apply نشده
- نیاز به rebuild یا hard reload extension

---

### روش ۴: Manual Proxy Setup (موقتی)

اگر extension کار نکرد، می‌تونی manual تنظیم کنی:

#### Option A: Chrome System Proxy
1. Settings → System → Open your computer's proxy settings
2. SOCKS Host: `192.168.1.1`
3. Port: `1081`

**مشکل:** همه ترافیک از proxy می‌ره (کند میشه)

#### Option B: SwitchyOmega Extension
1. نصب کن: [Proxy SwitchyOmega](https://chrome.google.com/webstore/detail/proxy-switchyomega/padekgcemlokbadohgkifijomclgjgif)
2. New Profile → PAC Profile
3. PAC Script:
```javascript
function FindProxyForURL(url, host) {
    // Instagram
    if (shExpMatch(host, "*.instagram.com") ||
        shExpMatch(host, "*.cdninstagram.com") ||
        shExpMatch(host, "*.fbcdn.net")) {
        return "SOCKS5 192.168.1.1:1081";
    }
    
    // Company
    if (shExpMatch(host, "*.kixy.com")) {
        return "SOCKS5 192.168.1.1:1032";
    }
    
    return "DIRECT";
}
```
4. Apply changes
5. کلیک روی آیکون SwitchyOmega → انتخاب profile

---

### روش ۵: چک کردن Router SOCKS Proxy

```bash
# تست دسترسی به SOCKS از سیستم
nc -zv 192.168.1.1 1081

# اگر خطا داد، چک کن روتر:
ssh root@192.168.1.1 "netstat -lntp | grep 1081"

# باید ببینی:
# tcp  0  0  0.0.0.0:1081  0.0.0.0:*  LISTEN  <pid>/sing-box

# اگر ندیدی، restart کن:
ssh root@192.168.1.1 "/etc/init.d/passwall2 restart"
```

---

### روش ۶: Debug Extension Background Script

1. برو `chrome://extensions/`
2. Developer mode رو فعال کن
3. زیر **Holocron** کلیک کن **service worker** (یا "Inspect views: background page")
4. Console باز میشه
5. اگر error هست، بهم بگو

**Errors احتمالی:**
- `Failed to set proxy settings` → مشکل permission یا config
- `Native host exited` → Python backend مشکل داره
- `Connection refused` → نمی‌تونه به router وصل بشه

---

## 🎯 Quick Fixes

### Fix 1: Hard Reload Extension
```bash
cd /Users/majidsoorani/chrome_holocron
# اگر git changes داری، commit کن:
git add background.js
git commit -m "Add Instagram routing to PAC script"
```

بعد در Chrome:
1. `chrome://extensions/`
2. Remove کن **Holocron**
3. Load unpacked دوباره از folder

### Fix 2: Force Proxy Update
در extension popup:
1. Disconnect کن tunnel
2. صبر کن 3 ثانیه
3. Connect کن دوباره
4. تست کن Instagram

### Fix 3: Clear Chrome Cache
```
chrome://settings/clearBrowserData
```
- فقط "Cached images and files"
- Last hour
- Clear data

---

## 📊 تشخیص مشکل

| علامت | مشکل | راه حل |
|-------|------|--------|
| curl کار می‌کنه، Chrome نه | Extension proxy active نیست | Reload extension |
| خطای "connection refused" | SOCKS proxy down | Restart passwall2 |
| خطای "timeout" | Router unreachable | Check WiFi/network |
| Instagram باز میشه ولی load نمیشه | PAC مشکل داره | Manual SwitchyOmega |
| Extension icon "bad" | Tunnel disconnected | Reconnect |

---

## 🚀 بهترین راه حل (توصیه)

**استفاده از SwitchyOmega** (تا مشکل extension حل بشه):

1. نصب [SwitchyOmega](https://chrome.google.com/webstore/detail/proxy-switchyomega/padekgcemlokbadohgkifijomclgjgif)
2. Import کن این config: [switchyomega_instagram.json]

یا manual setup:
- Profile name: `Instagram`
- Protocol: `SOCKS5`
- Server: `192.168.1.1`
- Port: `1081`
- Auto Switch conditions:
  - `*.instagram.com` → Instagram profile
  - `*.cdninstagram.com` → Instagram profile
  - `*.fbcdn.net` → Instagram profile

---

## 📞 اگر هیچکدوم کار نکرد

یکی از این commandها رو run کن و output رو بفرست:

```bash
# تست کامل
curl -v -x socks5h://192.168.1.1:1081 https://www.instagram.com 2>&1 | head -50

# چک router
ssh root@192.168.1.1 "
  echo '=== SOCKS Proxy ==='
  netstat -lntp | grep 1081
  echo '=== Passwall2 Status ==='
  /etc/init.d/passwall2 status
  echo '=== Recent Logs ==='
  logread | grep -i passwall | tail -10
"

# چک extension
# در Chrome DevTools console:
chrome.proxy.settings.get({}, c => console.log(JSON.stringify(c, null, 2)))
```
