import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AuthUser = {
  id: string;
  email: string;
  role: string;
  display_name: string;
};

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  setSession: (args: {
    accessToken: string;
    refreshToken: string | null;
    user: AuthUser;
  }) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: ({ accessToken, refreshToken, user }) =>
        set({ accessToken, refreshToken, user }),
      clear: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      // localStorage is fine for Phase 0; we'll re-evaluate against httpOnly
      // cookies + CSRF when SSO lands. Tracked in DECISIONS.md (open item).
      name: "aegis.auth",
    },
  ),
);
