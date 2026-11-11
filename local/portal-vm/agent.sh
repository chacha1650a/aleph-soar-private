#!/bin/bash
# haedam lab: install Wazuh agent 4.9.0 as ID 010 with FIM on the portal web root.
set -euo pipefail
KEYFILE=/tmp/agent010.key
if ! dpkg -s wazuh-agent >/dev/null 2>&1; then
  curl -fsSL https://packages.wazuh.com/key/GPG-KEY-WAZUH | sudo gpg --dearmor -o /usr/share/keyrings/wazuh.gpg
  echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" | sudo tee /etc/apt/sources.list.d/wazuh.list >/dev/null
  sudo apt-get -qq update
  sudo WAZUH_MANAGER=10.250.0.100 WAZUH_AGENT_NAME=haedam-portal DEBIAN_FRONTEND=noninteractive apt-get -qq install -y wazuh-agent=4.9.0-1 >/dev/null
  sudo apt-mark hold wazuh-agent >/dev/null
fi
sudo bash -c "echo y | /var/ossec/bin/manage_agents -i \"\$(cat $KEYFILE)\" >/dev/null"
rm -f $KEYFILE
C=/var/ossec/etc/ossec.conf
sudo python3 - <<'PY'
import re
p='/var/ossec/etc/ossec.conf'; s=open(p).read()
s=re.sub(r'<enrollment>.*?</enrollment>', '<enrollment><enabled>no</enabled></enrollment>', s, flags=re.S)
if '<enrollment>' not in s:
    s=s.replace('</client>', '  <enrollment><enabled>no</enabled></enrollment>\n  </client>',1)
d='<directories realtime="yes" check_all="yes">/home/haedam/haedam-portal-frontend/dist</directories>'
if d not in s:
    s=s.replace('<syscheck>', '<syscheck>\n    '+d, 1)
open(p,'w').write(s)
PY
sudo grep -n -E "<address>|haedam-portal-frontend|<enabled>no</enabled></enrollment>" $C | head
sudo systemctl enable --now wazuh-agent >/dev/null 2>&1; sudo systemctl restart wazuh-agent; sleep 8
systemctl is-active wazuh-agent
sudo grep -E "Connected to the server|ERROR" /var/ossec/logs/ossec.log | tail -3
