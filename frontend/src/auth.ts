import {
  confirmResetPassword,
  confirmSignIn,
  fetchAuthSession,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
  updatePassword,
} from 'aws-amplify/auth';

export {
  confirmResetPassword,
  confirmSignIn,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
  updatePassword,
};

export async function getAccessToken(forceRefresh = false): Promise<string | null> {
  const session = await fetchAuthSession({ forceRefresh });
  return session.tokens?.accessToken?.toString() ?? null;
}
