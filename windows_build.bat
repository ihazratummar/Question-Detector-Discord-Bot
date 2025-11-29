@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller flet

echo Building Windows Executable...
flet pack gui.py --name DiscordQuestionExporter

echo Renaming executable...
if exist dist\DiscordQuestionExporter.exe (
    ren dist\DiscordQuestionExporter.exe DiscordQuestionExporter_Windows.exe
    echo Build successful! Executable is in dist\DiscordQuestionExporter_Windows.exe
) else (
    echo Build failed or executable not found.
)
pause
