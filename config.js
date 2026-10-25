// Configuración del dashboard.
//
// El publicador local sube "datos_web.json" a la rama `data` del repositorio.
// El dashboard lo lee desde raw.githubusercontent.com con cache-busting.
window.DATOS_URL = "https://raw.githubusercontent.com/rquiroga7/brasil2026/data/datos_web.json";
// 2ª vuelta (rama data2t, la publica publicar_2t.py)
window.DATOS_URL_2T = "https://raw.githubusercontent.com/rquiroga7/brasil2026/data2t/datos_web_2t.json";
