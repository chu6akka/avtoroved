$ErrorActionPreference = 'Stop'
$corePython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$coreRoot = Split-Path -Parent $PSScriptRoot

Add-Type -AssemblyName PresentationFramework

if (-not (Test-Path -LiteralPath $corePython)) {
    [System.Windows.MessageBox]::Show(
        'Компоненты новой программы не установлены. Откройте authoroved_core\README.md.',
        'Авторовед Core'
    ) | Out-Null
    exit 1
}

try {
    # pythonw.exe сам не открывает консоль. WindowStyle=Hidden здесь нельзя
    # использовать: на части систем он скрывает и главное окно Qt.
    $coreProcess = Start-Process `
        -FilePath $corePython `
        -ArgumentList '-m', 'authoroved_core.app' `
        -WorkingDirectory $coreRoot `
        -PassThru

    Start-Sleep -Milliseconds 1200
    if ($coreProcess.HasExited -and $coreProcess.ExitCode -ne 0) {
        [System.Windows.MessageBox]::Show(
            'Программа не запустилась. Подробности: authoroved_core\.local\technical.log',
            'Авторовед Core'
        ) | Out-Null
        exit $coreProcess.ExitCode
    }
} catch {
    [System.Windows.MessageBox]::Show(
        ('Не удалось запустить программу: ' + $_.Exception.Message),
        'Авторовед Core'
    ) | Out-Null
    exit 1
}
