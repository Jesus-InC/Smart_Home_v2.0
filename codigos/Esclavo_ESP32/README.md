# 🔌 Esclavo ESP32

Esta carpeta contiene el firmware del nodo esclavo del sistema domótico. La ESP32 se encarga de interactuar directamente con los sensores, actuadores y elementos físicos de la maqueta.

La ESP32 recibe comandos desde la Raspberry Pi mediante MQTT y publica estados para que la interfaz pueda mostrar el comportamiento del sistema en tiempo real.

---

## 📂 Estructura

```text
Esclavo_ESP32
└── Firmware_ESP32
    ├── CMakeLists.txt
    ├── idf_component.yml
    ├── Inc
    └── Src
```

---

## ⚙️ Funciones principales

- Lectura de sensores ambientales.
- Control del foco, ventilador y bomba.
- Control del portón mediante motor DC.
- Lectura de botones físicos y finales de carrera.
- Gestión de parada de emergencia.
- Comunicación MQTT con la Raspberry Pi.
- Publicación de estados y fallas.
- Ejecución de tareas con FreeRTOS.

---

## 📡 Comunicación con el maestro

La ESP32 actúa como cliente MQTT. Recibe comandos publicados por la Raspberry Pi y responde con estados del sistema.

Ejemplo general:

```text
Raspberry Pi → MQTT → ESP32 → Actuadores
ESP32 → MQTT → Raspberry Pi → Interfaz
```

---

## 🧠 Modos soportados

- Manual
- Automático
- Smart

Cada modo modifica la forma en que se toman decisiones sobre los actuadores del sistema.

