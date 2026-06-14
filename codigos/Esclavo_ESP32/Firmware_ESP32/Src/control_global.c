#include "control_global.h"
#include "configuracion.h"
#include "actuadores.h"
#include "memoria_nvs.h"

#include <string.h>
#include <strings.h>
#include <stdlib.h>

static estado_sistema_t estado;

#define NVS_CLAVE_MODO          "modo"
#define NVS_CLAVE_FOCO          "foco"
#define NVS_CLAVE_BOMBA         "bomba"
#define NVS_CLAVE_VENT          "vent"
#define NVS_CLAVE_FALLAS        "fallas"
#define NVS_CLAVE_ULT_FALLA     "ult_falla"

static uint8_t limitar_porcentaje(int valor)
{
    if (valor < 0) return 0;
    if (valor > 100) return 100;
    return (uint8_t)valor;
}

static bool mensaje_es_reset(const char *mensaje)
{
    return strcasecmp(mensaje, "RESET") == 0;
}

static bool mensaje_es_estop(const char *topico)
{
    return strcmp(topico, TOPICO_SISTEMA_ESTOP) == 0 || strcmp(topico, TOPICO_SISTEMA_ESTOP_CMD) == 0;
}

static void limpiar_overrides(void)
{
    estado.foco_override = false;
    estado.bomba_override = false;
    estado.ventilador_override = false;
}

void control_global_iniciar(void)
{
    memset(&estado, 0, sizeof(estado));
    estado.modo_actual = MODO_MANUAL;
    estado.ultima_falla[0] = '\0';
}

void control_global_cargar_nvs(void)
{
    uint8_t modo = MODO_MANUAL;

    memoria_nvs_leer_u8(NVS_CLAVE_MODO, &modo, MODO_MANUAL);
    memoria_nvs_leer_u8(NVS_CLAVE_FOCO, &estado.nivel_foco, 0);
    memoria_nvs_leer_bool(NVS_CLAVE_BOMBA, &estado.bomba_encendida, false);
    memoria_nvs_leer_u8(NVS_CLAVE_VENT, &estado.velocidad_ventilador, 0);
    memoria_nvs_leer_u32(NVS_CLAVE_FALLAS, &estado.contador_fallas, 0);
    memoria_nvs_leer_string(NVS_CLAVE_ULT_FALLA, estado.ultima_falla, sizeof(estado.ultima_falla), "");

    if (modo > MODO_SMART) modo = MODO_MANUAL;
    estado.modo_actual = (modo_sistema_t)modo;

    if (estado.modo_actual == MODO_MANUAL) {
        estado.nivel_foco = limitar_porcentaje(estado.nivel_foco);
        estado.velocidad_ventilador = limitar_porcentaje(estado.velocidad_ventilador);

        actuadores_set_foco(estado.nivel_foco);
        actuadores_set_bomba(estado.bomba_encendida);
        actuadores_set_ventilador(estado.velocidad_ventilador > 0, estado.velocidad_ventilador);
    } else {
        estado.estado_seguro_arranque = true;
        estado.nivel_foco = 0;
        estado.bomba_encendida = false;
        estado.velocidad_ventilador = 0;

        actuadores_set_foco(0);
        actuadores_set_bomba(false);
        actuadores_set_ventilador(false, 0);
    }
}

void control_global_guardar_nvs(void)
{
    memoria_nvs_guardar_u8(NVS_CLAVE_MODO, (uint8_t)estado.modo_actual);
    memoria_nvs_guardar_u8(NVS_CLAVE_FOCO, estado.nivel_foco);
    memoria_nvs_guardar_bool(NVS_CLAVE_BOMBA, estado.bomba_encendida);
    memoria_nvs_guardar_u8(NVS_CLAVE_VENT, estado.velocidad_ventilador);
}

