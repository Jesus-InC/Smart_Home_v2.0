#ifndef PORTAL_WIFI_H
#define PORTAL_WIFI_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool portal_wifi_cargar_credenciales(char *ssid, size_t tamano_ssid, char *clave, size_t tamano_clave);
bool portal_wifi_cargar_broker(char *host, size_t tamano_host, uint16_t *puerto);
void portal_wifi_guardar_credenciales(const char *ssid, const char *clave);
void portal_wifi_guardar_broker(const char *host, uint16_t puerto);
void portal_wifi_guardar_configuracion(const char *ssid, const char *clave, const char *broker_host, uint16_t broker_puerto);
void portal_wifi_olvidar_credenciales(void);
void portal_wifi_iniciar_ap_config(void);
bool portal_wifi_en_modo_config(void);

#endif
