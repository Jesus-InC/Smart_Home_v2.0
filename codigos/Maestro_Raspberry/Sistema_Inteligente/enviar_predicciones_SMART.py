from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import paho.mqtt.client as mqtt

# CONFIGURACIÓN MQTT
BROKER_DEFECTO = "192.168.1.19"
PUERTO_DEFECTO = 1883
KEEPALIVE = 60
CLIENT_ID = "rasp_smart_python_v2"

TOPIC_PRESENCIA = "casa/ia/presencia"
TOPIC_PROB_LLUVIA = "casa/ia/prob_lluvia"
TOPIC_MODO_INTERIOR_CMD = "casa/interior/modo/cmd"

QOS = 1
RETENER_VALORES = True


# VALIDACIÓN DE DATOS
def convertir_presencia(valor: str) -> int:
    """Convierte la presencia a 0 o 1."""
    texto = str(valor).strip().lower()

    mapa = {
        "0": 0,
        "1": 1,
        "no": 0,
        "n": 0,
        "false": 0,
        "falso": 0,
        "off": 0,
        "si": 1,
        "sí": 1,
        "s": 1,
        "true": 1,
        "verdadero": 1,
        "on": 1,
    }

    if texto not in mapa:
        raise ValueError("La presencia debe ser 0 o 1.")

    return mapa[texto]


def convertir_probabilidad_lluvia(valor: str) -> float:
    """
    Convierte la probabilidad de lluvia a rango 0.0 - 1.0.

    Formatos aceptados:
      - 0.75  -> 75 %
      - 75    -> 75 %
      - 75%   -> 75 %
      - 0,75  -> 75 %
    """
    texto = str(valor).strip().replace(",", ".")

    if not texto:
        raise ValueError("La probabilidad de lluvia no puede estar vacía.")

    tiene_porcentaje = texto.endswith("%")
    if tiene_porcentaje:
        texto = texto[:-1].strip()

    try:
        numero = float(texto)
    except ValueError as exc:
        raise ValueError("La probabilidad de lluvia debe ser un número.") from exc

    if tiene_porcentaje or numero > 1.0:
        numero = numero / 100.0

    if numero < 0.0 or numero > 1.0:
        raise ValueError("La probabilidad de lluvia debe estar entre 0.0 y 1.0, o entre 0% y 100%.")

    return numero

# MQTT

def crear_cliente() -> mqtt.Client:
    """Crea un cliente MQTT compatible con paho-mqtt 1.x y 2.x."""
    try:
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=CLIENT_ID,
        )
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=CLIENT_ID)


def conectar_mqtt(broker: str, puerto: int) -> mqtt.Client:
    client = crear_cliente()
    client.connect(broker, puerto, KEEPALIVE)
    client.loop_start()
    time.sleep(0.2)
    return client


def publicar_valores(
    client: mqtt.Client,
    presencia: int,
    prob_lluvia: float,
    activar_smart: bool = False,
    retain: bool = RETENER_VALORES,
) -> None:
    """Publica los valores SMART en los tópicos que esperan la ESP32 y la interfaz."""
    payload_presencia = str(presencia)
    payload_lluvia = f"{prob_lluvia:.3f}"

    publicaciones = []

    if activar_smart:
        publicaciones.append(
            client.publish(TOPIC_MODO_INTERIOR_CMD, "SMART", qos=QOS, retain=False)
        )

    publicaciones.append(
        client.publish(TOPIC_PRESENCIA, payload_presencia, qos=QOS, retain=retain)
    )
    publicaciones.append(
        client.publish(TOPIC_PROB_LLUVIA, payload_lluvia, qos=QOS, retain=retain)
    )

    for pub in publicaciones:
        pub.wait_for_publish(timeout=3)

    print("\nValores SMART publicados por MQTT:")
    if activar_smart:
        print(f"  {TOPIC_MODO_INTERIOR_CMD} = SMART")
    print(f"  {TOPIC_PRESENCIA} = {payload_presencia}")
    print(f"  {TOPIC_PROB_LLUVIA} = {payload_lluvia}  ({prob_lluvia * 100:.1f} %)")


# ENTRADA POR TERMINAL

def pedir_valor(mensaje: str) -> Optional[str]:
    valor = input(mensaje).strip()
    if valor.lower() in {"q", "quit", "salir", "exit"}:
        return None
    return valor


def pedir_presencia() -> Optional[int]:
    while True:
        valor = pedir_valor("Presencia en casa [0 = no, 1 = sí, salir = terminar]: ")
        if valor is None:
            return None
        try:
            return convertir_presencia(valor)
        except ValueError as e:
            print(f"Error: {e}")


def pedir_probabilidad_lluvia() -> Optional[float]:
    while True:
        valor = pedir_valor("Probabilidad de lluvia [0.0 a 1.0, ejemplo 0.75]: ")
        if valor is None:
            return None
        try:
            return convertir_probabilidad_lluvia(valor)
        except ValueError as e:
            print(f"Error: {e}")


def ejecutar_interactivo(client: mqtt.Client, activar_smart: bool, retain: bool, repetir: bool) -> None:
    print("\nModo SMART manual desde terminal")
    print("Escribe 'salir' en cualquier entrada para terminar.\n")

    while True:
        presencia = pedir_presencia()
        if presencia is None:
            break

        prob_lluvia = pedir_probabilidad_lluvia()
        if prob_lluvia is None:
            break

        publicar_valores(client, presencia, prob_lluvia, activar_smart=activar_smart, retain=retain)

        if not repetir:
            break

        print("\nPuedes ingresar nuevos valores.\n")


# PROGRAMA PRINCIPAL

def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publica presencia y probabilidad de lluvia para el modo SMART por MQTT."
    )
    parser.add_argument("--broker", default=BROKER_DEFECTO, help="IP o host del broker MQTT.")
    parser.add_argument("--puerto", type=int, default=PUERTO_DEFECTO, help="Puerto MQTT.")
    parser.add_argument("--presencia", help="Presencia en casa: 0 o 1.")
    parser.add_argument("--lluvia", help="Probabilidad de lluvia: 0.0 a 1.0, o porcentaje como 75.")
    parser.add_argument("--loop", action="store_true", help="Permite ingresar valores varias veces.")
    parser.add_argument(
        "--activar-smart",
        action="store_true",
        help="Además de publicar los valores, cambia el modo interior a SMART.",
    )
    parser.add_argument(
        "--no-retain",
        action="store_true",
        help="Publica sin retain. Por defecto se usa retain para guardar el último valor SMART.",
    )
    return parser


def main() -> int:
    args = crear_parser().parse_args()
    retain = not args.no_retain

    try:
        client = conectar_mqtt(args.broker, args.puerto)
    except Exception as e:
        print(f"No se pudo conectar al broker MQTT {args.broker}:{args.puerto}")
        print(f"Detalle: {e}")
        return 1

    try:
        tiene_argumentos = args.presencia is not None or args.lluvia is not None

        if tiene_argumentos:
            if args.presencia is None or args.lluvia is None:
                print("Error: si usas argumentos, debes indicar --presencia y --lluvia juntos.")
                return 1

            presencia = convertir_presencia(args.presencia)
            prob_lluvia = convertir_probabilidad_lluvia(args.lluvia)
            publicar_valores(client, presencia, prob_lluvia, activar_smart=args.activar_smart, retain=retain)
        else:
            ejecutar_interactivo(client, activar_smart=args.activar_smart, retain=retain, repetir=args.loop)

    except KeyboardInterrupt:
        print("\nScript detenido por el usuario.")
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    finally:
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
