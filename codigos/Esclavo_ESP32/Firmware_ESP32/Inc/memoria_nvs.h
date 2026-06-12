#ifndef MEMORIA_NVS_H
#define MEMORIA_NVS_H

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

void memoria_nvs_iniciar(void);

esp_err_t memoria_nvs_guardar_u8(const char *clave, uint8_t valor);
esp_err_t memoria_nvs_leer_u8(const char *clave, uint8_t *valor, uint8_t valor_defecto);

esp_err_t memoria_nvs_guardar_u32(const char *clave, uint32_t valor);
esp_err_t memoria_nvs_leer_u32(const char *clave, uint32_t *valor, uint32_t valor_defecto);

esp_err_t memoria_nvs_guardar_bool(const char *clave, bool valor);
esp_err_t memoria_nvs_leer_bool(const char *clave, bool *valor, bool valor_defecto);

esp_err_t memoria_nvs_guardar_string(const char *clave, const char *valor);
esp_err_t memoria_nvs_leer_string(const char *clave, char *valor, size_t tamano, const char *valor_defecto);
esp_err_t memoria_nvs_borrar_clave(const char *clave);

#endif
