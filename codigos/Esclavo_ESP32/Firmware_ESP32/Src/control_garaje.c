#include "control_garaje.h"
#include "configuracion.h"
#include "control_global.h"
#include "actuadores.h"
#include "entradas_fisicas.h"
#include "memoria_nvs.h"

#include "esp_log.h"

#include <string.h>
#include <strings.h>

#define VELOCIDAD_MOTOR_PORTON 45
#define NVS_MODO_GARAJE "modo_gar"

static const char *TAG = "control_garaje";

static modo_garaje_t modo_garaje = MODO_GARAJE_NORMAL;
static estado_porton_t estado_porton = PORTON_CERRADO;
static bool alarma_activa = false;

static bool btn_abrir_anterior = false;
static bool btn_cerrar_anterior = false;

static void guardar_modo_garaje(void)
{
    memoria_nvs_guardar_u8(NVS_MODO_GARAJE, (uint8_t)modo_garaje);
}

static void actualizar_alarma(bool activa)
{
    alarma_activa = activa;
    actuadores_set_alarma_visual(alarma_activa);
}

static void detener_porton(void)
{
    actuadores_motor_detener();
    estado_porton = PORTON_DETENIDO;
}

static bool bloquear_por_modo_seguro(void)
{
    if (modo_garaje == MODO_GARAJE_SEGURO) {
        detener_porton();
        actualizar_alarma(true);
        ESP_LOGW(TAG, "Movimiento bloqueado por modo SEGURO");
        return true;
    }

    return false;
}

static void iniciar_apertura_porton(void)
{
    entradas_estado_t entradas = entradas_fisicas_obtener_estado();

    if (entradas.fc_abierto) {
        actuadores_motor_detener();
        estado_porton = PORTON_ABIERTO;
        ESP_LOGI(TAG, "No abre: FC_ABIERTO activo");
        return;
    }

    if (bloquear_por_modo_seguro()) return;

    if (modo_garaje == MODO_GARAJE_VISITA) {
        detener_porton();
        actualizar_alarma(true);
        ESP_LOGW(TAG, "Apertura bloqueada en modo VISITA");
        return;
    }

    estado_porton = PORTON_ABRIENDO;
    actuadores_motor_abrir(VELOCIDAD_MOTOR_PORTON);
    ESP_LOGI(TAG, "Porton abriendo");
}

static void iniciar_cierre_porton(void)
{
    entradas_estado_t entradas = entradas_fisicas_obtener_estado();

    if (entradas.fc_cerrado) {
        actuadores_motor_detener();
        estado_porton = PORTON_CERRADO;
        ESP_LOGI(TAG, "No cierra: FC_CERRADO activo");
        return;
    }

    if (bloquear_por_modo_seguro()) return;

    estado_porton = PORTON_CERRANDO;
    actuadores_motor_cerrar(VELOCIDAD_MOTOR_PORTON);
    ESP_LOGI(TAG, "Porton cerrando");
}

void control_garaje_iniciar(void)
{
    uint8_t modo_guardado = MODO_GARAJE_NORMAL;
    memoria_nvs_leer_u8(NVS_MODO_GARAJE, &modo_guardado, MODO_GARAJE_NORMAL);

    if (modo_guardado > MODO_GARAJE_SEGURO) modo_guardado = MODO_GARAJE_NORMAL;

    modo_garaje = (modo_garaje_t)modo_guardado;
    estado_porton = PORTON_CERRADO;
    alarma_activa = false;

    btn_abrir_anterior = false;
    btn_cerrar_anterior = false;

    ESP_LOGI(TAG, "Garaje iniciado");
}

