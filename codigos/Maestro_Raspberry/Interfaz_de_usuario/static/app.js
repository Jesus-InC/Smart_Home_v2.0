let estadoActual = {};
let ultimoEvento = ""; // Variable para rastrear el último evento y no duplicarlo

function valorNumero(x, defecto = 0) {
    const n = Number(x);
    return Number.isFinite(n) ? n : defecto;
}

async function publicar(topic, payload) {
    try {
        const r = await fetch("/api/publicar", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({topic, payload})
        });

        const data = await r.json();

        if (!data.ok) {
            alert(data.error || "Error publicando MQTT");
        }
    } catch (e) {
        alert("Error comunicando con Flask");
        console.error(e);
    }
}

function estadoPortonVisible(valor) {
    const v = String(valor || "").toUpperCase();

    const mapa = {
        "ABRIENDO": "ABRIENDO",
        "CERRANDO": "CERRANDO",
        "ABIERTO": "ABIERTO",
        "CERRADO": "CERRADO",
        "DETENIDO": "DETENIDO"
    };

    return mapa[v] || valor;
}

function actualizarTexto(id, valor) {
    const el = document.getElementById(id);
    if (el) el.textContent = valor;
}

function setDisabled(id, valor) {
    const el = document.getElementById(id);
    if (el) el.disabled = valor;
}

function actualizarValorSlider(nombre) {
    const slider = document.getElementById(`${nombre}_slider`);
    const etiqueta = document.getElementById(`${nombre}_slider_val`);

    if (slider && etiqueta) {
        etiqueta.textContent = slider.value;
    }
}

function agregarNotificacion(mensaje) {
    const caja = document.getElementById("caja_notificaciones");
    if (!caja) return;

    const div = document.createElement("div");
    const hora = new Date().toLocaleTimeString();
    
    div.innerHTML = `<span style="color: #64748b;">[${hora}]</span> ${mensaje}`;
    div.style.marginBottom = "4px";

    caja.appendChild(div);
    
    caja.scrollTop = caja.scrollHeight; 
}

function limpiarNotificaciones() {
    const caja = document.getElementById("caja_notificaciones");
    if (caja) caja.innerHTML = "";
    ultimoEvento = "";
}

function aplicarModoInterfaz() {
    const modo = String(estadoActual.modo_interior || "").toUpperCase();
    const esManual = modo === "MANUAL";

    const ventOverride = String(estadoActual.vent_override || "0") === "1";
    const bombaOverride = String(estadoActual.bomba_override || "0") === "1";

    setDisabled("btn_vent_off", !esManual);
    setDisabled("btn_vent_on", !esManual);
    setDisabled("vent_slider", !esManual);

    setDisabled("btn_bomba_off", !esManual);
    setDisabled("btn_bomba_on", !esManual);

    setDisabled("btn_cancelar_vent", !ventOverride);
    setDisabled("btn_cancelar_bomba", !bombaOverride);

    const notaVent = document.getElementById("nota_vent");
    const notaBomba = document.getElementById("nota_bomba");

    if (notaVent) {
        notaVent.textContent = esManual
            ? "En MANUAL puedes controlar ON/OFF y PWM desde la interfaz."
            : "En AUTO/SMART el ventilador obedece la lógica automática. La interfaz solo permite cancelar override si existe.";
    }

    if (notaBomba) {
        notaBomba.textContent = esManual
            ? "En MANUAL puedes controlar la bomba desde la interfaz."
            : "En AUTO/SMART la bomba obedece la lógica automática. La interfaz solo permite cancelar override si existe.";
    }
}

async function cargarEstado() {
    try {
        const r = await fetch("/api/estado");
        estadoActual = await r.json();

        estadoActual.porton = estadoPortonVisible(estadoActual.porton);

        const dot = document.getElementById("mqtt-dot");
        const texto = document.getElementById("mqtt-text");

        if (estadoActual.mqtt_conectado) {
            dot.className = "dot on";
            texto.textContent = "MQTT conectado";
        } else {
            dot.className = "dot off";
            texto.textContent = "MQTT desconectado";
        }

        for (const [clave, valor] of Object.entries(estadoActual)) {
            actualizarTexto(clave, valor);
        }

        let jsonDecision = estadoActual.decision_estado || estadoActual["casa/vision/decision/estado"];
        if (jsonDecision) {
            try {
                let obj = typeof jsonDecision === "string" ? JSON.parse(jsonDecision) : jsonDecision;
                actualizarTexto("decision_vision", obj.decision || "--");
                actualizarTexto("zona_vision", obj.zona || "--");
            } catch(e) { console.error("Error parseando decisión JSON", e); }
        } else {
            if (estadoActual.decision) actualizarTexto("decision_vision", estadoActual.decision);
            if (estadoActual.zona) actualizarTexto("zona_vision", estadoActual.zona);
        }

        let nuevoEvento = estadoActual.evento_vision || estadoActual.evento || estadoActual["casa/vision/evento"];
        if (nuevoEvento && nuevoEvento !== ultimoEvento) {
            agregarNotificacion(nuevoEvento);
            ultimoEvento = nuevoEvento;
        }

        const foco = valorNumero(estadoActual.foco, 0);
        const vent = valorNumero(estadoActual.vent, 0);

        const focoSlider = document.getElementById("foco_slider");
        const ventSlider = document.getElementById("vent_slider");

        if (focoSlider) {
            focoSlider.value = foco;
            actualizarTexto("foco_slider_val", foco);
        }

        if (ventSlider) {
            ventSlider.value = vent;
            actualizarTexto("vent_slider_val", vent);
        }

        const configIds = [
            "temp_min",
            "temp_max",
            "hum_amb_min",
            "hum_amb_max",
            "hum_suelo_min",
            "hum_suelo_max",
            "bomba_umbral"
        ];

        for (const id of configIds) {
            const el = document.getElementById(id);
            if (el && document.activeElement !== el) {
                el.value = estadoActual[id] ?? "";
            }
        }

        aplicarModoInterfaz();

    } catch (e) {
        console.error("Error cargando estado:", e);
    }
}

async function guardarConfig() {
    const datos = {
        temp_min: document.getElementById("temp_min").value,
        temp_max: document.getElementById("temp_max").value,
        hum_amb_min: document.getElementById("hum_amb_min").value,
        hum_amb_max: document.getElementById("hum_amb_max").value,
        hum_suelo_min: document.getElementById("hum_suelo_min").value,
        hum_suelo_max: document.getElementById("hum_suelo_max").value,
        bomba_umbral: document.getElementById("bomba_umbral").value
    };

    try {
        const r = await fetch("/api/config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(datos)
        });

        const data = await r.json();

        if (data.ok) {
            alert("Configuración enviada por MQTT");
        } else {
            alert("Error guardando configuración");
        }
    } catch (e) {
        alert("Error comunicando con Flask");
        console.error(e);
    }
}

function cancelarOverride(actuador) {
    const mapa = {
        vent: "casa/interior/vent/cmd",
        bomba: "casa/interior/bomba/cmd"
    };

    if (!mapa[actuador]) return;

    publicar(mapa[actuador], "RESET");
}

function olvidarWifiESP32() {
    const confirmar = confirm(
        "Esto borrará el WiFi y broker MQTT guardados en la ESP32. " +
        "La ESP32 se reiniciará y volverá a SmartHome-Config. ¿Continuar?"
    );

    if (!confirmar) return;

    publicar("casa/sistema/wifi/olvidar/cmd", "RESET");
}

cargarEstado();
setInterval(cargarEstado, 1000);