// This file contains functions to parse various proxy URI schemes.

function parseVlessUri(uri) {
    try {
        const url = new URL(uri);
        const config = {
            type: 'v2ray', // It's a type of V2Ray connection
            protocol: 'vless', // Specify the protocol
            remarks: decodeURIComponent(url.hash.substring(1)),
            server: url.hostname,
            port: parseInt(url.port, 10),
            uuid: url.username,
            // Extract query parameters
            tls: url.searchParams.get('tls') === '1',
            peer: url.searchParams.get('peer'),
            alpn: url.searchParams.get('alpn'),
            // VLESS doesn't have a standard socks port in the URI, so we'll need a default or user input
            socksPort: 1080
        };
        return config;
    } catch (e) {
        console.error("Failed to parse VLESS URI:", uri, e);
        return null;
    }
}

function parseShadowsocksUri(uri) {
    try {
        const url = new URL(uri);
        const remarks = decodeURIComponent(url.hash.substring(1));

        // The user info part is base64 encoded
        const userInfo = atob(url.hostname); // atob() decodes base64
        const [methodAndPassword, hostAndPort] = userInfo.split('@');
        const [method, password] = methodAndPassword.split(':');
        const [server, port] = hostAndPort.split(':');

        const config = {
            type: 'ss',
            remarks: remarks,
            server: server,
            port: parseInt(port, 10),
            method: method,
            password: password,
            // Shadowsocks default local SOCKS port
            socksPort: 1080
        };
        return config;
    } catch (e) {
        console.error("Failed to parse Shadowsocks URI:", uri, e);
        return null;
    }
}

// A generic parser that detects the scheme and calls the appropriate function
function parseUri(uri) {
    if (uri.startsWith('vless://')) {
        return parseVlessUri(uri);
    }
    if (uri.startsWith('ss://')) {
        return parseShadowsocksUri(uri);
    }
    // SSH parsing would be more complex due to the private key and will be added later.
    // if (uri.startsWith('ssh://')) {
    //     return parseSshUri(uri);
    // }
    console.warn("Unsupported URI scheme for:", uri);
    return null;
}
