# Decisión central de visión — Raspberry Pi

Este módulo recibe la percepción calculada por la laptop, consulta el estado real del garaje y decide si una acción es segura. Es el único módulo de visión autorizado para publicar comandos hacia la ESP32.

## Responsabilidades

- Validar que la percepción sea reciente.
- Comprobar las dos cámaras y el estado de la laptop.
- Leer modo del garaje, E-STOP, portón y finales de carrera.
- Aplicar reglas para A/B/C/D.
- Abrir solamente con dueño, zona A, trayectoria de ingreso y D libre.
- Detener el portón si D queda ocupada.
- Activar alarma por permanencia de un vehículo ajeno.
- Cerrar después de detectar el paso por D y comprobar que D vuelve a estar libre.
- Ante pérdida crítica de visión (falla de cámara, laptop offline, múltiples vehículos), bloquear la automatización y, según configuración, activar la alarma — sin cambiar el modo del garaje (solo existen NORMAL, VISITA y MANUAL).

## Archivos

- `decision_garaje.py`: lógica central y MQTT.
- `config_decision.json`: umbrales, tiempos, seguridad y tópicos.
- `requirements_decision.txt`: dependencia MQTT.
- `decision-vision.service.example`: plantilla opcional de systemd para más adelante.

## Instalación

Copia esta carpeta en:

```text
~/Smart_Home_v2/codigos/Maestro_Raspberry/Decision_Vision
```

Desde el entorno virtual del proyecto:

```bash
cd ~/Smart_Home_v2/codigos/Maestro_Raspberry/Decision_Vision
python -m pip install -r requirements_decision.txt
```

La configuración usa `127.0.0.1` porque Mosquitto corre en la misma Raspberry.

## Primera ejecución segura

Ejecuta inicialmente sin mandar órdenes:

```bash
python decision_garaje.py --solo-monitoreo
```

En otra terminal puedes observar los mensajes:

```bash
mosquitto_sub -h 127.0.0.1 -t 'casa/vision/#' -v
```

Desde la laptop prueba escenarios simulados, por ejemplo:

```powershell
python simular_percepcion.py dueno_ingreso --segundos 10
python simular_percepcion.py obstaculo_d --segundos 10
python simular_percepcion.py ajeno_b --segundos 15
```

Cuando las decisiones sean correctas, detén el programa y ejecútalo sin la bandera:

```bash
python decision_garaje.py
```

## Comandos existentes que utiliza

```text
casa/garaje/porton/cmd   ABRIR / CERRAR / STOP
casa/garaje/alarma/cmd   ON / OFF
casa/garaje/modo/cmd     NORMAL / VISITA / MANUAL
```

No hace falta modificar el firmware actual para esta primera integración.

## Nota sobre bloqueo de seguridad (sin modo SEGURO)

Este proyecto solo contempla los modos NORMAL, VISITA y MANUAL. Cuando la visión detecta una condición crítica (cámara caída, laptop offline, múltiples vehículos, baja iluminación), la Raspberry **no cambia el modo del garaje**: simplemente detiene el portón si estaba en movimiento, bloquea la apertura/cierre automático mientras dure la condición y, según `config_decision.json`, activa la alarma. En cuanto la percepción vuelve a ser válida, la automatización se reanuda sola en el modo en el que ya estaba el usuario.
