import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAppStore } from '../store/AppStore';
import type { Role } from '../types';

/** Client-side role guard. The backend must enforce RBAC too; this only routes the UI. */
export function RequireRole({ role, children }: { role: Role; children: React.ReactNode }) {
  const { state } = useAppStore();
  if (!state.authReady) return <div className="flex min-h-screen items-center justify-center text-muted">Đang kiểm tra phiên đăng nhập…</div>;
  if (!state.user) return <Navigate to="/login" replace />;
  if (state.user.role !== role) return <Navigate to="/403" replace />;
  return <>{children}</>;
}

export function homeFor(role?: Role) {
  if (role === 'student') return '/plan';
  if (role === 'instructor') return '/instructor';
  if (role === 'guest') return '/403';
  return '/login';
}
