#ifndef ENTRADAS_FISICAS_H
#define ENTRADAS_FISICAS_H

#include <stdbool.h>

typedef struct {
    bool btn_foco;
    bool btn_vent;
    bool btn_bomba;
    bool btn_abrir;
    bool btn_cerrar;
    bool btn_stop_motor;
    bool btn_stop;
    bool fc_abierto;
    bool fc_cerrado;
} entradas_estado_t;

void entradas_fisicas_iniciar(void);
bool entradas_fisicas_actualizar(void);
entradas_estado_t entradas_fisicas_obtener_estado(void);

#endif