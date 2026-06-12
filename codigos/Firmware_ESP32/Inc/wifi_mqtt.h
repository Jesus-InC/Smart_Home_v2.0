#ifndef WIFI_MQTT_H
#define WIFI_MQTT_H

void wifi_mqtt_iniciar(void);

void wifi_mqtt_publicar_estado(void);
void wifi_mqtt_publicar_actuadores(void);
void wifi_mqtt_publicar_sensores(void);
void wifi_mqtt_publicar_garaje(void);
void wifi_mqtt_publicar_config(void);
void wifi_mqtt_publicar_entradas(void);
void wifi_mqtt_publicar_dimmer(void);
void wifi_mqtt_publicar_accion_fisica(const char *topico, const char *accion);

#endif
