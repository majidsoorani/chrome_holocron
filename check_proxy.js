// ==========================================
// Holocron Proxy Quick Check
// ==========================================
// این کد رو در Chrome DevTools Console کپی/پیست کن
// (F12 → Console tab)

console.clear();
console.log('%c🔍 Holocron Proxy Check', 'font-size: 20px; font-weight: bold; color: #4ec9b0');
console.log('');

// 1. Check Proxy Settings
chrome.proxy.settings.get({incognito: false}, (settings) => {
    console.log('%c1️⃣ Proxy Configuration:', 'font-size: 16px; font-weight: bold; color: #dcdcaa');
    console.log('Mode:', settings.value.mode);
    console.log('Level of Control:', settings.levelOfControl);
    
    if (settings.value.mode === 'pac_script') {
        console.log('%c✅ PAC Script Mode Active', 'color: #4ec9b0');
        
        const pacData = settings.value.pacScript?.data;
        if (pacData) {
            console.log('PAC Script Length:', pacData.length, 'characters');
            
            // Check for Instagram
            if (pacData.includes('instagram')) {
                console.log('%c✅ Instagram routing FOUND', 'color: #4ec9b0');
                
                // Extract Instagram section
                const instagramMatch = pacData.match(/instagram[\s\S]{0,300}/i);
                if (instagramMatch) {
                    console.log('%cInstagram Routing Code:', 'color: #9cdcfe');
                    console.log(instagramMatch[0]);
                }
            } else {
                console.log('%c❌ Instagram routing NOT FOUND', 'color: #f48771');
            }
            
            // Check for SOCKS5
            if (pacData.includes('SOCKS5 192.168.1.1:1081')) {
                console.log('%c✅ Router SOCKS5 proxy FOUND (192.168.1.1:1081)', 'color: #4ec9b0');
            } else {
                console.log('%c❌ Router SOCKS5 proxy NOT FOUND', 'color: #f48771');
            }
            
            // Show full PAC if needed
            console.log('');
            console.log('%cTo see full PAC script, run:', 'color: #ce9178');
            console.log('chrome.proxy.settings.get({incognito: false}, s => console.log(s.value.pacScript.data))');
        }
    } else {
        console.log('%c⚠️ Not using PAC script mode!', 'color: #f9ab00');
        console.log('Current mode:', settings.value.mode);
    }
    
    console.log('');
    console.log('%c2️⃣ Quick Fix:', 'font-size: 16px; font-weight: bold; color: #dcdcaa');
    console.log('If Instagram routing is missing, reload the extension:');
    console.log('1. Go to chrome://extensions/');
    console.log('2. Find "Holocron"');
    console.log('3. Click the Reload button (🔄)');
    console.log('');
    console.log('Then run this check again.');
});

// 2. Check Extension Status
console.log('%c3️⃣ Extension Info:', 'font-size: 16px; font-weight: bold; color: #dcdcaa');
const manifest = chrome.runtime.getManifest();
console.log('Name:', manifest.name);
console.log('Version:', manifest.version);
console.log('Permissions:', manifest.permissions);

if (manifest.permissions.includes('proxy')) {
    console.log('%c✅ Proxy permission granted', 'color: #4ec9b0');
} else {
    console.log('%c❌ Proxy permission MISSING', 'color: #f48771');
}
