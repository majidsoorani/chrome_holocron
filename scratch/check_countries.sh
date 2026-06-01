#!/bin/sh
CONFIG_FILE="/etc/sing-box/config.json"
TEST_PORT=10089

get_outbound_block() {
    local tag="$1"
    ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) exit(1);
    let cfg = json(f.read('all'));
    f.close();
    for (let o in cfg.outbounds) {
        if (o.tag == '$tag') {
            print(o);
            exit(0);
        }
    }
    exit(1);
    " 2>/dev/null
}

test_node_country() {
    local tag="$1"
    local outbound_json
    outbound_json=$(get_outbound_block "$tag")
    if [ -z "$outbound_json" ]; then
        echo "error:missing_outbound"
        return
    fi
    
    # Create temp config
    local temp_path="/tmp/test_sb_country_${TEST_PORT}.json"
    cat <<EOF > "$temp_path"
{
  "log": {"level": "warn"},
  "inbounds": [{
    "type": "mixed",
    "tag": "mixed-in",
    "listen": "127.0.0.1",
    "listen_port": $TEST_PORT
  }],
  "outbounds": [
    $outbound_json,
    {"type": "direct", "tag": "direct"}
  ]
}
EOF

    # Run sing-box in background
    /usr/bin/sing-box run -c "$temp_path" >/dev/null 2>&1 &
    local sb_pid=$!
    
    # Wait for sing-box to start
    sleep 2
    
    if ! kill -0 $sb_pid 2>/dev/null; then
        rm -f "$temp_path"
        echo "error:start_failed"
        return
    fi
    
    # Run curl country test
    local country
    country=$(curl -s -m 5 --socks5-hostname 127.0.0.1:$TEST_PORT "https://ipinfo.io/country" 2>/dev/null)
    local curl_res=$?
    
    # Terminate sing-box
    kill $sb_pid 2>/dev/null
    wait $sb_pid 2>/dev/null
    rm -f "$temp_path"
    
    if [ $curl_res -ne 0 ] || [ -z "$country" ]; then
        echo "error:curl_failed"
        return
    fi
    
    # Trim whitespace/newlines
    echo "$country" | tr -d ' \n\r'
}

# Get top 5 nodes currently in balancer
nodes=$(ucode -e "
let fs = require('fs');
let f = fs.open('$CONFIG_FILE', 'r');
let cfg = json(f.read('all'));
f.close();
for (let o in cfg.outbounds) {
    if (o.tag == 'balancer') {
        let core = ['tunnel-zitel', 'tunnel-rightel', 'tunnel-mobinnet', 'ssh-vps-zitel', 'ssh-vps-rightel', 'ssh-vps-mobinnet'];
        let count = 0;
        for (let tag in o.outbounds) {
            if (index(core, tag) < 0 && count < 5) {
                print(tag, '\n');
                count++;
            }
        }
        break;
    }
}
" 2>/dev/null)

echo "Checking countries for top balancer nodes:"
echo "$nodes"
echo "----------------------------------------"

old_ifs="$IFS"
IFS=$'\n'
for node in $nodes; do
    IFS="$old_ifs"
    if [ -n "$node" ]; then
        echo -n "Node '$node': "
        res=$(test_node_country "$node")
        echo "$res"
    fi
    IFS=$'\n'
done
IFS="$old_ifs"
