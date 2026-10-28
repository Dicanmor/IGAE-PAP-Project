/**
 * Suscripciones y avisos por correo del dashboard IGAE.
 *
 * Es el "backend" gratuito: una hoja de Google Sheets guarda los correos y este script
 *   - recibe las altas desde la página (doGet ?accion=suscribir&email=...),
 *   - confirma el correo (doble opt-in: nadie puede inscribir a otra persona),
 *   - da de baja (enlace en cada correo),
 *   - y manda el aviso con el reporte Word adjunto cuando GitHub Actions se lo pide (doPost).
 *
 * Instalación: ver apps_script/README.md
 */

var HOJA = 'Suscriptores';
var COLS = ['email', 'token', 'confirmado', 'alta', 'confirmacion', 'baja', 'ultimo_correo_confirmacion'];

/* ------------------------------ utilidades ------------------------------ */

function hoja_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA);
  if (!sh) {
    sh = ss.insertSheet(HOJA);
    sh.appendRow(COLS);
    sh.setFrozenRows(1);
  }
  return sh;
}

function filas_() {
  var sh = hoja_();
  var n = sh.getLastRow();
  if (n < 2) return [];
  var vals = sh.getRange(2, 1, n - 1, COLS.length).getValues();
  return vals.map(function (v, i) {
    var o = { fila: i + 2 };
    COLS.forEach(function (c, j) { o[c] = v[j]; });
    return o;
  });
}

