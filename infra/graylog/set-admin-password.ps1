# Graylog 관리자 비밀번호를 직접 정해 .env에 해시로 넣는다. 사용자가 자기 터미널에서 실행한다.
# 비밀번호는 화면에 나오지 않고, 해시(SHA-256)만 .env에 저장한다. 비밀번호 자체는 어디에도 남기지 않는다.
$envPath = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envPath)) { Write-Error ".env가 없습니다. .env.example을 복사해 .env를 만든 뒤 다시 실행하세요."; exit 1 }

$secure = Read-Host "Graylog 관리자 비밀번호" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ($plain.Length -lt 8) { Write-Error "8자 이상으로 정하세요."; exit 1 }

$bytes = [Text.Encoding]::UTF8.GetBytes($plain)
$hash = -join ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") })
$plain = $null

$lines = Get-Content $envPath
if ($lines -match '^GRAYLOG_ROOT_PASSWORD_SHA2=') {
    $lines = $lines | ForEach-Object { if ($_ -match '^GRAYLOG_ROOT_PASSWORD_SHA2=') { "GRAYLOG_ROOT_PASSWORD_SHA2=$hash" } else { $_ } }
} else {
    $lines += "GRAYLOG_ROOT_PASSWORD_SHA2=$hash"
}
Set-Content -Path $envPath -Value $lines -Encoding utf8
Write-Host "해시를 .env에 저장했습니다. 비밀번호는 저장하지 않았습니다."