void control_global_registrar_falla(const char *codigo)
{
    if (codigo == NULL || codigo[0] == '\0') return;

    snprintf(estado.ultima_falla, sizeof(estado.ultima_falla), "%s", codigo);
    estado.contador_fallas++;

    memoria_nvs_guardar_string(NVS_CLAVE_ULT_FALLA, estado.ultima_falla);
    memoria_nvs_guardar_u32(NVS_CLAVE_FALLAS, estado.contador_fallas);
}

bool control_global_procesar_mensaje(const char *topico, const char *mensaje)
{
    if (mensaje_es_estop(topico)) {
        if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "ON") == 0) {
            estado.paro_emergencia = true;
            estado.nivel_foco = 0;
            estado.bomba_encendida = false;
            estado.velocidad_ventilador = 0;

            actuadores_set_foco(0);
            actuadores_set_bomba(false);
            actuadores_set_ventilador(false, 0);
            control_global_guardar_nvs();
            return true;
        }

        if (strcmp(mensaje, "0") == 0 || strcasecmp(mensaje, "OFF") == 0) {
            estado.paro_emergencia = false;
            return true;
        }

        return false;
    }

    if (strcmp(topico, TOPICO_INTERIOR_MODO_CMD) == 0) {
        if (strcasecmp(mensaje, "MANUAL") == 0) {
            estado.modo_actual = MODO_MANUAL;
        } else if (strcasecmp(mensaje, "AUTO") == 0) {
            estado.modo_actual = MODO_AUTO;
        } else if (strcasecmp(mensaje, "SMART") == 0) {
            estado.modo_actual = MODO_SMART;
        } else {
            return false;
        }

        estado.estado_seguro_arranque = false;
        limpiar_overrides();
        control_global_guardar_nvs();
        return true;
    }

    if (strcmp(topico, TOPICO_IA_PRESENCIA) == 0) {
        if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "ON") == 0) {
            estado.presencia = true;
        } else if (strcmp(mensaje, "0") == 0 || strcasecmp(mensaje, "OFF") == 0) {
            estado.presencia = false;
        } else {
            return false;
        }
        return true;
    }

    if (strcmp(topico, TOPICO_IA_PROB_LLUVIA) == 0) {
        float valor = atof(mensaje);
        if (valor < 0.0f) valor = 0.0f;
        if (valor > 1.0f) valor = 1.0f;
        estado.probabilidad_lluvia = valor;
        return true;
    }

    if (estado.paro_emergencia) return false;

    if (strcmp(topico, TOPICO_INTERIOR_FOCO_CMD) == 0) {
        if (mensaje_es_reset(mensaje)) {
            estado.foco_override = false;
            return true;
        }

        bool activar_override = estado.modo_actual != MODO_MANUAL;
        control_global_set_nivel_foco(limitar_porcentaje(atoi(mensaje)), activar_override);
        control_global_guardar_nvs();
        return true;
    }

    if (strcmp(topico, TOPICO_INTERIOR_BOMBA_CMD) == 0) {
        if (mensaje_es_reset(mensaje)) {
            estado.bomba_override = false;
            return true;
        }

        bool encender;
        if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "ON") == 0) {
            encender = true;
        } else if (strcmp(mensaje, "0") == 0 || strcasecmp(mensaje, "OFF") == 0) {
            encender = false;
        } else {
            return false;
        }

        bool activar_override = estado.modo_actual != MODO_MANUAL;
        control_global_set_bomba(encender, activar_override);
        control_global_guardar_nvs();
        return true;
    }

    if (strcmp(topico, TOPICO_INTERIOR_VENT_CMD) == 0) {
        if (mensaje_es_reset(mensaje)) {
            estado.ventilador_override = false;
            return true;
        }

        bool activar_override = estado.modo_actual != MODO_MANUAL;
        control_global_set_ventilador(limitar_porcentaje(atoi(mensaje)), activar_override);
        control_global_guardar_nvs();
        return true;
    }

    return false;
}

void control_global_actualizar_sensores(float temperatura, float humedad_ambiente, uint8_t humedad_suelo)
{
    estado.temperatura = temperatura;
    estado.humedad_ambiente = humedad_ambiente;
    estado.humedad_suelo = humedad_suelo;
}

