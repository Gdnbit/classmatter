[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$errors = [System.Collections.Generic.List[string]]::new()
$markdownFiles = Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Filter '*.md' |
    Where-Object { $_.FullName -notmatch '[\\/](node_modules|dist|\.git|\.venv|__pycache__|\.pytest_cache)[\\/]' }

foreach ($file in $markdownFiles) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $text = $utf8.GetString($bytes)
    }
    catch {
        $errors.Add("Invalid UTF-8: $($file.FullName)")
        continue
    }

    if ($text.Contains([char]0xFFFD)) {
        $errors.Add("Replacement character found: $($file.FullName)")
    }

    $matches = [regex]::Matches($text, '!?(?:\[[^\]]*\])\((?<target>[^)]+)\)')
    foreach ($match in $matches) {
        $target = $match.Groups['target'].Value.Trim()
        if ($target.StartsWith('<') -and $target.EndsWith('>')) {
            $target = $target.Substring(1, $target.Length - 2)
        }
        if ($target -match '^(?:https?://|mailto:|#|chatgpt-conversation:|codex:)' -or [string]::IsNullOrWhiteSpace($target)) {
            continue
        }

        $pathPart = [System.Uri]::UnescapeDataString(($target -split '#', 2)[0])
        if ([string]::IsNullOrWhiteSpace($pathPart)) {
            continue
        }

        $resolved = if ([System.IO.Path]::IsPathRooted($pathPart)) {
            $pathPart
        }
        else {
            Join-Path $file.DirectoryName $pathPart
        }
        if (-not (Test-Path -LiteralPath $resolved)) {
            $relativeFile = [System.IO.Path]::GetRelativePath($RepoRoot, $file.FullName)
            $errors.Add("Broken local link in ${relativeFile}: $target")
        }
    }
}

if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Checked $($markdownFiles.Count) Markdown files."