function escribir_(fila, campo, valor) {
  hoja_().getRange(fila, COLS.indexOf(campo) + 1).setValue(valor);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function pagina_(titulo, mensaje) {
  var html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<body style="font-family:system-ui,Arial,sans-serif;max-width:520px;margin:15vh auto;padding:0 20px;color:#1c2430">' +
    '<h2>' + esc_(titulo) + '</h2><p>' + esc_(mensaje) + '</p></body>';
  return HtmlService.createHtmlOutput(html).setTitle(titulo);
}

function esc_(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function token_() {
  return Utilities.getUuid().replace(/-/g, '');
}

function urlScript_() {
  return ScriptApp.getService().getUrl();
}

function sitio_() {
  return PropertiesService.getScriptProperties().getProperty('SITIO_URL') || '';
}

/* ---------------------------- GET: página web ---------------------------- */

function doGet(e) {
  var p = (e && e.parameter) || {};
  try {
    if (p.accion === 'suscribir') return json_(suscribir_(String(p.email || '')));
    if (p.accion === 'confirmar') return confirmar_(String(p.t || ''));
    if (p.accion === 'baja') return baja_(String(p.t || ''));
  } catch (err) {
    return json_({ ok: false, error: 'interno' });
  }
  return json_({ ok: true, servicio: 'IGAE avisos' });
}

function suscribir_(email) {
  email = email.trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    return { ok: false, error: 'correo_invalido' };
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ahora = new Date();
    var f = filas_().filter(function (r) { return r.email === email; })[0];
    if (f && f.confirmado === true && !f.baja) return { ok: true, estado: 'ya' };

    var tok;
    if (f) {
      tok = f.token;
      // no reenviar confirmaciones más de una vez cada 10 minutos
      var ult = f.ultimo_correo_confirmacion ? new Date(f.ultimo_correo_confirmacion) : null;
      if (ult && ahora - ult < 10 * 60 * 1000 && !f.baja) return { ok: true, estado: 'pendiente' };
      if (f.baja) { escribir_(f.fila, 'baja', ''); escribir_(f.fila, 'confirmado', false); }
    } else {
      tok = token_();
      hoja_().appendRow([email, tok, false, ahora, '', '', '']);
      f = filas_().filter(function (r) { return r.email === email; })[0];
    }
    if (MailApp.getRemainingDailyQuota() < 5) return { ok: false, error: 'cuota' };
    enviarConfirmacion_(email, tok);
    escribir_(f.fila, 'ultimo_correo_confirmacion', ahora);
    return { ok: true, estado: 'pendiente' };
  } finally {
    lock.releaseLock();
  }
}

function enviarConfirmacion_(email, tok) {
  var enlace = urlScript_() + '?accion=confirmar&t=' + tok;
  var html = '<div style="font-family:system-ui,Arial,sans-serif;max-width:520px;color:#1c2430">' +
    '<h2>Confirma tu suscripción</h2>' +
    '<p>Pediste recibir un aviso cada vez que INEGI publique datos nuevos del IGAE, con el reporte en Word adjunto.</p>' +
    '<p><a href="' + enlace + '" style="background:#1f3b63;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600">Confirmar mi correo</a></p>' +
    '<p style="color:#667085;font-size:13px">Si no fuiste tú, ignora este mensaje: no recibirás nada más.</p></div>';
  MailApp.sendEmail({
    to: email,
    subject: 'Confirma tu suscripción a los avisos del IGAE',
    htmlBody: html,
    body: 'Confirma tu suscripción a los avisos del IGAE entrando a: ' + enlace,
    name: 'Avisos IGAE'
  });
}

function confirmar_(tok) {
  var f = tok && filas_().filter(function (r) { return r.token === tok; })[0];
  if (!f) return pagina_('Enlace no válido', 'Este enlace no existe o ya expiró.');
  escribir_(f.fila, 'confirmado', true);
  escribir_(f.fila, 'confirmacion', new Date());
  escribir_(f.fila, 'baja', '');
  var sitio = sitio_();
  return pagina_('Listo, quedaste suscrito', 'Te avisaremos por correo, con el reporte adjunto, cuando se publiquen datos nuevos del IGAE.' +
    (sitio ? ' Puedes cerrar esta pestaña o volver al dashboard: ' + sitio : ''));
}

function baja_(tok) {
  var f = tok && filas_().filter(function (r) { return r.token === tok; })[0];
  if (!f) return pagina_('Enlace no válido', 'Este enlace no existe o ya expiró.');
  escribir_(f.fila, 'confirmado', false);
  escribir_(f.fila, 'baja', new Date());
  return pagina_('Te diste de baja', 'Ya no recibirás avisos del IGAE. Si fue un error, puedes volver a suscribirte desde la página.');
}

/* ------------------------ POST: aviso desde GitHub ----------------------- */

function doPost(e) {
  var d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: 'json' }); }
  var esperado = PropertiesService.getScriptProperties().getProperty('NOTIFY_TOKEN');
  if (!esperado || d.token !== esperado) return json_({ ok: false, error: 'no_autorizado' });
  if (d.accion === 'notificar' || d.accion === 'prueba') return json_(notificar_(d));
  return json_({ ok: false, error: 'accion' });
}

