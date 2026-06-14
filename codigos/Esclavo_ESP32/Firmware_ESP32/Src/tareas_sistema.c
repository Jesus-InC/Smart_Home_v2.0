#include "tareas_sistema.h"

#include "control_global.h"
#include "control_interior.h"
#include "control_garaje.h"
#include "driver_dht22.h"
#include "driver_fc28.h"
#include "entradas_fisicas.h"
#include "wifi_mqtt.h"
#include "configuracion.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_log.h"

static const char *TAG = "tareas_sistema";

#define TIEMPO_TELEMETRIA_MS 5000
#define TIEMPO_ENTRADAS_MS   100

static void publicar_estado_completo(void)
{
    wifi_mqtt_publicar_estado();
    wifi_mqtt_publicar_actuadores();
    wifi_mqtt_publicar_garaje();
    wifi_mqtt_publicar_config();
}

static void tarea_telemetria(void *parametros)
{
    static float temperatura = 25.0f;
    static float humedad_ambiente = 60.0f;
    static uint8_t humedad_suelo = 0;
    static bool error_dht_reportado = false;
    static bool error_fc28_reportado = false;

    while (1) {
        lectura_dht22_t lectura_dht22;

        esp_err_t resultado_dht = driver_dht22_leer(&lectura_dht22);

        if (resultado_dht == ESP_OK) {
            temperatura = lectura_dht22.temperatura;
            humedad_ambiente = lectura_dht22.humedad_ambiente;
            error_dht_reportado = false;
        } else {
            ESP_LOGW(TAG, "DHT22 sin lectura valida, manteniendo ultimo valor");

            if (!error_dht_reportado) {
                control_global_registrar_falla("DHT22_ERROR");
                error_dht_reportado = true;
            }
        }

        esp_err_t resultado_fc28 = driver_fc28_leer_porcentaje(&humedad_suelo);

        if (resultado_fc28 == ESP_OK) {
            error_fc28_reportado = false;
        } else {
            if (!error_fc28_reportado) {
                control_global_registrar_falla("FC28_ERROR");
                error_fc28_reportado = true;
            }
        }

        control_global_actualizar_sensores(
            temperatura,
            humedad_ambiente,
            humedad_suelo
        );

        control_interior_ejecutar();
        control_garaje_ejecutar();

        wifi_mqtt_publicar_estado();
        wifi_mqtt_publicar_actuadores();
        wifi_mqtt_publicar_sensores();
        wifi_mqtt_publicar_dimmer();
        wifi_mqtt_publicar_garaje();
        wifi_mqtt_publicar_config();

        vTaskDelay(pdMS_TO_TICKS(TIEMPO_TELEMETRIA_MS));
    }
}

static void tarea_entradas_fisicas(void *parametros)
{
    static bool btn_foco_anterior = false;
    static bool btn_vent_anterior = false;
    static bool btn_bomba_anterior = false;
    static bool btn_stop_anterior = false;

    ESP_LOGI(TAG, "Control fisico clasico ON/OFF cargado");

    while (1) {
        bool cambio_entradas = entradas_fisicas_actualizar();
        entradas_estado_t entradas = entradas_fisicas_obtener_estado();

        if (entradas.btn_stop != btn_stop_anterior) {
            control_global_procesar_mensaje(
                TOPICO_SISTEMA_ESTOP_CMD,
                entradas.btn_stop ? "1" : "0"
            );

            publicar_estado_completo();
        }

        btn_stop_anterior = entradas.btn_stop;

        if (entradas.btn_foco && !btn_foco_anterior) {
            ESP_LOGI(TAG, "BTN_FOCO detectado: ON/OFF");

            control_global_toggle_foco_fisico();
            wifi_mqtt_publicar_actuadores();
        }

        if (entradas.btn_vent && !btn_vent_anterior) {
            ESP_LOGI(TAG, "BTN_VENT detectado: ON/OFF");

            control_global_toggle_ventilador_fisico();
            control_interior_ejecutar();
            wifi_mqtt_publicar_actuadores();
        }

        if (entradas.btn_bomba && !btn_bomba_anterior) {
            ESP_LOGI(TAG, "BTN_BOMBA detectado: ON/OFF");

            control_global_toggle_bomba_fisico();
            control_interior_ejecutar();
            wifi_mqtt_publicar_actuadores();
        }

        btn_foco_anterior = entradas.btn_foco;
        btn_vent_anterior = entradas.btn_vent;
        btn_bomba_anterior = entradas.btn_bomba;

        control_garaje_ejecutar();

        if (cambio_entradas) {
            wifi_mqtt_publicar_entradas();
            wifi_mqtt_publicar_garaje();
        }

        vTaskDelay(pdMS_TO_TICKS(TIEMPO_ENTRADAS_MS));
    }
}

void tareas_sistema_iniciar(void)
{
    xTaskCreate(
        tarea_telemetria,
        "tarea_telemetria",
        4096,
        NULL,
        5,
        NULL
    );

    xTaskCreate(
        tarea_entradas_fisicas,
        "tarea_entradas",
        3072,
        NULL,
        6,
        NULL
    );

    ESP_LOGI(TAG, "Tareas del sistema iniciadas");
}