#include "config_usuario.h"
#include "configuracion.h"
#include "memoria_nvs.h"

#include <string.h>
#include <strings.h>
#include <stdlib.h>

static config_usuario_t config;

#define NVS_TEMP_MIN        "cfg_tmin"
#define NVS_TEMP_MAX        "cfg_tmax"
#define NVS_HUM_AMB_MIN     "cfg_hamin"
#define NVS_HUM_AMB_MAX     "cfg_hamax"
#define NVS_HUM_SUELO_MIN   "cfg_hsmin"
#define NVS_HUM_SUELO_MAX   "cfg_hsmax"
#define NVS_BOMBA_UMBRAL    "cfg_bumb"

static uint8_t limitar_rango(int valor, uint8_t minimo, uint8_t maximo)
{
    if (valor < minimo) return minimo;
    if (valor > maximo) return maximo;
    return (uint8_t)valor;
}

static void guardar_config(void)
{
    memoria_nvs_guardar_u8(NVS_TEMP_MIN, config.temp_min);
    memoria_nvs_guardar_u8(NVS_TEMP_MAX, config.temp_max);
    memoria_nvs_guardar_u8(NVS_HUM_AMB_MIN, config.hum_amb_min);
    memoria_nvs_guardar_u8(NVS_HUM_AMB_MAX, config.hum_amb_max);
    memoria_nvs_guardar_u8(NVS_HUM_SUELO_MIN, config.hum_suelo_min);
    memoria_nvs_guardar_u8(NVS_HUM_SUELO_MAX, config.hum_suelo_max);
    memoria_nvs_guardar_u8(NVS_BOMBA_UMBRAL, config.bomba_umbral_auto);
}

static void corregir_config(void)
{
    if (config.temp_min >= config.temp_max) {
        config.temp_min = CONFIG_TEMP_MIN_DEFECTO;
        config.temp_max = CONFIG_TEMP_MAX_DEFECTO;
    }

    if (config.hum_amb_min >= config.hum_amb_max) {
        config.hum_amb_min = CONFIG_HUM_AMB_MIN_DEFECTO;
        config.hum_amb_max = CONFIG_HUM_AMB_MAX_DEFECTO;
    }

    if (config.hum_suelo_min >= config.hum_suelo_max) {
        config.hum_suelo_min = CONFIG_HUM_SUELO_MIN_DEFECTO;
        config.hum_suelo_max = CONFIG_HUM_SUELO_MAX_DEFECTO;
    }

    config.bomba_umbral_auto = limitar_rango(config.bomba_umbral_auto, 0, 100);
}

void config_usuario_restaurar_defecto(void)
{
    config.temp_min = CONFIG_TEMP_MIN_DEFECTO;
    config.temp_max = CONFIG_TEMP_MAX_DEFECTO;
    config.hum_amb_min = CONFIG_HUM_AMB_MIN_DEFECTO;
    config.hum_amb_max = CONFIG_HUM_AMB_MAX_DEFECTO;
    config.hum_suelo_min = CONFIG_HUM_SUELO_MIN_DEFECTO;
    config.hum_suelo_max = CONFIG_HUM_SUELO_MAX_DEFECTO;
    config.bomba_umbral_auto = CONFIG_BOMBA_UMBRAL_DEFECTO;

    guardar_config();
}

void config_usuario_iniciar(void)
{
    memoria_nvs_leer_u8(NVS_TEMP_MIN, &config.temp_min, CONFIG_TEMP_MIN_DEFECTO);
    memoria_nvs_leer_u8(NVS_TEMP_MAX, &config.temp_max, CONFIG_TEMP_MAX_DEFECTO);
    memoria_nvs_leer_u8(NVS_HUM_AMB_MIN, &config.hum_amb_min, CONFIG_HUM_AMB_MIN_DEFECTO);
    memoria_nvs_leer_u8(NVS_HUM_AMB_MAX, &config.hum_amb_max, CONFIG_HUM_AMB_MAX_DEFECTO);
    memoria_nvs_leer_u8(NVS_HUM_SUELO_MIN, &config.hum_suelo_min, CONFIG_HUM_SUELO_MIN_DEFECTO);
    memoria_nvs_leer_u8(NVS_HUM_SUELO_MAX, &config.hum_suelo_max, CONFIG_HUM_SUELO_MAX_DEFECTO);
    memoria_nvs_leer_u8(NVS_BOMBA_UMBRAL, &config.bomba_umbral_auto, CONFIG_BOMBA_UMBRAL_DEFECTO);

    corregir_config();
}

bool config_usuario_procesar_mensaje(const char *topico, const char *mensaje)
{
    if (strcmp(topico, TOPICO_CONFIG_INTERIOR_RESET_CMD) == 0) {
        if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "RESET") == 0) {
            config_usuario_restaurar_defecto();
            return true;
        }
        return false;
    }

    int valor = atoi(mensaje);
    bool procesado = true;

    if (strcmp(topico, TOPICO_CONFIG_TEMP_MIN_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_TEMP_MIN_CMD) == 0) {
        config.temp_min = limitar_rango(valor, 0, 60);
    } else if (strcmp(topico, TOPICO_CONFIG_TEMP_MAX_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_TEMP_MAX_CMD) == 0) {
        config.temp_max = limitar_rango(valor, 0, 60);
    } else if (strcmp(topico, TOPICO_CONFIG_HUM_AMB_MIN_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_HUM_AMB_MIN_CMD) == 0) {
        config.hum_amb_min = limitar_rango(valor, 0, 100);
    } else if (strcmp(topico, TOPICO_CONFIG_HUM_AMB_MAX_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_HUM_AMB_MAX_CMD) == 0) {
        config.hum_amb_max = limitar_rango(valor, 0, 100);
    } else if (strcmp(topico, TOPICO_CONFIG_HUM_SUELO_MIN_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_HUM_SUELO_MIN_CMD) == 0) {
        config.hum_suelo_min = limitar_rango(valor, 0, 100);
    } else if (strcmp(topico, TOPICO_CONFIG_HUM_SUELO_MAX_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_HUM_SUELO_MAX_CMD) == 0) {
        config.hum_suelo_max = limitar_rango(valor, 0, 100);
    } else if (strcmp(topico, TOPICO_CONFIG_BOMBA_UMBRAL_CMD) == 0 || strcmp(topico, TOPICO_CONFIG_INTERIOR_BOMBA_UMBRAL_CMD) == 0) {
        config.bomba_umbral_auto = limitar_rango(valor, 0, 100);
    } else {
        procesado = false;
    }

    if (procesado) {
        corregir_config();
        guardar_config();
    }

    return procesado;
}

config_usuario_t config_usuario_obtener(void)
{
    return config;
}
