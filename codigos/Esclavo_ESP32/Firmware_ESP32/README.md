# ⚙️ Firmware ESP32 – Smart Home v2.0

Este firmware corresponde al nodo esclavo del sistema domótico **Smart Home v2.0**. Está desarrollado para ESP32 usando ESP-IDF y una estructura modular en archivos `.c` y `.h`.

El firmware se encarga de controlar los actuadores físicos, leer sensores, gestionar entradas locales, ejecutar lógica de seguridad y comunicarse con la Raspberry Pi mediante MQTT.

---

## 📂 Estructura general

```text
Firmware_ESP32
├── CMakeLists.txt
├── idf_component.yml
├── Inc
│   ├── actuadores.h
│   ├── config_usuario.h
│   ├── configuracion.h
│   ├── control_dimmer.h
│   ├── control_garaje.h
│   ├── control_global.h
│   ├── control_interior.h
│   ├── driver_dht22.h
│   ├── driver_fc28.h
│   ├── entradas_fisicas.h
│   ├── memoria_nvs.h
│   ├── portal_wifi.h
│   ├── tareas_sistema.h
│   └── wifi_mqtt.h
└── Src
    ├── actuadores.c
    ├── config_usuario.c
    ├── control_dimmer.c
    ├── control_garaje.c
    ├── control_global.c
    ├── control_interior.c
    ├── driver_dht22.c
    ├── driver_fc28.c
    ├── entradas_fisicas.c
    ├── main.c
    ├── memoria_nvs.c
    ├── portal_wifi.c
    ├── tareas_sistema.c
    └── wifi_mqtt.c
```

---

## 🔹 main.c

Archivo principal del firmware.

Funciones principales:

- Inicializar hardware.
- Inicializar módulos del sistema.
- Configurar WiFi y MQTT.
- Crear tareas FreeRTOS.
- Arrancar la lógica general del sistema.

---

## 🔹 configuracion.h

Archivo de configuración general del sistema.

Contiene definiciones globales como:

- Pines de sensores y actuadores.
- Parámetros de control.
- Constantes del sistema.
- Configuraciones comunes entre módulos.

---

## 🔹 config_usuario.c / config_usuario.h

Módulo asociado a configuraciones modificables por el usuario.

Puede incluir umbrales, parámetros de funcionamiento y valores utilizados por la lógica automática o inteligente.

---

## 🔹 actuadores.c / actuadores.h

Módulo encargado del control directo de los actuadores.

Actuadores considerados:

- Foco.
- Ventilador.
- Bomba.
- Motor del portón.
- Señales auxiliares o de alarma.

---

## 🔹 control_interior.c / control_interior.h

Módulo encargado de la lógica de los actuadores interiores del sistema domótico.

Incluye el comportamiento asociado a:

- Foco.
- Ventilador.
- Bomba.
- Modos manual, automático y smart.

---

## 🔹 control_garaje.c / control_garaje.h

Módulo encargado de la lógica del portón de garaje.

Funciones principales:

- Abrir portón.
- Cerrar portón.
- Detener motor.
- Leer finales de carrera.
- Aplicar condiciones de seguridad.

---

## 🔹 control_global.c / control_global.h

Módulo de coordinación general del sistema.

Se encarga de integrar los estados globales, modos de operación, flags de seguridad y condiciones compartidas entre diferentes bloques del firmware.

---

## 🔹 control_dimmer.c / control_dimmer.h

Módulo asociado al control del foco mediante etapa de potencia.

Puede incluir lógica de disparo, sincronización y ajuste de intensidad dependiendo de la configuración final del sistema.

---

## 🔹 entradas_fisicas.c / entradas_fisicas.h

Módulo encargado de leer los botones físicos del sistema.

Entradas consideradas:

- Botón de foco.
- Botón de ventilador.
- Botón de bomba.
- Botones de abrir, cerrar y detener portón.
- Parada de emergencia.
- Finales de carrera.

---

## 🔹 driver_dht22.c / driver_dht22.h

Driver para la lectura del sensor DHT22.

Variables medidas:

- Temperatura ambiente.
- Humedad ambiente.

---

## 🔹 driver_fc28.c / driver_fc28.h

Driver para la lectura del sensor FC-28.

Variable medida:

- Humedad del suelo.

---

## 🔹 memoria_nvs.c / memoria_nvs.h

Módulo encargado del uso de memoria no volátil.

Permite guardar configuraciones importantes que deben conservarse después de reiniciar la ESP32.

---

## 🔹 portal_wifi.c / portal_wifi.h

Módulo relacionado con la configuración de red WiFi.

Se utiliza para gestionar la conexión del dispositivo y facilitar la configuración de credenciales cuando sea necesario.

---

## 🔹 wifi_mqtt.c / wifi_mqtt.h

Módulo encargado de la comunicación inalámbrica y MQTT.

Funciones principales:

- Conectar la ESP32 a la red WiFi.
- Conectar al broker MQTT.
- Suscribirse a tópicos de comando.
- Publicar estados del sistema.
- Procesar mensajes recibidos.

---

## 🔹 tareas_sistema.c / tareas_sistema.h

Módulo encargado de definir y ejecutar tareas FreeRTOS.

Permite separar responsabilidades como:

- Lectura de sensores.
- Comunicación MQTT.
- Lógica de control.
- Revisión de seguridad.

---

## 📡 Integración con MQTT

La ESP32 se comunica con la Raspberry Pi mediante MQTT. Los comandos son recibidos desde la interfaz o desde el sistema inteligente, y los estados son publicados para monitoreo.

---

## 🎯 Objetivo del firmware

Implementar un nodo embebido robusto y modular para controlar una maqueta domótica, manteniendo separación clara entre hardware, lógica de control, comunicación y configuración.

