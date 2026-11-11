#!/bin/sh
# haedam lab: start Suricata EVE alert forwarder at boot (pfSense runs rc.d/*.sh)
case "$1" in
  start) /usr/sbin/daemon -r -f -p /var/run/haedam-eve-forward.pid /usr/local/bin/python3.11 /root/haedam-eve-forward.py ;;
  stop)  [ -f /var/run/haedam-eve-forward.pid ] && kill "$(cat /var/run/haedam-eve-forward.pid)" ;;
  *) echo "usage: $0 start|stop" ;;
esac
