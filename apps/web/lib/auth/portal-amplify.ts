import { Amplify } from "aws-amplify";

const userPoolId = process.env.NEXT_PUBLIC_COGNITO_PATIENT_POOL_ID;
const userPoolClientId = process.env.NEXT_PUBLIC_COGNITO_PATIENT_CLIENT_ID;

export function configurePortalAmplify(): boolean {
  if (!userPoolId || !userPoolClientId) {
    return false;
  }

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
      },
    },
  });

  return true;
}

export function isPortalAmplifyConfigured(): boolean {
  return Boolean(userPoolId && userPoolClientId);
}
