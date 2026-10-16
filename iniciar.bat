@echo off
REM Lanzador para Windows. Doble clic o: iniciar.bat [comprobar|demo|tablero|tests|validar|graficos|alerta|preguntar|asistente|importar|vigentes]
cd /d "%~dp0"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" call :cred
if not exist .venv (
  echo Creando entorno virtual en .venv ...
  python -m venv .venv || goto :error
  call .venv\Scripts\activate.bat
  python -m pip install -q -r requirements.txt || goto :error
) else (
  call .venv\Scripts\activate.bat
)
set ACCION=%1
if "%ACCION%"=="" set ACCION=tablero
if /i "%ACCION%"=="comprobar" ( python src\ia\comprobar_ia.py & goto :fin )
if /i "%ACCION%"=="demo"      ( python src\analizar_ia.py --demo & goto :fin )
if /i "%ACCION%"=="tests"     ( python tests\test_ia.py & python tests\test_ml.py & python tests\test_alerta.py & python tests\test_graficos.py & python tests\test_conocimiento.py & python tests\test_ficha_seace.py & python tests\test_interfaz.py & goto :fin )
if /i "%ACCION%"=="graficos"  ( python src\ruido_datos.py & goto :fin )
if /i "%ACCION%"=="validar"   ( python src\ml\validar.py & goto :fin )
if /i "%ACCION%"=="alerta"    ( python src\alerta_diaria.py --actualizar & goto :fin )
if /i "%ACCION%"=="preguntar" ( python src\preguntar.py & goto :fin )
if /i "%ACCION%"=="asistente" ( python -m streamlit run src\asistente_app.py & goto :fin )
if /i "%ACCION%"=="vigentes"  ( python src\vigentes.py & goto :fin )
if /i "%ACCION%"=="importar"  ( python src\importar_postores.py & python src\importar_conocimiento.py & goto :fin )
python src\ia\comprobar_ia.py
python -m streamlit run src\dashboard.py
goto :fin
:error
echo Fallo la preparacion del entorno.
:fin
pause
goto :eof
:cred
mkdir "%USERPROFILE%\.streamlit" 2>nul
echo [general]> "%USERPROFILE%\.streamlit\credentials.toml"
echo email = "">> "%USERPROFILE%\.streamlit\credentials.toml"
exit /b
