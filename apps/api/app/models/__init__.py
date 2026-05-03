# Import all models here so Alembic's env.py picks them up via Base.metadata.
from app.models.appointment import Appointment as Appointment
from app.models.appointment_reminder import AppointmentReminder as AppointmentReminder
from app.models.appointment_type import AppointmentType as AppointmentType
from app.models.audit_log import AuditLog as AuditLog
from app.models.insurance_plan import InsurancePlan as InsurancePlan
from app.models.intake_form import IntakeForm as IntakeForm
from app.models.medical_history_version import MedicalHistoryVersion as MedicalHistoryVersion
from app.models.operatory import Operatory as Operatory
from app.models.patient import Patient as Patient
from app.models.patient_insurance import PatientInsurance as PatientInsurance
from app.models.practice import Practice as Practice
from app.models.provider import Provider as Provider
from app.models.user import PracticeUser as PracticeUser
from app.models.user import User as User
