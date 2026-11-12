# Huellas de esperanza

Aplicación Django para la gestión del refugio, adopciones, hogares temporales y
donaciones.

## Levantar con Docker

Requisitos: Docker Desktop (o Docker Engine) con Docker Compose v2.

1. Crear el archivo de variables local y editarlo:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Configurar `DATABASE_URL` con una base PostgreSQL accesible que ya tenga el
   esquema del proyecto. Generar una clave propia para Django y reemplazar
   `DJANGO_SECRET_KEY`:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

   No usar los valores de ejemplo en producción. 

3. Construir e iniciar la aplicación:

   ```powershell
   docker compose up --build
   ```

   Django aplica las migraciones pendientes y luego inicia Gunicorn. La
   aplicación queda disponible en
   [http://localhost:8000](http://localhost:8000). Para cambiar el puerto del
   host, ajustar `APP_PORT` en `.env`.

El contenedor web utiliza la base PostgreSQL externa indicada en `.env`; no
crea ni borra esa base. El esquema debe estar inicializado, ya que algunas
migraciones del proyecto modifican tablas existentes.

Para detener el contenedor:

```powershell
docker compose down
```

## Variables de entorno

| Variable | Uso | Valor local de ejemplo |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Clave secreta de Django; generar una propia. | — |
| `DJANGO_DEBUG` | Activa el modo de depuración. Mantener `false` en producción. | `true` |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos por Django, separados por comas. | `localhost,127.0.0.1` |
| `APP_PORT` | Puerto publicado en el equipo anfitrión. | `8000` |
| `DATABASE_URL` | URL completa de la base PostgreSQL existente. | — |
| `DATABASE_SSLMODE` | Modo SSL para conectarse a PostgreSQL. | `require` |
| `SUPABASE_URL` | URL del proyecto Supabase; opcional. | vacío |
| `SUPABASE_KEY` | Clave pública de Supabase; opcional. | vacío |
| `SUPABASE_SECRET_KEY` | Clave de servidor para Supabase Storage; opcional y sensible. | vacío |

Supabase Storage necesita las tres variables `SUPABASE_*`; si se dejan vacías,
la aplicación puede iniciar, pero las funciones que dependen de Storage no
estarán configuradas. Mantener `.env` fuera del control de versiones y no
compartir claves secretas.

## Comandos útiles

Ver el estado de los servicios:

```powershell
docker compose ps
```

Seguir los registros:

```powershell
docker compose logs -f web
```

Crear un usuario administrador:

```powershell
docker compose exec web python manage.py createsuperuser
```
