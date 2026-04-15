/**
 * generate-pydantic.ts
 *
 * Converts Zod schemas → JSON Schema → Pydantic models.
 *
 * Pipeline:
 *   1. Import all Zod schemas from src/schemas/
 *   2. Convert each to JSON Schema via zod-to-json-schema
 *   3. Bundle into a single $defs JSON Schema document
 *   4. Run datamodel-codegen (Python CLI) to produce Pydantic models
 *   5. Write output to apps/api/app/schemas/generated.py
 *
 * Run via: pnpm --filter @dental/shared-types generate
 */

import { execSync } from "child_process";
import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { zodToJsonSchema } from "zod-to-json-schema";

// ── Schema imports ────────────────────────────────────────────────────────────
import {
  PracticeSchema,
  CreatePracticeSchema,
  ProviderSchema,
  CreateProviderSchema,
  OperatorySchema,
  CreateOperatorySchema,
} from "../src/schemas/practice.js";
import {
  PatientSchema,
  CreatePatientSchema,
  UpdatePatientSchema,
  PatientSearchQuerySchema,
} from "../src/schemas/patient.js";
import {
  IntakeFormTokenInfoSchema,
  SubmitIntakeFormSchema,
  SendIntakeFormSchema,
  SendIntakeFormResponseSchema,
  IntakeFormSummarySchema,
  IntakeFormDetailSchema,
} from "../src/schemas/intake.js";
import {
  InsuranceSchema,
  CreateInsuranceSchema,
  UpdateInsuranceSchema,
} from "../src/schemas/insurance.js";
import {
  PaginationQuerySchema,
  PaginationMetaSchema,
  ApiErrorSchema,
} from "../src/schemas/common.js";
import {
  AppointmentTypeSchema,
  CreateAppointmentTypeSchema,
  UpdateAppointmentTypeSchema,
  AppointmentSchema,
  CreateAppointmentSchema,
  UpdateAppointmentSchema,
  CancelAppointmentSchema,
  ProviderResponseSchema,
  CreateProviderBodySchema,
  UpdateProviderBodySchema,
  OperatoryResponseSchema,
  CreateOperatoryBodySchema,
  UpdateOperatoryBodySchema,
} from "../src/schemas/scheduling.js";

// ── Schema registry ───────────────────────────────────────────────────────────
const schemas: Record<string, Parameters<typeof zodToJsonSchema>[0]> = {
  Practice: PracticeSchema,
  CreatePractice: CreatePracticeSchema,
  Provider: ProviderSchema,
  CreateProvider: CreateProviderSchema,
  Operatory: OperatorySchema,
  CreateOperatory: CreateOperatorySchema,
  Patient: PatientSchema,
  CreatePatient: CreatePatientSchema,
  UpdatePatient: UpdatePatientSchema,
  PatientSearchQuery: PatientSearchQuerySchema,
  PaginationQuery: PaginationQuerySchema,
  PaginationMeta: PaginationMetaSchema,
  ApiError: ApiErrorSchema,
  IntakeFormTokenInfo: IntakeFormTokenInfoSchema,
  SubmitIntakeForm: SubmitIntakeFormSchema,
  SendIntakeForm: SendIntakeFormSchema,
  SendIntakeFormResponse: SendIntakeFormResponseSchema,
  IntakeFormSummary: IntakeFormSummarySchema,
  IntakeFormDetail: IntakeFormDetailSchema,
  Insurance: InsuranceSchema,
  CreateInsurance: CreateInsuranceSchema,
  UpdateInsurance: UpdateInsuranceSchema,
  // Scheduling
  AppointmentType: AppointmentTypeSchema,
  CreateAppointmentType: CreateAppointmentTypeSchema,
  UpdateAppointmentType: UpdateAppointmentTypeSchema,
  Appointment: AppointmentSchema,
  CreateAppointment: CreateAppointmentSchema,
  UpdateAppointment: UpdateAppointmentSchema,
  CancelAppointment: CancelAppointmentSchema,
  ProviderResponse: ProviderResponseSchema,
  CreateProviderBody: CreateProviderBodySchema,
  UpdateProviderBody: UpdateProviderBodySchema,
  OperatoryResponse: OperatoryResponseSchema,
  CreateOperatoryBody: CreateOperatoryBodySchema,
  UpdateOperatoryBody: UpdateOperatoryBodySchema,
};

// ── Paths ─────────────────────────────────────────────────────────────────────
const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const jsonSchemaPath = join(__dirname, "..", "dist", "schemas.json");
const outputPath = join(repoRoot, "apps", "api", "app", "schemas", "generated.py");

// ── Build bundled JSON Schema ─────────────────────────────────────────────────
const defs: Record<string, unknown> = {};

for (const [name, schema] of Object.entries(schemas)) {
  const jsonSchema = zodToJsonSchema(schema, {
    name,
    $refStrategy: "none", // inline all refs — simpler for codegen
  });
  // zodToJsonSchema wraps in { $schema, definitions, ... } when name is given
  // We want only the schema body
  const { $schema: _schema, definitions, ...body } = jsonSchema as Record<string, unknown>;
  defs[name] = body;

  // Include any inlined definitions
  if (definitions) {
    Object.assign(defs, definitions);
  }
}

const bundled = {
  $schema: "http://json-schema.org/draft-07/schema#",
  title: "DentalPMSSchemas",
  definitions: defs,
};

mkdirSync(dirname(jsonSchemaPath), { recursive: true });
writeFileSync(jsonSchemaPath, JSON.stringify(bundled, null, 2));
console.log(`✓ JSON Schema written to ${jsonSchemaPath}`);

// ── Run datamodel-codegen ─────────────────────────────────────────────────────
// Requires: pip install datamodel-code-generator
// In CI/Docker this is installed in the Python venv under apps/api
const apiVenv = join(repoRoot, "apps", "api", ".venv");
const codegenBin = join(apiVenv, "bin", "datamodel-codegen");

mkdirSync(dirname(outputPath), { recursive: true });

const cmd = [
  codegenBin,
  `--input ${jsonSchemaPath}`,
  `--input-file-type jsonschema`,
  `--output ${outputPath}`,
  `--output-model-type pydantic_v2.BaseModel`,
  `--field-constraints`,
  `--use-standard-collections`,
  `--use-union-operator`,
  `--target-python-version 3.12`,
  `--snake-case-field`,
  `--formatters ruff-format`,
  `--formatters ruff-check`,
].join(" ");

try {
  execSync(cmd, { stdio: "inherit" });
  console.log(`✓ Pydantic models written to ${outputPath}`);
} catch {
  // If venv doesn't exist yet (e.g. first clone before uv sync), fall back to
  // system datamodel-codegen if available, otherwise emit a helpful error.
  try {
    const fallbackCmd = cmd.replace(codegenBin, "datamodel-codegen");
    execSync(fallbackCmd, { stdio: "inherit" });
    console.log(`✓ Pydantic models written to ${outputPath} (via system datamodel-codegen)`);
  } catch {
    console.error(
      [
        "✗ datamodel-codegen not found.",
        "  Run: cd apps/api && uv sync",
        "  Then: pnpm --filter @dental/shared-types generate",
      ].join("\n"),
    );
    process.exit(1);
  }
}
