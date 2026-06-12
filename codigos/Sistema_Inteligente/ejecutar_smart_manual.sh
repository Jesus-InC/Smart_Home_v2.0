#!/bin/bash
cd ~/Smart_Home_v2/Sistema_Inteligente || exit
source ../.SH2/bin/activate 2>/dev/null || true
python enviar_predicciones_ESP32.py
