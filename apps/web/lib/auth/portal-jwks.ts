import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

export interface PortalJwtPayload extends JWTPayload {
  email?: string;
  token_use: "access" | "id";
}

function getPatientPoolId(): string | undefined {
  return process.env.NEXT_PUBLIC_COGNITO_PATIENT_POOL_ID;
}

function getPatientPoolRegion(): string {
  return (
    process.env.NEXT_PUBLIC_COGNITO_PATIENT_REGION ??
    process.env.NEXT_PUBLIC_COGNITO_REGION ??
    "us-east-1"
  );
}

export function isPortalAuthConfigured(): boolean {
  return Boolean(getPatientPoolId() && process.env.NEXT_PUBLIC_COGNITO_PATIENT_CLIENT_ID);
}

export async function validatePortalAccessToken(
  token: string,
): Promise<PortalJwtPayload | null> {
  const poolId = getPatientPoolId();
  if (!poolId) return null;

  const region = getPatientPoolRegion();
  const issuer = `https://cognito-idp.${region}.amazonaws.com/${poolId}`;

  try {
    const jwks = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks.json`));
    const { payload } = await jwtVerify(token, jwks, { issuer });
    return payload as PortalJwtPayload;
  } catch (err) {
    console.error("[validatePortalAccessToken] failed:", err);
    return null;
  }
}
