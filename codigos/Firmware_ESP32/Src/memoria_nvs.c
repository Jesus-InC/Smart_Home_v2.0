#include "memoria_nvs.h"

#include "esp_log.h"
#include "nvs.h"

#include <string.h>
#include <stdio.h>

static const char *TAG = "memoria_nvs";
static const char *ESPACIO_NVS = "smart_home";

void memoria_nvs_iniciar(void)
{
    ESP_LOGI(TAG, "Memoria NVS lista");
}

esp_err_t memoria_nvs_guardar_u8(const char *clave, uint8_t valor)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READWRITE, &manejador);

    if (resultado != ESP_OK) return resultado;

    resultado = nvs_set_u8(manejador, clave, valor);
    if (resultado == ESP_OK) resultado = nvs_commit(manejador);

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_leer_u8(const char *clave, uint8_t *valor, uint8_t valor_defecto)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READONLY, &manejador);

    if (resultado != ESP_OK) {
        *valor = valor_defecto;
        return resultado;
    }

    resultado = nvs_get_u8(manejador, clave, valor);
    if (resultado == ESP_ERR_NVS_NOT_FOUND) *valor = valor_defecto;

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_guardar_u32(const char *clave, uint32_t valor)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READWRITE, &manejador);

    if (resultado != ESP_OK) return resultado;

    resultado = nvs_set_u32(manejador, clave, valor);
    if (resultado == ESP_OK) resultado = nvs_commit(manejador);

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_leer_u32(const char *clave, uint32_t *valor, uint32_t valor_defecto)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READONLY, &manejador);

    if (resultado != ESP_OK) {
        *valor = valor_defecto;
        return resultado;
    }

    resultado = nvs_get_u32(manejador, clave, valor);
    if (resultado == ESP_ERR_NVS_NOT_FOUND) *valor = valor_defecto;

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_guardar_bool(const char *clave, bool valor)
{
    return memoria_nvs_guardar_u8(clave, valor ? 1 : 0);
}

esp_err_t memoria_nvs_leer_bool(const char *clave, bool *valor, bool valor_defecto)
{
    uint8_t valor_u8 = valor_defecto ? 1 : 0;
    esp_err_t resultado = memoria_nvs_leer_u8(clave, &valor_u8, valor_u8);

    *valor = valor_u8 ? true : false;
    return resultado;
}

esp_err_t memoria_nvs_guardar_string(const char *clave, const char *valor)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READWRITE, &manejador);

    if (resultado != ESP_OK) return resultado;

    resultado = nvs_set_str(manejador, clave, valor);
    if (resultado == ESP_OK) resultado = nvs_commit(manejador);

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_leer_string(const char *clave, char *valor, size_t tamano, const char *valor_defecto)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READONLY, &manejador);

    if (resultado != ESP_OK) {
        snprintf(valor, tamano, "%s", valor_defecto);
        return resultado;
    }

    size_t requerido = tamano;
    resultado = nvs_get_str(manejador, clave, valor, &requerido);

    if (resultado == ESP_ERR_NVS_NOT_FOUND) {
        snprintf(valor, tamano, "%s", valor_defecto);
    }

    nvs_close(manejador);
    return resultado;
}

esp_err_t memoria_nvs_borrar_clave(const char *clave)
{
    nvs_handle_t manejador;
    esp_err_t resultado = nvs_open(ESPACIO_NVS, NVS_READWRITE, &manejador);

    if (resultado != ESP_OK) return resultado;

    resultado = nvs_erase_key(manejador, clave);
    if (resultado == ESP_ERR_NVS_NOT_FOUND) resultado = ESP_OK;
    if (resultado == ESP_OK) resultado = nvs_commit(manejador);

    nvs_close(manejador);
    return resultado;
}
