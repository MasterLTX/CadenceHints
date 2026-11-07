' CadenceHints silent launcher (ASCII only: wscript parses this as ANSI)
' Double-click to run; copy a shortcut of this file into shell:startup for autostart.
Option Explicit

Dim fso, shell, here, pyw, args
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
If Not fso.FileExists(pyw) Then
    pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
End If
If Not fso.FileExists(pyw) Then
    pyw = "pythonw.exe"
End If

args = ""
Dim i
For i = 0 To WScript.Arguments.Count - 1
    args = args & " " & WScript.Arguments(i)
Next

shell.Run """" & pyw & """ app.py" & args, 0, False