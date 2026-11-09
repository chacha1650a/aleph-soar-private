# Wazuh 4.9.0 single-node를 이 PC의 Docker에 준비한다. 한 번만 실행한다.
# 하는 일: 공식 wazuh-docker v4.9.0 복제 -> 인증서 생성 -> syslog_output 삽입. 컨테이너는 시작하지 않는다.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$up = Join-Path $here 'upstream'
if (-not (Test-Path $up)) {
  git clone --depth 1 --branch v4.9.0 https://github.com/wazuh/wazuh-docker.git $up
}
$sn = Join-Path $up 'single-node'
Push-Location $sn
try {
  if (-not (Test-Path 'config/wazuh_indexer_ssl_certs/root-ca.pem')) {
    docker compose -f generate-indexer-certs.yml run --rm generator
  }
} finally { Pop-Location }
$conf = Join-Path $sn 'config/wazuh_cluster/wazuh_manager.conf'
$snippet = Get-Content (Join-Path $here 'syslog-output.xml') -Raw
$text = Get-Content $conf -Raw
if ($text -notmatch '<syslog_output>') {
  $i = $text.LastIndexOf('</ossec_config>')
  $text = $text.Insert($i, $snippet + "`n")
  Set-Content -Path $conf -Value $text -Encoding utf8
  Write-Host 'syslog_output 블록을 넣었습니다.'
}
docker network inspect wazuh-net *> $null; if ($LASTEXITCODE -ne 0) { docker network create wazuh-net | Out-Null }
Write-Host '준비 완료. local/up.ps1로 시작합니다.'
