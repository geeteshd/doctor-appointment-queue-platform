import os
os.environ["DATABASE_URL"] = "sqlite:///./test_clinic.db"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.core.database import Base, engine
    # Reset schema for isolation; dispose stale connections first.
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.main import app
    with TestClient(app) as c:
        yield c
