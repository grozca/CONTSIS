# AWS EC2 Deployment

This setup is prepared for a first deployment on EC2 using Docker Compose and a host-side `runtime/` folder.

## 0. AWS setup

Create an Ubuntu EC2 instance and make sure the security group allows:

- TCP `22` from your IP for SSH
- TCP `8501` from the IP range that should access the app

## 1. Prepare the server

```bash
bash deploy/ec2/bootstrap_ubuntu.sh
```

Reconnect to the server after the bootstrap if your user was just added to the `docker` group.

## 2. Clone the repository

```bash
git clone <YOUR_REPO_URL> CONTAISISR
cd CONTAISISR
```

## 3. Create the environment file

The deploy script can create `.env` for you the first time, but editing it manually is still recommended:

```bash
cp .env.example .env
nano .env
```

Recommended values for the first cloud run:

```env
CONTSIS_HOME=/app/runtime
CONTSIS_SERVER_HOST=0.0.0.0
CONTSIS_SERVER_PORT=8501
CONTSIS_OPEN_BROWSER=0
```

Add the real values only if you need them:

- `EMAIL_REMITENTE`
- `EMAIL_PASSWORD`
- `EMAIL_DESTINATARIOS`
- `SAT_CER_PATH`
- `SAT_KEY_PATH`
- `SAT_PWD_PATH`
- `BOVEDA_DIR`
- `DB_PATH`
- `LOG_PATH`

If you want the app to read XMLs from the server filesystem, point `BOVEDA_DIR` to a path inside the instance, for example:

```env
BOVEDA_DIR=/home/ubuntu/contsis-data/boveda
```

## 4. Build and start the app

```bash
bash deploy/ec2/deploy.sh
```

## 5. Open the app

Use:

```text
http://<EC2_PUBLIC_IP>:8501
```

Your EC2 security group must allow inbound TCP traffic on port `8501`.

## 6. Runtime data on the server

The app writes runtime data to the host folder:

```text
./runtime
```

That includes:

- generated local config
- local SQLite files
- logs
- runtime alert history

Important paths you will likely edit:

- `runtime/data/config/clientes.json`
- `runtime/data/config/rfc_names.json`
- `runtime/alertas/config/config.yaml`

## 7. Useful commands

See running containers:

```bash
docker compose ps
```

See logs:

```bash
docker compose logs -f
```

Restart after changes:

```bash
docker compose up -d --build
```

Stop the app:

```bash
docker compose down
```

Restart after editing `.env` or config:

```bash
docker compose up -d --build
```

Open a shell inside the container:

```bash
docker compose exec contsis bash
```

## 8. Recommended next step

For production, the next hardening step is:

1. Put Nginx in front of Streamlit.
2. Add HTTPS with a real domain.
3. Move secrets out of `.env` into AWS Secrets Manager or SSM Parameter Store.
4. If XMLs will live outside the container, mount a host path or EFS into the runtime path used by `BOVEDA_DIR`.
