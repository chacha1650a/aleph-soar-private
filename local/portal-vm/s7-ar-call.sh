#!/bin/bash
# usage: ar.sh <file_key> <run_id>   (local lab manager API, upstream default test account)
cd /c/gov/team-project/aleph-soar-private/local/wazuh/upstream/single-node
U=$(grep -m1 "API_USERNAME" docker-compose.yml | sed 's/.*=//;s/[" ]//g'); P=$(grep -m1 "API_PASSWORD" docker-compose.yml | sed 's/.*API_PASSWORD=//;s/^"//;s/"$//')
T=$(curl -sk -u "$U:$P" -X POST "https://127.0.0.1:55000/security/user/authenticate?raw=true")
curl -sk -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -X PUT "https://127.0.0.1:55000/active-response?agents_list=010&pretty=false" -d "{\"command\":\"!s7-restore-ar\",\"arguments\":[\"$1\",\"$2\"]}" | python -c "import sys,json;d=json.load(sys.stdin);print('api error',d.get('error'),'affected',d['data'].get('affected_items'),'failed',d['data'].get('total_failed_items'))"
