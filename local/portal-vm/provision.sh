#!/bin/bash
# haedam lab: provision the portal VM (10.250.0.2). Run as user haedam with sudo.
set -euo pipefail
H=/home/haedam
sudo apt-get -qq update
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq install -y python3.12-venv >/dev/null
mkdir -p $H/haedam-portal-backend $H/haedam-portal-frontend
tar -xf /tmp/backend.tar -C $H/haedam-portal-backend
tar -xf /tmp/frontend-dist.tar -C $H/haedam-portal-frontend
cd $H/haedam-portal-backend
python3 -m venv .venv
.venv/bin/pip -q install --upgrade pip
.venv/bin/pip -q install -e .
mkdir -p instance
cat > instance/portal.env <<ENV
DATABASE_URL=sqlite:///$H/haedam-portal-backend/instance/haedam.sqlite3
FRONTEND_DIST=$H/haedam-portal-frontend/dist
COOKIE_SECURE=0
EVENT_LOG_PATH=$H/haedam-portal-backend/instance/events.jsonl
ASSET_ID=haedam-portal
GELF_ENABLED=1
GELF_HOST=10.250.0.100
GELF_PORT=12201
GELF_TRANSPORT=udp
RESPONSE_API_KEY=
RESPONSE_ALLOWED_CIDRS=
DASHBOARD_URL=
ENV
chmod 600 instance/portal.env
set -a; . instance/portal.env; set +a
.venv/bin/python -m flask --app haedam_portal:create_app db upgrade
if [ ! -f instance/demo-accounts.txt ]; then
  umask 077; .venv/bin/python -m flask --app haedam_portal:create_app seed-demo --confirm > instance/demo-accounts.txt 2>&1 || true
fi
sudo tee /etc/systemd/system/haedam-portal.service >/dev/null <<UNIT
[Unit]
Description=Haedam civic portal (Flask/Waitress, lab)
After=network-online.target
Wants=network-online.target
[Service]
User=haedam
WorkingDirectory=$H/haedam-portal-backend
EnvironmentFile=$H/haedam-portal-backend/instance/portal.env
ExecStart=$H/haedam-portal-backend/.venv/bin/waitress-serve --host=10.250.0.2 --port=5000 --threads=4 --call haedam_portal:create_app
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now haedam-portal >/dev/null 2>&1
sleep 3
systemctl is-active haedam-portal
curl -s -o /dev/null -w "health=%{http_code}\n" http://10.250.0.2:5000/api/v1/health
curl -s -o /dev/null -w "root=%{http_code}\n" http://10.250.0.2:5000/
echo "seed lines: $(wc -l < instance/demo-accounts.txt) (file kept private, not printed)"
