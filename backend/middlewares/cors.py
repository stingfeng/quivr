from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://23.251.122.106:3000",
]


def add_cors_middleware(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
