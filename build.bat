@echo off
rem Builds build\ToLissFAP.xpl (Windows x64) with MSVC. Needs Visual Studio 2019/2022/2026
rem with the "Desktop development with C++" workload.
setlocal
cd /d "%~dp0"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
if not defined VSDIR ( echo Visual Studio with C++ tools not found & exit /b 1 )
rem prefer the 14.29 (VS2019) toolset when installed, else the default one
call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" -vcvars_ver=14.29 >nul 2>&1 || call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
if not exist build mkdir build
set DEFS=/DIBM=1 /DAPL=0 /DLIN=0 /DXPLM200 /DXPLM210 /DXPLM300 /DXPLM301 /DXPLM302 /DXPLM303 /DXPLM400 /DXPLM410 /DXPLM420 /DXPLM430 /DXPLM440 /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS
cl /nologo /std:c++17 /O2 /EHsc /MT /W3 /LD %DEFS% /Isdk\CHeaders\XPLM src\fap.cpp src\audio.cpp /Fobuild\ /Fe:build\ToLissFAP.xpl /link sdk\Libraries\Win\XPLM_64.lib || exit /b 1
echo BUILD OK
