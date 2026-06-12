# 📁 Códigos del Proyecto

Esta carpeta contiene los módulos de software principales del sistema **Smart Home v2.0**. La organización separa el código según el dispositivo o función que cumple dentro de la arquitectura del proyecto.

---

## 📂 Estructura

```text
codigos
├── Entorno_Virtual
├── Esclavo_ESP32
└── Maestro_Raspberry
```

---

## 🔹 Entorno_Virtual

Contiene el archivo `requirements.txt` con las dependencias necesarias para ejecutar los scripts de Python del proyecto.

No se sube el entorno virtual completo al repositorio, solo la lista de librerías necesarias.

---

## 🔹 Esclavo_ESP32

Contiene el firmware de la ESP32. Este bloque se encarga del control embebido del sistema:

- Lectura de sensores.
- Control de actuadores.
- Recepción de comandos MQTT.
- Publicación de estados.
- Lógica local de seguridad.

---

## 🔹 Maestro_Raspberry

Contiene el software que se ejecuta en la Raspberry Pi:

- Interfaz gráfica web.
- Scripts del modo inteligente.
- Comunicación con la ESP32 mediante MQTT.

---

## 🧩 Relación entre módulos

```text
Usuario
  ↓
Interfaz Web en Raspberry Pi
  ↓ MQTT
ESP32
  ↓
Sensores y actuadores físicos
```

El módulo inteligente también corre en la Raspberry Pi y publica datos o decisiones hacia la ESP32 usando MQTT.

