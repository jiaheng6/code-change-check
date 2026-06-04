param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ToolArgs
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolScript = Join-Path $scriptDir "scripts/code_change_check.py"

function Test-Python310 {
    param(
        [string] $Command,
        [string[]] $CommandArgs
    )

    try {
        & $Command @CommandArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$pythonCommand = $null
$pythonArgs = @()

if (Get-Command python -ErrorAction SilentlyContinue) {
    python --version | Out-Null
    if (Test-Python310 -Command "python" -CommandArgs @()) {
        $pythonCommand = "python"
        $pythonArgs = @()
    }
}

if (-not $pythonCommand -and (Get-Command py -ErrorAction SilentlyContinue)) {
    py -3 --version | Out-Null
    if (Test-Python310 -Command "py" -CommandArgs @("-3")) {
        $pythonCommand = "py"
        $pythonArgs = @("-3")
    }
}

if (-not $pythonCommand) {
    Write-Host "未检测到 Python 3.10+。"
    Write-Host "请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/"
    Write-Host "安装后请确认 python 或 py 命令可用。"
    exit 1
}

& $pythonCommand @pythonArgs $toolScript @ToolArgs
exit $LASTEXITCODE
