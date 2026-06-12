#include "control_dimmer.h"
#include "configuracion.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_err.h"

static const char *TAG = "control_dimmer";

#define ZC_PERIODO_MIN_US       7000
#define ZC_PERIODO_MAX_US       25000

#define DIMMER_RETARDO_MIN_US   800
#define DIMMER_RETARDO_MAX_US   8500
#define DIMMER_PULSO_TRIAC_US   700

static volatile uint32_t contador_zc = 0;
static volatile int64_t ultimo_zc_us = 0;
static volatile uint32_t frecuencia_zc_hz = 0;

static volatile uint8_t nivel_dimmer = 0;

static esp_timer_handle_t timer_disparo_triac = NULL;
static esp_timer_handle_t timer_apagar_triac = NULL;

static uint32_t calcular_retardo_disparo(uint8_t nivel)
{
    if (nivel >= 95) {
        return DIMMER_RETARDO_MIN_US;
    }

    if (nivel == 0) {
        return DIMMER_RETARDO_MAX_US;
    }

    uint32_t rango = DIMMER_RETARDO_MAX_US - DIMMER_RETARDO_MIN_US;
    uint32_t retardo = DIMMER_RETARDO_MIN_US + ((100 - nivel) * rango) / 100;

    return retardo;
}
static void apagar_triac_callback(void *arg)
{
    gpio_set_level(PIN_FOCO_TRIAC, 0);
}

static void disparar_triac_callback(void *arg)
{
#if HABILITAR_PRUEBA_FOCO_TRIAC
    if (nivel_dimmer > 0) {
        gpio_set_level(PIN_FOCO_TRIAC, 1);

        if (timer_apagar_triac != NULL) {
            esp_timer_stop(timer_apagar_triac);
            esp_timer_start_once(timer_apagar_triac, DIMMER_PULSO_TRIAC_US);
        }
    }
#else
    gpio_set_level(PIN_FOCO_TRIAC, 0);
#endif
}

static void IRAM_ATTR interrupcion_cruce_cero(void *arg)
{
    int64_t ahora_us = esp_timer_get_time();

    if (ultimo_zc_us == 0) {
        ultimo_zc_us = ahora_us;
        return;
    }

    int64_t periodo_us = ahora_us - ultimo_zc_us;

    if (periodo_us < ZC_PERIODO_MIN_US) {
        return;
    }

    if (periodo_us > ZC_PERIODO_MAX_US) {
        ultimo_zc_us = ahora_us;
        return;
    }

    contador_zc++;
    frecuencia_zc_hz = 1000000 / periodo_us;
    ultimo_zc_us = ahora_us;

#if HABILITAR_PRUEBA_FOCO_TRIAC
    if (nivel_dimmer > 0 && timer_disparo_triac != NULL) {
        uint32_t retardo_us = calcular_retardo_disparo(nivel_dimmer);

        esp_timer_stop(timer_disparo_triac);
        esp_timer_start_once(timer_disparo_triac, retardo_us);
    }
#endif
}

void control_dimmer_iniciar(void)
{
    gpio_reset_pin(PIN_FOCO_TRIAC);
    gpio_set_direction(PIN_FOCO_TRIAC, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_FOCO_TRIAC, 0);

    gpio_config_t zc_cfg = {
        .pin_bit_mask = (1ULL << PIN_FOCO_ZC),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE
    };

    gpio_config(&zc_cfg);

    esp_timer_create_args_t timer_disparo_args = {
        .callback = disparar_triac_callback,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "triac_on"
    };

    esp_timer_create_args_t timer_apagado_args = {
        .callback = apagar_triac_callback,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "triac_off"
    };

    ESP_ERROR_CHECK(esp_timer_create(&timer_disparo_args, &timer_disparo_triac));
    ESP_ERROR_CHECK(esp_timer_create(&timer_apagado_args, &timer_apagar_triac));

    esp_err_t resultado_isr = gpio_install_isr_service(0);

    if (resultado_isr != ESP_OK && resultado_isr != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "Error instalando ISR GPIO: %s", esp_err_to_name(resultado_isr));
    }

    gpio_isr_handler_add(PIN_FOCO_ZC, interrupcion_cruce_cero, NULL);

    ESP_LOGI(TAG, "Dimmer iniciado: ZC GPIO%d, TRIAC GPIO%d", PIN_FOCO_ZC, PIN_FOCO_TRIAC);
}

void control_dimmer_set_nivel(uint8_t nivel)
{
    if (nivel > 100) {
        nivel = 100;
    }

    nivel_dimmer = nivel;

    if (nivel_dimmer == 0) {
        gpio_set_level(PIN_FOCO_TRIAC, 0);

        if (timer_disparo_triac != NULL) {
            esp_timer_stop(timer_disparo_triac);
        }

        if (timer_apagar_triac != NULL) {
            esp_timer_stop(timer_apagar_triac);
        }
    }

    ESP_LOGI(TAG, "Nivel dimmer foco: %u%%", nivel_dimmer);
}

uint8_t control_dimmer_get_nivel(void)
{
    return nivel_dimmer;
}

uint32_t control_dimmer_obtener_contador_zc(void)
{
    return contador_zc;
}

uint32_t control_dimmer_obtener_frecuencia_zc(void)
{
    return frecuencia_zc_hz;
}