#include "wifi_mqtt.h"
#include "configuracion.h"
#include "control_global.h"
#include "control_garaje.h"
#include "config_usuario.h"
#include "entradas_fisicas.h"
#include "control_dimmer.h"
#include "portal_wifi.h"

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"

#include "mqtt_client.h"

#include <stdio.h>
#include <string.h>
#include <strings.h>

static const char *TAG = "wifi_mqtt";

static EventGroupHandle_t grupo_wifi;
static esp_mqtt_client_handle_t cliente_mqtt = NULL;
static bool mqtt_iniciado = false;
static bool mqtt_conectado = false;
static bool modo_ap_config = false;
static bool netif_sta_creada = false;
static int reintentos_wifi = 0;
static char ip_actual[16] = "0.0.0.0";
static int rssi_actual = 0;

#define BIT_WIFI_CONECTADO BIT0

static void mqtt_iniciar(void);

static void publicar_texto(const char *topico, const char *mensaje)
{
    if (!mqtt_conectado || cliente_mqtt == NULL) return;
    esp_mqtt_client_publish(cliente_mqtt, topico, mensaje, 0, 1, 0);
}

static void publicar_entero(const char *topico, int valor)
{
    char mensaje[16];
    snprintf(mensaje, sizeof(mensaje), "%d", valor);
    publicar_texto(topico, mensaje);
}

static void publicar_float(const char *topico, float valor)
{
    char mensaje[24];
    snprintf(mensaje, sizeof(mensaje), "%.1f", valor);
    publicar_texto(topico, mensaje);
}

static void suscribir_topicos(void)
{
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_SISTEMA_ESTOP, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_SISTEMA_ESTOP_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_SISTEMA_WIFI_OLVIDAR_CMD, 1);

    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_INTERIOR_MODO_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_INTERIOR_FOCO_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_INTERIOR_BOMBA_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_INTERIOR_VENT_CMD, 1);

    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_IA_PRESENCIA, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_IA_PROB_LLUVIA, 1);

    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_GARAJE_MODO_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_GARAJE_PORTON_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_GARAJE_ALARMA_CMD, 1);

    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_TEMP_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_TEMP_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_HUM_AMB_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_HUM_AMB_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_HUM_SUELO_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_HUM_SUELO_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_BOMBA_UMBRAL_CMD, 1);

    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_TEMP_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_TEMP_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_HUM_AMB_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_HUM_AMB_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_HUM_SUELO_MIN_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_HUM_SUELO_MAX_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_BOMBA_UMBRAL_CMD, 1);
    esp_mqtt_client_subscribe(cliente_mqtt, TOPICO_CONFIG_INTERIOR_RESET_CMD, 1);
}

static bool procesar_comando_wifi(const char *topico, const char *mensaje)
{
    if (strcmp(topico, TOPICO_SISTEMA_WIFI_OLVIDAR_CMD) != 0) return false;

    if (strcmp(mensaje, "1") == 0 || strcasecmp(mensaje, "ON") == 0 || strcasecmp(mensaje, "RESET") == 0) {
        publicar_texto(TOPICO_SISTEMA_FALLA_EVENTO, "WIFI_CREDENCIALES_BORRADAS");
        portal_wifi_olvidar_credenciales();
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
    }

    return true;
}

static void manejador_mqtt(void *args, esp_event_base_t base, int32_t id_evento, void *datos_evento)
{
    esp_mqtt_event_handle_t evento = datos_evento;

    switch ((esp_mqtt_event_id_t)id_evento) {
        case MQTT_EVENT_CONNECTED:
            mqtt_conectado = true;
            control_global_set_mqtt(true);
            ESP_LOGI(TAG, "MQTT conectado");

            suscribir_topicos();
            wifi_mqtt_publicar_estado();
            wifi_mqtt_publicar_actuadores();
            wifi_mqtt_publicar_sensores();
            wifi_mqtt_publicar_garaje();
            wifi_mqtt_publicar_config();
            wifi_mqtt_publicar_entradas();
            break;

        case MQTT_EVENT_DISCONNECTED:
            mqtt_conectado = false;
            control_global_set_mqtt(false);
            ESP_LOGW(TAG, "MQTT desconectado");
            break;

        case MQTT_EVENT_DATA: {
            char topico[128];
            char mensaje[128];

            int largo_topico = evento->topic_len;
            int largo_mensaje = evento->data_len;

            if (largo_topico >= sizeof(topico)) largo_topico = sizeof(topico) - 1;
            if (largo_mensaje >= sizeof(mensaje)) largo_mensaje = sizeof(mensaje) - 1;

            memcpy(topico, evento->topic, largo_topico);
            topico[largo_topico] = '\0';

            memcpy(mensaje, evento->data, largo_mensaje);
            mensaje[largo_mensaje] = '\0';

            ESP_LOGI(TAG, "MQTT RX [%s]: %s", topico, mensaje);

            bool mensaje_procesado = procesar_comando_wifi(topico, mensaje);

            if (!mensaje_procesado) mensaje_procesado = control_global_procesar_mensaje(topico, mensaje);
            if (!mensaje_procesado) mensaje_procesado = control_garaje_procesar_mensaje(topico, mensaje);
            if (!mensaje_procesado) mensaje_procesado = config_usuario_procesar_mensaje(topico, mensaje);

            if (mensaje_procesado) {
                control_garaje_ejecutar();
                wifi_mqtt_publicar_estado();
                wifi_mqtt_publicar_actuadores();
                wifi_mqtt_publicar_garaje();
                wifi_mqtt_publicar_config();
            }

            break;
        }

        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "Error MQTT");
            control_global_registrar_falla("MQTT_ERROR");
            break;

        default:
            break;
    }
}

