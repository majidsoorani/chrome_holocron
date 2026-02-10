# ProtonVPN Auto Mode - User Guide

## 🎯 Overview

The ProtonVPN Auto mode is a powerful new feature in Holocron that automatically discovers accessible ProtonVPN servers from Iran (or other censored regions), selects the fastest one, and connects automatically. No manual configuration needed!

## ✨ Features

### Automatic Server Discovery
- **Smart Scanning**: Tests 15+ ProtonVPN servers across 6 countries
- **Real-time Testing**: Checks TCP port accessibility and measures latency
- **Free Server Support**: Option to use only FREE ProtonVPN servers
- **Caching**: Saves discovered servers to avoid repeated scans

### Intelligent Server Selection
- **Fastest**: Automatically connects to the server with lowest latency
- **Random**: Randomly selects from accessible servers for load balancing
- **Specific**: Choose your preferred country, server name, or IP

### Protocol Support
- **OpenVPN TCP** (Recommended for Iran): Works on port 443, looks like HTTPS traffic
- **OpenVPN UDP**: Faster but often blocked in censored regions
- **WireGuard**: Fastest protocol (when accessible)

### Scheduled Updates
- **Manual**: Update server list only when you click "Discover"
- **Hourly**: Re-scan every hour to find newly accessible servers
- **Every 6 Hours**: Balance between freshness and resource usage
- **Daily**: Recommended for most users
- **Weekly**: For stable connections

## 📋 Setup Guide

### Step 1: Add ProtonVPN Configuration

1. Open Holocron Options
2. Go to "Connections & Health" tab
3. Click "+ Add Custom Configuration"
4. Set "Configuration Name": e.g., "ProtonVPN Auto"
5. Select "Connection Type": **ProtonVPN Auto**

### Step 2: Enter Credentials

1. **ProtonVPN Username**: Your ProtonVPN account username
2. **ProtonVPN Password**: Your ProtonVPN account password

> **Note**: Your credentials are stored locally and never sent anywhere except to ProtonVPN servers.

### Step 3: Configure Settings

#### Protocol Type
- **OpenVPN (TCP)** ✅ RECOMMENDED for Iran
  - Uses port 443 (HTTPS)
  - Works best in censored regions
  - Looks like normal web traffic
  
- **OpenVPN (UDP)**: Faster but often blocked
- **WireGuard**: Fastest but may be blocked

#### Server Selection Strategy
- **Fastest** ✅ RECOMMENDED
  - Automatically selects server with lowest latency
  - Best performance
  
- **Random**: Good for load balancing
- **Specific**: Choose exact server/country

#### Only Use FREE Servers
- ☑ Check this if you have a FREE ProtonVPN account
- ☐ Uncheck for Plus/Unlimited accounts (more servers available)

#### Server Discovery Schedule
- **Daily** ✅ RECOMMENDED
  - Balances freshness with resource usage
  - Automatically updates server list every 24 hours
  
- **Hourly**: For rapidly changing network conditions
- **Manual**: You control when to update

### Step 4: Discover Servers

1. Click "🔍 Discover Servers Now"
2. Wait 30-60 seconds for scan to complete
3. Review discovered servers in the status box
4. Servers are automatically cached

### Step 5: Enable and Connect

1. Check the "Enable" checkbox for your ProtonVPN config
2. Click the connection status button to connect
3. Wait for connection establishment
4. Browse with ProtonVPN protection!

## 🌍 Discovered Servers (as of Nov 2025)

Based on deep scan results from Iran:

### 🥇 Best - France (2 servers)
- **fr-01** (146.70.152.2): 3 open ports (443, 80, 8080)
- **fr-02** (146.70.152.3): 3 open ports (443, 80, 8080)
- **Latency**: ~150-200ms
- **Success Rate**: 100%

### 🥈 Good - Singapore (2 servers)
- **sg-01** (37.19.220.2): 2 open ports (443, 80)
- **sg-02** (37.19.220.3): 2 open ports (443, 80)
- **Latency**: ~180-250ms
- **Success Rate**: 100%

### 🥉 Others
- **Switzerland**: ch-04, ch-ch-01 (2 servers)
- **UK**: uk-01 (1 server)
- **Spain**: es-01, es-free-01 (1 FREE server!)
- **Netherlands**: nl-04 (1 server)

**Total**: 10 accessible servers with 19 endpoints

## 🔧 Advanced Configuration

### Using Specific Server

1. Set Strategy to "Specific"
2. Enter in "Preferred Server" field:
   - Country code: `FR`, `SG`, `CH`
   - Server name: `fr-01`, `sg-02`
   - IP address: `146.70.152.2`

### Combining with V2Ray

For maximum censorship resistance:

1. Keep your V2Ray connection active
2. Add ProtonVPN Auto configuration
3. V2Ray provides first layer of obfuscation
4. ProtonVPN adds additional privacy layer
5. Double-hop protection!

### Using Proxy Rules

Route specific domains through ProtonVPN:

1. Go to "Proxy & Routing" tab
2. Add proxy rule: `*.sensitive-site.com`
3. Set target: "Proxy via: ProtonVPN Auto"
4. Traffic to that domain uses ProtonVPN

## 📊 Understanding Discovery Results

### Server Status Display

