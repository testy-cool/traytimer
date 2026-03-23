Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "F:\code\taskbartimer"
WshShell.Run "cmd /c uv run python timer.py", 0, False
