@echo off
for %%f in (*.py) do (
    echo Compilando %%f ...
    pyinstaller --noconsole --onefile --clean --noconfirm "%%f"
)
pause