#!/bin/sh
CONFIG_FILE="/etc/sing-box/config.json"
candidates=$(ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) exit(1);
    let cfg = json(f.read('all'));
    f.close();
    let core_tunnels = ['tunnel-zitel', 'tunnel-rightel', 'tunnel-mobinnet', 'ssh-vps-zitel', 'ssh-vps-rightel', 'ssh-vps-mobinnet', 'balancer', 'balancer-streaming', 'direct', 'block'];
    for (let o in cfg.outbounds) {
        if (o.server && o.server_port && index(core_tunnels, o.tag) < 0) {
            print(o.tag, '|', o.server, '|', o.server_port, '\n');
        }
    }
" 2>/dev/null | head -n 10)

echo "Found candidates:"
echo "$candidates"
echo "-----------------------------------"

# Enable IFS=newline to loop over lines
old_ifs="$IFS"
IFS=$'\n'
for cand in $candidates; do
    IFS="$old_ifs"
    tag="${cand%%|*}"
    remain="${cand#*|}"
    host="${remain%%|*}"
    port="${remain#*|}"
    
    # Strip brackets from IPv6 host if present
    host=$(echo "$host" | tr -d '[]')
    
    echo "Testing '$tag' at '$host':'$port'..."
    ms=$(ucode -e "
        let s = require('socket');
        let t1 = clock();
        let ms1 = t1[0] * 1000 + int(t1[1] / 1000000);
        let sock = s.connect('$host', $port, null, 2000);
        if (sock) {
            let t2 = clock();
            let ms2 = t2[0] * 1000 + int(t2[1] / 1000000);
            sock.close();
            print(ms2 - ms1);
        } else {
            print(-1);
        }
    " 2>&1)
    echo "Result for '$tag': $ms"
    IFS=$'\n'
done
IFS="$old_ifs"
