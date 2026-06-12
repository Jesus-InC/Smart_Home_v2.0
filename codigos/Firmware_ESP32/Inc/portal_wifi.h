#ifndef PORTAL_WIFI_H
#define PORTAL_WIFI_H

#include <stdbool.h>
#include <stddef.h>

bool portal_wifi_cargar_credenciales(char *ssid, size_t tamano_ssid, char *clave, size_t tamano_clave);
void portal_wifi_guardar_credenciales(const char *ssid, const char *clave);
void portal_wifi_olvidar_credenciales(void);
void portal_wifi_iniciar_ap_config(void);
bool portal_wifi_en_modo_config(void);

#endif
