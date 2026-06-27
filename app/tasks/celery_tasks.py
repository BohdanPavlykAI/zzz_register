"""
Celery задача: раз на добу перевіряє ATTACHED пацієнтів,
у яких остання самооцінка була 90+ днів тому (або жодної немає),
генерує токен і надсилає email-нагадування.
"""
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from celery import Celery
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.models import PatientProfile, PatientSelfAssessment, PatientStatus, SelfAssessmentToken

celery_app = Celery("zzk", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.beat_schedule = {
    "send-self-assessment-reminders": {
        "task": "app.tasks.celery_tasks.send_self_assessment_reminders",
        "schedule": 86400.0,
    }
}


def _send_email(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/self-assessment?token={token}"
    msg = MIMEText(
        f"Доброго дня!\n\n"
        f"Будь ласка, заповніть самооцінку стану здоров'я за посиланням:\n{link}\n\n"
        f"Посилання дійсне 7 днів.",
        "plain",
        "utf-8",
    )
    msg["Subject"] = "ЗЗК Реєстр — самооцінка стану"
    msg["From"] = settings.SMTP_USER
    msg["To"] = to

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


@celery_app.task(name="app.tasks.celery_tasks.send_self_assessment_reminders")
def send_self_assessment_reminders() -> dict:
    """
    Синхронна обгортка: запускає асинхронну логіку через event loop.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_send_reminders())


async def _async_send_reminders() -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=90)
    sent = 0
    errors = []

    async with AsyncSessionLocal() as db:
        patients_result = await db.execute(
            select(PatientProfile).where(PatientProfile.status == PatientStatus.ATTACHED)
        )
        patients = patients_result.scalars().all()

        for patient in patients:
            last_result = await db.execute(
                select(PatientSelfAssessment.created_at)
                .where(PatientSelfAssessment.patient_id == patient.id)
                .order_by(PatientSelfAssessment.created_at.desc())
                .limit(1)
            )
            last_assessment = last_result.scalar_one_or_none()

            if last_assessment:
                last_dt = last_assessment if last_assessment.tzinfo else last_assessment.replace(tzinfo=timezone.utc)
                if last_dt > cutoff:
                    continue

            existing_result = await db.execute(
                select(SelfAssessmentToken).where(
                    SelfAssessmentToken.patient_id == patient.id,
                    SelfAssessmentToken.used_at.is_(None),
                )
            )
            existing_tokens = existing_result.scalars().all()
            active = any(
                (t.expires_at if t.expires_at.tzinfo else t.expires_at.replace(tzinfo=timezone.utc)) > now
                for t in existing_tokens
            )
            if active:
                continue

            token_value = secrets.token_urlsafe(64)
            token_obj = SelfAssessmentToken(
                patient_id=patient.id,
                token=token_value,
                expires_at=now + timedelta(days=7),
            )
            db.add(token_obj)
            await db.flush()

            try:
                _send_email(patient.email, token_value)
                sent += 1
            except Exception as e:
                errors.append({"patient_id": patient.id, "error": str(e)})

        await db.commit()

    return {"sent": sent, "errors": errors}