bool control_garaje_procesar_mensaje(const char *topico, const char *mensaje)
{
    estado_sistema_t estado = control_global_obtener_estado();

    if (estado.paro_emergencia) {
        detener_porton();
        return false;
    }

    if (strcmp(topico, TOPICO_GARAJE_MODO_CMD) == 0) {
        if (strcasecmp(mensaje, "NORMAL") == 0) {
            modo_garaje = MODO_GARAJE_NORMAL;
        } else if (strcasecmp(mensaje, "VISITA") == 0) {
            modo_garaje = MODO_GARAJE_VISITA;
        } else if (strcasecmp(mensaje, "MANUAL") == 0) {
            modo_garaje = MODO_GARAJE_MANUAL;
        } else if (strcasecmp(mensaje, "SEGURO") == 0) {
            modo_garaje = MODO_GARAJE_SEGURO;
            detener_porton();
        } else {
            return false;
        }

        guardar_modo_garaje();
        ESP_LOGI(TAG, "Modo garaje: %s", control_garaje_modo_texto());
        return true;
    }

    if (strcmp(topico, TOPICO_GARAJE_PORTON_CMD) == 0) {
        if (strcasecmp(mensaje, "STOP") == 0) {
            detener_porton();
            return true;
        }

        if (strcasecmp(mensaje, "ABRIR") == 0) {
            iniciar_apertura_porton();
            return true;
        }

        if (strcasecmp(mensaje, "CERRAR") == 0) {
            iniciar_cierre_porton();
            return true;
        }

        return false;
    }

    if (strcmp(topico, TOPICO_GARAJE_ALARMA_CMD) == 0) {
        if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "ON") == 0) {
            actualizar_alarma(true);
        } else if (strcmp(mensaje, "0") == 0 || strcasecmp(mensaje, "OFF") == 0) {
            actualizar_alarma(false);
        } else {
            return false;
        }

        ESP_LOGI(TAG, "Alarma garaje: %s", alarma_activa ? "ON" : "OFF");
        return true;
    }

    return false;
}

void control_garaje_ejecutar(void)
{
    estado_sistema_t estado = control_global_obtener_estado();
    entradas_estado_t entradas = entradas_fisicas_obtener_estado();

    if (estado.paro_emergencia) {
        detener_porton();
        actualizar_alarma(false);
        return;
    }

    if (modo_garaje == MODO_GARAJE_SEGURO) {
        detener_porton();
        return;
    }

    if (entradas.fc_abierto && estado_porton != PORTON_ABRIENDO && estado_porton != PORTON_CERRANDO) {
        estado_porton = PORTON_ABIERTO;
    } else if (entradas.fc_cerrado && estado_porton != PORTON_ABRIENDO && estado_porton != PORTON_CERRANDO) {
        estado_porton = PORTON_CERRADO;
    }

    if (entradas.btn_stop_motor) {
        detener_porton();
        return;
    }

    if (entradas.btn_abrir && !btn_abrir_anterior) {
        iniciar_apertura_porton();
    }

    if (entradas.btn_cerrar && !btn_cerrar_anterior) {
        iniciar_cierre_porton();
    }

    btn_abrir_anterior = entradas.btn_abrir;
    btn_cerrar_anterior = entradas.btn_cerrar;

    if (estado_porton == PORTON_ABRIENDO && entradas.fc_abierto) {
        actuadores_motor_detener();
        estado_porton = PORTON_ABIERTO;
        ESP_LOGI(TAG, "Porton abierto por FC_ABIERTO");
    }

    if (estado_porton == PORTON_CERRANDO && entradas.fc_cerrado) {
        actuadores_motor_detener();
        estado_porton = PORTON_CERRADO;
        ESP_LOGI(TAG, "Porton cerrado por FC_CERRADO");
    }
}

const char *control_garaje_estado_texto(void)
{
    switch (estado_porton) {
        case PORTON_CERRADO:   return "CERRADO";
        case PORTON_ABRIENDO:  return "ABRIENDO";
        case PORTON_ABIERTO:   return "ABIERTO";
        case PORTON_CERRANDO:  return "CERRANDO";
        case PORTON_DETENIDO:  return "DETENIDO";
        default:               return "DESCONOCIDO";
    }
}

const char *control_garaje_modo_texto(void)
{
    switch (modo_garaje) {
        case MODO_GARAJE_NORMAL: return "NORMAL";
        case MODO_GARAJE_VISITA: return "VISITA";
        case MODO_GARAJE_MANUAL: return "MANUAL";
        case MODO_GARAJE_SEGURO: return "SEGURO";
        default:                 return "DESCONOCIDO";
    }
}

bool control_garaje_alarma_activa(void)
{
    return alarma_activa;
}
