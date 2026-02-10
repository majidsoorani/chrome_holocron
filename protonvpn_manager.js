/**
 * ProtonVPN Manager Module
 * Handles server discovery, configuration, and connection management
 */

class ProtonVPNManager {
    constructor() {
        this.discoveredServers = [];
        this.lastDiscoveryTime = null;
        this.discoveryInProgress = false;
    }

    /**
     * Discover accessible ProtonVPN servers
     * @param {Object} options - Discovery options
     * @returns {Promise<Array>} List of accessible servers
     */
    async discoverServers(options = {}) {
        if (this.discoveryInProgress) {
            throw new Error('Discovery already in progress');
        }

        this.discoveryInProgress = true;
        const discoveredServers = [];

        try {
            // ProtonVPN server list by country with known working servers from deep search
            const serverList = this.getProtonVPNServerList(options.freeOnly);

            // Test each server for accessibility
            for (const server of serverList) {
                try {
                    const result = await this.testServer(server, options);
                    if (result.accessible) {
                        discoveredServers.push({
                            ...server,
                            latency: result.latency,
                            ports: result.ports,
                            flag: this.getCountryFlag(server.country),
                            testedAt: Date.now()
                        });
                    }
                } catch (error) {
                    console.error(`Error testing server ${server.name}:`, error);
                }
            }

            // Sort by latency (fastest first)
            discoveredServers.sort((a, b) => a.latency - b.latency);

            this.discoveredServers = discoveredServers;
            this.lastDiscoveryTime = Date.now();

            // Save to storage with configId
            await this.saveDiscoveredServers(discoveredServers, options.configId);

            return discoveredServers;
        } finally {
            this.discoveryInProgress = false;
        }
    }

    /**
     * Get ProtonVPN server list
     * Based on deep search results from November 14, 2025
     */
    getProtonVPNServerList(freeOnly = false) {
        const servers = [
            // France - BEST (3 ports each)
            { country: 'FR', name: 'fr-01', ip: '146.70.152.2', hostname: 'fr-01.protonvpn.net', isFree: false, ports: [443, 80, 8080], priority: 1 },
            { country: 'FR', name: 'fr-02', ip: '146.70.152.3', hostname: 'fr-02.protonvpn.net', isFree: false, ports: [443, 80, 8080], priority: 1 },
            
            // Singapore - GOOD (2 ports each)
            { country: 'SG', name: 'sg-01', ip: '37.19.220.2', hostname: 'sg-01.protonvpn.net', isFree: false, ports: [443, 80], priority: 2 },
            { country: 'SG', name: 'sg-02', ip: '37.19.220.3', hostname: 'sg-02.protonvpn.net', isFree: false, ports: [443, 80], priority: 2 },
            
            // Switzerland (2 ports)
            { country: 'CH', name: 'ch-04', ip: '146.70.198.2', hostname: 'ch-04.protonvpn.net', isFree: false, ports: [443], priority: 3 },
            { country: 'CH', name: 'ch-ch-01', ip: '146.70.174.2', hostname: 'ch-ch-01.protonvpn.net', isFree: false, ports: [443, 80], priority: 3 },
            
            // UK
            { country: 'UK', name: 'uk-01', ip: '146.70.184.2', hostname: 'uk-01.protonvpn.net', isFree: false, ports: [443, 80], priority: 3 },
            
            // Spain (includes FREE server)
            { country: 'ES', name: 'es-01', ip: '146.70.149.2', hostname: 'es-01.protonvpn.net', isFree: false, ports: [443], priority: 4 },
            { country: 'ES', name: 'es-free-01', ip: '146.70.149.226', hostname: 'es-free-01.protonvpn.net', isFree: true, ports: [443, 80], priority: 4 },
            
            // Netherlands
            { country: 'NL', name: 'nl-04', ip: '185.159.156.27', hostname: 'nl-04.protonvpn.net', isFree: false, ports: [443], priority: 4 },
            
            // Additional servers to test (may not be accessible)
            { country: 'NL', name: 'nl-free-01', ip: '95.215.61.163', hostname: 'nl-free-01.protonvpn.net', isFree: true, ports: [443], priority: 5 },
            { country: 'SE', name: 'se-free-01', ip: '185.107.56.228', hostname: 'se-free-01.protonvpn.net', isFree: true, ports: [443], priority: 5 },
            { country: 'IS', name: 'is-free-01', ip: '89.22.98.226', hostname: 'is-free-01.protonvpn.net', isFree: true, ports: [443], priority: 5 },
            { country: 'UK', name: 'uk-free-01', ip: '146.70.184.226', hostname: 'uk-free-01.protonvpn.net', isFree: true, ports: [443], priority: 5 },
            { country: 'FR', name: 'fr-free-01', ip: '146.70.152.226', hostname: 'fr-free-01.protonvpn.net', isFree: true, ports: [443], priority: 5 },
        ];

        if (freeOnly) {
            return servers.filter(s => s.isFree);
        }

        return servers;
    }

