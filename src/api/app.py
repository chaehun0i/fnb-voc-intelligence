from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ServIQ API")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
