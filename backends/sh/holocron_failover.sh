#!/bin/sh

CONFIG_FILE="/etc/sing-box/config.json"
TEST_URL="https://www.gstatic.com/generate_204"
LATENCY_THRESHOLD_MS=2000
CHECK_INTERVAL_S=20
TEST_PORT=10089

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

get_active_tag() {
    ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) exit(1);
    let cfg = json(f.read('all'));
    f.close();
    print(cfg.route?.final || '');
    " 2>/dev/null
}

get_candidate_pool() {
    ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) exit(1);
    let cfg = json(f.read('all'));
    f.close();
    for (let o in cfg.outbounds) {
        if (o.tag == 'balancer' && o.outbounds) {
            for (let tag in o.outbounds) {
                print(tag, '\n');
            }
            exit(0);
        }
    }
    exit(1);
    " 2>/dev/null
}

get_outbound_block() {
    local tag="$1"
    # Extract the JSON block for the outbound with the matching tag from config.json
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

test_node() {
    local tag="$1"
    local outbound_json
    outbound_json=$(get_outbound_block "$tag")
    if [ -z "$outbound_json" ]; then
        echo "-1:missing_outbound"
        return
    fi
    
    # Create temp config
    local temp_path="/tmp/test_sb_${TEST_PORT}.json"
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
    
    # Check if sing-box is still running
    if ! kill -0 $sb_pid 2>/dev/null; then
        rm -f "$temp_path"
        echo "-1:start_failed"
        return
    fi
    
    # Run curl test
    local curl_out
    curl_out=$(curl -s -m 8 -o /dev/null -w "%{http_code}:%{time_total}" --socks5-hostname 127.0.0.1:$TEST_PORT "$TEST_URL" 2>/dev/null)
    local curl_res=$?
    
    # Terminate sing-box
    kill $sb_pid 2>/dev/null
    wait $sb_pid 2>/dev/null
    rm -f "$temp_path"
    
    if [ $curl_res -ne 0 ] || [ -z "$curl_out" ]; then
        echo "-1:curl_failed"
        return
    fi
    
    local code="${curl_out%%:*}"
    local time_total="${curl_out#*:}"
    
    case "$code" in
        200|204|301|302|307|308)
            local ms
            ms=$(awk -v t="$time_total" 'BEGIN { print int(t * 1000) }')
            echo "$ms:ok"
            ;;
        *)
            echo "-1:http_code_${code}"
            ;;
    esac
}

switch_active_node() {
    local old_tag="$1"
    local new_tag="$2"
    log "Switching default proxy detour from $old_tag to $new_tag ..."
    
    # Update config.json using ucode
    ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) { print('ERROR: Cannot open config file'); exit(1); }
    let cfg = json(f.read('all'));
    f.close();
    
    if (!cfg.route) cfg.route = {};
    cfg.route.final = '$new_tag';
    
    if (cfg.dns && cfg.dns.servers) {
        for (let s in cfg.dns.servers) {
            if (s.tag == 'dns-remote') {
                s.detour = '$new_tag';
            }
        }
    }
    
    let out = fs.open('$CONFIG_FILE', 'w');
    if (!out) { print('ERROR: Cannot write config file'); exit(1); }
    out.write(cfg);
    out.close();
    print('SUCCESS');
    " 2>/dev/null
}

