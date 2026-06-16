# Visión Artificial - Garaje SmartHome v2.0

Este módulo corre en la Raspberry Pi y funciona como una capa inteligente externa. Observa dos cámaras, calcula zona/score/trayectoria/obstáculo y publica decisiones por MQTT hacia la ESP32.

## Cámaras

- Cámara ABC: monitorea zonas A, B y C.
- Cámara D: monitorea la zona de seguridad del portón.

## Archivos

```text
Vision_Artificial/
├── vision_garaje.py          # Script principal de visión + MQTT
├── config_vision.json        # Cámaras, zonas, score y tiempos
├── probar_camaras.py         # Ayuda a identificar índices de cámaras
├── requirements_vision.txt   # Dependencias del módulo
└── README.md
```

## Instalación recomendada

Desde la Raspberry, dentro del entorno virtual del proyecto:

```bash
cd ~/Smart_Home_v2.0/codigos/Maestro_Raspberry/Vision_Artificial
python -m pip install -r requirements_vision.txt
```

Si `opencv-python-headless` tarda demasiado en Raspberry Pi 3, puedes instalar OpenCV desde apt y crear el entorno virtual con acceso a paquetes del sistema:

```bash
sudo apt update
sudo apt install -y python3-opencv
```

## 1. Identificar las cámaras

```bash
cd ~/Smart_Home_v2.0/codigos/Maestro_Raspberry/Vision_Artificial
python probar_camaras.py --desde 0 --hasta 5
```

Revisa las imágenes generadas en `capturas_prueba/`. Luego modifica en `config_vision.json`:

```json
"camaras": {
  "abc": 0,
  "d": 1
}
```

## 2. Ajustar zonas

Las zonas están en coordenadas normalizadas de 0 a 1, así no dependen de la resolución exacta de la cámara.

Ejemplo:

```json
"A": [[0.08, 0.45], [0.38, 0.45], [0.38, 0.92], [0.08, 0.92]]
```

Cada punto es `[x, y]` relativo al ancho y alto de la imagen.

## 3. Ejecutar en prueba visual

Si tu Raspberry tiene entorno gráfico o estás probando en una PC:

```bash
python vision_garaje.py --mostrar
```

Presiona `q` para salir. Si usas Raspberry Pi OS Lite, omite `--mostrar`.

## 4. Ejecutar sin ventanas, publicando MQTT

```bash
python vision_garaje.py
```

## Tópicos publicados

```text
casa/vision/estado
casa/vision/camara_abc/estado
casa/vision/camara_d/estado
casa/vision/vehiculo_detectado
casa/vision/zona
casa/vision/score
casa/vision/score_detalle
casa/vision/tipo_vehiculo
casa/vision/trayectoria
casa/vision/obstaculo_d
casa/vision/confianza
casa/vision/decision
casa/vision/evento
```

## Comandos que puede enviar

```text
casa/garaje/porton/cmd -> ABRIR / CERRAR / STOP
casa/garaje/alarma/cmd -> ON / OFF
casa/garaje/modo/cmd -> SEGURO, solo ante falla crítica de cámara
```

## Nota importante sobre sentido del motor

El script usa los comandos lógicos `ABRIR`, `CERRAR` y `STOP`.

Si en tu maqueta el motor quedó cableado invertido y físicamente abre con `CERRAR`, modifica en `config_vision.json`:

```json
"comandos": {
  "abrir": "CERRAR",
  "cerrar": "ABRIR",
  "stop": "STOP"
}
```

Así no se toca el firmware.
