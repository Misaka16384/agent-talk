# One-line installer for agent_talk (Windows PowerShell 5.1+ or PowerShell 7):
#
#   irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1 | iex
#
# To pass arguments to install.py (e.g. uninstall):
#
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1))) --uninstall
#
# It downloads the repository into a temporary folder, runs install.py, and deletes the folder.

$ErrorActionPreference = 'Stop'
$repo = if ($env:AGENT_TALK_REPO) { $env:AGENT_TALK_REPO } else { 'Misaka16384/agent-talk' }
$ref = if ($env:AGENT_TALK_REF) { $env:AGENT_TALK_REF } else { 'main' }

# Find Python 3.7+. The Microsoft Store "python" stub fails the version check and is skipped.
$py = $null
foreach ($candidate in 'py -3', 'python', 'python3') {
    $parts = $candidate -split ' '
    $rest = @($parts | Select-Object -Skip 1)
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    try {
        $null = & $parts[0] @rest -c 'import sys; sys.exit(sys.version_info < (3, 7))' 2>&1
        if ($LASTEXITCODE -eq 0) { $py = $parts; break }
    } catch { }
}
if (-not $py) {
    Write-Error 'agent_talk: Python 3.7 or newer is required (https://www.python.org/downloads/).'
    return
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ('agent_talk_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $tmp 'src.zip'
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$repo/zip/$ref" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
    $pyArgs = @($py | Select-Object -Skip 1) + @((Join-Path $src.FullName 'install.py')) + @($args)
    & $py[0] @pyArgs
    if ($LASTEXITCODE) { Write-Error "agent_talk: install.py exited with code $LASTEXITCODE" }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
