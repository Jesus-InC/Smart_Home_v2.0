import time
import paho.mqtt.client as mqtt

BROKER = "192.168.1.19"
PUERTO = 1883

TOPICO_PRESENCIA = "casa/ia/presencia"
TOPICO_PROB_LLUVIA = "casa/ia/prob_lluvia"

def leer_01(mensaje):
    while True:
        v = input(mensaje).strip()
        if v in ("0", "1"):
            return int(v)
        print("Usa 0 o 1.")

def leer_probabilidad(mensaje):
    while True:
        try:
            v = float(input(mensaje).strip().replace(",", "."))
            if 0.0 <= v <= 1.0:
                return v
        except ValueError:
            pass
        print("Usa un valor entre 0.0 y 1.0.")

presencia = leer_01("Presencia en casa [0/1]: ")
prob_lluvia = leer_probabilidad("Probabilidad de lluvia [0.0 a 1.0]: ")

cliente = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="rasp_smart_manual"
)

cliente.connect(BROKER, PUERTO, 60)
cliente.loop_start()

pub1 = cliente.publish(TOPICO_PRESENCIA, str(presencia), retain=True)
pub2 = cliente.publish(TOPICO_PROB_LLUVIA, f"{prob_lluvia:.2f}", retain=True)

pub1.wait_for_publish()
pub2.wait_for_publish()

time.sleep(0.5)

cliente.loop_stop()
cliente.disconnect()

print("\nValores publicados:")
print(f"{TOPICO_PRESENCIA} = {presencia}")
print(f"{TOPICO_PROB_LLUVIA} = {prob_lluvia:.2f}")
