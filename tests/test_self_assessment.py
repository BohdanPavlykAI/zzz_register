"""
Тести для самооцінки PRO2:
- Лікар заповнює від імені пацієнта
- Пацієнт заповнює за токеном
- Генерація токену
- Повна історія / остання самооцінка
- Розрахунок pro2_score (ХК і ВК)
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SelfAssessmentToken, UserRole
from tests.conftest import create_user, get_token_for_user


async def _setup_patient(client, db, doctor_email, patient_email, diagnosis="CD"):
    doctor = await create_user(db, doctor_email, UserRole.DOCTOR)
    token = get_token_for_user(doctor)

    resp = await client.post(
        "/api/v1/patients",
        json={
            "initials": "С.О.",
            "sex": "F",
            "email": patient_email,
            "birth_year": 1990,
            "disability": "NONE",
            "diagnosis": diagnosis,
            "histologically_confirmed": "YES",
            "doctor_id": doctor.id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return doctor, token, resp.json()["id"]


@pytest.mark.asyncio
async def test_doctor_creates_self_assessment_cd(client: AsyncClient, db: AsyncSession):
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_cd@test.com", "pat_sa_cd@test.com", "CD"
    )

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"cd_abdominal_pain": 2, "cd_stool_count": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    # (2*5) + (4*2) = 10 + 8 = 18
    assert data["pro2_score"] == 18
    assert data["patient_id"] == patient_id


@pytest.mark.asyncio
async def test_doctor_creates_self_assessment_uc(client: AsyncClient, db: AsyncSession):
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_uc@test.com", "pat_sa_uc@test.com", "UC"
    )

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"uc_rectal_bleeding": 1, "uc_defecation_freq": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    # 1 + 3 = 4
    assert resp.json()["pro2_score"] == 4


@pytest.mark.asyncio
async def test_pro2_score_none_if_incomplete(client: AsyncClient, db: AsyncSession):
    """Якщо не всі поля заповнені — pro2_score = None."""
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_none@test.com", "pat_sa_none@test.com", "CD"
    )

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"cd_abdominal_pain": 1},  # cd_stool_count відсутній
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["pro2_score"] is None


@pytest.mark.asyncio
async def test_self_assessment_history(client: AsyncClient, db: AsyncSession):
    """Повна історія зберігається — тільки INSERT."""
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_hist@test.com", "pat_sa_hist@test.com", "CD"
    )

    for pain in [1, 2, 3]:
        await client.post(
            f"/api/v1/patients/{patient_id}/self-assessments",
            json={"cd_abdominal_pain": pain, "cd_stool_count": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/self-assessments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_get_latest_self_assessment(client: AsyncClient, db: AsyncSession):
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_latest@test.com", "pat_sa_latest@test.com", "UC"
    )

    await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"uc_rectal_bleeding": 0, "uc_defecation_freq": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"uc_rectal_bleeding": 3, "uc_defecation_freq": 3},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/self-assessments/latest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["pro2_score"] == 6  # 3+3


@pytest.mark.asyncio
async def test_latest_returns_404_when_empty(client: AsyncClient, db: AsyncSession):
    _, token, patient_id = await _setup_patient(
        client, db, "doc_sa_empty@test.com", "pat_sa_empty@test.com", "CD"
    )

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/self-assessments/latest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_token(client: AsyncClient, db: AsyncSession):
    _, token, patient_id = await _setup_patient(
        client, db, "doc_gen_tok@test.com", "pat_gen_tok@test.com", "CD"
    )

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments/generate-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_patient_submits_via_token(client: AsyncClient, db: AsyncSession):
    """Пацієнт заповнює самооцінку за email-токеном без JWT."""
    doctor, doc_token, patient_id = await _setup_patient(
        client, db, "doc_tok_sub@test.com", "pat_tok_sub@test.com", "CD"
    )

    # Лікар генерує токен
    gen_resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments/generate-token",
        headers={"Authorization": f"Bearer {doc_token}"},
    )
    tok = gen_resp.json()["token"]

    # Пацієнт надсилає самооцінку за токеном (без Authorization)
    resp = await client.post(
        f"/api/v1/self-assessments/by-token/{tok}",
        json={"cd_abdominal_pain": 1, "cd_stool_count": 2},
    )
    assert resp.status_code == 201
    # (1*5) + (2*2) = 5 + 4 = 9
    assert resp.json()["pro2_score"] == 9


@pytest.mark.asyncio
async def test_token_cannot_be_used_twice(client: AsyncClient, db: AsyncSession):
    doctor, doc_token, patient_id = await _setup_patient(
        client, db, "doc_tok_twice@test.com", "pat_tok_twice@test.com", "UC"
    )

    gen_resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments/generate-token",
        headers={"Authorization": f"Bearer {doc_token}"},
    )
    tok = gen_resp.json()["token"]

    await client.post(
        f"/api/v1/self-assessments/by-token/{tok}",
        json={"uc_rectal_bleeding": 1, "uc_defecation_freq": 1},
    )
    # Другий раз — 400
    resp = await client.post(
        f"/api/v1/self-assessments/by-token/{tok}",
        json={"uc_rectal_bleeding": 2, "uc_defecation_freq": 2},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient, db: AsyncSession):
    from app.models.models import PatientProfile, SelfAssessmentToken
    from sqlalchemy import select

    doctor, doc_token, patient_id = await _setup_patient(
        client, db, "doc_tok_exp@test.com", "pat_tok_exp@test.com", "CD"
    )

    # Вставляємо протермінований токен напряму
    expired_tok = secrets.token_urlsafe(48)
    db.add(SelfAssessmentToken(
        patient_id=patient_id,
        token=expired_tok,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    await db.commit()

    resp = await client.post(
        f"/api/v1/self-assessments/by-token/{expired_tok}",
        json={"cd_abdominal_pain": 1, "cd_stool_count": 1},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_another_doctor_cannot_access_assessments(client: AsyncClient, db: AsyncSession):
    _, doc1_token, patient_id = await _setup_patient(
        client, db, "doc_sa_acc1@test.com", "pat_sa_acc@test.com", "CD"
    )
    doc2 = await create_user(db, "doc_sa_acc2@test.com", UserRole.DOCTOR)
    doc2_token = get_token_for_user(doc2)

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/self-assessments",
        headers={"Authorization": f"Bearer {doc2_token}"},
    )
    assert resp.status_code == 403