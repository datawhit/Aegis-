import { api } from "@/lib/api";
import { useAuthStore, type AuthUser } from "@/stores/authStore";

type LoginResponse = {
  access_token: string;
  refresh_token: string | null;
  token_type: string;
  expires_at: string | null;
};

export async function login(email: string, password: string): Promise<AuthUser> {
  const { data } = await api.post<LoginResponse>("/auth/login", { email, password });
  // Set token first so the /auth/me request can use it.
  useAuthStore.getState().setSession({
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    user: { id: "", email, role: "", display_name: "" },
  });
  const me = await api.get<AuthUser>("/auth/me");
  useAuthStore.getState().setSession({
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    user: me.data,
  });
  return me.data;
}

export function logout() {
  useAuthStore.getState().clear();
}
