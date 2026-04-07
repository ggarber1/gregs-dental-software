import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

export interface CognitoJwtPayload extends JWTPayload {
  email?: string;
  "cognito:groups"?: string[];
  "custom:practice_id"?: string;
  "custom:role"?: string;
  token_use: "access" | "id";
}

// Module-level JWKS set — cached for the process lifetime.
// jose's createRemoteJWKSet caches keys in memory after first fetch.
// This means token validation works offline once the keys have been fetched once.
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function getJwks(): ReturnType<typeof createRemoteJWKSet> {
  if (!jwks) {
    const region = process.env.NEXT_PUBLIC_COGNITO_REGION ?? "us-east-1";
    const poolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID;
    if (!poolId) {
      throw new Error("NEXT_PUBLIC_COGNITO_USER_POOL_ID is not set");
    }
    const jwksUrl = new URL(
      `https://cognito-idp.${region}.amazonaws.com/${poolId}/.well-known/jwks.json`,
    );
    jwks = createRemoteJWKSet(jwksUrl);
  }
  return jwks;
}

// Validates a Cognito access token. Returns the decoded payload on success,
// null on any failure (expired, bad signature, missing env vars, network error
// after JWKS is cached).
export async function validateAccessToken(
  token: string,
): Promise<CognitoJwtPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getJwks(), {
      issuer: `https://cognito-idp.${process.env.NEXT_PUBLIC_COGNITO_REGION ?? "us-east-1"}.amazonaws.com/${process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID}`,
    });
    return payload as CognitoJwtPayload;
  } catch {
    return null;
  }
}
