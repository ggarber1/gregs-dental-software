import { describe, it, expect } from "vitest";

import {
  EMPTY_DRAFT,
  buildCreateProcedureBody,
  withCatalogCode,
  withCodeText,
} from "@/components/scheduling/procedureDraft";
import type { CdtCode } from "@/lib/api/procedures";

const D0120: CdtCode = {
  id: "0b9d6f7e-1c2a-4e5b-8f9a-123456789abc",
  code: "D0120",
  description: "Periodic oral evaluation",
  category: "diagnostic",
  defaultFeeCents: null,
  resolvedFeeCents: 6500,
  isActive: true,
};

describe("withCatalogCode", () => {
  it("fills code, name, fee and the catalog link", () => {
    const draft = withCatalogCode(EMPTY_DRAFT, D0120);
    expect(draft.cdtCodeId).toBe(D0120.id);
    expect(draft.procedureCode).toBe("D0120");
    expect(draft.procedureName).toBe("Periodic oral evaluation");
    expect(draft.fee).toBe("65");
  });
});

describe("withCodeText", () => {
  it("clears a previously picked catalog link when the code is edited", () => {
    const picked = withCatalogCode(EMPTY_DRAFT, D0120);
    const edited = withCodeText(picked, "D0150");
    expect(edited.cdtCodeId).toBeNull();
    expect(edited.procedureCode).toBe("D0150");
  });
});

describe("buildCreateProcedureBody", () => {
  it("sends cdtCodeId when a catalog code was picked", () => {
    const body = buildCreateProcedureBody(withCatalogCode(EMPTY_DRAFT, D0120));
    expect(body).toEqual({
      cdtCodeId: D0120.id,
      procedureCode: "D0120",
      procedureName: "Periodic oral evaluation",
      feeCents: 6500,
    });
  });

  it("omits cdtCodeId for a hand-typed code", () => {
    const draft = { ...withCodeText(EMPTY_DRAFT, " D0120 "), procedureName: "Exam", fee: "50" };
    const body = buildCreateProcedureBody(draft);
    expect(body.cdtCodeId).toBeUndefined();
    expect(body.procedureCode).toBe("D0120");
    expect(body.feeCents).toBe(5000);
  });

  it("includes optional fields only when filled", () => {
    const draft = {
      ...withCatalogCode(EMPTY_DRAFT, D0120),
      toothNumber: " 14 ",
      insuranceEst: "40",
      estimateSource: "manual" as const,
    };
    const body = buildCreateProcedureBody(draft);
    expect(body.toothNumber).toBe("14");
    expect(body.insuranceEstCents).toBe(4000);
    expect(body.estimateSource).toBe("manual");
    expect(body.surface).toBeUndefined();
    expect(body.notes).toBeUndefined();
  });
});
