#include "driver_fc28.h"
#include "configuracion.h"

#include "esp_log.h"
#include "esp_err.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if !USAR_SENSORES_SIMULADOS
#include "esp_adc/adc_oneshot.h"
#endif

static const char *TAG = "driver_fc28";

#define FC28_NUM_MUESTRAS 10
#define FC28_TIEMPO_ENTRE_MUESTRAS_MS 5

#if !USAR_SENSORES_SIMULADOS
static adc_oneshot_unit_handle_t adc1_handle;
#endif

static uint8_t limitar_porcentaje(int valor)
{
    if (valor < 0) {
        return 0;
    }

    if (valor > 100) {
        return 100;
    }

    return (uint8_t)valor;
}

void driver_fc28_iniciar(void)
{
#if USAR_SENSORES_SIMULADOS
    ESP_LOGI(TAG, "FC-28 en modo simulado");
#else
    adc_oneshot_unit_init_cfg_t unidad_cfg = {
        .unit_id = ADC_UNIT_1,
    };

    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unidad_cfg, &adc1_handle));

    adc_oneshot_chan_cfg_t canal_cfg = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };

    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, ADC_CHANNEL_4, &canal_cfg));

    ESP_LOGI(TAG, "FC-28 en modo real - GPIO32 / ADC1_CH4");
#endif
}

esp_err_t driver_fc28_leer_porcentaje(uint8_t *humedad_suelo)
{
    if (humedad_suelo == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

#if USAR_SENSORES_SIMULADOS
    static uint8_t humedad = HUM_SUELO_SIM_INICIAL;
    static int direccion = 1;

    humedad += direccion;

    if (humedad >= 70) {
        direccion = -1;
    } else if (humedad <= 30) {
        direccion = 1;
    }

    *humedad_suelo = humedad;

    return ESP_OK;
#else
    int acumulado = 0;
    int muestras_validas = 0;
    int adc_min = 4095;
    int adc_max = 0;

    for (int i = 0; i < FC28_NUM_MUESTRAS; i++) {
        int muestra = 0;
        esp_err_t resultado = adc_oneshot_read(adc1_handle, ADC_CHANNEL_4, &muestra);

        if (resultado == ESP_OK) {
            acumulado += muestra;
            muestras_validas++;

            if (muestra < adc_min) {
                adc_min = muestra;
            }

            if (muestra > adc_max) {
                adc_max = muestra;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(FC28_TIEMPO_ENTRE_MUESTRAS_MS));
    }

    if (muestras_validas == 0) {
        ESP_LOGW(TAG, "Error leyendo ADC FC-28");
        return ESP_FAIL;
    }

    int adc_raw = acumulado / muestras_validas;

    int seco = FC28_ADC_SECO;
    int mojado = FC28_ADC_MOJADO;

    if (seco == mojado) {
        ESP_LOGW(TAG, "Error calibracion FC-28: seco y mojado son iguales");
        *humedad_suelo = 0;
        return ESP_ERR_INVALID_ARG;
    }

    int porcentaje = ((seco - adc_raw) * 100) / (seco - mojado);

    *humedad_suelo = limitar_porcentaje(porcentaje);

    ESP_LOGW(
        TAG,
        "FC-28 ADC RAW=%d min=%d max=%d Humedad=%u%%",
        adc_raw,
        adc_min,
        adc_max,
        *humedad_suelo
    );

    return ESP_OK;
#endif
}