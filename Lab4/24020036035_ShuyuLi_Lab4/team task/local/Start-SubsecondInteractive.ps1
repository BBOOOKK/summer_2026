$ErrorActionPreference = 'Stop'
$labRoot = Split-Path $PSScriptRoot -Parent
$workspacePath = $labRoot.Replace([char]92, [char]47)
if ($workspacePath -match '^([A-Za-z]):/(.*)$') {
    $workspacePath = '/mnt/' + $Matches[1].ToLower() + '/' + $Matches[2]
}
Write-Host 'Starting the 0.640 s native-physics race and visual timer...'
& wsl.exe -d Ubuntu-22.04 -u root --exec env LAB4_SUBSECOND=1 bash "$workspacePath/local/start_interactive.sh"
if ($LASTEXITCODE -ne 0) { throw "Race launcher exited with code $LASTEXITCODE" }
