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
- Pasar a modo seguro ante pérdida crítica de visión, según configuración.

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
casa/garaje/modo/cmd     SEGURO
```

No hace falta modificar el firmware actual para esta primera integración.

## Nota sobre modo SEGURO

Cuando la Raspberry ordena `SEGURO`, el firmware conserva ese modo hasta que el usuario seleccione nuevamente un modo permitido desde la interfaz o el control correspondiente. Esto evita que el sistema reanude automáticamente una maniobra después de perder la visión.