    /**
     * Test server accessibility via TCP ping
     */
    async testServer(server, options = {}) {
        const portsToTest = server.ports || [443];
        const accessiblePorts = [];
        let minLatency = Infinity;

        for (const port of portsToTest) {
            try {
                const startTime = Date.now();
                const response = await this.tcpPing(server.ip, port, options);
                const latency = Date.now() - startTime;

                if (response.success) {
                    accessiblePorts.push(port);
                    minLatency = Math.min(minLatency, latency);
                }
            } catch (error) {
                console.debug(`Port ${port} on ${server.ip} not accessible:`, error);
            }
        }

        return {
            accessible: accessiblePorts.length > 0,
            ports: accessiblePorts,
            latency: minLatency === Infinity ? null : minLatency
        };
    }

    /**
     * Perform TCP ping using native host
     */
    async tcpPing(host, port, options = {}) {
        return new Promise((resolve, reject) => {
            const message = {
                command: 'tcpPing',
                host: host,
                port: port,
                timeout: options.timeout || 5000
            };

            chrome.runtime.sendNativeMessage('com.holocron.native_host', message, response => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response && response.success) {
                    resolve(response);
                } else {
                    reject(new Error(response?.error || 'TCP ping failed'));
                }
            });
        });
    }

    /**
     * Download OpenVPN configuration for a server
     */
    async downloadOpenVPNConfig(server, username, protocol = 'tcp') {
        const configUrl = `https://account.protonvpn.com/api/vpn/config?Platform=linux&Protocol=${protocol}&ServerID=${server.name}`;
        
        // This would typically be done via the ProtonVPN API
        // For now, we'll generate a basic config
        return this.generateOpenVPNConfig(server, username, protocol);
    }

    /**
     * Generate OpenVPN configuration
     */
    generateOpenVPNConfig(server, username, protocol = 'tcp') {
        const port = protocol === 'tcp' ? 443 : 1194;
        
        return `# ProtonVPN ${server.country} ${server.name} ${protocol.toUpperCase()}
client
dev tun
proto ${protocol}
remote ${server.ip} ${port}
resolv-retry infinite
nobind
persist-key
persist-tun
cipher AES-256-CBC
auth SHA512
comp-lzo
verb 3
auth-user-pass
# ProtonVPN credentials
# Username: ${username}
# Password: [Enter your ProtonVPN password]
`;
    }

    /**
     * Generate WireGuard configuration
     */
    async generateWireGuardConfig(server, credentials) {
        // This would require ProtonVPN API integration
        // For now, return a placeholder
        return `# WireGuard configuration for ${server.name}
# This requires ProtonVPN API integration
# Please use OpenVPN for now
`;
    }

    /**
     * Select best server based on strategy
     */
    async selectServer(strategy, options = {}) {
        if (!this.discoveredServers || this.discoveredServers.length === 0) {
            await this.discoverServers(options);
        }

        let servers = [...this.discoveredServers];

        // Filter by country/server if specified
        if (options.preferred) {
            const pref = options.preferred.toUpperCase();
            const filtered = servers.filter(s => 
                s.country === pref || 
                s.name === pref || 
                s.ip === pref ||
                s.hostname.includes(pref.toLowerCase())
            );
            if (filtered.length > 0) {
                servers = filtered;
            }
        }

        // Filter free only if requested
        if (options.freeOnly) {
            servers = servers.filter(s => s.isFree);
        }

        if (servers.length === 0) {
            throw new Error('No accessible servers found matching criteria');
        }

        switch (strategy) {
            case 'fastest':
                // Already sorted by latency
                return servers[0];
            
            case 'random':
                return servers[Math.floor(Math.random() * servers.length)];
            
            case 'specific':
                // Return first match (already filtered above)
                return servers[0];
            
            default:
                return servers[0];
        }
    }

    /**
     * Save discovered servers to storage
     */
    async saveDiscoveredServers(servers = null, configId = null) {
        const serversToSave = servers || this.discoveredServers;
        const id = configId || this.configId;
        
        if (!id) {
            console.error('Cannot save servers: no configId provided');
            return;
        }
        
        const storageKey = `protonvpn_servers_${id}`;
        const timestampKey = `protonvpn_timestamp_${id}`;
        
        const data = {
            [storageKey]: serversToSave,
            [timestampKey]: Date.now()
        };
        
        await chrome.storage.local.set(data);
        console.log(`Saved ${serversToSave.length} ProtonVPN servers for config ${id}`);
        
        // Update instance variables
        this.discoveredServers = serversToSave;
        this.lastDiscoveryTime = data[timestampKey];
    }

    /**
     * Load discovered servers from storage
     */
    async loadDiscoveredServers(configId = null) {
        const id = configId || this.configId;
        
        if (!id) {
            console.error('Cannot load servers: no configId provided');
            return { servers: [], lastUpdate: null };
        }
        
        const storageKey = `protonvpn_servers_${id}`;
        const timestampKey = `protonvpn_timestamp_${id}`;
        
        const data = await chrome.storage.local.get([storageKey, timestampKey]);
        
        const servers = data[storageKey] || [];
        const lastUpdate = data[timestampKey] || null;
        
        console.log(`Loaded ${servers.length} ProtonVPN servers for config ${id}`, 
                   lastUpdate ? `(last updated: ${new Date(lastUpdate).toLocaleString()})` : '(no timestamp)');
        
        // Update instance variables
        this.discoveredServers = servers;
        this.lastDiscoveryTime = lastUpdate;
        
        return { servers, lastUpdate };
    }

    /**
     * Check if discovery is needed based on update interval
     */
    needsDiscovery(updateInterval) {
        if (!this.lastDiscoveryTime) return true;
        
        const intervals = {
            manual: Infinity,
            hourly: 60 * 60 * 1000,
            every6hours: 6 * 60 * 60 * 1000,
            daily: 24 * 60 * 60 * 1000,
            weekly: 7 * 24 * 60 * 60 * 1000
        };
        
        const interval = intervals[updateInterval] || Infinity;
        const elapsed = Date.now() - this.lastDiscoveryTime;
        
        return elapsed >= interval;
    }

    /**
     * Connect to ProtonVPN server
     */
    async connect(configId, config) {
        // Load discovered servers if not already loaded
        if (this.discoveredServers.length === 0) {
            await this.loadDiscoveredServers();
        }

        // Check if discovery is needed
        if (this.needsDiscovery(config.protonvpnUpdateInterval)) {
            try {
                await this.discoverServers({
                    freeOnly: config.protonvpnFreeOnly
                });
            } catch (error) {
                console.error('Server discovery failed, using cached servers:', error);
            }
        }

        // Select server
        const server = await this.selectServer(config.protonvpnStrategy, {
            preferred: config.protonvpnServer,
            freeOnly: config.protonvpnFreeOnly
        });

        if (!server) {
            throw new Error('No accessible ProtonVPN server found');
        }

        // Generate configuration based on protocol
        let configContent;
        let connectionType;

        if (config.protonvpnProtocol.startsWith('openvpn')) {
            const protocol = config.protonvpnProtocol === 'openvpn-tcp' ? 'tcp' : 'udp';
            configContent = this.generateOpenVPNConfig(server, config.protonvpnUsername, protocol);
            connectionType = 'openvpn';
        } else if (config.protonvpnProtocol === 'wireguard') {
            configContent = await this.generateWireGuardConfig(server, config);
            connectionType = 'wireguard';
        }

        // Connect via native host
        return new Promise((resolve, reject) => {
            const message = {
                command: 'connectProtonVPN',
                configId: configId,
                server: server,
                config: configContent,
                username: config.protonvpnUsername,
                password: config.protonvpnPassword,
                protocol: config.protonvpnProtocol,
                connectionType: connectionType
            };

            chrome.runtime.sendNativeMessage('com.holocron.native_host', message, response => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response && response.success) {
                    resolve({
                        ...response,
                        server: server,
                        configId: configId
                    });
                } else {
                    reject(new Error(response?.error || 'Connection failed'));
                }
            });
        });
    }

    /**
     * Disconnect from ProtonVPN
     */
    async disconnect(configId) {
        return new Promise((resolve, reject) => {
            const message = {
                command: 'disconnectProtonVPN',
                configId: configId
            };

            chrome.runtime.sendNativeMessage('com.holocron.native_host', message, response => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response && response.success) {
                    resolve(response);
                } else {
                    reject(new Error(response?.error || 'Disconnection failed'));
                }
            });
        });
    }

    /**
     * Format server info for display
     */
    formatServerInfo(server) {
        const flag = this.getCountryFlag(server.country);
        const freeLabel = server.isFree ? ' [FREE]' : '';
        const latencyLabel = server.latency ? ` (${server.latency}ms)` : '';
        const portsLabel = server.ports ? ` - Ports: ${server.ports.join(', ')}` : '';
        
        return `${flag} ${server.country} ${server.name}${freeLabel}${latencyLabel}${portsLabel}`;
    }

    /**
     * Get country flag emoji
     */
    getCountryFlag(countryCode) {
        const flags = {
            'FR': '🇫🇷',
            'SG': '🇸🇬',
            'CH': '🇨🇭',
            'UK': '🇬🇧',
            'ES': '🇪🇸',
            'NL': '🇳🇱',
            'SE': '🇸🇪',
            'IS': '🇮🇸',
            'DE': '🇩🇪',
            'US': '🇺🇸',
            'JP': '🇯🇵',
            'AU': '🇦🇺',
            'IT': '🇮🇹',
            'PL': '🇵🇱',
            'RO': '🇷🇴'
        };
        return flags[countryCode] || '🌍';
    }
}

// Export for use in other modules
export { ProtonVPNManager };

// CommonJS fallback for Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ProtonVPNManager };
}