```
🇫🇷 FR fr-01 [FREE] (150ms) - Ports: 443, 80, 8080
│   │   │      │      │         └─ Accessible ports
│   │   │      │      └─ Round-trip latency
│   │   │      └─ FREE server indicator
│   │   └─ Server name
│   └─ Country code
└─ Country flag
```

### Port Information

- **Port 443**: HTTPS - Most reliable, looks like web traffic
- **Port 80**: HTTP - Alternative, less encrypted
- **Port 8080**: HTTP-Alt - Additional option
- **Port 1194**: OpenVPN default - Usually BLOCKED in Iran
- **Port 5060**: UDP - Usually BLOCKED in Iran

## ⚠️ Troubleshooting

### No Servers Found

**Symptoms**: Discovery returns 0 servers

**Solutions**:
1. Check internet connection
2. Temporarily disable firewall
3. Try different time of day (ISP blocking varies)
4. Use V2Ray as base proxy for discovery

### Connection Fails

**Symptoms**: Can't connect to discovered server

**Solutions**:
1. Run "Discover Servers Now" again (servers may change)
2. Try different protocol (switch to OpenVPN TCP)
3. Check ProtonVPN credentials
4. Enable "Only use FREE servers" if you have free account

### Slow Connection

**Symptoms**: Connected but very slow

**Solutions**:
1. Change strategy to "Fastest"
2. Run discovery to find faster servers
3. Try French servers (usually fastest from Iran)
4. Check if multiple configs are enabled

### Discovery Takes Too Long

**Symptoms**: "Discovering..." for 5+ minutes

**Solutions**:
1. Cancel and try again
2. Reduce number of servers being tested
3. Check background script isn't blocked
4. Restart browser

## 🔐 Security Notes

### Credential Storage
- Credentials stored locally in Chrome storage
- Encrypted by Chrome's security
- Never sent to Holocron servers (we have none!)
- Only sent to ProtonVPN for authentication

### Privacy Considerations
- ProtonVPN sees your real IP (normal for VPN)
- Websites see ProtonVPN IP
- No DNS leaks with proper configuration
- Kill switch not yet implemented (coming soon)

### Best Practices
1. Use OpenVPN TCP for censored regions
2. Enable auto-reconnect in settings
3. Run discovery at least weekly
4. Don't share discovered server list publicly
5. Use strong ProtonVPN password

## 📈 Performance Tips

### Fastest Connection
1. Strategy: **Fastest**
2. Protocol: **OpenVPN TCP** (for Iran)
3. Discovery: **Daily**
4. Preferred: French servers

### Most Stable
1. Strategy: **Specific**
2. Server: `fr-01` or `fr-02`
3. Protocol: **OpenVPN TCP**
4. Discovery: **Weekly**

### Best Privacy
1. Use with V2Ray (double-hop)
2. Enable ProtonVPN Secure Core (in ProtonVPN account)
3. Avoid FREE servers for sensitive use
4. Change servers regularly

## 🆘 Support

### Common Error Messages

**"No accessible servers found matching criteria"**
- Run discovery again
- Uncheck "Only use FREE servers"
- Try different time

**"Connection failed: Authentication error"**
- Check username/password
- Verify ProtonVPN account is active
- Check account type (Free vs Plus)

**"Discovery failed: Timeout"**
- Check internet connection
- Try manual discovery
- Check firewall settings

### Getting Help

1. Check logs: Settings & Logs → Log Viewer
2. Run test: Click "Test Configuration" button
3. View discovered servers: Click "📋 View Available Servers"
4. Re-discover: Click "🔍 Discover Servers Now"

## 🔄 Update Schedule Examples

### Recommended for Iran

```
Configuration Name: ProtonVPN FR
Protocol: OpenVPN (TCP)
Strategy: Fastest
Update Schedule: Daily
Free Only: No (if you have Plus)
```

### For FREE Users

```
Configuration Name: ProtonVPN Free
Protocol: OpenVPN (TCP)
Strategy: Fastest
Update Schedule: Daily
Free Only: Yes ☑
```

### For Maximum Privacy

```
Configuration Name: ProtonVPN Secure
Protocol: OpenVPN (TCP)
Strategy: Specific
Preferred Server: CH (Switzerland)
Update Schedule: Weekly
```

## 📝 FAQ

**Q: Do I need a ProtonVPN subscription?**
A: Free account works! But Plus/Unlimited gives more servers.

**Q: Will this work in China/Russia/other countries?**
A: Yes! The discovery feature tests servers specifically for accessibility.

**Q: How often should I run discovery?**
A: Daily is recommended. ISP blocking changes frequently.

**Q: Can I use multiple ProtonVPN configs?**
A: Yes! Create separate configs for different countries/strategies.

**Q: Does this use ProtonVPN's official API?**
A: We use standard OpenVPN/WireGuard protocols. No unofficial APIs.

**Q: What's the difference from manual ProtonVPN setup?**
A: This auto-discovers working servers, selects fastest, and auto-reconnects.

**Q: Is WireGuard faster than OpenVPN?**
A: Yes, but often blocked in censored regions. OpenVPN TCP recommended for Iran.

**Q: Can I see which server I'm connected to?**
A: Yes! Check the connection status in the Connections tab.

---

**Version**: 1.0  
**Last Updated**: November 14, 2025  
**Based on**: Deep scan results from Iran
