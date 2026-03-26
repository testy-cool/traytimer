Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "dist\TaskbarTimer.exe")
If fso.FileExists(exePath) Then
    WshShell.Run """" & exePath & """", 0, False
Else
    WshShell.Run "cmd /c uv run python timer.py", 0, False
End If
