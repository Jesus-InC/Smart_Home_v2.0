#ifndef CONTROL_GARAJE_H
#define CONTROL_GARAJE_H

#include <stdbool.h>

typedef enum {
    MODO_GARAJE_NORMAL = 0,
    MODO_GARAJE_VISITA,
    MODO_GARAJE_MANUAL,
    MODO_GARAJE_SEGURO
} modo_garaje_t;

typedef enum {
    PORTON_CERRADO = 0,
    PORTON_ABRIENDO,
    PORTON_ABIERTO,
    PORTON_CERRANDO,
    PORTON_DETENIDO
} estado_porton_t;

void control_garaje_iniciar(void);

bool control_garaje_procesar_mensaje(const char *topico, const char *mensaje);
void control_garaje_ejecutar(void);

const char *control_garaje_estado_texto(void);
const char *control_garaje_modo_texto(void);

bool control_garaje_alarma_activa(void);

#endif
