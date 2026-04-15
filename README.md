# CONTSIS

Cloud-first base for the CONTSIS CFDI workflow.

## Project Structure

- `app.py`: Streamlit entry point for the dashboard.
- `main.py`: CLI entry point for the processing pipeline and alerts.
- `requirements.txt`: application dependencies.
- `data/`: local runtime folders and config examples.
- `src/`: analytics, dashboard, robots, and shared application logic.
- `alertas/`: alerting and email flows.

## Local Run

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Open the dashboard:

```powershell
streamlit run app.py
```

Run the pipeline:

```powershell
python main.py --rfc IIS891106AE6 --year 2025 --month 7
```

Run alerts only:

```powershell
python main.py --alertas --piloto
```

## Notes

- Runtime-generated data under `data/boveda`, `data/exports`, `data/db`, and `logs` is intentionally ignored in Git.
- Client desktop packaging files were removed from this repo to prepare for GitHub and AWS deployment.

## Docker Run

Build the image:

```powershell
docker build -t contsis-app .
```

Run the dashboard:

```powershell
docker run --rm -p 8501:8501 contsis-app
```

Or run it with Docker Compose:

```powershell
docker compose up -d --build
```

The container stores writable runtime data in `/app/runtime` and seeds example config files there on startup:

- `/app/runtime/data/config/clientes.json`
- `/app/runtime/data/config/rfc_names.json`
- `/app/runtime/alertas/config/config.yaml`

For real cloud deployment, mount `/app/runtime` as persistent storage and inject your real `.env` values through AWS secrets or environment variables.

Detailed EC2 steps are in `AWS_EC2_DEPLOY.md`.
