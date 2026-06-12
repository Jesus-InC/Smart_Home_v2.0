# 🏠 Smart Home v2.0 – Sistema Domótico Inteligente

## 📌 Descripción breve

**Smart Home v2.0** es un sistema domótico inteligente. El sistema integra una **ESP32** como nodo esclavo encargado del control físico de sensores y actuadores, y una **Raspberry Pi** como nodo maestro encargado de la interfaz de usuario, comunicación MQTT y lógica inteligente externa.

El proyecto permite controlar y monitorear elementos de una maqueta de vivienda inteligente, incluyendo iluminación, ventilación, riego y portón de garaje. La arquitectura está diseñada para separar claramente el firmware embebido de la lógica de supervisión y de la interfaz gráfica.

---

## 🧠 Objetivo general

Diseñar e implementar un sistema domótico modular capaz de controlar actuadores, leer sensores ambientales y ejecutar modos de operación manual, automático e inteligente mediante comunicación MQTT entre una ESP32 y una Raspberry Pi.

---

## 🧩 Arquitectura general del sistema

El sistema se divide en dos bloques principales:

### 🔹 Maestro – Raspberry Pi

La Raspberry Pi actúa como servidor local y capa de supervisión. Sus funciones principales son:

- Ejecutar la interfaz gráfica web.
- Comunicarse con la ESP32 mediante MQTT.
- Ejecutar scripts del modo inteligente.
- Centralizar comandos y estados del sistema.

### 🔹 Esclavo – ESP32

La ESP32 actúa como nodo embebido de control. Sus funciones principales son:

- Leer sensores físicos.
- Controlar actuadores.
- Ejecutar lógica local de seguridad.
- Recibir comandos MQTT desde la Raspberry Pi.
- Publicar estados y fallas del sistema.

---

## 📂 Estructura del repositorio

```text
.
├── README.md
└── codigos
    ├── Entorno_Virtual
    │   ├── README.md
    │   └── requirements.txt
    ├── Esclavo_ESP32
    │   ├── README.md
    │   └── Firmware_ESP32
    │       ├── README.md
    │       ├── CMakeLists.txt
    │       ├── idf_component.yml
    │       ├── Inc
    │       └── Src
    └── Maestro_Raspberry
        ├── README.md
        ├── Interfaz_de_usuario
        │   ├── README.md
        │   ├── app.py
        │   ├── config.py
        │   ├── requirements.txt
        │   ├── static
        │   └── templates
        └── Sistema_Inteligente
            ├── README.md
            └── enviar_predicciones_SMART.py
```

---

## ⚙️ Modos de operación

### 🖐️ Modo Manual

El usuario controla directamente los actuadores desde la interfaz o desde entradas físicas disponibles en la maqueta.

### 🤖 Modo Automático

La ESP32 toma decisiones según sensores y umbrales configurados para el sistema.

### 🧠 Modo Smart

La Raspberry Pi ejecuta la lógica inteligente externa y envía predicciones o decisiones hacia la ESP32 mediante MQTT.

---

## 🛠️ Tecnologías utilizadas

### Hardware

- ESP32
- Raspberry Pi 3
- Sensor DHT22
- Sensor FC-28
- Foco AC controlado por etapa de potencia
- Ventilador DC
- Bomba DC
- Motor DC para portón
- Driver TB6612FNG
- Botonera física y finales de carrera

### Software

- Python 3
- Flask
- HTML, CSS y JavaScript
- MQTT / Mosquitto
- paho-mqtt
- ESP-IDF
- FreeRTOS
- Git y GitHub

---

## 📡 Comunicación MQTT

La comunicación entre la Raspberry Pi y la ESP32 se realiza mediante tópicos MQTT. La Raspberry Pi publica comandos y la ESP32 responde publicando estados, sensores y fallas.

Ejemplos de tópicos utilizados:

```text
casa/interior/modo/cmd
casa/interior/foco/cmd
casa/interior/vent/cmd
casa/interior/bomba/cmd
casa/sistema/estop
casa/sistema/falla/ultima
```

---

## 🚀 Componentes principales

- **Interfaz de usuario:** panel web local para controlar y visualizar el estado del sistema.
- **Sistema inteligente:** scripts de Python que publican información inteligente hacia la ESP32.
- **Firmware ESP32:** control embebido de sensores, actuadores, seguridad, MQTT y lógica local.
- **Entorno virtual:** dependencias necesarias para ejecutar los módulos de Python.

---

## ✨ Estado del proyecto

Esta versión representa la integración funcional del sistema domótico con arquitectura maestro–esclavo, comunicación MQTT, interfaz gráfica y lógica inteligente externa.

