#include "entradas_fisicas.h"
#include "configuracion.h"

#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "entradas_fisicas";

static entradas_estado_t estado_actual;
static entradas_estado_t estado_anterior;
static bool primera_lectura = true;

static bool leer_activo_bajo(gpio_num_t pin)
{
    return gpio_get_level(pin) == 0;
}

static bool leer_activo_alto(gpio_num_t pin)
{
    return gpio_get_level(pin) == 1;
}

void entradas_fisicas_iniciar(void)
{
    gpio_config_t entradas_pullup = {
        .pin_bit_mask =
            (1ULL << BTN_FOCO) |
            (1ULL << BTN_VENT) |
            (1ULL << BTN_BOMBA) |
            (1ULL << BTN_ABRIR) |
            (1ULL << BTN_CERRAR),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    gpio_config(&entradas_pullup);

    gpio_config_t entradas_sin_pullup = {
        .pin_bit_mask =
            (1ULL << FC_ABIERTO) |
            (1ULL << FC_CERRADO) |
            (1ULL << BTN_STOP_MOTOR) |
            (1ULL << BTN_STOP),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    gpio_config(&entradas_sin_pullup);

    entradas_fisicas_actualizar();

    ESP_LOGI(TAG, "Entradas fisicas inicializadas");
}

bool entradas_fisicas_actualizar(void)
{
    estado_anterior = estado_actual;

    estado_actual.btn_foco = leer_activo_bajo(BTN_FOCO);
    estado_actual.btn_vent = leer_activo_bajo(BTN_VENT);
    estado_actual.btn_bomba = leer_activo_bajo(BTN_BOMBA);
    estado_actual.btn_abrir = leer_activo_bajo(BTN_ABRIR);
    estado_actual.btn_cerrar = leer_activo_bajo(BTN_CERRAR);

    estado_actual.btn_stop_motor = leer_activo_bajo(BTN_STOP_MOTOR);
	estado_actual.fc_abierto = leer_activo_alto(FC_ABIERTO);
	estado_actual.fc_cerrado = leer_activo_alto(FC_CERRADO);

    // STOP general recomendado NC:
    // normal = 0, presionado/falla/cable abierto = 1
    estado_actual.btn_stop = leer_activo_alto(BTN_STOP);

    bool cambio =
        primera_lectura ||
        estado_actual.btn_foco != estado_anterior.btn_foco ||
        estado_actual.btn_vent != estado_anterior.btn_vent ||
        estado_actual.btn_bomba != estado_anterior.btn_bomba ||
        estado_actual.btn_abrir != estado_anterior.btn_abrir ||
        estado_actual.btn_cerrar != estado_anterior.btn_cerrar ||
        estado_actual.btn_stop_motor != estado_anterior.btn_stop_motor ||
        estado_actual.btn_stop != estado_anterior.btn_stop ||
        estado_actual.fc_abierto != estado_anterior.fc_abierto ||
        estado_actual.fc_cerrado != estado_anterior.fc_cerrado;

    primera_lectura = false;

    return cambio;
}

entradas_estado_t entradas_fisicas_obtener_estado(void)
{
    return estado_actual;
}