refresh_balancer_pools() {
    log "Performing periodic balancer optimization scan..."
    
    # 1. Get all candidates
    local candidates
    candidates=$(ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) exit(1);
    let cfg = json(f.read('all'));
    f.close();
    let core_tunnels = ['tunnel-zitel', 'tunnel-rightel', 'tunnel-mobinnet', 'ssh-vps-zitel', 'ssh-vps-rightel', 'ssh-vps-mobinnet', 'balancer', 'balancer-streaming', 'balancer-gemini', 'direct', 'block'];
    for (let o in cfg.outbounds) {
        if (o.server && o.server_port && index(core_tunnels, o.tag) < 0) {
            print(o.tag, '|', o.server, '|', o.server_port, '\n');
        }
    }
    " 2>/dev/null)
    
    if [ -z "$candidates" ]; then
        log "WARNING: No proxy candidates found for balancer refresh."
        return
    fi
    
    # 2. Ping all candidates in parallel using ucode sockets
    local tmp_results="/tmp/ping_sweep_$$.txt"
    rm -f "$tmp_results"
    touch "$tmp_results"
    
    local running_jobs=0
    local max_parallel=30
    
    # Enable IFS=newline to loop over lines
    local old_ifs="$IFS"
    IFS=$'\n'
    for cand in $candidates; do
        IFS="$old_ifs"
        local tag="${cand%%|*}"
        local remain="${cand#*|}"
        local host="${remain%%|*}"
        local port="${remain#*|}"
        host=$(echo "$host" | tr -d '[]')
        
        (
            local ms
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
            " 2>/dev/null)
            echo "$tag:${ms:- -1}" >> "$tmp_results"
        ) &
        
        running_jobs=$((running_jobs + 1))
        if [ $((running_jobs % max_parallel)) -eq 0 ]; then
            wait
        fi
        IFS=$'\n'
    done
    IFS="$old_ifs"
    wait
    
    # 3. Sort results in ucode, select top 15, and update config.json
    local top_nodes
    top_nodes=$(ucode -e "
    let fs = require('fs');
    let f = fs.open('$tmp_results', 'r');
    if (!f) exit(1);
    let lines = split(f.read('all'), '\n');
    f.close();
    
    let results = [];
    for (let line in lines) {
        if (!line) continue;
        let parts = split(line, ':');
        let tag = parts[0];
        let ms = int(parts[1]);
        if (ms >= 0) {
            push(results, {tag: tag, ms: ms});
        }
    }
    
    sort(results, (a, b) => a.ms - b.ms);
    let top = [];
    let count = length(results) < 15 ? length(results) : 15;
    for (let i = 0; i < count; i++) {
        push(top, results[i].tag);
    }
    print(join(',', top));
    " 2>/dev/null)
    
    rm -f "$tmp_results"
    
    if [ -z "$top_nodes" ]; then
        log "WARNING: No healthy candidate nodes found during balancer scan."
        return
    fi
    
    log "Top healthy nodes found: $top_nodes"
    
    # 4. Write updated outbounds to balancer and balancer-streaming in config.json
    local update_res
    update_res=$(ucode -e "
    let fs = require('fs');
    let f = fs.open('$CONFIG_FILE', 'r');
    if (!f) { print('ERROR: Cannot open config'); exit(1); }
    let cfg = json(f.read('all'));
    f.close();
    
    let top_arr = split('$top_nodes', ',');
    let core_tunnels = [
        'ss-zitel', 'ss-rightel', 'ss-mobinnet',
        'tunnel-zitel', 'tunnel-rightel', 'tunnel-mobinnet',
        'ssh-vps-zitel', 'ssh-vps-rightel', 'ssh-vps-mobinnet',
        'vless-reality-vps', 'vless-reality-zitel', 'vless-reality-rightel', 'vless-reality-mobinnet',
        'nooshdaroo'
    ];
    let existing_tags = [];
    for (let o in cfg.outbounds) {
        push(existing_tags, o.tag);
    }
    
    let updated = false;
    for (let o in cfg.outbounds) {
        if (o.tag == 'balancer' || o.tag == 'balancer-streaming' || o.tag == 'balancer-gemini') {
            let current = o.outbounds || [];
            let preserved_core = [];
            for (let t in current) {
                if (index(core_tunnels, t) >= 0 && index(existing_tags, t) >= 0) {
                    push(preserved_core, t);
                }
            }
            if (length(preserved_core) == 0) {
                for (let t in core_tunnels) {
                    if (index(existing_tags, t) >= 0) {
                        push(preserved_core, t);
                    }
                }
            }
            let final_detours = [...preserved_core, ...top_arr];
            if (join(',', current) != join(',', final_detours)) {
                o.outbounds = final_detours;
                updated = true;
            }
        }
    }
    
    if (updated) {
        let out = fs.open('$CONFIG_FILE', 'w');
        if (!out) { print('ERROR: Cannot write config'); exit(1); }
        out.write(cfg);
        out.close();
        print('UPDATED');
    } else {
        print('NO_CHANGE');
    }
    " 2>/dev/null)
    
    if [ "$update_res" = "UPDATED" ]; then
        log "Balancer pools updated in config.json. Restarting sing-box..."
        /etc/init.d/sing-box restart
    else
        log "No change in balancer pools. Skipping sing-box restart."
    fi
}

check_and_failover() {
    local active_tag
    active_tag=$(get_active_tag)
    if [ -z "$active_tag" ]; then
        return
    fi
    
    # Ignore balancer tags
    if [ "$active_tag" = "balancer" ] || [ "$active_tag" = "balancer-streaming" ] || [ "$active_tag" = "balancer-gemini" ]; then
        return
    fi
    
    # Ignore direct and block tags
    if [ "$active_tag" = "direct" ] || [ "$active_tag" = "block" ]; then
        return
    fi
    
    # Check if active tag is in the candidate pool
    local in_pool=0
    local pool
    pool=$(get_candidate_pool)
    for cand in $pool; do
        if [ "$cand" = "$active_tag" ]; then
            in_pool=1
            break
        fi
    done
    
    if [ $in_pool -eq 0 ]; then
        # Active tag is not in pool (e.g. user selected a static node). Skip monitoring.
        return
    fi
    
    log "Checking active proxy node: $active_tag ..."
    local check_res
    check_res=$(test_node "$active_tag")
    local latency="${check_res%%:*}"
    local status="${check_res#*:}"
    
    if [ "$latency" -gt 0 ] && [ "$latency" -lt $LATENCY_THRESHOLD_MS ]; then
        log "SUCCESS: Active node $active_tag is healthy (${latency}ms)."
        return
    fi
    
    log "ALERT: Active node $active_tag failed check (latency=$latency, status=$status). Initiating failover..."
    
    # Find next candidate in round-robin order
    local next_tag=""
    local found_active=0
    # First pass: find candidate after active_tag
    for cand in $pool; do
        if [ "$cand" = "balancer" ] || [ "$cand" = "direct" ] || [ "$cand" = "block" ]; then
            continue
        fi
        if [ $found_active -eq 1 ]; then
            log "Testing candidate node: $cand ..."
            local cand_res
            cand_res=$(test_node "$cand")
            local c_lat="${cand_res%%:*}"
            if [ "$c_lat" -gt 0 ] && [ "$c_lat" -lt $LATENCY_THRESHOLD_MS ]; then
                log "FOUND: Candidate node $cand is healthy (${c_lat}ms)!"
                next_tag="$cand"
                break
            fi
        fi
        if [ "$cand" = "$active_tag" ]; then
            found_active=1
        fi
    done
    
    # Second pass (wrap around): find candidate before active_tag
    if [ -z "$next_tag" ]; then
        for cand in $pool; do
            if [ "$cand" = "$active_tag" ]; then
                break
            fi
            if [ "$cand" = "balancer" ] || [ "$cand" = "direct" ] || [ "$cand" = "block" ]; then
                continue
            fi
            log "Testing candidate node: $cand ..."
            local cand_res
            cand_res=$(test_node "$cand")
            local c_lat="${cand_res%%:*}"
            if [ "$c_lat" -gt 0 ] && [ "$c_lat" -lt $LATENCY_THRESHOLD_MS ]; then
                log "FOUND: Candidate node $cand is healthy (${c_lat}ms)!"
                next_tag="$cand"
                break
            fi
        done
    fi
    
    if [ -n "$next_tag" ]; then
        local switch_res
        switch_res=$(switch_active_node "$active_tag" "$next_tag")
        if [ "$switch_res" = "SUCCESS" ]; then
            /etc/init.d/sing-box restart
            log "FAILOVER COMPLETE: Switched default proxy detour to $next_tag"
        else
            log "ERROR: Switch to $next_tag failed: $switch_res"
        fi
    else
        log "CRITICAL: All candidate nodes failed checks! No backup proxy available."
    fi
}

# Daemon loop
log "Holocron Failover Watchdog (Shell Edition) starting..."
counter=0
while true; do
    if [ $((counter % 45)) -eq 0 ]; then
        refresh_balancer_pools
    fi
    check_and_failover
    counter=$((counter + 1))
    sleep $CHECK_INTERVAL_S
done
