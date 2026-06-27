from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator, computed_field

from app.models.models import (
    AssessmentType, CdComplicationType, DiagnosisType, DisabilityGroup,
    DrugType, HistologyStatus, LabType, PatientStatus, ResistantDrugType,
    SexType, SmokingStatus, UserRole,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Region ────────────────────────────────────────────────────────────────────

class RegionOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


# ── User ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole
    first_name: str
    last_name: str
    patronymic: Optional[str] = None
    region_id: Optional[int] = None
    job_position: Optional[str] = None
    job_place: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronymic: Optional[str] = None
    region_id: Optional[int] = None
    job_position: Optional[str] = None
    job_place: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    role: UserRole
    first_name: str
    last_name: str
    patronymic: Optional[str]
    region: Optional[RegionOut] = None
    job_position: Optional[str]
    job_place: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Patient ───────────────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    surname: Optional[str] = None
    initials: str
    sex: SexType
    region_id: Optional[int] = None
    email: EmailStr
    birth_year: int
    weight: Optional[float] = None
    height: Optional[int] = None
    disability: DisabilityGroup = DisabilityGroup.NONE
    diagnosis: DiagnosisType
    histologically_confirmed: HistologyStatus
    diagnosis_year: Optional[int] = None
    doctor_id: Optional[int] = None

    @field_validator("birth_year")
    @classmethod
    def validate_birth_year(cls, v: int) -> int:
        if not (1900 <= v <= 2100):
            raise ValueError("birth_year має бути між 1900 та 2100")
        return v


class PatientUpdate(BaseModel):
    surname: Optional[str] = None
    initials: Optional[str] = None
    sex: Optional[SexType] = None
    region_id: Optional[int] = None
    email: Optional[EmailStr] = None
    birth_year: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[int] = None
    disability: Optional[DisabilityGroup] = None
    diagnosis: Optional[DiagnosisType] = None
    histologically_confirmed: Optional[HistologyStatus] = None
    diagnosis_year: Optional[int] = None
    doctor_id: Optional[int] = None


class PatientStatusUpdate(BaseModel):
    status: PatientStatus
    doctor_id: Optional[int] = None


class PatientListItem(BaseModel):
    id: int
    initials: str
    sex: SexType
    diagnosis: DiagnosisType
    status: PatientStatus
    birth_year: int
    disability: DisabilityGroup
    doctor: Optional[UserOut] = None
    region: Optional[RegionOut] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientOut(PatientListItem):
    surname: Optional[str] = None
    email: str
    weight: Optional[float]
    height: Optional[int]
    histologically_confirmed: HistologyStatus
    diagnosis_year: Optional[int]
    updated_at: datetime


class PatientMeOut(BaseModel):
    id: int
    email: EmailStr
    initials: str
    sex: SexType
    birth_year: int
    weight: Optional[float] = None
    height: Optional[int] = None
    disability: DisabilityGroup
    diagnosis: DiagnosisType
    status: PatientStatus
    histologically_confirmed: HistologyStatus
    diagnosis_year: Optional[int] = None
    region: Optional[RegionOut] = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def role(self) -> UserRole:
        return UserRole.PATIENT

    model_config = {"from_attributes": True}


# ── Records & Assessments ─────────────────────────────────────────────────────

class CdRecordCreate(BaseModel):
    localization: Optional[str] = None
    perianal_lesions: Optional[bool] = None
    behavior: Optional[str] = None
    general_wellbeing: Optional[int] = None
    abdominal_pain: Optional[int] = None
    stool_count: Optional[int] = None
    abdominal_mass: Optional[int] = None
    ses_cd: Optional[str] = None
    ses_cd_other: Optional[str] = None
    complications: List[CdComplicationType] = []
    comments: Optional[str] = None


class CdRecordOut(BaseModel):
    id: int
    patient_id: int
    created_by: int
    created_at: datetime
    localization: Optional[str]
    perianal_lesions: Optional[bool]
    behavior: Optional[str]
    general_wellbeing: Optional[int]
    abdominal_pain: Optional[int]
    stool_count: Optional[int]
    abdominal_mass: Optional[int]
    ses_cd: Optional[str]
    ses_cd_other: Optional[str]
    harvey_bradshaw: Optional[int]
    comments: Optional[str]

    model_config = {"from_attributes": True}


class UcRecordCreate(BaseModel):
    extent: Optional[str] = None
    stool_frequency: Optional[int] = None
    rectal_bleeding: Optional[int] = None
    physician_assessment: Optional[int] = None
    endoscopic_mayo: Optional[int] = None
    endoscopic_mayo_other: Optional[str] = None
    comments: Optional[str] = None


class UcRecordOut(BaseModel):
    id: int
    patient_id: int
    created_by: int
    created_at: datetime
    extent: Optional[str]
    stool_frequency: Optional[int]
    rectal_bleeding: Optional[int]
    physician_assessment: Optional[int]
    endoscopic_mayo: Optional[int]
    endoscopic_mayo_other: Optional[str]
    partial_mayo: Optional[int]
    comments: Optional[str]

    model_config = {"from_attributes": True}


class ClinicalRecordCreate(BaseModel):
    strictures: Optional[bool] = None
    penetrations_fistulas: Optional[bool] = None
    fecal_incontinence: Optional[str] = None
    infectious_complications: Optional[str] = None
    abdominal_surgeries: Optional[bool] = None
    steroid_dependence: Optional[bool] = None
    steroid_resistance: Optional[bool] = None
    advanced_therapy_resistance: Optional[bool] = None
    smoking_status: Optional[SmokingStatus] = None
    side_effects: Optional[str] = None
    resistant_drugs_other: Optional[str] = None


class SelfAssessmentCreate(BaseModel):
    assessment_type: AssessmentType
    cd_abdominal_pain: Optional[int] = None
    cd_stool_count: Optional[int] = None
    uc_rectal_bleeding: Optional[int] = None
    uc_defecation_freq: Optional[int] = None
    first_symptoms_date: Optional[date] = None
    first_symptoms_desc: Optional[str] = None
    possible_factors: Optional[str] = None
    constipation_on_flare: Optional[bool] = None
    constipation_stool_freq: Optional[str] = None


class SelfAssessmentOut(BaseModel):
    id: int
    patient_id: int
    created_by: Optional[int]
    created_at: datetime
    assessment_type: AssessmentType
    cd_abdominal_pain: Optional[int]
    cd_stool_count: Optional[int]
    uc_rectal_bleeding: Optional[int]
    uc_defecation_freq: Optional[int]
    pro2_score: Optional[int]
    first_symptoms_date: Optional[date]
    first_symptoms_desc: Optional[str]
    possible_factors: Optional[str]
    constipation_on_flare: Optional[bool]
    constipation_stool_freq: Optional[str]

    model_config = {"from_attributes": True}

class LabResultOut(BaseModel):
    id: int
    lab_type: LabType
    value: float
    result_date: date

    model_config = {"from_attributes": True}


class SurgeryOut(BaseModel):
    id: int
    operation_date: date

    model_config = {"from_attributes": True}


class TreatmentOut(BaseModel):
    id: int
    drug: DrugType
    other_drug_name: Optional[str] = None

    model_config = {"from_attributes": True}


class ResistantDrugOut(BaseModel):
    id: int
    drug: ResistantDrugType
    other_drug_name: Optional[str] = None

    model_config = {"from_attributes": True}


class ClinicalRecordOut(BaseModel):
    id: int
    patient_id: int
    created_by: int
    created_at: datetime
    strictures: Optional[bool] = None
    penetrations_fistulas: Optional[bool] = None
    fecal_incontinence: Optional[str] = None
    infectious_complications: Optional[str] = None
    abdominal_surgeries: Optional[bool] = None
    steroid_dependence: Optional[bool] = None
    steroid_resistance: Optional[bool] = None
    advanced_therapy_resistance: Optional[bool] = None
    smoking_status: Optional[SmokingStatus] = None
    side_effects: Optional[str] = None
    resistant_drugs_other: Optional[str] = None
    lab_results: List[LabResultOut] = []
    surgeries: List[SurgeryOut] = []
    treatments: List[TreatmentOut] = []
    resistant_drugs: List[ResistantDrugOut] = []

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str