static void mqtt_iniciar(void)
{
    if (mqtt_iniciado) return;

    esp_mqtt_client_config_t config_mqtt = {
        .broker.address.uri = MQTT_URI
    };

    cliente_mqtt = esp_mqtt_client_init(&config_mqtt);
    esp_mqtt_client_register_event(cliente_mqtt, ESP_EVENT_ANY_ID, manejador_mqtt, NULL);
    esp_mqtt_client_start(cliente_mqtt);

    mqtt_iniciado = true;
}

static void iniciar_modo_ap_config(void)
{
    modo_ap_config = true;
    control_global_set_wifi(false);
    control_global_registrar_falla("WIFI_CONFIG_AP");
    portal_wifi_iniciar_ap_config();
}

static void manejador_wifi(void *arg, esp_event_base_t base_evento, int32_t id_evento, void *datos_evento)
{
    if (modo_ap_config) return;

    if (base_evento == WIFI_EVENT && id_evento == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    }

    if (base_evento == WIFI_EVENT && id_evento == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(grupo_wifi, BIT_WIFI_CONECTADO);
        control_global_set_wifi(false);

        reintentos_wifi++;

        if (reintentos_wifi >= WIFI_REINTENTOS_MAX) {
            ESP_LOGW(TAG, "WiFi no conectado. Activando AP de configuracion");
            iniciar_modo_ap_config();
        } else {
            ESP_LOGW(TAG, "WiFi desconectado, reintento %d/%d", reintentos_wifi, WIFI_REINTENTOS_MAX);
            esp_wifi_connect();
        }
    }

    if (base_evento == IP_EVENT && id_evento == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *evento = datos_evento;
        wifi_ap_record_t info_ap;

        reintentos_wifi = 0;
        xEventGroupSetBits(grupo_wifi, BIT_WIFI_CONECTADO);
        control_global_set_wifi(true);

        snprintf(ip_actual, sizeof(ip_actual), IPSTR, IP2STR(&evento->ip_info.ip));

        if (esp_wifi_sta_get_ap_info(&info_ap) == ESP_OK) {
            rssi_actual = info_ap.rssi;
        }

        ESP_LOGI(TAG, "WiFi conectado. IP: %s", ip_actual);
        mqtt_iniciar();
    }
}

void wifi_mqtt_iniciar(void)
{
    char ssid[33];
    char clave[65];

    grupo_wifi = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t config_inicial = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&config_inicial));

    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, manejador_wifi, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, manejador_wifi, NULL, NULL);

    if (!portal_wifi_cargar_credenciales(ssid, sizeof(ssid), clave, sizeof(clave))) {
        ESP_LOGW(TAG, "No hay credenciales WiFi guardadas");
        iniciar_modo_ap_config();
        return;
    }

    if (!netif_sta_creada) {
        esp_netif_create_default_wifi_sta();
        netif_sta_creada = true;
    }

    wifi_config_t config_wifi = {0};
    snprintf((char *)config_wifi.sta.ssid, sizeof(config_wifi.sta.ssid), "%s", ssid);
    snprintf((char *)config_wifi.sta.password, sizeof(config_wifi.sta.password), "%s", clave);
    config_wifi.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config_wifi));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi iniciado en modo STA");
}

void wifi_mqtt_publicar_estado(void)
{
    estado_sistema_t estado = control_global_obtener_estado();

    publicar_texto(TOPICO_INTERIOR_MODO_ESTADO, control_global_modo_texto(estado.modo_actual));
    publicar_entero(TOPICO_SISTEMA_ESTOP_ESTADO, estado.paro_emergencia ? 1 : 0);
    publicar_entero(TOPICO_SISTEMA_ESTADO_SEGURO, estado.estado_seguro_arranque ? 1 : 0);
    publicar_texto(TOPICO_SISTEMA_CONEXION_ESTADO, estado.mqtt_conectado ? "ONLINE" : "OFFLINE");
    publicar_texto(TOPICO_SISTEMA_WIFI_ESTADO, estado.wifi_conectado ? "CONECTADO" : "DESCONECTADO");
    publicar_texto(TOPICO_SISTEMA_WIFI_IP, ip_actual);
    publicar_entero(TOPICO_SISTEMA_WIFI_RSSI, rssi_actual);
    publicar_texto(TOPICO_SISTEMA_FALLA_ULTIMA, estado.ultima_falla);
    publicar_entero(TOPICO_SISTEMA_FALLA_CONTADOR, estado.contador_fallas);
}

