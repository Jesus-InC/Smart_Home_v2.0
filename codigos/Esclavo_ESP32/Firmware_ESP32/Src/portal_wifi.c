#include "portal_wifi.h"
#include "configuracion.h"
#include "memoria_nvs.h"

#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *TAG = "portal_wifi";

#define NVS_WIFI_SSID       "wifi_ssid"
#define NVS_WIFI_CLAVE      "wifi_clave"
#define NVS_MQTT_HOST       "mqtt_host"
#define NVS_MQTT_PUERTO     "mqtt_puerto"

static httpd_handle_t servidor = NULL;
static bool modo_config = false;
static bool netif_ap_creada = false;

static int hex_a_int(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return 0;
}

static void decodificar_url(const char *entrada, char *salida, size_t tamano)
{
    size_t j = 0;

    for (size_t i = 0; entrada[i] != '\0' && j + 1 < tamano; i++) {
        if (entrada[i] == '+') {
            salida[j++] = ' ';
        } else if (entrada[i] == '%' && isxdigit((unsigned char)entrada[i + 1]) && isxdigit((unsigned char)entrada[i + 2])) {
            salida[j++] = (char)((hex_a_int(entrada[i + 1]) << 4) | hex_a_int(entrada[i + 2]));
            i += 2;
        } else {
            salida[j++] = entrada[i];
        }
    }

    salida[j] = '\0';
}

static void extraer_campo(const char *cuerpo, const char *nombre, char *salida, size_t tamano)
{
    char patron[32];
    snprintf(patron, sizeof(patron), "%s=", nombre);

    const char *inicio = strstr(cuerpo, patron);
    if (inicio == NULL) {
        salida[0] = '\0';
        return;
    }

    inicio += strlen(patron);
    const char *fin = strchr(inicio, '&');
    size_t largo = fin ? (size_t)(fin - inicio) : strlen(inicio);

    char temporal[128];
    if (largo >= sizeof(temporal)) largo = sizeof(temporal) - 1;

    memcpy(temporal, inicio, largo);
    temporal[largo] = '\0';

    decodificar_url(temporal, salida, tamano);
}

static bool puerto_mqtt_valido(uint16_t puerto)
{
    return puerto > 0;
}

bool portal_wifi_cargar_credenciales(char *ssid, size_t tamano_ssid, char *clave, size_t tamano_clave)
{
    memoria_nvs_leer_string(NVS_WIFI_SSID, ssid, tamano_ssid, "");
    memoria_nvs_leer_string(NVS_WIFI_CLAVE, clave, tamano_clave, "");

    return strlen(ssid) > 0;
}

bool portal_wifi_cargar_broker(char *host, size_t tamano_host, uint16_t *puerto)
{
    uint32_t puerto_nvs = MQTT_BROKER_PUERTO_DEFECTO;

    memoria_nvs_leer_string(NVS_MQTT_HOST, host, tamano_host, MQTT_BROKER_HOST_DEFECTO);
    memoria_nvs_leer_u32(NVS_MQTT_PUERTO, &puerto_nvs, MQTT_BROKER_PUERTO_DEFECTO);

    if (strlen(host) == 0) {
        snprintf(host, tamano_host, "%s", MQTT_BROKER_HOST_DEFECTO);
    }

    if (puerto_nvs == 0 || puerto_nvs > 65535) {
        puerto_nvs = MQTT_BROKER_PUERTO_DEFECTO;
    }

    if (puerto != NULL) {
        *puerto = (uint16_t)puerto_nvs;
    }

    return strlen(host) > 0 && puerto_mqtt_valido((uint16_t)puerto_nvs);
}

void portal_wifi_guardar_credenciales(const char *ssid, const char *clave)
{
    memoria_nvs_guardar_string(NVS_WIFI_SSID, ssid);
    memoria_nvs_guardar_string(NVS_WIFI_CLAVE, clave);
    ESP_LOGI(TAG, "Credenciales WiFi guardadas");
}

void portal_wifi_guardar_broker(const char *host, uint16_t puerto)
{
    const char *host_final = (host != NULL && strlen(host) > 0) ? host : MQTT_BROKER_HOST_DEFECTO;
    uint16_t puerto_final = puerto_mqtt_valido(puerto) ? puerto : MQTT_BROKER_PUERTO_DEFECTO;

    memoria_nvs_guardar_string(NVS_MQTT_HOST, host_final);
    memoria_nvs_guardar_u32(NVS_MQTT_PUERTO, puerto_final);

    ESP_LOGI(TAG, "Broker MQTT guardado: %s:%u", host_final, puerto_final);
}

void portal_wifi_guardar_configuracion(const char *ssid, const char *clave, const char *broker_host, uint16_t broker_puerto)
{
    portal_wifi_guardar_credenciales(ssid, clave);
    portal_wifi_guardar_broker(broker_host, broker_puerto);
}

void portal_wifi_olvidar_credenciales(void)
{
    memoria_nvs_borrar_clave(NVS_WIFI_SSID);
    memoria_nvs_borrar_clave(NVS_WIFI_CLAVE);
    memoria_nvs_borrar_clave(NVS_MQTT_HOST);
    memoria_nvs_borrar_clave(NVS_MQTT_PUERTO);
    ESP_LOGW(TAG, "Credenciales WiFi y broker MQTT borrados");
}

