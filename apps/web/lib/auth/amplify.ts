import { Amplify } from "aws-amplify";

const userPoolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID;
const userPoolClientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;

if (!userPoolId || !userPoolClientId) {
  throw new Error(
    `Cognito env vars missing at build time: NEXT_PUBLIC_COGNITO_USER_POOL_ID=${userPoolId} NEXT_PUBLIC_COGNITO_CLIENT_ID=${userPoolClientId}`
  );
}

// Configure Amplify Auth once at module load time (client-side only).
// Imported as a side-effect from providers.tsx — do not call this elsewhere.
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId,
      userPoolClientId,
    },
  },
});
