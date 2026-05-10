<#
.SYNOPSIS
    Write a Markdown note to the vault inbox with UTF-8 encoding (no BOM).

.DESCRIPTION
    PowerShell 5.1 Set-Content defaults to ANSI encoding, which corrupts
    Korean and other non-ASCII characters. This script writes UTF-8 without
    BOM, which Obsidian and the Python vault layer both expect.

.PARAMETER Content
    The text content to write. Accepts pipeline input.

.PARAMETER FileName
    The filename for the note (e.g. "my-note.md"). Defaults to a timestamp.

.EXAMPLE
    "# 첫 메모`n`nAI, 업무 기록" | .\scripts\Write-InboxNote.ps1 -FileName "first-note.md"

.EXAMPLE
    .\scripts\Write-InboxNote.ps1 -FileName "idea.md" -Content "# Idea`nDetails here."
#>
param(
    [Parameter(ValueFromPipeline = $true, Mandatory = $true)]
    [string]$Content,

    [Parameter()]
    [string]$FileName = "note-$(Get-Date -Format 'yyyyMMdd-HHmmss').md"
)

$vaultPath = $env:SECOND_BRAIN_VAULT_PATH
if (-not $vaultPath) {
    Write-Error "SECOND_BRAIN_VAULT_PATH is not set. Export it in your PowerShell profile."
    exit 1
}

$inboxDir = Join-Path $vaultPath "raw\inbox"
if (-not (Test-Path $inboxDir)) {
    New-Item -ItemType Directory -Path $inboxDir -Force | Out-Null
}

$destPath = Join-Path $inboxDir $FileName
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($destPath, $Content, $utf8NoBom)

Write-Host "Written to: $destPath"
