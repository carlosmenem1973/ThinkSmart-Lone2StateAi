import { Amplify } from 'aws-amplify';

const region = import.meta.env.VITE_AWS_REGION;
const userPoolId = import.meta.env.VITE_USER_POOL_ID;
const userPoolClientId = import.meta.env.VITE_USER_POOL_CLIENT_ID;

if (!region || !userPoolId || !userPoolClientId) {
  throw new Error('Missing Cognito frontend configuration. Set VITE_AWS_REGION, VITE_USER_POOL_ID and VITE_USER_POOL_CLIENT_ID.');
}

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId,
      userPoolClientId,
      loginWith: { email: true },
    },
  },
});
