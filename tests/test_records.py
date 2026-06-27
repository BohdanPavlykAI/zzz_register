import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import UserRole
from tests.conftest import create_user, get_token_for_user


async def _create_patient(client, token, doctor_id, email, diagnosis="CD"):
    resp = await client.post(
        "/api/v1/patients",
        json={
            "initials": "Т.Т.",
            "sex": "M",
            "email": email,
            "birth_year": 1980,
            "disability": "NONE",
            "diagnosis": diagnosis,
            "histologically_confirmed": "YES",
            "doctor_id": doctor_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_state_record_cd(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_record_cd@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "rec_cd@test.com", "CD")

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={
            "cd_wellbeing": 1,
            "cd_abdominal_pain": 2,
            "cd_stool_count": 3,
            "cd_abdominal_mass": 1,
            "cd_complications": ["ARTHRALGIA", "UVEITIS"],
            "treatments": [{"drug": "ANTI_TNF"}],
            "lab_results": [{"lab_type": "CRP", "value": 12.5, "result_date": "2024-01-15"}],
            "comments": ["Перший запис"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()

    # harvey_bradshaw = 1+2+3+1 + 2 ускладнення = 9
    assert data["cd_harvey_bradshaw"] == 9
    assert len(data["treatments"]) == 1
    assert len(data["lab_results"]) == 1
    assert len(data["cd_complications"]) == 2
    assert len(data["comments"]) == 1


@pytest.mark.asyncio
async def test_create_state_record_uc(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_record_uc@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "rec_uc@test.com", "UC")

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={
            "uc_stool_frequency": 2,
            "uc_rectal_bleeding": 1,
            "uc_physician_assess": 2,
            "uc_extent": "E2",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()

    # partial_mayo = 2+1+2 = 5
    assert data["uc_partial_mayo"] == 5


@pytest.mark.asyncio
async def test_record_history_preserved(client: AsyncClient, db: AsyncSession):
    """Перевіряємо що записи не перезаписуються — зберігається вся історія."""
    doc = await create_user(db, "doc_history@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "rec_history@test.com", "CD")

    # Перший запис
    await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={"cd_wellbeing": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Другий запис
    await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={"cd_wellbeing": 3},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/records",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 2  # обидва збережені


@pytest.mark.asyncio
async def test_get_latest_record(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_latest@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "rec_latest@test.com", "UC")

    await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={"uc_stool_frequency": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={"uc_stool_frequency": 3},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        f"/api/v1/patients/{patient_id}/records/latest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # Останній — з uc_stool_frequency=3
    assert resp.json()["uc_stool_frequency"] == 3


@pytest.mark.asyncio
async def test_surgeries_saved_when_flag_true(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_surgery@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "rec_surgery@test.com")

    resp = await client.post(
        f"/api/v1/patients/{patient_id}/records",
        json={
            "abdominal_surgeries": True,
            "surgeries": [
                {"operation_date": "2023-05-10"},
                {"operation_date": "2024-01-20"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert len(resp.json()["surgeries"]) == 2


@pytest.mark.asyncio
async def test_pro2_cd_calculation(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_pro2_cd@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "pro2_cd@test.com", "CD")

    # PRO2 для ХК: (pain*5) + (stool*2)
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"cd_abdominal_pain": 2, "cd_stool_count": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    # (2*5) + (3*2) = 10 + 6 = 16
    assert resp.json()["pro2_score"] == 16


@pytest.mark.asyncio
async def test_pro2_uc_calculation(client: AsyncClient, db: AsyncSession):
    doc = await create_user(db, "doc_pro2_uc@test.com", UserRole.DOCTOR)
    token = get_token_for_user(doc)
    patient_id = await _create_patient(client, token, doc.id, "pro2_uc@test.com", "UC")

    # PRO2 для ВК: bleeding + freq
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/self-assessments",
        json={"uc_rectal_bleeding": 2, "uc_defecation_freq": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["pro2_score"] == 5