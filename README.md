# Discord Bot + Dashboard Flask

Bot modular para `discord.py 2.x` con Cogs, SQLite y dashboard responsive.

## Estructura

```text
discord_app/
├── bot.py                    # arranque, intents, carga dinámica de Cogs
├── config.py                 # variables de entorno y rutas
├── database.py               # SQLite y repositorios persistentes
├── cogs/
│   ├── giveaways.py          # /giveaway create, botón, claim timer
│   ├── moderation.py         # kick, ban, mute, warn, modstats
│   ├── logs.py               # entradas, salidas, voz, ediciones y archivos borrados
│   └── automod.py            # scam, spam, adjuntos, palabras y NSFW básico
└── web/
    ├── app.py                # rutas Flask y puente con el loop de Discord
    ├── templates/            # login y dashboard
    └── static/css/style.css  # interfaz responsive
```

## Arranque

1. Instala dependencias: `python -m pip install -r requirements.txt`.
2. Configura `DISCORD_TOKEN` como secreto del entorno.
3. Invita el bot con `bot`, `applications.commands`, `Manage Messages`, `Manage Channels`,
   `Kick Members`, `Ban Members`, `Moderate Members` y `View Audit Log` según los módulos.
4. Habilita en el Developer Portal los intents **Server Members**, **Message Content** y
   **Voice States**.
5. Ejecuta: `python -m discord_app.bot` o `./start.sh`.

El dashboard se sirve en `PORT` (5000 por defecto). Para protegerlo, configura
`DASHBOARD_TOKEN`; sin ese valor solo debe usarse en desarrollo local.

## Hosting 24/7

El ZIP incluye `Procfile` y `start.sh`. En un hosting compatible con Procfile,
usa:

```text
web: python -m discord_app.bot
```

Configura como variables o secretos del hosting:

- `DISCORD_TOKEN`: token privado del bot.
- `DASHBOARD_TOKEN`: contraseña del dashboard.
- `SESSION_SECRET`: secreto largo para las sesiones Flask.
- `PORT`: lo proporciona normalmente el hosting.
- `DATABASE_PATH`: opcional; usa `data/bot.sqlite3` por defecto.

El dashboard usa Waitress en lugar del servidor de desarrollo de Flask. La base SQLite
se crea automáticamente al iniciar. En un hosting efímero, monta un volumen persistente
para `data/` o cambia `DATABASE_PATH` a una ubicación persistente.

## Formato de fecha

`/giveaway create` acepta ISO 8601, por ejemplo:
`2026-09-15T22:30:00-06:00`.

El detector NSFW es una primera capa basada en texto y nombres de archivo. Para moderación
visual real debe conectarse un clasificador externo y aplicar su política de privacidad.

Los logs registran las ediciones de texto mostrando el contenido anterior y el nuevo.
Cuando se elimina un mensaje con imágenes o videos, el Embed muestra el tipo, nombre,
tamaño y enlace de cada archivo; las imágenes incluyen una vista previa cuando su URL
continúa disponible.