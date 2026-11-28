param(
    [Parameter(Mandatory = $true)]
    [string]$QueryOrVerse,

    [switch]$Rejudge,
    [string]$StatusFilter = "",
    [switch]$AI,
    [switch]$Clipboard
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$argsList = @("search_and_judge.py", "--query", $QueryOrVerse)
if ($Rejudge) { $argsList += "--rejudge" }
if ($StatusFilter) { $argsList += @("--status", $StatusFilter) }
if ($AI) { $argsList += "--ai" }

$output = python @argsList
if ($Clipboard) {
    $output | Set-Clipboard
    Write-Host "Copied Graphē 10-point output for '$QueryOrVerse' to clipboard."
}
$output
