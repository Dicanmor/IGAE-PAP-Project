# Avisos por correo (Google Apps Script) — instalación, ~10 minutos

Sirve para que la página pueda registrar correos y mandar el aviso con el reporte adjunto.
Es gratis y no necesita servidor. Los correos quedan en **tu** hoja de Google (nadie más los ve).

1. Crea una hoja nueva en Google Sheets (nombre: `IGAE suscriptores`).
2. En la hoja: **Extensiones → Apps Script**. Borra lo que haya y pega todo `Code.gs`. Guarda.
3. En Apps Script: **Configuración del proyecto (engrane) → Propiedades del script → Añadir propiedad**:
   - `NOTIFY_TOKEN` = una contraseña larga inventada por ti (ej. 30 caracteres al azar). Cópiala, la usarás en GitHub.
4. **Implementar → Nueva implementación → tipo "Aplicación web"**:
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier persona**
   - Implementar y autorizar los permisos (Sheets y envío de correo). Copia la **URL de la aplicación web** (termina en `/exec`).
5. En el repositorio de GitHub:
   - Edita `config.json` y pega la URL en `suscripcion_url`.
   - **Settings → Secrets and variables → Actions → New repository secret**: nombre `NOTIFY_TOKEN`, valor = la misma contraseña del paso 3.
6. Sube los cambios y corre el workflow. Para probar el correo sin molestar a nadie, en **Actions → IGAE mensual → Run workflow** activa **"Enviar correo de prueba"**: te llega solo a ti.

Notas
- Cada correo nuevo recibe un mensaje para **confirmar** (doble confirmación); solo los confirmados reciben avisos.
- Cada aviso lleva un enlace para darse de baja.
- Gmail permite ~100 correos al día con una cuenta normal (1,500 con Workspace). Para un proyecto de clase sobra.
- Si cambias `Code.gs`, hay que hacer **Implementar → Administrar implementaciones → editar → Nueva versión**; la URL no cambia.
