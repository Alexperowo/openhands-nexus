$wscript = New-Object -ComObject WScript.Shell
$desktop = 'C:\Users\User\Desktop'
$folder = 'C:\Users\User\Desktop\OpenHands Local'

Write-Host "=== FOLDER: $folder ==="
Get-ChildItem -LiteralPath $folder -Filter '*.lnk' | ForEach-Object {
    $s = $wscript.CreateShortcut($_.FullName)
    Write-Host "$($_.Name) -> $($s.TargetPath) | $($s.Arguments)"
}

Write-Host "`n=== DESKTOP ROOT ==="
Get-ChildItem -LiteralPath $desktop -Filter '*OpenHands*.lnk' | ForEach-Object {
    $s = $wscript.CreateShortcut($_.FullName)
    Write-Host "$($_.Name) -> $($s.TargetPath) | $($s.Arguments)"
}
