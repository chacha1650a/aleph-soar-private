# 로컬 랩 시작: Graylog -> n8n -> Wazuh -> 중계기. 순서대로 시작하고 상태를 보여 준다.
param([switch]$Down)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$loc = Join-Path $root 'local'
$envFile = Join-Path $loc '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $loc '.env.example') $envFile; Write-Host 'local/.env를 만들었습니다. BIND_IP를 확인하세요.' }
Get-Content $envFile | Where-Object { $_ -match '^\s*([A-Z_]+)=(.*)$' } | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item "env:$($k.Trim())" $v.Trim() }
$gl = Join-Path $root 'infra/graylog'
$n8 = Join-Path $root 'infra/n8n/docker-compose.yml'
$wz = Join-Path $loc 'wazuh'
$sn = Join-Path $wz 'upstream/single-node/docker-compose.yml'
if ($Down) {
  docker compose -f (Join-Path $wz 'relay.compose.yml') down
  docker compose -f $sn -f (Join-Path $wz 'docker-compose.override.yml') down
  docker compose -f $n8 down
  docker compose -f (Join-Path $gl 'docker-compose.yml') --env-file (Join-Path $gl '.env') down
  return
}
if (-not (Test-Path (Join-Path $gl '.env'))) { throw 'infra/graylog/.env가 없습니다. infra/graylog/README.md의 실행 순서 1~3을 먼저 하세요.' }
if (-not (Test-Path $sn)) { throw 'Wazuh가 준비되지 않았습니다. local/wazuh/setup.ps1을 먼저 실행하세요.' }
docker volume inspect n8n_data *> $null; if ($LASTEXITCODE -ne 0) { docker volume create n8n_data | Out-Null }
docker compose -f (Join-Path $gl 'docker-compose.yml') --env-file (Join-Path $gl '.env') up -d
docker compose -f $n8 up -d
docker compose -f $sn -f (Join-Path $wz 'docker-compose.override.yml') up -d
docker compose -f (Join-Path $wz 'relay.compose.yml') up -d
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
