; ==============================================================================
; AI Dock — Windows Global Hotkey (Win+C / Super+C)
; ==============================================================================
; This script maps the Windows Key + C shortcut to toggle AI Dock running in WSL.
; To use this:
;   1. Install AutoHotkey (https://www.autohotkey.com/)
;   2. Right-click this file on Windows and select "Run Script" (or compile it).
;   3. Press Win+C to open, hide, or restore the AI Dock.
; ==============================================================================

#NoEnv  ; Recommended for performance and compatibility.
SendMode Input  ; Recommended for new scripts due to its superior speed and reliability.
SetWorkingDir %A_ScriptDir%  ; Ensures a consistent starting directory.

; Shortcut: Win + C
#c::
    ; Runs the command in WSL hidden so no cmd/powershell window flashes on screen.
    Run, wsl.exe python3 ~/Documents/C_Programming/ai-dock/ai_dock.py, , Hide
return

; ==============================================================================
; AutoHotkey v2 Syntax (uncomment if you are using AHK v2)
; ==============================================================================
; #c::
; {
;     Run("wsl.exe python3 ~/Documents/C_Programming/ai-dock/ai_dock.py", , "Hide")
; }
; ==============================================================================
