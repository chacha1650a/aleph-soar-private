# Start an interactive topic discussion using the user's default Claude model.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw 'Claude Code was not found. Install it or use prompts/claude-topic-discussion.md in your Claude app.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    # One ASCII line: .cmd shims cut multi-line arguments, and PS 5.1 reads BOM-less scripts as ANSI.
    & claude --permission-mode plan 'Read prompts/claude-topic-discussion.md and follow its request.'
}
finally {
    Pop-Location
}
