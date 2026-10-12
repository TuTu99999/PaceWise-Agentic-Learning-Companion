import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { ToastProvider } from './components/ui/Toast';
import { AppRoutes } from './routes/AppRoutes';
import { AppStoreProvider } from './store/AppStore';
import './styles/index.css';
import { LocaleProvider } from './i18n/LocaleContext';
import { applyTheme, preferredTheme, themeFromStorageEvent } from './utils/uiPreferences';

applyTheme(preferredTheme());
window.addEventListener('storage', themeFromStorageEvent);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LocaleProvider>
      <HashRouter>
        <AppStoreProvider>
          <ToastProvider>
            <AppRoutes />
          </ToastProvider>
        </AppStoreProvider>
      </HashRouter>
    </LocaleProvider>
  </StrictMode>,
);
