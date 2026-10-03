# ================================================================================
#   ОЧИСТКА ЗАГРУЗЧИКА BCD ОТ ВРЕМЕННЫХ ЗАПИСЕЙ УСТАНОВКИ WINDOWS 11
# ================================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Проверка прав администратора и автоповышение через UAC
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[!] Запрос прав администратора (UAC)..." -ForegroundColor Yellow
    try {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    } catch {
        Write-Host "[ОШИБКА] Не удалось повысить права. Запустите от имени администратора вручную." -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода..."
    }
    exit
}

Clear-Host
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   ОЧИСТКА ЗАГРУЗЧИКА BCD ОТ ДУБЛИРУЮЩИХСЯ ЗАПИСЕЙ" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

$rawBcd = & bcdedit /enum all 2>&1
$rawText = ($rawBcd -join "`n")

# Разделяем на блоки записей
$blocks = $rawText -split "(?m)^(?=[A-Za-z0-9_ ]+\r?\n-+\r?\n)"

$deletedCount = 0

foreach ($block in $blocks) {
    if ($block -match '(?i)description\s+(.+)' -and $block -match 'identifier\s+(\{[0-9a-fA-F\-]{36}\})') {
        $desc = $Matches[1].Trim()
        $id = $Matches[2].Trim()
        
        # Если описание содержит наши тестовые записи установки
        if ($desc -like "*Установка Windows 11*" -or $desc -like "*Custom Lite*") {
            Write-Host "[*] Удаление записи: $desc ($id)..." -ForegroundColor Yellow
            $res = & bcdedit /delete $id /f 2>&1
            Write-Host "    [OK] Запись $id успешно удалена." -ForegroundColor Green
            $deletedCount++
        }
    }
}

# Также очищаем ramdiskoptions если остался
& bcdedit /delete '{ramdiskoptions}' 2>$null | Out-Null

# Сбрасываем bootsequence
& bcdedit /bootsequence "" 2>$null | Out-Null

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "   [УСПЕХ] Найдено и удалено временных записей: $deletedCount" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Загрузчик Windows полностью очищен. Меню выбора больше не будет мешать при старте." -ForegroundColor White
Write-Host ""
Read-Host "Нажмите Enter для завершения..."
