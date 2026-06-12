# 🧠 Sistema Inteligente – Modo Smart

Esta carpeta contiene los scripts encargados de complementar el funcionamiento del sistema domótico mediante una capa inteligente ejecutada desde la Raspberry Pi.

El objetivo de este módulo es enviar información procesada o predicciones hacia la ESP32 mediante MQTT, para que el firmware pueda tomar decisiones en modo Smart.

---

## 📂 Archivos principales

```text
Sistema_Inteligente
└── enviar_predicciones_SMART.py
```

---

## 🔹 enviar_predicciones_SMART.py

Script principal del sistema inteligente.

Funciones principales:

- Preparar datos de entrada para el modo Smart.
- Generar o simular predicciones.
- Publicar resultados mediante MQTT.
- Enviar información útil a la ESP32.

---

## 📡 Comunicación MQTT

El script publica información en tópicos MQTT que son leídos por la ESP32.

Estos datos pueden representar variables inteligentes como:

- Presencia del usuario.
- Probabilidad de lluvia.
- Información auxiliar para decisiones automáticas.

---

## 🧩 Integración con el firmware

La ESP32 recibe los datos enviados desde la Raspberry Pi y los utiliza dentro de la lógica del modo Smart.

Ejemplos de decisiones asociadas:

- Activar o desactivar ventilación según condiciones ambientales.
- Controlar la bomba según humedad de suelo y predicción de lluvia.
- Ajustar el comportamiento del sistema según presencia del usuario.

---

## ▶️ Ejecución

Activar el entorno virtual y ejecutar el script:

```bash
python enviar_predicciones_SMART.py
```

El broker MQTT debe estar activo antes de ejecutar este módulo.

---

## 🎯 Objetivo del módulo

Separar la inteligencia del sistema de la lógica embebida de la ESP32, permitiendo que la Raspberry Pi actúe como una capa de procesamiento externo.

