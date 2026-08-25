' ExpMon desktop launcher — runs Electron with no visible console window.
' 0 = hidden window; False = do not wait for the process to finish.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\Code\ExpMon"
sh.Run """D:\Code\ExpMon\node_modules\.bin\electron.cmd"" .", 0, False
