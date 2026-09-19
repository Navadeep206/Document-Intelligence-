import React, { createContext, useContext, useEffect, useState } from 'react';
import { LoginCredentials, RegisterCredentials, User } from '@/types/auth';
import { getCurrentUserApi, loginApi, registerApi } from '@/api/auth';

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (credentials: RegisterCredentials) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const cached = localStorage.getItem('user');
    if (cached) {
      try {
        return JSON.parse(cached);
      } catch {
        return null;
      }
    }
    return null;
  });

  const [accessToken, setAccessToken] = useState<string | null>(() => {
    return localStorage.getItem('access_token');
  });

  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const initializeAuth = async () => {
      const token = localStorage.getItem('access_token');
      if (token) {
        try {
          const profile = await getCurrentUserApi();
          setUser(profile);
          localStorage.setItem('user', JSON.stringify(profile));
        } catch {
          // Token invalid or expired
          localStorage.removeItem('access_token');
          localStorage.removeItem('user');
          setAccessToken(null);
          setUser(null);
        }
      }
      setLoading(false);
    };

    initializeAuth();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    const tokenRes = await loginApi(credentials);
    const token = tokenRes.access_token;
    localStorage.setItem('access_token', token);
    setAccessToken(token);

    // Fetch user profile
    const profile = await getCurrentUserApi();
    setUser(profile);
    localStorage.setItem('user', JSON.stringify(profile));
  };

  const register = async (credentials: RegisterCredentials) => {
    await registerApi(credentials);
    // Automatically log in after registration
    await login(credentials);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    setAccessToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated: !!accessToken,
        loading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