function notificar_(d) {
  var props = PropertiesService.getScriptProperties();
  var prueba = d.accion === 'prueba';
  if (d.sitio_url) props.setProperty('SITIO_URL', d.sitio_url);

  if (!prueba && !d.forzar && props.getProperty('ULTIMO_PERIODO') === d.periodo) {
    return { ok: true, enviados: 0, omitido: 'ya_se_notifico_' + d.periodo };
  }

  var destinos;
  if (prueba) {
    destinos = [{ email: Session.getEffectiveUser().getEmail(), token: '' }];
  } else {
    destinos = filas_().filter(function (r) { return r.confirmado === true && !r.baja; });
  }

  var adjuntos = [];
  if (d.docx_b64) {
    adjuntos.push(Utilities.newBlob(Utilities.base64Decode(d.docx_b64),
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', d.archivo || 'Reporte_IGAE.docx'));
  }

  var cuota = MailApp.getRemainingDailyQuota();
  var enviados = 0, fallidos = 0, sinCuota = 0;
  destinos.forEach(function (r) {
    if (cuota - enviados <= 0) { sinCuota++; return; }
    try {
      var baja = r.token ? urlScript_() + '?accion=baja&t=' + r.token : '';
      MailApp.sendEmail({
        to: r.email,
        subject: (prueba ? '[PRUEBA] ' : '') + 'IGAE: datos de ' + d.label + ' ya disponibles',
        htmlBody: cuerpoHtml_(d, baja),
        body: cuerpoTexto_(d, baja),
        attachments: adjuntos,
        name: 'Avisos IGAE'
      });
      enviados++;
    } catch (err) {
      fallidos++;
    }
  });

  if (!prueba && sinCuota === 0 && fallidos === 0) props.setProperty('ULTIMO_PERIODO', d.periodo);
  return { ok: true, enviados: enviados, fallidos: fallidos, sin_cuota: sinCuota, destinatarios: destinos.length };
}

function fmt_(v) { return v == null ? '–' : String(v).replace('.', '.'); }
function pct_(v) { return v == null ? '–' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }

function cuerpoHtml_(d, bajaUrl) {
  var r = d.resumen || {};
  var filas = (r.actividades || []).map(function (a) {
    return '<tr><td style="padding:6px 10px;border-bottom:1px solid #e3e8ef">' + esc_(a.nombre) + '</td>' +
      '<td style="padding:6px 10px;border-bottom:1px solid #e3e8ef;text-align:right">' + pct_(a.var_anual) + '</td>' +
      '<td style="padding:6px 10px;border-bottom:1px solid #e3e8ef;text-align:right">' + (a.contrib == null ? '–' : a.contrib.toFixed(2)) + '</td></tr>';
  }).join('');
  return '<div style="font-family:system-ui,Arial,sans-serif;max-width:560px;color:#1c2430">' +
    '<h2 style="margin-bottom:4px">IGAE · ' + esc_(d.label) + '</h2>' +
    '<p style="margin-top:0;color:#667085">INEGI publicó datos nuevos. Adjuntamos el reporte en Word.</p>' +
    '<table style="border-collapse:collapse;width:100%;margin:12px 0"><tr>' +
    celda_('Índice (2018=100)', fmt_(r.nivel)) + celda_('Variación mensual', pct_(r.var_mensual)) +
    celda_('Variación anual', pct_(r.var_anual)) + celda_('Acumulada', pct_(r.var_acum)) + '</tr></table>' +
    (filas ? '<table style="border-collapse:collapse;width:100%;font-size:14px"><tr style="color:#667085;text-align:left">' +
      '<th style="padding:6px 10px">Actividad</th><th style="padding:6px 10px;text-align:right">Var. anual</th>' +
      '<th style="padding:6px 10px;text-align:right">Contrib. (pp)</th></tr>' + filas + '</table>' : '') +
    (d.sitio_url ? '<p><a href="' + esc_(d.sitio_url) + '" style="background:#1f3b63;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600">Abrir el dashboard</a></p>' : '') +
    (d.proxima_texto ? '<p style="color:#667085;font-size:13px">Próxima actualización esperada: ' + esc_(d.proxima_texto) + '.</p>' : '') +
    '<p style="color:#667085;font-size:12px">Fuente: INEGI. Cifras preliminares. ' +
    (bajaUrl ? '<a href="' + bajaUrl + '">Darme de baja</a>' : '') + '</p></div>';
}

function celda_(t, v) {
  return '<td style="padding:8px 10px;background:#f4f6fa;border-radius:8px;text-align:center"><div style="font-size:12px;color:#667085">' +
    esc_(t) + '</div><div style="font-size:20px;font-weight:700">' + esc_(v) + '</div></td>';
}

function cuerpoTexto_(d, bajaUrl) {
  var r = d.resumen || {};
  return 'IGAE ' + d.label + ': índice ' + fmt_(r.nivel) + ', variación mensual ' + pct_(r.var_mensual) +
    ', anual ' + pct_(r.var_anual) + ', acumulada ' + pct_(r.var_acum) + '.\n' +
    'El reporte en Word va adjunto.\n' + (d.sitio_url ? 'Dashboard: ' + d.sitio_url + '\n' : '') +
    (bajaUrl ? 'Darme de baja: ' + bajaUrl : '');
}
