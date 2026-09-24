$wscript = New-Object -ComObject WScript.Shell
$desktop = 'C:\Users\User\Desktop'

# Create Desktop root shortcut to open OpenHands UI in default browser
$shortcutPath = Join-Path $desktop 'OpenHands Local — Открыть.lnk'
$shortcut = $wscript.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'http://localhost:8000'
$shortcut.Description = 'Открыть веб-интерфейс OpenHands Nexus'
$shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,14'
$shortcut.Save()

Write-Host "Created: $shortcutPath -> http://localhost:8000"
