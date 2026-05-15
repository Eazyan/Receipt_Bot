// Telegram Web App integration
declare global {
  interface Window {
    Telegram: {
      WebApp: {
        ready: () => void;
        expand: () => void;
        close: () => void;
        onEvent: (eventType: string, callback: () => void) => void;
        offEvent: (eventType: string, callback?: () => void) => void;
        initData: string;
        initDataUnsafe: {
          user?: {
            id: number;
            is_bot: boolean;
            first_name: string;
            last_name?: string;
            username?: string;
            language_code?: string;
          };
          auth_date: number;
          hash: string;
        };
        platform: string;
        colorScheme: 'light' | 'dark';
        themeParams: {
          bg_color: string;
          secondary_bg_color: string;
          text_color: string;
          hint_color: string;
          link_color: string;
          button_color: string;
          button_text_color: string;
        };
        isExpanded: boolean;
        viewportHeight: number;
        headerColor: string;
        backgroundColor: string;
        setHeaderColor: (color: string) => void;
        setBackgroundColor: (color: string) => void;
        version?: string;
        openTelegramLink?: (url: string) => void;
        switchInlineQuery?: (query: string, choose_chat_types?: string[]) => void;
        showAlert: (message: string) => void;
        showConfirm: (message: string, callback: (ok: boolean) => void) => void;
        HapticFeedback: {
          impactOccurred: (style: string) => void;
          notificationOccurred: (type: string) => void;
          selectionChanged: () => void;
        };
      };
    };
  }
}

export const initTelegramApp = () => {
  const webApp = window.Telegram?.WebApp;
  if (webApp) {
    try {
      webApp.ready?.();
      webApp.expand?.();
    } catch {
      // Telegram's injected script can expose methods that are unavailable in older clients.
    }
    return webApp;
  }
  return null;
};

const isHexColor = (value?: string) => Boolean(value && /^#[0-9a-f]{6}$/i.test(value));

const mixHex = (from: string, to: string, amount: number) => {
  if (!isHexColor(from) || !isHexColor(to)) return from;
  const parse = (hex: string) => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  const [r1, g1, b1] = parse(from);
  const [r2, g2, b2] = parse(to);
  const channel = (a: number, b: number) => Math.round(a + (b - a) * amount).toString(16).padStart(2, '0');
  return `#${channel(r1, r2)}${channel(g1, g2)}${channel(b1, b2)}`;
};

export const applyTelegramTheme = () => {
  const webApp = window.Telegram?.WebApp;
  const params = webApp?.themeParams;
  const colorScheme = webApp?.colorScheme || 'light';
  const fallback = colorScheme === 'dark'
    ? {
      bg: '#0F1720',
      surface: '#17212B',
      text: '#F5F7FA',
      hint: '#8A97A8',
      button: '#2F80ED',
    }
    : {
      bg: '#F4F7FB',
      surface: '#FFFFFF',
      text: '#17212B',
      hint: '#617082',
      button: '#2F80ED',
    };

  const bg = isHexColor(params?.bg_color) ? params.bg_color : fallback.bg;
  const surface = isHexColor(params?.secondary_bg_color) ? params.secondary_bg_color : fallback.surface;
  const text = isHexColor(params?.text_color) ? params.text_color : fallback.text;
  const hint = isHexColor(params?.hint_color) ? params.hint_color : fallback.hint;
  const button = isHexColor(params?.button_color) ? params.button_color : fallback.button;
  const root = document.documentElement;

  root.style.setProperty('--app-bg', bg);
  root.style.setProperty('--app-surface', surface);
  root.style.setProperty('--app-surface-alt', mixHex(surface, colorScheme === 'dark' ? '#FFFFFF' : '#2F80ED', colorScheme === 'dark' ? 0.08 : 0.09));
  root.style.setProperty('--app-secondary-bg', mixHex(button, surface, colorScheme === 'dark' ? 0.78 : 0.9));
  root.style.setProperty('--app-text', text);
  root.style.setProperty('--app-text-secondary', hint);
  root.style.setProperty('--app-muted', mixHex(hint, bg, 0.28));
  root.style.setProperty('--app-border', mixHex(hint, surface, colorScheme === 'dark' ? 0.5 : 0.68));
  root.style.setProperty('--app-divider', mixHex(hint, surface, colorScheme === 'dark' ? 0.62 : 0.78));
  root.style.setProperty('--app-primary', button);
  root.style.setProperty('--app-primary-dark', mixHex(button, '#000000', 0.16));
  root.style.setProperty('--app-color-scheme', colorScheme);
  document.body.style.backgroundColor = bg;

  try {
    webApp?.setBackgroundColor?.(bg);
    webApp?.setHeaderColor?.(bg);
  } catch {
    // Theme sync is progressive enhancement.
  }
};

export const getTelegramUser = () => {
  if (window.Telegram?.WebApp?.initDataUnsafe) {
    return window.Telegram.WebApp.initDataUnsafe.user;
  }
  return null;
};

export const getTelegramInitData = () => {
  return window.Telegram?.WebApp?.initData || '';
};

export const showTelegramAlert = (message: string) => {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.showAlert) {
    try {
      webApp.showAlert(message);
      return;
    } catch {
      // Fall through to browser alert for old Telegram WebApp versions.
    }
  }
  window.alert(message);
};

export const showTelegramConfirm = (message: string): Promise<boolean> => {
  return new Promise((resolve) => {
    const webApp = window.Telegram?.WebApp;
    if (webApp?.showConfirm) {
      try {
        webApp.showConfirm(message, (ok) => {
          resolve(ok);
        });
        return;
      } catch {
        // Fall through to browser confirm.
      }
    }
    resolve(window.confirm(message));
  });
};

export const hapticFeedback = (type: 'success' | 'impact' | 'selection' = 'selection') => {
  const haptic = window.Telegram?.WebApp?.HapticFeedback;
  if (!haptic) return;

  try {
    switch (type) {
      case 'success':
        haptic.notificationOccurred?.('success');
        break;
      case 'impact':
        haptic.impactOccurred?.('medium');
        break;
      case 'selection':
        haptic.selectionChanged?.();
        break;
    }
  } catch {
    // Haptics are progressive enhancement only.
  }
};

export const shareText = async (text: string, title = 'Receipt Manager') => {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.switchInlineQuery) {
    try {
      webApp.switchInlineQuery(text, ['users', 'groups', 'channels']);
      return true;
    } catch {
      // Fall through to Web Share / clipboard.
    }
  }

  if (navigator.share) {
    try {
      await navigator.share({ title, text });
      return true;
    } catch {
      return false;
    }
  }

  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

export const getThemeColor = (key: keyof typeof window.Telegram.WebApp.themeParams): string => {
  return window.Telegram?.WebApp?.themeParams?.[key] || '#ffffff';
};
