"""
Тести Celery задачі send_self_assessment_reminders.

Підхід: unit-тести без реального broker/worker.
- Викликаємо _async_send_reminders() напряму через AsyncSession тестової БД.
- Email мокаємо через unittest.mock.patch.
- Перевіряємо бізнес-логіку: хто отримує нагадування, коли, без дублювань.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    PatientProfile, PatientSelfAssessment, PatientStatus,
    SelfAssessmentToken, UserRole,
)
from tests.conftest import create_user, TestingSession


async def _create_attached_patient(db: AsyncSession, doctor_id: int, email: str, diagnosis="CD"):
    patient = PatientProfile(
        doctor_id=doctor_id,
        initials="Т.Т.",
        sex="M",
        email=email,
        birth_year=1980,
        disability="NONE",
        diagnosis=diagnosis,
        histologically_confirmed="YES",
        status=PatientStatus.ATTACHED,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


async def _run_task(db: AsyncSession):
    """
    Запускаємо логіку задачі з тестовою сесією замість реальної БД.
    Патчимо AsyncSessionLocal щоб повертала нашу тестову сесію.
    """
    from app.tasks import celery_tasks

    # Контекстний менеджер для підміни сесії
    class FakeSessionContext:
        async def __aenter__(self):
            return db
        async def __aexit__(self, *args):
            pass

    with patch.object(celery_tasks, "AsyncSessionLocal", return_value=FakeSessionContext()):
        with patch.object(celery_tasks, "_send_email") as mock_email:
            result = await celery_tasks._async_send_reminders()
            return result, mock_email


# ── Тест 1: пацієнт без жодної самооцінки → отримує токен і email ─────────────

@pytest.mark.asyncio
async def test_patient_without_assessment_gets_reminder(db: AsyncSession):
    doctor = await create_user(db, "cel_doc1@test.com", UserRole.DOCTOR)
    patient = await _create_attached_patient(db, doctor.id, "cel_pat1@test.com")

    result, mock_email = await _run_task(db)

    assert result["sent"] == 1
    assert mock_email.call_count == 1
    # Перевіряємо що токен збережено в БД
    from sqlalchemy import select
    tokens = await db.execute(
        select(SelfAssessmentToken).where(SelfAssessmentToken.patient_id == patient.id)
    )
    assert tokens.scalar_one_or_none() is not None


# ── Тест 2: пацієнт з нещодавньою самооцінкою (< 90 днів) → НЕ отримує ───────

@pytest.mark.asyncio
async def test_patient_with_recent_assessment_skipped(db: AsyncSession):
    doctor = await create_user(db, "cel_doc2@test.com", UserRole.DOCTOR)
    patient = await _create_attached_patient(db, doctor.id, "cel_pat2@test.com")

    # Додаємо нещодавню самооцінку (30 днів тому)
    db.add(PatientSelfAssessment(
        patient_id=patient.id,
        created_by=doctor.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
    ))
    await db.commit()

    result, mock_email = await _run_task(db)

    # Цей пацієнт не повинен отримати нагадування
    from sqlalchemy import select
    emails_sent_to = [call.args[0] for call in mock_email.call_args_list]
    assert "cel_pat2@test.com" not in emails_sent_to


# ── Тест 3: пацієнт з давньою самооцінкою (> 90 днів) → отримує ──────────────

@pytest.mark.asyncio
async def test_patient_with_old_assessment_gets_reminder(db: AsyncSession):
    doctor = await create_user(db, "cel_doc3@test.com", UserRole.DOCTOR)
    patient = await _create_attached_patient(db, doctor.id, "cel_pat3@test.com")

    # Давня самооцінка (100 днів тому)
    db.add(PatientSelfAssessment(
        patient_id=patient.id,
        created_by=doctor.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
    ))
    await db.commit()

    result, mock_email = await _run_task(db)

    emails_sent_to = [call.args[0] for call in mock_email.call_args_list]
    assert "cel_pat3@test.com" in emails_sent_to


# ── Тест 4: DETACHED / PENDING пацієнти НЕ отримують нагадування ─────────────

@pytest.mark.asyncio
async def test_non_attached_patients_skipped(db: AsyncSession):
    doctor = await create_user(db, "cel_doc4@test.com", UserRole.DOCTOR)

    # PENDING
    pending = PatientProfile(
        doctor_id=doctor.id, initials="П.П.", sex="M",
        email="cel_pending@test.com", birth_year=1980,
        disability="NONE", diagnosis="CD", histologically_confirmed="YES",
        status=PatientStatus.PENDING,
    )
    # DETACHED
    detached = PatientProfile(
        doctor_id=doctor.id, initials="В.В.", sex="F",
        email="cel_detached@test.com", birth_year=1985,
        disability="NONE", diagnosis="UC", histologically_confirmed="YES",
        status=PatientStatus.DETACHED,
    )
    db.add_all([pending, detached])
    await db.commit()

    result, mock_email = await _run_task(db)

    emails_sent_to = [call.args[0] for call in mock_email.call_args_list]
    assert "cel_pending@test.com" not in emails_sent_to
    assert "cel_detached@test.com" not in emails_sent_to


# ── Тест 5: не спамить якщо невикористаний токен вже є ───────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_token_if_active_exists(db: AsyncSession):
    doctor = await create_user(db, "cel_doc5@test.com", UserRole.DOCTOR)
    patient = await _create_attached_patient(db, doctor.id, "cel_pat5@test.com")

    # Вже є активний невикористаний токен
    db.add(SelfAssessmentToken(
        patient_id=patient.id,
        token="existing-active-token-unique-123",
        expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        used_at=None,
    ))
    await db.commit()

    result, mock_email = await _run_task(db)

    # Email не надсилається повторно
    emails_sent_to = [call.args[0] for call in mock_email.call_args_list]
    assert "cel_pat5@test.com" not in emails_sent_to


# ── Тест 6: якщо попередній токен використано — надсилає новий ───────────────

@pytest.mark.asyncio
async def test_sends_new_token_if_previous_used(db: AsyncSession):
    doctor = await create_user(db, "cel_doc6@test.com", UserRole.DOCTOR)
    patient = await _create_attached_patient(db, doctor.id, "cel_pat6@test.com")

    # Попередній токен вже використаний
    db.add(SelfAssessmentToken(
        patient_id=patient.id,
        token="used-token-unique-456",
        expires_at=datetime.now(timezone.utc) - timedelta(days=7),
        used_at=datetime.now(timezone.utc) - timedelta(days=8),
    ))
    await db.commit()

    result, mock_email = await _run_task(db)

    emails_sent_to = [call.args[0] for call in mock_email.call_args_list]
    assert "cel_pat6@test.com" in emails_sent_to


# ── Тест 7: SMTP помилка — записує в errors, не падає ────────────────────────

@pytest.mark.asyncio
async def test_smtp_error_logged_not_raised(db: AsyncSession):
    doctor = await create_user(db, "cel_doc7@test.com", UserRole.DOCTOR)
    await _create_attached_patient(db, doctor.id, "cel_pat7@test.com")

    from app.tasks import celery_tasks

    class FakeSessionContext:
        async def __aenter__(self): return db
        async def __aexit__(self, *args): pass

    with patch.object(celery_tasks, "AsyncSessionLocal", return_value=FakeSessionContext()):
        with patch.object(
            celery_tasks, "_send_email",
            side_effect=Exception("SMTP connection refused")
        ):
            # Не має кидати exception
            result = await celery_tasks._async_send_reminders()

    assert result["sent"] == 0
    assert len(result["errors"]) == 1
    assert "SMTP connection refused" in result["errors"][0]["error"]


# ── Тест 8: кілька пацієнтів — кожен отримує свій токен ──────────────────────

@pytest.mark.asyncio
async def test_multiple_patients_all_get_reminders(db: AsyncSession):
    doctor = await create_user(db, "cel_doc8@test.com", UserRole.DOCTOR)

    emails = ["cel_multi1@test.com", "cel_multi2@test.com", "cel_multi3@test.com"]
    for email in emails:
        await _create_attached_patient(db, doctor.id, email)

    result, mock_email = await _run_task(db)

    sent_to = {call.args[0] for call in mock_email.call_args_list}
    for email in emails:
        assert email in sent_to


# ── Тест 9: розрахунок pro2 — граничні значення ──────────────────────────────

def test_pro2_cd_boundary_values():
    """Юніт-тест формули PRO2 для ХК без HTTP."""
    from app.api.v1.endpoints.self_assessment import _calc_pro2
    from app.models.models import DiagnosisType
    from app.schemas.schemas import SelfAssessmentCreate

    # Мінімум: 0+0 = 0
    body = SelfAssessmentCreate(cd_abdominal_pain=0, cd_stool_count=0)
    assert _calc_pro2(DiagnosisType.CD, body) == 0

    # Максимум: (3*5) + (великий stool * 2)
    body = SelfAssessmentCreate(cd_abdominal_pain=3, cd_stool_count=10)
    assert _calc_pro2(DiagnosisType.CD, body) == 35

    # Неповні дані → None
    body = SelfAssessmentCreate(cd_abdominal_pain=2)
    assert _calc_pro2(DiagnosisType.CD, body) is None


def test_pro2_uc_boundary_values():
    """Юніт-тест формули PRO2 для ВК."""
    from app.api.v1.endpoints.self_assessment import _calc_pro2
    from app.models.models import DiagnosisType
    from app.schemas.schemas import SelfAssessmentCreate

    # Мінімум: 0+0 = 0
    body = SelfAssessmentCreate(uc_rectal_bleeding=0, uc_defecation_freq=0)
    assert _calc_pro2(DiagnosisType.UC, body) == 0

    # Максимум: 3+3 = 6
    body = SelfAssessmentCreate(uc_rectal_bleeding=3, uc_defecation_freq=3)
    assert _calc_pro2(DiagnosisType.UC, body) == 6

    # Неповні дані → None
    body = SelfAssessmentCreate(uc_rectal_bleeding=2)
    assert _calc_pro2(DiagnosisType.UC, body) is None


# ── Тест 10: harvey_bradshaw розрахунок ──────────────────────────────────────

def test_harvey_bradshaw_calculation():
    """Юніт-тест формули Харвея-Бредшоу."""
    from app.api.v1.endpoints.records import _calc_harvey_bradshaw
    from app.schemas.schemas import StateRecordCreate

    body = StateRecordCreate(
        cd_wellbeing=1,
        cd_abdominal_pain=2,
        cd_stool_count=3,
        cd_abdominal_mass=1,
    )
    # 1+2+3+1 + 2 ускладнення = 9
    assert _calc_harvey_bradshaw(body, complications_count=2) == 9

    # Без ускладнень
    assert _calc_harvey_bradshaw(body, complications_count=0) == 7

    # Всі None → None
    empty = StateRecordCreate()
    assert _calc_harvey_bradshaw(empty, complications_count=0) is None


def test_partial_mayo_calculation():
    """Юніт-тест формули Partial Mayo."""
    from app.api.v1.endpoints.records import _calc_partial_mayo
    from app.schemas.schemas import StateRecordCreate

    body = StateRecordCreate(
        uc_stool_frequency=2,
        uc_rectal_bleeding=1,
        uc_physician_assess=2,
    )
    assert _calc_partial_mayo(body) == 5

    # Мінімум
    body = StateRecordCreate(
        uc_stool_frequency=0,
        uc_rectal_bleeding=0,
        uc_physician_assess=0,
    )
    assert _calc_partial_mayo(body) == 0

    # Всі None → None
    assert _calc_partial_mayo(StateRecordCreate()) is None