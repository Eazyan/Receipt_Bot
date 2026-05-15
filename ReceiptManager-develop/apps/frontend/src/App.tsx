import React, { useEffect } from 'react';
import { colors } from '@/styles/theme';
import { useAppStore } from '@/hooks/useAppStore';
import { initTelegramApp, getTelegramUser, applyTelegramTheme } from '@/utils/telegram';
import { HomePage } from '@/pages/HomePage';
import { JoinRoomPage } from '@/pages/JoinRoomPage';
import { SelectItemsPage } from '@/pages/SelectItemsPage';
import { ResultsPage } from '@/pages/ResultsPage';
import { CreateRoomPage } from '@/pages/CreateRoomPage';
import { RoomPage } from '@/pages/RoomPage';

export const APP: React.FC = () => {
  const { currentPage, setTelegramUser } = useAppStore();

  useEffect(() => {
    // Initialize Telegram Web App
    const tgApp = initTelegramApp();
    applyTelegramTheme();
    if (tgApp) {
      const user = getTelegramUser();
      if (user) {
        setTelegramUser(user);
      }
    }

    // Inject global styles
    const style = document.createElement('style');
    style.textContent = `
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
      @keyframes riseIn {
        from { opacity: 0; transform: translateY(14px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes scanLine {
        0% { transform: translateY(-36px); opacity: 0; }
        15% { opacity: 1; }
        100% { transform: translateY(152px); opacity: 0; }
      }
      @keyframes shimmer {
        100% { transform: translateX(100%); }
      }
      @keyframes pop {
        0% { transform: scale(0.96); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
      }
      @keyframes shineSweep {
        0%, 58% { transform: translateX(0) skewX(-18deg); opacity: 0; }
        68% { opacity: 1; }
        100% { transform: translateX(420%) skewX(-18deg); opacity: 0; }
      }
      @keyframes confettiDrift {
        0%, 100% { transform: translateY(0) rotate(0deg); opacity: 0.2; }
        50% { transform: translateY(8px) rotate(18deg); opacity: 0.46; }
      }

      * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }

      html, body, #root {
        width: 100%;
        height: 100%;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
      }

      body {
        background-color: var(--app-bg, #F4F7FB);
        color: var(--app-text, #17212B);
        overscroll-behavior: none;
      }

      button, input, textarea, select {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
      }

      button {
        border: none;
        outline: none;
        -webkit-tap-highlight-color: transparent;
      }

      button:focus, button:focus-visible {
        outline: none;
        box-shadow: none;
      }

      input:focus, textarea:focus {
        outline: none;
      }

      ::placeholder {
        color: #8A97A8;
      }

      .safe-bottom {
        padding-bottom: max(16px, env(safe-area-inset-bottom));
      }

      ::-webkit-scrollbar {
        width: 6px;
      }

      ::-webkit-scrollbar-track {
        background: transparent;
      }

      ::-webkit-scrollbar-thumb {
        background: #ccc;
        border-radius: 3px;
      }
    `;
    document.head.appendChild(style);
  }, [setTelegramUser]);

  const renderPage = () => {
    switch (currentPage) {
      case 'home':
        return <HomePage />;
      case 'create-room':
        return <CreateRoomPage />;
      case 'room-code':
        return <JoinRoomPage />;
      case 'select-items':
        return <SelectItemsPage />;
      case 'results':
        return <ResultsPage />;
      case 'room':
        return <RoomPage />;
      default:
        return <HomePage />;
    }
  };

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: colors.background,
      }}
    >
      {renderPage()}
    </div>
  );
};

export default APP;
