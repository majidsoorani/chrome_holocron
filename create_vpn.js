const puppeteer = require('puppeteer');
const fs = require('fs');
const readline = require('readline');

const UUIDS = [
    'eec10c4f-2d51-4966-ba32-050d9e57519d',
    '8d5b90c1-6507-458f-a24f-82de08860379',
    '70f1a3ac-0df0-4dac-bd56-89b9f3d69377'
];

function askQuestion(query) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });
    return new Promise(resolve => rl.question(query, ans => {
        rl.close();
        resolve(ans);
    }));
}

async function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
    console.log('Starting Cloudflare VPN Automation Setup...');
    
    // Read the worker code
    let workerCode = '';
    try {
        workerCode = fs.readFileSync('worker.js', 'utf8');
    } catch (e) {
        console.error('Error: worker.js not found in current directory. Please make sure worker.js exists.');
        process.exit(1);
    }

    const browser = await puppeteer.launch({
        headless: false,
        defaultViewport: null,
        args: ['--start-maximized']
    });

    const results = [];

    for (let i = 0; i < 3; i++) {
        console.log(`\n=================== Creating Account ${i + 1}/3 ===================`);
        const page = await browser.newPage();
        
        // 1. Get Temporary Email
        console.log('Navigating to temp-mail.org...');
        await page.goto('https://temp-mail.org/fa/', { waitUntil: 'networkidle2' });
        
        console.log('Waiting for temporary email to be generated...');
        await page.waitForSelector('#mail', { timeout: 30000 });
        let email = '';
        while (!email || email.includes('Loading')) {
            email = await page.evaluate(() => document.querySelector('#mail').value);
            await delay(1000);
        }
        console.log(`Generated Email: ${email}`);

        // Generate a random password
        const password = 'VpnPass' + Math.random().toString(36).slice(-8) + 'A1!';
        console.log(`Generated Password: ${password}`);

        // 2. Open Cloudflare Sign up
        console.log('Opening Cloudflare Sign Up...');
        const cfPage = await browser.newPage();
        await cfPage.goto('https://dash.cloudflare.com/sign-up', { waitUntil: 'networkidle2' });
        
        // Fill email and password
        await cfPage.type('input[type="email"]', email);
        await cfPage.type('input[type="password"]', password);

        console.log('\n[ACTION REQUIRED] Please solve the Cloudflare Captcha on the browser window and click "Sign up".');
        await askQuestion('Once you have successfully signed up and are logged in, press Enter here to continue...');

        // 3. Email Verification
        console.log('Please check the temp-mail tab and click the verification link sent by Cloudflare.');
        await askQuestion('Once you have verified the email and are on the Cloudflare Dashboard, press Enter here to continue...');

        // 4. Create Worker
        console.log('Navigating to Workers & Pages...');
        await cfPage.goto('https://dash.cloudflare.com/?to=/:account/workers-and-pages', { waitUntil: 'networkidle2' });
        
        console.log('[ACTION REQUIRED] Please create a new Worker named "vpn-worker" (or any name you prefer).');
        console.log('Steps: Create application -> Create Worker -> Deploy -> Close/Back to Worker Settings page.');
        await askQuestion('Once the Worker is created and deployed, and you are on the Worker detail/dashboard page, press Enter here...');

        const currentUrl = cfPage.url();
        console.log(`Current URL: ${currentUrl}`);

        // 5. KV Namespace
        console.log('Navigating to KV creation...');
        await cfPage.goto('https://dash.cloudflare.com/?to=/:account/workers/kv/namespaces', { waitUntil: 'networkidle2' });
        console.log('[ACTION REQUIRED] Create a KV Namespace named "vpn-data".');
        await askQuestion('Once the KV Namespace is created, press Enter here...');

        // 6. Bind KV and Variables
        console.log('Please go back to the Worker -> Settings -> Variables.');
        console.log('1. Add KV Namespace binding: Variable name = "C", KV namespace = "vpn-data".');
        console.log(`2. Add Environment Variable: Variable name = "u", Value = "${UUIDS[i]}".`);
        console.log('3. Save and Deploy.');
        await askQuestion('Once you have saved the bindings and variables, press Enter here...');

        // 7. Paste Code
        console.log('Please click "Edit Code" or "Quick Edit" in the Worker page.');
        console.log('Delete all existing code, paste the contents of worker.js, and click "Save and Deploy".');
        await askQuestion('Once you have deployed the code, press Enter here...');

        const workerUrl = await askQuestion('Please paste the deployed Worker URL (e.g., https://vpn-worker.username.workers.dev): ');
        const cleanUrl = workerUrl.trim().replace(/\/$/, '');
        
        const subLink = `${cleanUrl}/${UUIDS[i]}/sub`;
        console.log(`Successfully configured Proxy ${i + 1}: ${subLink}`);
        results.push({
            email,
            password,
            uuid: UUIDS[i],
            subscription: subLink
        });
    }

    console.log('\n=================== ALL PROXIES CREATED ===================');
    console.log(JSON.stringify(results, null, 2));
    
    fs.writeFileSync('vpn_results.json', JSON.stringify(results, null, 2));
    console.log('Results saved to vpn_results.json');
    
    await browser.close();
}

run().catch(console.error);
