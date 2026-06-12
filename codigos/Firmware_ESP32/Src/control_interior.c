#include "control_interior.h"
#include "control_global.h"
#include "config_usuario.h"

static float limitar_float(float valor, float minimo, float maximo)
{
    if (valor < minimo) return minimo;
    if (valor > maximo) return maximo;
    return valor;
}

static float pertenencia_subida(float valor, float minimo, float maximo)
{
    if (valor <= minimo) return 0.0f;
    if (valor >= maximo) return 1.0f;
    return (valor - minimo) / (maximo - minimo);
}

static float pertenencia_bajada(float valor, float minimo, float maximo)
{
    if (valor <= minimo) return 1.0f;
    if (valor >= maximo) return 0.0f;
    return (maximo - valor) / (maximo - minimo);
}

static float max_float(float a, float b)
{
    return a > b ? a : b;
}

static uint8_t calcular_ventilador_difuso(float temperatura, float humedad_ambiente, config_usuario_t config)
{
    float grado_calor = pertenencia_subida(temperatura, config.temp_min, config.temp_max);
    float grado_humedad = pertenencia_subida(humedad_ambiente, config.hum_amb_min, config.hum_amb_max);
    float demanda = max_float(grado_calor, grado_humedad);

    if (demanda < 0.05f) return 0;

    float velocidad = 25.0f + demanda * 75.0f;
    return (uint8_t)limitar_float(velocidad, 0.0f, 100.0f);
}

static bool calcular_bomba_auto(uint8_t humedad_suelo, bool bomba_actual, config_usuario_t config)
{
    uint8_t umbral = config.bomba_umbral_auto;
    uint8_t apagado = umbral + 5 > 100 ? 100 : umbral + 5;

    if (humedad_suelo <= umbral) return true;
    if (humedad_suelo >= apagado) return false;

    return bomba_actual;
}

static bool calcular_bomba_smart(uint8_t humedad_suelo, bool bomba_actual, float probabilidad_lluvia, config_usuario_t config)
{
    float grado_sequedad = pertenencia_bajada(humedad_suelo, config.hum_suelo_min, config.hum_suelo_max);
    float lluvia = limitar_float(probabilidad_lluvia, 0.0f, 1.0f);
    float demanda_riego = grado_sequedad * (1.0f - 0.85f * lluvia);

    if (demanda_riego >= 0.45f) return true;
    if (demanda_riego <= 0.25f) return false;

    return bomba_actual;
}

void control_interior_ejecutar(void)
{
    estado_sistema_t estado = control_global_obtener_estado();
    config_usuario_t config = config_usuario_obtener();

    if (estado.paro_emergencia || estado.modo_actual == MODO_MANUAL) {
        return;
    }

    if (!estado.ventilador_override) {
        uint8_t velocidad = calcular_ventilador_difuso(
            estado.temperatura,
            estado.humedad_ambiente,
            config
        );

        if (estado.modo_actual == MODO_SMART && !estado.presencia) {
            velocidad = 0;
        }

        control_global_set_ventilador(velocidad, false);
    }

    if (!estado.bomba_override) {
        bool encender_bomba = false;

        if (estado.modo_actual == MODO_AUTO) {
            encender_bomba = calcular_bomba_auto(
                estado.humedad_suelo,
                estado.bomba_encendida,
                config
            );
        } else if (estado.modo_actual == MODO_SMART) {
            encender_bomba = calcular_bomba_smart(
                estado.humedad_suelo,
                estado.bomba_encendida,
                estado.probabilidad_lluvia,
                config
            );
        }

        control_global_set_bomba(encender_bomba, false);
    }
}
