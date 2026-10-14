import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  clearToken,
  getToken,
  setToken,
  type RegisterPayload,
  type User,
} from "../api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

// The extension popup's "Open dashboard" button hands its session over in
// the URL fragment (e.g. /#ext_token=…). Fragments are never sent to the
// server, and we strip it from the URL immediately so it doesn't linger in
// history — but adopting it REPLACES whatever account the website was last
// signed in as, so an employee always lands on their own dashboard.
const handoffMatch = /(?:^|[#&])ext_token=([^&]+)/.exec(window.location.hash);
if (handoffMatch) {
  setToken(decodeURIComponent(handoffMatch[1]));
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null); // token expired/revoked — guards bounce to /login
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
    const onUnauthorized = () => setUser(null);
    window.addEventListener("aidlp:unauthorized", onUnauthorized);
    return () => window.removeEventListener("aidlp:unauthorized", onUnauthorized);
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await api.login(email, password);
    setToken(resp.access_token);
    setUser(resp.user);
  }, []);

  // Self-signup always yields an employee account; the API ignores any role.
  const register = useCallback(async (payload: RegisterPayload) => {
    const resp = await api.register(payload);
    setToken(resp.access_token);
    setUser(resp.user);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
