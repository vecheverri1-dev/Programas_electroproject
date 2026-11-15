from datetime import datetime
from functools import wraps
import os
from pathlib import Path
import re
import secrets
import sqlite3

from flask import Flask, jsonify, redirect, render_template_string, request, send_file, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
DB_PATH = Path(__file__).with_name("casilleros.db")
BANNER_PATH = Path(__file__).with_name("utp_banner.png")
SECRET_PATH = Path(__file__).with_name("flask_secret.key")


def cargar_clave_secreta():
    configurada = os.environ.get("FLASK_SECRET_KEY")
    if configurada:
        return configurada
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    clave = secrets.token_hex(32)
    SECRET_PATH.write_text(clave, encoding="utf-8")
    return clave


app.secret_key = cargar_clave_secreta()
TOTAL_CASILLEROS = 19  # <- n de casilleros

LOGIN_PAGE = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ingreso de empleados</title>
  <style>
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:20px; background:#f4f7fb; color:#17212b; font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif; }
    main { width:min(100%,390px); background:white; border:1px solid #e4e9ef; border-radius:16px; padding:26px; box-shadow:0 8px 28px #102a4312; }
    h1 { margin:0 0 5px; font-size:24px; }
    p { margin:0 0 18px; color:#637080; }
    label { display:block; margin:13px 0 5px; font-weight:600; }
    input { width:100%; border:1px solid #cbd5df; border-radius:8px; padding:11px; font:inherit; }
    button { width:100%; margin-top:18px; border:0; border-radius:8px; padding:12px; background:#175cd3; color:white; font:600 15px system-ui; cursor:pointer; }
    .error { margin:12px 0 0; padding:10px; border-radius:8px; background:#fff0ef; color:#9a271f; }
  </style>
</head>
<body>
  <main>
    <h1>Ingreso de empleados</h1>
    <p>Inicia sesión para abrir el panel de casilleros.</p>
    <form method="post">
      <label for="usuario">Usuario</label>
      <input id="usuario" name="usuario" required autocomplete="username" autofocus>
      <label for="contrasena">Contraseña</label>
      <input id="contrasena" name="contrasena" type="password" required autocomplete="current-password">
      <button type="submit">Iniciar sesión</button>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </form>
  </main>
</body>
</html>
"""

PAGE = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Panel de casilleros</title>
  <style>
    :root { color-scheme: light; --ink:#17212b; --muted:#637080; --line:#e4e9ef; --blue:#175cd3; --bg:#f4f7fb; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif; }
    .university-banner { background:#194e72; }
    .university-banner img { display:block; width:100%; max-width:1400px; height:auto; max-height:96px; object-fit:cover; margin:auto; }
    .top-nav { background:white; border-bottom:1px solid var(--line); box-shadow:0 2px 8px #102a4308; }
    .nav-inner { max-width:1100px; min-height:60px; margin:auto; padding:0 18px; display:flex; align-items:center; gap:8px; }
    .nav-link { display:inline-flex; align-items:center; min-height:60px; padding:0 18px; color:#526477; text-decoration:none; font-weight:650; border-bottom:3px solid transparent; }
    .nav-link:hover { color:var(--blue); background:#f6f9fc; }
    .nav-link.active { color:var(--blue); border-bottom-color:var(--blue); }
    .nav-spacer { flex:1; }
    main { max-width:1100px; margin:24px auto; padding:0 18px 38px; }
    .notice { background:#fff7df; border:1px solid #f0d98c; border-radius:12px; padding:12px 15px; margin-bottom:18px; }
    .alert { background:#fff0ef; border:1px solid #ffc9c4; color:#9a271f; border-radius:12px; padding:12px 15px; margin-bottom:14px; font-weight:650; }
    .layout { display:grid; grid-template-columns:300px 1fr; gap:18px; align-items:start; }
    .panel { background:white; border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 2px 8px #102a4308; }
    h2 { margin:0 0 14px; font-size:18px; }
    label { display:block; margin:12px 0 5px; font-weight:600; }
    input,select { width:100%; border:1px solid #cbd5df; border-radius:8px; padding:10px; font:inherit; background:white; }
    button { border:0; border-radius:8px; padding:9px 12px; font:600 13px system-ui; cursor:pointer; }
    .primary { width:100%; margin-top:16px; background:var(--blue); color:white; padding:11px; }
    .open-btn { background:#fee4e2; color:#b42318; }
    .close-btn { background:#e7f6ec; color:#16703d; }
    .release-btn { background:#eef2f6; color:#344054; }
    .logout-btn { background:#eaf1fb; color:#175cd3; border:1px solid #d5e2f4; }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(235px,1fr)); gap:12px; }
    .locker { border:1px solid var(--line); border-radius:12px; padding:14px; }
    .locker-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
    .locker h3 { margin:0; font-size:17px; }
    .pill { border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; }
    .open { color:#a1261c; background:#ffebe9; }
    .closed { color:#17663c; background:#e9f7ee; }
    .unassigned { color:#536273; background:#eef2f6; }
    .student { margin:12px 0; color:var(--muted); min-height:42px; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; }
    .events { margin:0; padding-left:20px; color:var(--muted); }
    .events li { margin:7px 0; }
    .muted { color:var(--muted); font-size:13px; }
    .empty { color:var(--muted); padding:8px 0; }
    .page-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin-bottom:18px; }
    .page-heading h1 { margin:0; font-size:25px; }
    .page-heading p { margin:4px 0 0; color:var(--muted); }
    .stats { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-bottom:18px; }
    .stat { background:white; border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
    .stat-label { color:var(--muted); font-size:13px; }
    .stat-value { display:block; font-size:23px; font-weight:750; margin-top:2px; }
    .history-table { width:100%; border-collapse:collapse; }
    .history-table th,.history-table td { padding:12px 10px; border-bottom:1px solid var(--line); text-align:left; }
    .history-table th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .history-table tr:last-child td { border-bottom:0; }
    .table-wrap { overflow-x:auto; }
    .search-form { display:flex; gap:10px; align-items:end; margin-bottom:18px; }
    .search-form .search-field { flex:1; }
    .search-form label { margin-top:0; }
    .search-btn { background:var(--blue); color:white; min-height:42px; }
    .clear-btn { display:inline-flex; align-items:center; min-height:42px; padding:0 12px; border-radius:8px; color:#526477; background:#eef2f6; text-decoration:none; font-weight:600; }
    .history-day { margin-top:20px; }
    .history-day:first-of-type { margin-top:0; }
    .history-day h2 { padding-bottom:10px; border-bottom:2px solid #d9e3ee; color:#183b56; }
    .history-row { display:grid; grid-template-columns:minmax(140px,1fr) minmax(160px,1fr) auto; align-items:center; gap:14px; padding:13px 10px; border-bottom:1px solid var(--line); }
    .history-id { font-weight:700; font-variant-numeric:tabular-nums; }
    .history-detail { color:#526477; }
    .history-time { color:var(--muted); font-variant-numeric:tabular-nums; }
    .event-tag { display:inline-block; margin-left:7px; border-radius:999px; padding:3px 8px; font-size:11px; font-weight:700; background:#eef2f6; color:#475467; }
    .event-tag.abierto { background:#ffebe9; color:#a1261c; }
    .event-tag.cerrado { background:#e9f7ee; color:#17663c; }
    .history-state { display:inline-block; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; }
    .history-state.open { color:#a1261c; background:#ffebe9; }
    .history-state.closed { color:#17663c; background:#e9f7ee; }
    @media (max-width:760px) {
      .layout { grid-template-columns:1fr; }
      .stats { grid-template-columns:1fr 1fr; }
      .nav-inner { padding:0 10px; }
      .nav-link { padding:0 12px; }
      .search-form { align-items:stretch; flex-wrap:wrap; }
      .search-form .search-field { flex-basis:100%; }
      .history-row { grid-template-columns:1fr auto; gap:4px 10px; }
      .history-detail { grid-column:1; }
      .history-time { grid-column:2; grid-row:1 / span 2; }
    }
  </style>
</head>
<body>
<div class="university-banner">
  <img src="{{ url_for('utp_banner') }}" alt="Universidad Tecnológica de Pereira — Educación">
</div>
<nav class="top-nav">
  <div class="nav-inner">
    <a class="nav-link {{ 'active' if active_tab == 'casilleros' else '' }}" href="{{ url_for('panel') }}">Casilleros</a>
    <a class="nav-link {{ 'active' if active_tab == 'historial' else '' }}" href="{{ url_for('historial') }}">Historial</a>
    <span class="nav-spacer"></span>
    <form action="{{ url_for('logout') }}" method="post"><button class="logout-btn" type="submit">Cerrar sesión</button></form>
  </div>
</nav>
<main>
  {% if active_tab == 'casilleros' %}
  <div class="page-heading"><div><h1>Panel de casilleros</h1><p>Asigna estudiantes y consulta el estado de cada puerta.</p></div></div>
  <div class="notice"></strong>Bienvenido/a al sistema de asignación de casilleros de los Escenarios Deportivos de la Universidad Tecnológica de Pereira.</div>
  {% if mensaje %}<div class="alert">{{ mensaje }}</div>{% endif %}
  {% if apertura_reciente %}<div class="alert">Alerta: se abrió el casillero {{ apertura_reciente.numero }}{% if apertura_reciente.nombre %}, asignado a {{ apertura_reciente.nombre }}{% endif %}.</div>{% endif %}
  <div class="stats">
    <div class="stat"><span class="stat-label">Total de casilleros</span><span class="stat-value">{{ total_casilleros }}</span></div>
    <div class="stat"><span class="stat-label">En uso</span><span class="stat-value">{{ asignados }}</span></div>
    <div class="stat"><span class="stat-label">Abiertos</span><span class="stat-value">{{ abiertos }}</span></div>
  </div>
  <div class="layout">
    <section class="panel">
      <h2>Asignar casillero</h2>
      <form action="{{ url_for('asignar') }}" method="post">
        <label for="nombre">Nombre del estudiante</label>
        <input id="nombre" name="nombre" required maxlength="100" placeholder="Estudiante">
        <label for="cedula">Cédula o identificador</label>
        <input id="cedula" name="cedula" required maxlength="40" placeholder="ID">
        <label for="telefono">Teléfono</label>
        <input id="telefono" name="telefono" required maxlength="30" placeholder="+57 300 000 0000">
        <label for="numero">Casillero disponible</label>
        <select id="numero" name="numero" required>
          {% for numero in disponibles %}<option value="{{ numero }}">Casillero {{ numero }}</option>{% endfor %}
        </select>
        <button class="primary" type="submit">Registrar y asignar</button>
      </form>
      {% if not disponibles %}<p class="muted">No hay casilleros libres.</p>{% endif %}
    </section>
    <section class="panel">
      <h2>Estado de los casilleros</h2>
      <div class="cards">
        {% for c in casilleros %}
          <article class="locker">
            <div class="locker-top">
              <h3>Casillero {{ c.numero }}</h3>
              <span class="pill {{ 'open' if c.estado == 'abierto' else 'closed' }}">{{ c.estado|capitalize }}</span>
            </div>
            <div class="student">
              {% if c.nombre %}<strong>{{ c.nombre }}</strong><br>ID: {{ c.cedula }}<br>Tel.: {{ c.telefono }}
              {% else %}<span class="pill unassigned">Sin asignar</span>{% endif %}
            </div>
            <div class="actions">
              <form action="{{ url_for('simular', numero=c.numero, estado='abierto') }}" method="post"><button class="open-btn">Simular apertura</button></form>
              <form action="{{ url_for('simular', numero=c.numero, estado='cerrado') }}" method="post"><button class="close-btn">Simular cierre</button></form>
              {% if c.cedula %}<form action="{{ url_for('liberar', numero=c.numero) }}" method="post" onsubmit="return confirm('¿Liberar este casillero? El nombre y teléfono se borrarán, pero la cédula quedará en el historial.');"><button class="release-btn">Liberar casillero</button></form>{% endif %}
            </div>
            <p class="muted">Actualizado: {{ c.actualizado or 'sin evento' }}</p>
          </article>
        {% endfor %}
      </div>
    </section>
  </div>
  <section class="panel" style="margin-top:18px">
    <h2>Eventos recientes</h2>
    {% if eventos %}<ul class="events">{% for e in eventos %}<li>Casillero {{ e.numero }}: {{ e.estado }} — {{ e.momento }}</li>{% endfor %}</ul>
    {% else %}<p class="empty">Todavía no hay eventos.</p>{% endif %}
  </section>
  <p class="muted">Para ver cambios recientes enviados por el ESP32, recarga la página.</p>
  {% else %}
  <div class="page-heading"><div><h1>Historial de actividad</h1><p>Registro de las últimas aperturas y cierres recibidos.</p></div></div>
  <section class="panel">
    <form class="search-form" method="get" action="{{ url_for('historial') }}">
      <div class="search-field">
        <label for="cedula_busqueda">Buscar por cédula</label>
        <input id="cedula_busqueda" name="cedula" value="{{ cedula_busqueda }}" inputmode="numeric" placeholder="Escribe la cédula completa o una parte">
      </div>
      <button class="search-btn" type="submit">Buscar</button>
      {% if cedula_busqueda %}<a class="clear-btn" href="{{ url_for('historial') }}">Limpiar</a>{% endif %}
    </form>
    {% if grupos %}
      {% for grupo in grupos %}
      <section class="history-day">
        <h2>{{ grupo.fecha }}</h2>
        {% for e in grupo.eventos %}
        <div class="history-row">
          <span class="history-id">{{ e.cedula or 'Cédula no registrada' }}</span>
          <span class="history-detail">Casillero {{ e.numero }} <span class="event-tag {{ e.estado }}">{{ e.etiqueta }}</span></span>
          <time class="history-time">{{ e.hora }}</time>
        </div>
        {% endfor %}
      </section>
      {% endfor %}
    {% elif cedula_busqueda %}
      <p class="empty">No hay registros históricos para esa cédula.</p>
    {% else %}
      <p class="empty">Todavía no hay actividad registrada.</p>
    {% endif %}
  </section>
  {% endif %}
</main>
</body>
</html>
"""


def conectar_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar_db():
    with conectar_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
            cedula TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS casilleros (
            numero INTEGER PRIMARY KEY,
            cedula TEXT UNIQUE REFERENCES estudiantes(cedula),
            estado TEXT NOT NULL DEFAULT 'cerrado',
            actualizado TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER NOT NULL,
            estado TEXT NOT NULL,
            momento TEXT NOT NULL,
            cedula TEXT
        )""")
        columnas_eventos = {fila[1] for fila in db.execute("PRAGMA table_info(eventos)").fetchall()}
        if "cedula" not in columnas_eventos:
            db.execute("ALTER TABLE eventos ADD COLUMN cedula TEXT")
        db.execute("""CREATE TABLE IF NOT EXISTS empleados (
            usuario TEXT PRIMARY KEY,
            contrasena_hash TEXT NOT NULL
        )""")
        for numero in range(1, TOTAL_CASILLEROS + 1):
            db.execute("INSERT OR IGNORE INTO casilleros(numero) VALUES (?)", (numero,))

        hay_empleados = db.execute("SELECT 1 FROM empleados LIMIT 1").fetchone()
        if not hay_empleados:
            usuario = os.environ.get("CASILLEROS_USER", "empleado").strip()
            contrasena = os.environ.get("CASILLEROS_PASSWORD")
            if not contrasena:
                contrasena = input(
                    "Crea la contraseña para el usuario '" + usuario + "' (mínimo 8 caracteres): "
                )
            if len(contrasena) < 8:
                raise SystemExit("La contraseña debe tener al menos 8 caracteres. Vuelve a ejecutar el programa.")
            db.execute(
                "INSERT INTO empleados(usuario, contrasena_hash) VALUES (?, ?)",
                (usuario, generate_password_hash(contrasena))
            )
            print("Cuenta de empleado creada. Usuario:", usuario)


def ahora():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def guardar_estado(numero, estado):
    momento = ahora()
    with conectar_db() as db:
        casillero = db.execute("SELECT cedula FROM casilleros WHERE numero = ?", (numero,)).fetchone()
        if not casillero:
            return False
        db.execute("UPDATE casilleros SET estado = ?, actualizado = ? WHERE numero = ?",
                   (estado, momento, numero))
        db.execute("INSERT INTO eventos(numero, estado, momento, cedula) VALUES (?, ?, ?, ?)",
                   (numero, estado, momento, casillero["cedula"]))
    print(f"Casillero {numero}: {estado}", flush=True)
    return True


@app.get("/utp-banner")
def utp_banner():
    return send_file(BANNER_PATH, mimetype="image/png")


def requiere_empleado(vista):
    @wraps(vista)
    def protegida(*args, **kwargs):
        if "empleado" not in session:
            return redirect(url_for("login", next=request.path))
        return vista(*args, **kwargs)
    return protegida


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contrasena = request.form.get("contrasena", "")
        with conectar_db() as db:
            empleado = db.execute(
                "SELECT usuario, contrasena_hash FROM empleados WHERE usuario = ?",
                (usuario,)
            ).fetchone()
        if empleado and check_password_hash(empleado["contrasena_hash"], contrasena):
            session.clear()
            session["empleado"] = empleado["usuario"]
            destino = request.args.get("next", "")
            if destino.startswith("/") and not destino.startswith("//"):
                return redirect(destino)
            return redirect(url_for("panel"))
        error = "Usuario o contraseña incorrectos."
    return render_template_string(LOGIN_PAGE, error=error)


def normalizar_telefono(telefono):
    return re.sub(r"\D", "", telefono or "")


STUDENT_TOKEN_TTL = 30 * 24 * 60 * 60
student_token_serializer = URLSafeTimedSerializer(app.secret_key, salt="casilleros-student-app")


@app.post("/api/app/login")
def api_app_login():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"error": "Se esperaba un objeto JSON"}), 400
    cedula = str(datos.get("cedula", "")).strip()
    telefono = normalizar_telefono(str(datos.get("telefono", "")))
    if not cedula or not telefono:
        return jsonify({"error": "Debes enviar cedula y telefono"}), 400

    with conectar_db() as db:
        estudiante_db = db.execute(
            "SELECT cedula, telefono FROM estudiantes WHERE cedula = ?", (cedula,)
        ).fetchone()
    if not estudiante_db or normalizar_telefono(estudiante_db["telefono"]) != telefono:
        return jsonify({"error": "Credenciales incorrectas o estudiante sin asignacion activa"}), 401

    token = student_token_serializer.dumps({"cedula": cedula})
    return jsonify({"ok": True, "token": token, "token_type": "Bearer",
                    "expires_in": STUDENT_TOKEN_TTL}), 200


def cedula_desde_token():
    cabecera = request.headers.get("Authorization", "")
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        return None
    try:
        datos = student_token_serializer.loads(token.strip(), max_age=STUDENT_TOKEN_TTL)
    except BadSignature:
        return None
    return datos.get("cedula") if isinstance(datos, dict) else None


@app.get("/api/app/mi-casillero")
def api_app_mi_casillero():
    cedula = cedula_desde_token()
    if not cedula:
        return jsonify({"error": "Token ausente, invalido o vencido"}), 401
    with conectar_db() as db:
        datos = db.execute("""SELECT e.cedula, e.nombre, c.numero, c.estado, c.actualizado,
            (SELECT MAX(v.id) FROM eventos v WHERE v.numero = c.numero AND v.estado = 'abierto') AS open_event_id
            FROM estudiantes e JOIN casilleros c ON c.cedula = e.cedula
            WHERE e.cedula = ?""", (cedula,)).fetchone()
    if not datos:
        return jsonify({"error": "No tienes un casillero asignado actualmente"}), 404
    return jsonify({
        "cedula": datos["cedula"],
        "nombre": datos["nombre"],
        "casillero": datos["numero"],
        "estado": datos["estado"],
        "actualizado": datos["actualizado"],
        "open_event_id": datos["open_event_id"],
    })


@app.post("/logout")
@requiere_empleado
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@requiere_empleado
def panel():
    with conectar_db() as db:
        casilleros = db.execute("""SELECT c.numero, c.estado, c.actualizado,
            e.nombre, e.cedula, e.telefono
            FROM casilleros c LEFT JOIN estudiantes e ON e.cedula = c.cedula
            ORDER BY c.numero""").fetchall()
        eventos = db.execute("SELECT numero, estado, momento FROM eventos ORDER BY id DESC LIMIT 12").fetchall()
        disponibles = [r[0] for r in db.execute("SELECT numero FROM casilleros WHERE cedula IS NULL ORDER BY numero").fetchall()]
        apertura_reciente = db.execute("""SELECT c.numero, e.nombre
            FROM eventos v JOIN casilleros c ON c.numero = v.numero
            LEFT JOIN estudiantes e ON e.cedula = c.cedula
            WHERE v.estado = 'abierto'
              AND v.id = (SELECT MAX(v2.id) FROM eventos v2
                          WHERE v2.numero = v.numero AND v2.estado IN ('abierto', 'cerrado'))
            ORDER BY v.id DESC LIMIT 1""").fetchone()
        resumen = db.execute("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN cedula IS NOT NULL THEN 1 ELSE 0 END) AS asignados,
            SUM(CASE WHEN estado = 'abierto' THEN 1 ELSE 0 END) AS abiertos
            FROM casilleros""").fetchone()
    return render_template_string(PAGE, casilleros=casilleros, eventos=eventos,
                                  disponibles=disponibles, apertura_reciente=apertura_reciente,
                                  mensaje=request.args.get("mensaje"), active_tab="casilleros",
                                  total_casilleros=resumen["total"] or 0,
                                  asignados=resumen["asignados"] or 0,
                                  abiertos=resumen["abiertos"] or 0)


@app.get("/historial")
@requiere_empleado
def historial():
    cedula_busqueda = request.args.get("cedula", "").strip()
    with conectar_db() as db:
        eventos = db.execute(
            "SELECT numero, estado, momento, cedula FROM eventos "
            "WHERE (? = '' OR cedula LIKE ?) ORDER BY id DESC LIMIT 500",
            (cedula_busqueda, f"%{cedula_busqueda}%")
        ).fetchall()

    grupos = []
    por_fecha = {}
    etiquetas = {
        "abierto": "Abierto",
        "cerrado": "Cerrado",
        "asignado": "Asignado",
        "liberado": "Liberado",
    }
    for evento in eventos:
        partes = evento["momento"].split()
        fecha_iso = partes[0] if partes else "Fecha desconocida"
        hora = partes[1] if len(partes) > 1 else ""
        try:
            fecha = datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            fecha = fecha_iso
        if fecha not in por_fecha:
            por_fecha[fecha] = {"fecha": fecha, "eventos": []}
            grupos.append(por_fecha[fecha])
        por_fecha[fecha]["eventos"].append({
            "numero": evento["numero"],
            "estado": evento["estado"],
            "etiqueta": etiquetas.get(evento["estado"], evento["estado"].capitalize()),
            "hora": hora,
            "cedula": evento["cedula"],
        })

    return render_template_string(PAGE, grupos=grupos, cedula_busqueda=cedula_busqueda,
                                  active_tab="historial")


@app.post("/asignar")
@requiere_empleado
def asignar():
    nombre = request.form.get("nombre", "").strip()
    cedula = request.form.get("cedula", "").strip()
    telefono = request.form.get("telefono", "").strip()
    try:
        numero = int(request.form.get("numero", ""))
    except ValueError:
        return redirect(url_for("panel", mensaje="Selecciona un casillero válido."))

    if not nombre or not cedula or not telefono:
        return redirect(url_for("panel", mensaje="Completa los datos del estudiante."))

    with conectar_db() as db:
        destino = db.execute("SELECT cedula FROM casilleros WHERE numero = ?", (numero,)).fetchone()
        if not destino:
            return redirect(url_for("panel", mensaje="Ese casillero no existe."))
        if destino["cedula"] and destino["cedula"] != cedula:
            return redirect(url_for("panel", mensaje="Ese casillero ya está asignado."))
        db.execute("INSERT INTO estudiantes(cedula, nombre, telefono) VALUES (?, ?, ?) "
                   "ON CONFLICT(cedula) DO UPDATE SET nombre=excluded.nombre, telefono=excluded.telefono",
                   (cedula, nombre, telefono))
        anterior = db.execute(
            "SELECT numero FROM casilleros WHERE cedula = ? AND numero != ?", (cedula, numero)
        ).fetchone()
        if anterior:
            momento = ahora()
            db.execute("UPDATE casilleros SET cedula = NULL WHERE numero = ?", (anterior["numero"],))
            db.execute("INSERT INTO eventos(numero, estado, momento, cedula) VALUES (?, 'liberado', ?, ?)",
                       (anterior["numero"], momento, cedula))
        db.execute("UPDATE casilleros SET cedula = ? WHERE numero = ?", (cedula, numero))
        db.execute("INSERT INTO eventos(numero, estado, momento, cedula) VALUES (?, 'asignado', ?, ?)",
                   (numero, ahora(), cedula))
    return redirect(url_for("panel", mensaje=f"Casillero {numero} asignado a {nombre}."))


@app.post("/simular/<int:numero>/<estado>")
@requiere_empleado
def simular(numero, estado):
    if estado not in {"abierto", "cerrado"} or not guardar_estado(numero, estado):
        return redirect(url_for("panel", mensaje="No se pudo actualizar ese casillero."))
    return redirect(url_for("panel"))


@app.post("/liberar/<int:numero>")
@requiere_empleado
def liberar(numero):
    with conectar_db() as db:
        casillero = db.execute(
            "SELECT cedula FROM casilleros WHERE numero = ?", (numero,)
        ).fetchone()
        if not casillero:
            return redirect(url_for("panel", mensaje="Ese casillero no existe."))
        cedula = casillero["cedula"]
        if not cedula:
            return redirect(url_for("panel", mensaje="Ese casillero ya está libre."))
        momento = ahora()
        db.execute("UPDATE casilleros SET cedula = NULL WHERE numero = ?", (numero,))
        db.execute("INSERT INTO eventos(numero, estado, momento, cedula) VALUES (?, 'liberado', ?, ?)",
                   (numero, momento, cedula))
        db.execute("DELETE FROM estudiantes WHERE cedula = ?", (cedula,))
    return redirect(url_for(
        "panel",
        mensaje=f"Casillero {numero} liberado. La cédula permanece en el historial de actividad."
    ))


@app.post("/api/casilleros/estado")
def recibir_estado():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"error": "Se esperaba un objeto JSON"}), 400
    try:
        numero = int(datos.get("casillero"))
    except (TypeError, ValueError):
        return jsonify({"error": "'casillero' debe ser un número"}), 400
    estado = str(datos.get("estado", "")).strip().lower()
    if estado not in {"abierto", "cerrado"}:
        return jsonify({"error": "'estado' debe ser 'abierto' o 'cerrado'"}), 400
    if not guardar_estado(numero, estado):
        return jsonify({"error": "Casillero no encontrado"}), 404
    return jsonify({"ok": True, "casillero": numero, "estado": estado})


@app.get("/api/casilleros")
@requiere_empleado
def consultar_estados():
    with conectar_db() as db:
        filas = db.execute("SELECT numero, estado, actualizado FROM casilleros ORDER BY numero").fetchall()
    return jsonify({"casilleros": [dict(fila) for fila in filas]})


inicializar_db()

if __name__ == "__main__":
    print("Abre http://127.0.0.1:5000 para iniciar sesión en el panel.")
    print("El ESP32 debe apuntar a la IP local del ordenador, en /api/casilleros/estado.")
    app.run(host="0.0.0.0", port=5000, debug=False)
