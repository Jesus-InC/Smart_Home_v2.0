#include "actuadores.h"
#include "control_global.h"
#include "driver_dht22.h"
#include "driver_fc28.h"
#include "tareas_sistema.h"
#include "wifi_mqtt.h"
#include "control_garaje.h"
#include "memoria_nvs.h"
#include "config_usuario.h"
#include "entradas_fisicas.h"
#include "control_dimmer.h"

#include "esp_log.h"
#include "nvs_flash.h"

static const char *TAG = "main";

void app_main(void)
{
    esp_err_t resultado_nvs = nvs_flash_init();

    if (resultado_nvs == ESP_ERR_NVS_NO_FREE_PAGES || resultado_nvs == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    ESP_LOGI(TAG, "Smart Home v2.0 - Inicio");

    memoria_nvs_iniciar();
    control_global_iniciar();
    config_usuario_iniciar();

    control_garaje_iniciar();
    actuadores_iniciar();
    control_dimmer_iniciar();
    entradas_fisicas_iniciar();
    control_global_cargar_nvs();

    driver_dht22_iniciar();
    driver_fc28_iniciar();
    wifi_mqtt_iniciar();

    tareas_sistema_iniciar();
}
