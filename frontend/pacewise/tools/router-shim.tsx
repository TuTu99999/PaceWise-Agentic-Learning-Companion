/**
 * LOCAL BUILD ONLY — not part of the app source.
 * A minimal implementation of the react-router-dom v6 API surface PaceWise uses
 * (HashRouter, Routes, Route, Navigate, Outlet, Link, NavLink, useNavigate,
 * useLocation, useParams). Used because the build sandbox cannot install
 * react-router-dom. In a normal install, `react-router-dom` is used directly.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

type Loc = { pathname: string; state: unknown; key: string };
type RouterCtx = { location: Loc; navigate: (to: string | number, opts?: { replace?: boolean; state?: unknown }) => void };
const RouterContext = createContext<RouterCtx | null>(null);
const OutletContext = createContext<React.ReactNode>(null);
const ParamsContext = createContext<Record<string, string>>({});

const stateStore = new Map<string, unknown>();
function readLocation(): Loc {
  const raw = window.location.hash.replace(/^#/, '') || '/';
  const pathname = raw.split('?')[0] || '/';
  const key = (history.state && (history.state as { k?: string }).k) || 'default';
  return { pathname, state: stateStore.get(key), key };
}

export function HashRouter({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useState<Loc>(readLocation);
  useEffect(() => {
    const onChange = () => setLocation(readLocation());
    window.addEventListener('hashchange', onChange);
    window.addEventListener('popstate', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
      window.removeEventListener('popstate', onChange);
    };
  }, []);
  const navigate = useMemo(
    () => (to: string | number, opts?: { replace?: boolean; state?: unknown }) => {
      if (typeof to === 'number') {
        history.go(to);
        return;
      }
      const k = Math.random().toString(36).slice(2);
      if (opts?.state !== undefined) stateStore.set(k, opts.state);
      const url = '#' + to;
      if (opts?.replace) history.replaceState({ k }, '', url);
      else history.pushState({ k }, '', url);
      setLocation(readLocation());
      window.scrollTo(0, 0);
    },
    [],
  );
  return <RouterContext.Provider value={{ location, navigate }}>{children}</RouterContext.Provider>;
}
export const BrowserRouter = HashRouter;

type RouteProps = { path?: string; index?: boolean; element?: React.ReactNode; children?: React.ReactNode };
export function Route(_props: RouteProps): null {
  return null;
}
type RouteObj = { path?: string; index?: boolean; element?: React.ReactNode; children: RouteObj[] };
function toRoutes(children: React.ReactNode): RouteObj[] {
  const out: RouteObj[] = [];
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return;
    const p = child.props as RouteProps;
    out.push({ path: p.path, index: p.index, element: p.element, children: toRoutes(p.children) });
  });
  return out;
}
const join = (a: string, b?: string) => {
  if (!b) return a;
  if (b.startsWith('/')) return b;
  return (a.endsWith('/') ? a : a + '/') + b;
};
function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  if (pattern.endsWith('*')) {
    const base = pattern.slice(0, -1).replace(/\/$/, '');
    return pathname.startsWith(base) ? {} : null;
  }
  const ps = pattern.split('/').filter(Boolean);
  const ss = pathname.split('/').filter(Boolean);
  if (ps.length !== ss.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < ps.length; i++) {
    if (ps[i].startsWith(':')) params[ps[i].slice(1)] = decodeURIComponent(ss[i]);
    else if (ps[i] !== ss[i]) return null;
  }
  return params;
}
function match(routes: RouteObj[], pathname: string, parent: string): { chain: RouteObj[]; params: Record<string, string> } | null {
  for (const r of routes) {
    const full = r.index ? parent : join(parent, r.path);
    if (r.children.length) {
      const sub = match(r.children, pathname, full);
      if (sub) return { chain: [r, ...sub.chain], params: sub.params };
    }
    if (r.index) {
      if (matchPath(parent || '/', pathname)) return { chain: [r], params: {} };
      continue;
    }
    if (r.path !== undefined && !r.children.length) {
      const p = matchPath(full, pathname);
      if (p) return { chain: [r], params: p };
    }
  }
  return null;
}
function renderChain(chain: RouteObj[], i: number): React.ReactNode {
  if (i >= chain.length) return null;
  const el = chain[i].element ?? <Outlet />;
  return <OutletContext.Provider value={renderChain(chain, i + 1)}>{el}</OutletContext.Provider>;
}
export function Routes({ children }: { children: React.ReactNode }) {
  const { location } = useRouter();
  const routes = toRoutes(children);
  const m = match(routes, location.pathname, '');
  if (!m) return null;
  return <ParamsContext.Provider value={m.params}>{renderChain(m.chain, 0)}</ParamsContext.Provider>;
}
export function Outlet() {
  return <>{useContext(OutletContext)}</>;
}
function useRouter() {
  const c = useContext(RouterContext);
  if (!c) throw new Error('Router missing');
  return c;
}
export const useNavigate = () => useRouter().navigate;
export const useLocation = () => useRouter().location;
export const useParams = <T extends Record<string, string | undefined> = Record<string, string>>() =>
  useContext(ParamsContext) as T;

export function Navigate({ to, replace, state }: { to: string; replace?: boolean; state?: unknown }) {
  const navigate = useNavigate();
  useEffect(() => navigate(to, { replace, state }), [to]);
  return null;
}
type LinkProps = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string; replace?: boolean; state?: unknown };
export const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link({ to, replace, state, onClick, ...rest }, ref) {
  const navigate = useNavigate();
  return (
    <a
      ref={ref}
      href={'#' + to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to, { replace, state });
      }}
      {...rest}
    />
  );
});
type NavLinkProps = Omit<LinkProps, 'className' | 'children'> & {
  end?: boolean;
  className?: string | ((a: { isActive: boolean }) => string);
  children?: React.ReactNode | ((a: { isActive: boolean }) => React.ReactNode);
};
export function NavLink({ end, className, children, to, ...rest }: NavLinkProps) {
  const { pathname } = useLocation();
  const isActive = end ? pathname === to : pathname === to || pathname.startsWith(to.endsWith('/') ? to : to + '/');
  return (
    <Link to={to} aria-current={isActive ? 'page' : undefined} className={typeof className === 'function' ? className({ isActive }) : className} {...rest}>
      {typeof children === 'function' ? children({ isActive }) : children}
    </Link>
  );
}
