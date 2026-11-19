@echo off
chcp 65001 >nul
REM FusionLab 后端启动脚本（独立 conda 环境 fusionlab / Python 3.12）
cd /d "%~dp0"
"C:\ProgramData\anaconda3\envs\fusionlab\python.exe" main.py
pause
