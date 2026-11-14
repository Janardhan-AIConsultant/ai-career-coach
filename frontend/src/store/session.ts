import { create } from "zustand";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "user" | "admin" | string;
}

const GUEST_KEY = "acc.guest";

function readGuest(): string | null {
  try {
    return sessionStorage.getItem(GUEST_KEY);
  } catch {
    return null;
  }
}

interface SessionState {
  /** Short-lived access token: kept in memory only (never localStorage). The refresh token is an HttpOnly cookie. */
  accessToken: string | null;
  user: User | null;
  /** Guest capability token: per-tab sessionStorage, so it disappears when the tab closes. */
  guestToken: string | null;
  ready: boolean;
  setAuth: (token: string | null, user?: User | null) => void;
  setUser: (user: User | null) => void;
  setGuestToken: (token: string | null) => void;
  setReady: () => void;
  clear: () => void;
}

export const useSession = create<SessionState>((set) => ({
  accessToken: null,
  user: null,
  guestToken: readGuest(),
  ready: false,
  setAuth: (accessToken, user) => set((s) => ({ accessToken, user: user === undefined ? s.user : user })),
  setUser: (user) => set({ user }),
  setGuestToken: (guestToken) => {
    try {
      if (guestToken) sessionStorage.setItem(GUEST_KEY, guestToken);
      else sessionStorage.removeItem(GUEST_KEY);
    } catch {
      /* storage unavailable: the token simply lives in memory */
    }
    set({ guestToken });
  },
  setReady: () => set({ ready: true }),
  clear: () => set({ accessToken: null, user: null }),
}));
