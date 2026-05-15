import type React from 'react';

export const createGlobalStyles = (): React.CSSProperties => ({
  margin: 0,
  padding: 0,
  boxSizing: 'border-box',
});

export const colors = {
  primary: 'var(--app-primary, #2F80ED)',
  primaryDark: 'var(--app-primary-dark, #1764C7)',
  accent: '#FFB020',
  accentSoft: '#FFF3D6',
  success: '#19A974',
  successSoft: '#E4F8EF',
  error: '#E5484D',
  errorSoft: '#FFECEF',
  warning: '#F5A524',
  warningSoft: '#FFF4D8',
  background: 'var(--app-bg, #F4F7FB)',
  surface: 'var(--app-surface, #FFFFFF)',
  surfaceAlt: 'var(--app-surface-alt, #EAF1FB)',
  secondaryBg: 'var(--app-secondary-bg, #EEF5FF)',
  text: 'var(--app-text, #17212B)',
  textSecondary: 'var(--app-text-secondary, #617082)',
  muted: 'var(--app-muted, #8A97A8)',
  border: 'var(--app-border, #DCE6F2)',
  divider: 'var(--app-divider, #E7EEF7)',
  shadow: 'rgba(20, 36, 58, 0.12)',

  pastelPink: '#FFECEF',
  pastelMint: '#E4F8EF',
  pastelLavender: '#F0ECFF',
  pastelPeach: '#FFF1E8',
  pastelBlue: '#E7F0FF',
  pastelYellow: '#FFF4D8',
  pastelCoral: '#FFE5DF',
  pastelSage: '#EAF7F1',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
};

export const typography = {
  title: {
    fontSize: '28px',
    fontWeight: 800,
    lineHeight: '1.12',
    letterSpacing: 0,
  },
  heading: {
    fontSize: '20px',
    fontWeight: 750,
    lineHeight: '1.2',
    letterSpacing: 0,
  },
  subtitle: {
    fontSize: '16px',
    fontWeight: 700,
    lineHeight: '1.3',
    letterSpacing: 0,
  },
  body: {
    fontSize: '15px',
    fontWeight: 400,
    lineHeight: '1.4',
  },
  bodySmall: {
    fontSize: '14px',
    fontWeight: 400,
    lineHeight: '1.4',
  },
  caption: {
    fontSize: '12px',
    fontWeight: 400,
    lineHeight: '1.3',
    color: '#65676b',
  },
};

export const borderRadius = {
  xs: '6px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '22px',
};

export const globalStyles = `
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
    background-color: #FFFAF6;
    color: #2D1F14;
  }

  button {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
    cursor: pointer;
    border: none;
    outline: none;
  }

  input, textarea, select {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
  }

  input:focus, textarea:focus, select:focus {
    outline: none;
  }

  ::placeholder {
    color: #99a2ad;
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

  ::-webkit-scrollbar-thumb:hover {
    background: #999;
  }
`;
