import { Amplify } from "aws-amplify";

// Configure Amplify Auth once at module load time (client-side only).
// Imported as a side-effect from providers.tsx — do not call this elsewhere.
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!,
      userPoolClientId: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!,
    },
  },
});