void control_global_set_nivel_foco(uint8_t nivel, bool activar_override)
{
    estado.nivel_foco = limitar_porcentaje(nivel);
    if (activar_override) estado.foco_override = true;
    actuadores_set_foco(estado.nivel_foco);
}

void control_global_set_bomba(bool encender, bool activar_override)
{
    estado.bomba_encendida = encender;
    if (activar_override) estado.bomba_override = true;
    actuadores_set_bomba(estado.bomba_encendida);
}

void control_global_set_ventilador(uint8_t velocidad, bool activar_override)
{
    estado.velocidad_ventilador = limitar_porcentaje(velocidad);
    if (activar_override) estado.ventilador_override = true;
    actuadores_set_ventilador(estado.velocidad_ventilador > 0, estado.velocidad_ventilador);
}

void control_global_toggle_foco_fisico(void)
{
    if (estado.paro_emergencia) {
        return;
    }

    bool activar_override = estado.modo_actual != MODO_MANUAL;

    if (estado.nivel_foco > 0) {
        control_global_set_nivel_foco(0, activar_override);
    } else {
        control_global_set_nivel_foco(100, activar_override);
    }

    control_global_guardar_nvs();
}

void control_global_toggle_bomba_fisico(void)
{
    if (estado.paro_emergencia) return;

    if (estado.modo_actual != MODO_MANUAL && estado.bomba_override) {
        estado.bomba_override = false;
        return;
    }

    bool activar_override = estado.modo_actual != MODO_MANUAL;
    control_global_set_bomba(!estado.bomba_encendida, activar_override);
    control_global_guardar_nvs();
}

void control_global_toggle_ventilador_fisico(void)
{
    if (estado.paro_emergencia) {
        return;
    }

    /*
     * En AUTO/SMART el boton fisico del ventilador tiene doble funcion:
     * 1) Si no hay override, interviene el ventilador y activa override.
     * 2) Si ya hay override, lo cancela y devuelve el control a la logica automatica.
     */
    if (estado.modo_actual != MODO_MANUAL && estado.ventilador_override) {
        estado.ventilador_override = false;
        return;
    }

    bool activar_override = estado.modo_actual != MODO_MANUAL;

    if (estado.velocidad_ventilador > 0) {
        control_global_set_ventilador(0, activar_override);
    } else {
        control_global_set_ventilador(60, activar_override);
    }

    control_global_guardar_nvs();
}

void control_global_ajustar_foco_fisico(int8_t delta)
{
    if (estado.paro_emergencia) return;

    bool activar_override = estado.modo_actual != MODO_MANUAL;
    int nuevo_nivel = (int)estado.nivel_foco + delta;

    if (estado.nivel_foco == 0 && delta > 0) nuevo_nivel = delta;

    control_global_set_nivel_foco(limitar_porcentaje(nuevo_nivel), activar_override);
    control_global_guardar_nvs();
}

void control_global_ajustar_ventilador_fisico(int8_t delta)
{
    if (estado.paro_emergencia) return;

    bool activar_override = estado.modo_actual != MODO_MANUAL;
    int nueva_velocidad = (int)estado.velocidad_ventilador + delta;

    if (estado.velocidad_ventilador == 0 && delta > 0) nueva_velocidad = delta;

    control_global_set_ventilador(limitar_porcentaje(nueva_velocidad), activar_override);
    control_global_guardar_nvs();
}

estado_sistema_t control_global_obtener_estado(void)
{
    return estado;
}

void control_global_set_wifi(bool conectado)
{
    estado.wifi_conectado = conectado;
}

void control_global_set_mqtt(bool conectado)
{
    estado.mqtt_conectado = conectado;
}

const char *control_global_modo_texto(modo_sistema_t modo)
{
    switch (modo) {
        case MODO_MANUAL: return "MANUAL";
        case MODO_AUTO:   return "AUTO";
        case MODO_SMART:  return "SMART";
        default:          return "DESCONOCIDO";
    }
}
