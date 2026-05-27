#!/bin/sh

case "$ACTION" in
    ifup|ifupdate)
        /usr/share/passwall2/holocron_refresh_gemini_ipset.sh >/tmp/log/holocron_gemini_ipset.log 2>&1 &
        ;;
esac
