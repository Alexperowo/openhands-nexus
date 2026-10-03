# ================================================================================
#   ПОДГОТОВКА ЧИСТОЙ УСТАНОВКИ WINDOWS 11 БЕЗ ФЛЕШКИ (ПРОТОКОЛ CLEAN SLATE)
# ================================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Проверка прав администратора и автоповышение через UAC
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[!] Запрос прав администратора (UAC)..." -ForegroundColor Yellow
    try {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    } catch {
        Write-Host "[ОШИБКА] Не удалось повысить права. Запустите скрипт от имени администратора вручную." -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода..."
    }
    exit
}

Clear-Host
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   ПОДГОТОВКА ЧИСТОЙ УСТАНОВКИ WINDOWS 11 БЕЗ ФЛЕШКИ (ПРОТОКОЛ CLEAN SLATE)" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

# 2. Проверка наличия установочных файлов на диске D:
$bootWim = "D:\Win11_Setup\sources\boot.wim"
$bootSdi = "D:\Win11_Setup\boot\boot.sdi"
$installWim = "D:\Win11_Setup\sources\install.wim"

Write-Host "[*] Проверка установочных файлов на диске D:..." -ForegroundColor Gray

if (-not (Test-Path $bootWim)) {
    Write-Host "[ОШИБКА] Файл $bootWim не найден!" -ForegroundColor Red
    Write-Host "Убедитесь, что дистрибутив распакован на диск D: в папку Win11_Setup." -ForegroundColor Yellow
    Read-Host "Нажмите Enter для выхода..."
    exit 1
}

if (-not (Test-Path $bootSdi)) {
    Write-Host "[ОШИБКА] Файл $bootSdi не найден!" -ForegroundColor Red
    Read-Host "Нажмите Enter для выхода..."
    exit 1
}

if (-not (Test-Path $installWim)) {
    Write-Host "[ОШИБКА] Файл $installWim не найден!" -ForegroundColor Red
    Read-Host "Нажмите Enter для выхода..."
    exit 1
}

Write-Host "    [OK] boot.wim, boot.sdi, install.wim найдены на диске D:." -ForegroundColor Green
Write-Host ""

# 3. Настройка параметров RAM-диска (bcdedit ramdiskoptions)
Write-Host "[1/4] Настройка параметров RAM-диска (bcdedit ramdiskoptions)..." -ForegroundColor Yellow
cmd.exe /c "bcdedit /create {ramdiskoptions} /d ""Ramdisk options"" >nul 2>&1"
& bcdedit /set "{ramdiskoptions}" ramdisksdidevice partition=D: | Out-Null
& bcdedit /set "{ramdiskoptions}" ramdisksdipath "\Win11_Setup\boot\boot.sdi" | Out-Null
Write-Host "    [OK] Секция {ramdiskoptions} привязана к D:\Win11_Setup\boot\boot.sdi" -ForegroundColor Green

# 4. Создание записи установщика Windows 11 в системном загрузчике
Write-Host "[2/4] Создание записи установщика Windows 11 в системном загрузчике..." -ForegroundColor Yellow
$createOutput = & bcdedit /create /d "Установка Windows 11 Custom Lite" /application osloader 2>&1

$bootGuid = $null
if ($createOutput -match '\{([0-9a-fA-F\-]{36})\}') {
    $bootGuid = "{$($Matches[1])}"
}

if (-not $bootGuid) {
    Write-Host "[ОШИБКА] Не удалось создать запись загрузчика:`n$createOutput" -ForegroundColor Red
    Read-Host "Нажмите Enter для выхода..."
    exit 1
}

Write-Host "    [OK] Создана запись загрузчика: $bootGuid" -ForegroundColor Green

# 5. Привязка WinPE и UEFI-загрузчика (winload.efi)
Write-Host "[3/4] Привязка WinPE и UEFI-загрузчика (winload.efi)..." -ForegroundColor Yellow
& bcdedit /set $bootGuid device "ramdisk=[D:]\Win11_Setup\sources\boot.wim,{ramdiskoptions}" | Out-Null
& bcdedit /set $bootGuid osdevice "ramdisk=[D:]\Win11_Setup\sources\boot.wim,{ramdiskoptions}" | Out-Null
& bcdedit /set $bootGuid path "\windows\system32\boot\winload.efi" | Out-Null
& bcdedit /set $bootGuid systemroot "\windows" | Out-Null
& bcdedit /set $bootGuid winpe yes | Out-Null
& bcdedit /set $bootGuid detecthal yes | Out-Null
& bcdedit /displayorder $bootGuid /addlast | Out-Null
& bcdedit /timeout 15 | Out-Null
Write-Host "    [OK] Параметры WinPE и RAM-диска успешно прописаны." -ForegroundColor Green

# 6. Назначение разовой загрузки установщика при следующей перезагрузке
Write-Host "[4/4] Назначение разовой загрузки установщика при перезагрузке..." -ForegroundColor Yellow
& bcdedit /bootsequence $bootGuid | Out-Null
Write-Host "    [OK] Флаг bootsequence установлен на $bootGuid." -ForegroundColor Green
Write-Host ""

# 7. Финальное сообщение и инструкции
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "   [УСПЕХ] ВСЁ ГОТОВО К ЧИСТОЙ УСТАНОВКЕ БЕЗ ФЛЕШКИ!" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Установщик загрузится прямо в оперативную память (RAM) при следующей перезагрузке." -ForegroundColor White
Write-Host ""
Write-Host "ИНСТРУКЦИЯ ПО УСТАНОВКЕ:" -ForegroundColor Yellow
Write-Host "1. Компьютер перезагрузится и автоматически запустит установщик Windows 11." -ForegroundColor White
Write-Host "2. На экране выбора диска выберите ваш диск C: (NVMe SSD на ~237 ГБ)." -ForegroundColor White
Write-Host "3. Нажмите кнопку 'Форматировать' и затем нажмите 'Далее'." -ForegroundColor White
Write-Host "4. ВНИМАНИЕ: Диски D: (SATA1) и K: (SATA2) НЕ ТРОГАЙТЕ - там лежат ваши данные!" -ForegroundColor Red
Write-Host "5. Вся остальная установка (программы, драйверы, профили) пройдет АВТОМАТИЧЕСКИ." -ForegroundColor White
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Gray

$choice = Read-Host "Перезагрузить компьютер прямо сейчас? (Y/N, по умолчанию N)"
if ($choice -ne "Y" -and $choice -ne "y") {
    Write-Host ""
    Write-Host "Перезагрузка отложена." -ForegroundColor Cyan
    Write-Host "Когда будете готовы, просто перезагрузите компьютер через меню Пуск -" -ForegroundColor White
    Write-Host "установщик запустится автоматически!" -ForegroundColor Green
    Write-Host ""
    Read-Host "Нажмите Enter для завершения..."
    exit 0
}

Write-Host ""
Write-Host "Перезагрузка через 5 секунд..." -ForegroundColor Yellow
& shutdown.exe /r /t 5 /c "Запуск чистой установки Windows 11 Custom Lite..."