static esp_err_t manejar_inicio(httpd_req_t *req)
{
    const char *html =
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SmartHome Config</title></head>"
        "<body style='font-family:Arial;max-width:460px;margin:30px auto;padding:0 14px;'>"
        "<h2>SmartHome WiFi</h2>"
        "<p>Portal minimo para configurar la red WiFi y el broker MQTT de la Raspberry Pi.</p>"
        "<form method='POST' action='/guardar'>"
        "<label>SSID de la red WiFi</label><br><input name='ssid' maxlength='32' style='width:100%;height:34px'><br><br>"
        "<label>Contrasena WiFi</label><br><input name='clave' type='password' maxlength='64' style='width:100%;height:34px'><br><br>"
        "<label>IP del broker MQTT / Raspberry Pi</label><br>"
        "<input name='broker' maxlength='63' placeholder='192.168.1.19' style='width:100%;height:34px'><br>"
        "<small>Ejemplo: la IP que muestra hostname -I en la Raspberry.</small><br><br>"
        "<label>Puerto MQTT</label><br>"
        "<input name='puerto' type='number' min='1' max='65535' value='1883' style='width:100%;height:34px'><br><br>"
        "<button type='submit' style='height:38px;width:100%;'>Guardar y reiniciar</button>"
        "</form></body></html>";

    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, html, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t manejar_guardar(httpd_req_t *req)
{
    char cuerpo[384];
    int recibido = httpd_req_recv(req, cuerpo, sizeof(cuerpo) - 1);

    if (recibido <= 0) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Sin datos");
        return ESP_FAIL;
    }

    cuerpo[recibido] = '\0';

    char ssid[33];
    char clave[65];
    char broker[64];
    char puerto_txt[8];

    extraer_campo(cuerpo, "ssid", ssid, sizeof(ssid));
    extraer_campo(cuerpo, "clave", clave, sizeof(clave));
    extraer_campo(cuerpo, "broker", broker, sizeof(broker));
    extraer_campo(cuerpo, "puerto", puerto_txt, sizeof(puerto_txt));

    if (strlen(ssid) == 0) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "SSID vacio");
        return ESP_FAIL;
    }

    int puerto_int = atoi(puerto_txt);
    uint16_t puerto = MQTT_BROKER_PUERTO_DEFECTO;

    if (puerto_int > 0 && puerto_int <= 65535) {
        puerto = (uint16_t)puerto_int;
    }

    if (strlen(broker) == 0) {
        snprintf(broker, sizeof(broker), "%s", MQTT_BROKER_HOST_DEFECTO);
    }

    portal_wifi_guardar_configuracion(ssid, clave, broker, puerto);

    httpd_resp_sendstr(req, "WiFi y broker MQTT guardados. Reiniciando ESP32...");
    vTaskDelay(pdMS_TO_TICKS(800));
    esp_restart();

    return ESP_OK;
}

static void iniciar_servidor(void)
{
    if (servidor != NULL) return;

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    if (httpd_start(&servidor, &config) != ESP_OK) {
        ESP_LOGE(TAG, "No se pudo iniciar servidor HTTP de configuracion");
        return;
    }

    httpd_uri_t uri_inicio = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = manejar_inicio,
        .user_ctx = NULL
    };

    httpd_uri_t uri_guardar = {
        .uri = "/guardar",
        .method = HTTP_POST,
        .handler = manejar_guardar,
        .user_ctx = NULL
    };

    httpd_register_uri_handler(servidor, &uri_inicio);
    httpd_register_uri_handler(servidor, &uri_guardar);

    ESP_LOGI(TAG, "Portal WiFi listo en http://192.168.4.1");
}

void portal_wifi_iniciar_ap_config(void)
{
    if (modo_config) return;

    modo_config = true;

    if (!netif_ap_creada) {
        esp_netif_create_default_wifi_ap();
        netif_ap_creada = true;
    }

    esp_wifi_stop();

    wifi_config_t config_ap = {0};
    snprintf((char *)config_ap.ap.ssid, sizeof(config_ap.ap.ssid), "%s", PORTAL_WIFI_SSID);
    snprintf((char *)config_ap.ap.password, sizeof(config_ap.ap.password), "%s", PORTAL_WIFI_PASSWORD);
    config_ap.ap.ssid_len = strlen(PORTAL_WIFI_SSID);
    config_ap.ap.channel = PORTAL_WIFI_CANAL;
    config_ap.ap.max_connection = PORTAL_WIFI_MAX_CONEX;
    config_ap.ap.authmode = strlen(PORTAL_WIFI_PASSWORD) == 0 ? WIFI_AUTH_OPEN : WIFI_AUTH_WPA_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &config_ap));
    ESP_ERROR_CHECK(esp_wifi_start());

    iniciar_servidor();

    ESP_LOGW(TAG, "Modo configuracion WiFi activo. SSID: %s", PORTAL_WIFI_SSID);
}

bool portal_wifi_en_modo_config(void)
{
    return modo_config;
}
