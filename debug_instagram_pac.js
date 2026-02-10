// Instagram PAC Test Console Commands
// Copy-paste these in Chrome DevTools Console (F12) while on any webpage

console.log("🧪 Instagram PAC Debug Helper");
console.log("================================\n");

// Test 1: Check if extension is loaded
console.log("1️⃣ Checking Chrome Extension API...");
if (typeof chrome !== 'undefined' && chrome.runtime) {
    console.log("✅ Chrome extension API available");
    console.log("   Extension ID:", chrome.runtime.id);
} else {
    console.error("❌ Chrome extension API not available");
}

// Test 2: Check proxy settings
console.log("\n2️⃣ Checking proxy settings...");
if (typeof chrome !== 'undefined' && chrome.proxy) {
    chrome.proxy.settings.get({}, (config) => {
        console.log("📋 Current proxy config:");
        console.log(config);
        
        if (config.value.mode === 'pac_script') {
            console.log("\n✅ PAC script mode is active");
            console.log("📄 PAC Script preview:");
            const pac = config.value.pacScript.data;
            
            // Extract Instagram routing section
            const instagramMatch = pac.match(/Instagram[\s\S]*?return "SOCKS5[^"]+";/);
            if (instagramMatch) {
                console.log("✅ Instagram routing found:");
                console.log(instagramMatch[0]);
            } else {
                console.error("❌ Instagram routing NOT found in PAC script!");
                console.log("📄 Full PAC script length:", pac.length, "chars");
            }
        } else {
            console.warn("⚠️  PAC script mode is NOT active. Current mode:", config.value.mode);
        }
    });
} else {
    console.error("❌ Chrome proxy API not available");
}

// Test 3: Manual PAC function test
console.log("\n3️⃣ Testing PAC function manually...");
function FindProxyForURL_Test(url, host) {
    if (host.match(/instagram\.com|cdninstagram\.com|fbcdn\.net/)) {
        return "SOCKS5 192.168.1.1:1081";
    }
    return "DIRECT";
}

const testHosts = [
    'www.instagram.com',
    'scontent.cdninstagram.com', 
    'static.xx.fbcdn.net',
    'www.google.com'
];

console.table(testHosts.map(host => ({
    Host: host,
    Proxy: FindProxyForURL_Test('https://' + host, host)
})));

// Test 4: Try to fetch Instagram with current settings
console.log("\n4️⃣ Testing Instagram access...");
fetch('https://www.instagram.com', { method: 'HEAD' })
    .then(response => {
        console.log("✅ Instagram response:");
        console.log("   Status:", response.status, response.statusText);
        console.log("   Headers:", Object.fromEntries(response.headers));
    })
    .catch(error => {
        console.error("❌ Instagram fetch failed:");
        console.error("   Error:", error.message);
        console.error("\n💡 Troubleshooting:");
        console.error("   1. Check if extension is active");
        console.error("   2. Reload extension (chrome://extensions)");
        console.error("   3. Check SOCKS proxy: curl -x socks5h://192.168.1.1:1081 https://www.instagram.com");
    });

console.log("\n================================");
console.log("📝 Next steps:");
console.log("1. Check output above for errors");
console.log("2. If PAC not found, reload extension");
console.log("3. Open test_instagram_pac.html for detailed tests");
console.log("4. Check background.js console for errors");
