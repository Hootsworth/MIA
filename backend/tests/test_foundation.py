# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Dataset, DatasetDocument, Document


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mia-lab-api"}


def test_database_creation(db):
    assert {"documents", "datasets", "results", "turnitin_reports"}.issubset(set(__import__("sqlalchemy").inspect(db).get_table_names()))


def test_foreign_keys_enforced(db):
    with Session(db) as session:
        session.add(DatasetDocument(dataset_id="missing", document_id="missing"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_unique_constraints(db):
    with Session(db) as session:
        doc = Document(filename="one.txt", sha256="a" * 64)
        dataset = Dataset(name="sample")
        session.add_all([doc, dataset])
        session.commit()
        session.add(Document(filename="duplicate.txt", sha256="a" * 64))
        with pytest.raises(IntegrityError):
            session.commit()


