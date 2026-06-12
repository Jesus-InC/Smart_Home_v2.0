# 🍓 Maestro Raspberry Pi

Esta carpeta contiene los módulos que se ejecutan en la **Raspberry Pi**, la cual funciona como nodo maestro del sistema domótico.

La Raspberry Pi centraliza la interfaz de usuario, la comunicación MQTT y la ejecución del modo inteligente.

---

## 📂 Estructura

```text
Maestro_Raspberry
├── Interfaz_de_usuario
└── Sistema_Inteligente
```

---

## 🌐 Interfaz de usuario

La carpeta `Interfaz_de_usuario` contiene una aplicación web desarrollada con Flask. Esta interfaz permite controlar el sistema desde un navegador conectado a la misma red local.

Funciones principales:

- Cambiar el modo de operación.
- Controlar foco, ventilador y bomba.
- Enviar comandos MQTT hacia la ESP32.
- Visualizar estados publicados por el sistema.

---

## 🧠 Sistema inteligente

La carpeta `Sistema_Inteligente` contiene scripts de Python que representan la capa inteligente externa del proyecto.

Funciones principales:

- Generar datos o predicciones para el modo Smart.
- Enviar información hacia la ESP32 por MQTT.
- Complementar la lógica automática local del firmware.

---

## 📡 Comunicación con la ESP32

La Raspberry Pi se comunica con la ESP32 usando MQTT. Para ello, se utiliza un broker local, normalmente Mosquitto, ejecutándose en la propia Raspberry Pi.

La Raspberry Pi publica comandos y la ESP32 responde con estados, sensores y fallas.


