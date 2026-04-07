import { createLocalJWKSet, jwtVerify, type JWTPayload } from "jose";

import jwksJson from "./cognito-jwks.json";

export interface CognitoJwtPayload extends JWTPayload {
  email?: string;
  "cognito:groups"?: string[];
  "custom:practice_id"?: string;
  "custom:role"?: string;
  token_use: "access" | "id";
}

// JWKS keys are pre-fetched from Cognito at Docker build time (see Dockerfile)
// and embedded as a static JSON file. This eliminates the runtime network
// dependency in middleware — the container never needs to reach cognito-idp.
const jwks = createLocalJWKSet(jwksJson);

// Validates a Cognito access token. Returns the decoded payload on success,
// null on any failure (expired, bad signature, wrong issuer).
export async function validateAccessToken(
  token: string,
): Promise<CognitoJwtPayload | null> {
  try {
    const { payload } = await jwtVerify(token, jwks, {
      issuer: `https://cognito-idp.${process.env.NEXT_PUBLIC_COGNITO_REGION ?? "us-east-1"}.amazonaws.com/${process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID}`,
    });
    return payload as CognitoJwtPayload;
  } catch (err) {
    console.error("[validateAccessToken] failed:", err);
    return null;
  }
}
