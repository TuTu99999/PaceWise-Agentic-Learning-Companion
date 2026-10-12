import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { homeFor } from '../../routes/guards';
import { useAppStore } from '../../store/AppStore';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export function ForbiddenPage({ notFound }: { notFound?: boolean }) {
  useDocumentTitle(notFound ? 'Không tìm thấy trang' : 'Không có quyền');
  const { state, dispatch } = useAppStore();
  const navigate = useNavigate();
  const role = state.user?.role;
  const canGoHome = role === 'student' || role === 'instructor';
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-3xl border border-line bg-white p-8 text-center shadow-card">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
          <Icon name={notFound ? 'info' : 'lock'} size={28} />
        </span>
        <p className="mt-5 text-sm font-semibold text-muted">{notFound ? '404' : '403'}</p>
        <h1 className="mt-1 text-2xl font-bold">{notFound ? 'Không tìm thấy trang' : 'Bạn không có quyền mở trang này'}</h1>
        <p className="mt-2 text-muted">
          {notFound ? 'Đường dẫn có thể đã thay đổi.' : 'Tài khoản hiện tại không được cấp quyền cho khu vực này. Không có dữ liệu nào được hiển thị.'}
        </p>
        <div className="mt-6 flex flex-col gap-3">
          {canGoHome ? (
            <Button onClick={() => navigate(homeFor(role), { replace: true })}>Quay về trang của bạn</Button>
          ) : (
            <Button
              onClick={() => {
                dispatch({ type: 'LOGOUT' });
                navigate('/login', { replace: true });
              }}
            >
              Đăng nhập bằng tài khoản khác
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
