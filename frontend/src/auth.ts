import {
  fetchAuthSession,
  getCurrentUser,
  signIn,
  signOut,
  updatePassword,
} from 'aws-amplify/auth';

export { getCurrentUser, signIn, signOut, updatePassword };

export async function getAccessToken(forceRefresh = false): Promise<string | null> {
  const session = await fetchAuthSession({ forceRefresh });
  return session.tokens?.accessToken?.toString() ?? null;
}
