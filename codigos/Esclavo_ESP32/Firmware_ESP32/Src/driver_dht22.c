#include "driver_dht22.h"
#include "configuracion.h"

#include "esp_err.h"
#include "esp_log.h"

#if !USAR_SENSORES_SIMULADOS
#include "dht.h"
#endif

static const char *TAG = "driver_dht22";

void driver_dht22_iniciar(void)
{
#if USAR_SENSORES_SIMULADOS
    ESP_LOGI(TAG, "DHT22 en modo simulado");
#else
    ESP_LOGI(TAG, "DHT22 usando componente esp-idf-lib/dht - GPIO4");
#endif
}

esp_err_t driver_dht22_leer(lectura_dht22_t *lectura)
{
    if (lectura == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

#if USAR_SENSORES_SIMULADOS
    static float temperatura = TEMP_SIM_INICIAL;
    static float humedad = HUM_AMB_SIM_INICIAL;
    static int direccion = 1;

    temperatura += 0.1f * direccion;
    humedad += 0.2f * direccion;

    if (temperatura > 27.0f || temperatura < 23.5f) {
        direccion *= -1;
    }

    lectura->temperatura = temperatura;
    lectura->humedad_ambiente = humedad;

    return ESP_OK;
#else
    float humedad = 0.0f;
    float temperatura = 0.0f;

    esp_err_t resultado = dht_read_float_data(
        DHT_TYPE_AM2301,
        DHT_PIN,
        &humedad,
        &temperatura
    );

    if (resultado != ESP_OK) {
        ESP_LOGW(TAG, "Error leyendo DHT22 con componente: %s", esp_err_to_name(resultado));
        return resultado;
    }

    lectura->temperatura = temperatura;
    lectura->humedad_ambiente = humedad;

    ESP_LOGI(TAG, "DHT22 Temp=%.1f C Hum=%.1f%%", temperatura, humedad);

    return ESP_OK;
#endif
}