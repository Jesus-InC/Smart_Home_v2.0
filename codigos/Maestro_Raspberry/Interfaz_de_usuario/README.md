# 🌐 Interfaz de Usuario – Raspberry Pi

Esta carpeta contiene la interfaz web del sistema domótico **Smart Home v2.0**. La interfaz se ejecuta en la Raspberry Pi y permite al usuario controlar el sistema desde un navegador web.

La aplicación utiliza Flask para servir la página principal y comunicarse con la ESP32 mediante MQTT.

---

## 📂 Archivos principales

```text
Interfaz_de_usuario
├── app.py
├── config.py
├── static
│   ├── app.js
│   └── styles.css
└── templates
    └── index.html
```

---

## 🔹 app.py

Archivo principal de la aplicación Flask.

Funciones principales:

- Inicializar el servidor web.
- Definir las rutas de la interfaz.
- Recibir acciones del usuario.
- Publicar comandos MQTT.
- Actualizar estados del sistema.

---

## 🔹 config.py

Archivo de configuración de la interfaz.

Puede incluir parámetros como:

- Dirección del broker MQTT.
- Puerto MQTT.
- Tópicos utilizados.
- Variables generales de configuración.

> Antes de publicar el repositorio, se recomienda revisar que este archivo no contenga contraseñas, tokens o datos sensibles.

---

## 🔹 static/app.js

Archivo JavaScript de la interfaz.

Se encarga de:

- Gestionar eventos de botones y controles.
- Enviar solicitudes hacia Flask.
- Actualizar dinámicamente elementos visuales del panel.

---

## 🔹 static/styles.css

Archivo de estilos de la interfaz.

Define la apariencia visual del panel web, incluyendo colores, distribución de elementos, botones y tarjetas de estado.

---

## 🔹 templates/index.html

Archivo HTML principal.

Contiene la estructura del panel de control que visualiza el usuario desde el navegador.

---

## ▶️ Ejecución

Desde esta carpeta, activar el entorno virtual e instalar dependencias si corresponde:

```bash
python -m pip install -r requirements.txt
```

Luego ejecutar:

```bash
python app.py
```

Después, abrir la interfaz desde un navegador usando la IP de la Raspberry Pi y el puerto configurado en Flask.

---

## 🎯 Objetivo del módulo

Proporcionar una interfaz gráfica sencilla y local para controlar el sistema domótico sin depender de plataformas externas.