void wifi_mqtt_publicar_actuadores(void)
{
    estado_sistema_t estado = control_global_obtener_estado();

    publicar_entero(TOPICO_INTERIOR_FOCO_ESTADO, estado.nivel_foco);
    publicar_entero(TOPICO_INTERIOR_BOMBA_ESTADO, estado.bomba_encendida ? 1 : 0);
    publicar_entero(TOPICO_INTERIOR_VENT_ESTADO, estado.velocidad_ventilador);

    publicar_entero(TOPICO_INTERIOR_FOCO_OVERRIDE, estado.foco_override ? 1 : 0);
    publicar_entero(TOPICO_INTERIOR_BOMBA_OVERRIDE, estado.bomba_override ? 1 : 0);
    publicar_entero(TOPICO_INTERIOR_VENT_OVERRIDE, estado.ventilador_override ? 1 : 0);
}

void wifi_mqtt_publicar_sensores(void)
{
    estado_sistema_t estado = control_global_obtener_estado();

    publicar_float(TOPICO_SENSOR_TEMP, estado.temperatura);
    publicar_float(TOPICO_SENSOR_HUM_AMB, estado.humedad_ambiente);
    publicar_entero(TOPICO_SENSOR_HUM_SUELO, estado.humedad_suelo);
}

void wifi_mqtt_publicar_garaje(void)
{
    publicar_texto(TOPICO_GARAJE_MODO_ESTADO, control_garaje_modo_texto());
    publicar_texto(TOPICO_GARAJE_PORTON_ESTADO, control_garaje_estado_texto());
    publicar_entero(TOPICO_GARAJE_ALARMA_ESTADO, control_garaje_alarma_activa() ? 1 : 0);
}

void wifi_mqtt_publicar_config(void)
{
    config_usuario_t config = config_usuario_obtener();

    publicar_entero(TOPICO_CONFIG_TEMP_MIN_ESTADO, config.temp_min);
    publicar_entero(TOPICO_CONFIG_TEMP_MAX_ESTADO, config.temp_max);
    publicar_entero(TOPICO_CONFIG_HUM_AMB_MIN_ESTADO, config.hum_amb_min);
    publicar_entero(TOPICO_CONFIG_HUM_AMB_MAX_ESTADO, config.hum_amb_max);
    publicar_entero(TOPICO_CONFIG_HUM_SUELO_MIN_ESTADO, config.hum_suelo_min);
    publicar_entero(TOPICO_CONFIG_HUM_SUELO_MAX_ESTADO, config.hum_suelo_max);
    publicar_entero(TOPICO_CONFIG_BOMBA_UMBRAL_ESTADO, config.bomba_umbral_auto);

    publicar_entero(TOPICO_CONFIG_INTERIOR_TEMP_MIN_ESTADO, config.temp_min);
    publicar_entero(TOPICO_CONFIG_INTERIOR_TEMP_MAX_ESTADO, config.temp_max);
    publicar_entero(TOPICO_CONFIG_INTERIOR_HUM_AMB_MIN_ESTADO, config.hum_amb_min);
    publicar_entero(TOPICO_CONFIG_INTERIOR_HUM_AMB_MAX_ESTADO, config.hum_amb_max);
    publicar_entero(TOPICO_CONFIG_INTERIOR_HUM_SUELO_MIN_ESTADO, config.hum_suelo_min);
    publicar_entero(TOPICO_CONFIG_INTERIOR_HUM_SUELO_MAX_ESTADO, config.hum_suelo_max);
    publicar_entero(TOPICO_CONFIG_INTERIOR_BOMBA_UMBRAL_ESTADO, config.bomba_umbral_auto);
}

void wifi_mqtt_publicar_entradas(void)
{
    entradas_estado_t entradas = entradas_fisicas_obtener_estado();

    publicar_entero(TOPICO_ENTRADA_BTN_FOCO, entradas.btn_foco ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_VENT, entradas.btn_vent ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_BOMBA, entradas.btn_bomba ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_ABRIR, entradas.btn_abrir ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_CERRAR, entradas.btn_cerrar ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_STOP_MOTOR, entradas.btn_stop_motor ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_BTN_STOP, entradas.btn_stop ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_FC_ABIERTO, entradas.fc_abierto ? 1 : 0);
    publicar_entero(TOPICO_ENTRADA_FC_CERRADO, entradas.fc_cerrado ? 1 : 0);
}

void wifi_mqtt_publicar_dimmer(void)
{
    publicar_entero(TOPICO_FOCO_ZC_CONTADOR, control_dimmer_obtener_contador_zc());
    publicar_entero(TOPICO_FOCO_ZC_FREQ, control_dimmer_obtener_frecuencia_zc());
}

void wifi_mqtt_publicar_accion_fisica(const char *topico, const char *accion)
{
    publicar_texto(topico, accion);
}
