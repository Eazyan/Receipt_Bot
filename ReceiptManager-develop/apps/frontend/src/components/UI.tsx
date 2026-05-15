import React from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'dark';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  loading = false,
  children,
  disabled,
  style,
  ...props
}) => {
  const baseStyles: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    fontWeight: 750,
    borderRadius: borderRadius.md,
    border: 'none',
    outline: 'none',
    transition: 'transform 0.14s ease, opacity 0.14s ease, box-shadow 0.14s ease',
    width: fullWidth ? '100%' : 'auto',
    opacity: disabled || loading ? 0.58 : 1,
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    letterSpacing: 0,
    WebkitTapHighlightColor: 'transparent',
    boxShadow: variant === 'primary' ? `0 12px 26px rgba(47, 128, 237, 0.24)` : 'none',
  };

  const variantStyles: Record<NonNullable<ButtonProps['variant']>, React.CSSProperties> = {
    primary: {
      background: `linear-gradient(135deg, ${colors.primary}, ${colors.primaryDark})`,
      color: '#ffffff',
    },
    secondary: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
    },
    danger: {
      backgroundColor: colors.error,
      color: '#ffffff',
    },
    ghost: {
      backgroundColor: 'transparent',
      color: colors.primary,
      border: `1px solid ${colors.border}`,
    },
    dark: {
      backgroundColor: colors.text,
      color: '#ffffff',
      boxShadow: `0 12px 24px rgba(23, 33, 43, 0.18)`,
    },
  };

  const sizeStyles: Record<NonNullable<ButtonProps['size']>, React.CSSProperties> = {
    sm: {
      ...typography.bodySmall,
      padding: `${spacing.sm}px ${spacing.md}px`,
      minHeight: 36,
    },
    md: {
      ...typography.body,
      padding: `${spacing.md}px ${spacing.lg}px`,
      minHeight: 46,
    },
    lg: {
      ...typography.subtitle,
      padding: `${spacing.lg}px ${spacing.xl}px`,
      minHeight: 56,
    },
  };

  return (
    <button
      style={{
        ...baseStyles,
        ...variantStyles[variant],
        ...sizeStyles[size],
        ...style,
      }}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            border: '2px solid rgba(255,255,255,0.44)',
            borderTopColor: '#fff',
            animation: 'spin 0.8s linear infinite',
          }}
        />
      )}
      {children}
    </button>
  );
};

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
  interactive?: boolean;
}

export const Card: React.FC<CardProps> = ({ elevated = false, interactive = false, children, style, ...props }) => (
  <div
    style={{
      backgroundColor: colors.surface,
      borderRadius: borderRadius.lg,
      padding: spacing.lg,
      boxShadow: elevated ? `0 16px 40px ${colors.shadow}` : `0 1px 0 rgba(20, 36, 58, 0.04)`,
      border: `1px solid ${colors.divider}`,
      animation: interactive ? 'riseIn 0.24s ease both' : undefined,
      ...style,
    }}
    {...props}
  >
    {children}
  </div>
);

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input: React.FC<InputProps> = ({ label, error, style, ...props }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
    {label && (
      <label style={{ ...typography.bodySmall, fontWeight: 750, color: colors.textSecondary }}>
        {label}
      </label>
    )}
    <input
      style={{
        ...typography.body,
        minHeight: 48,
        padding: `${spacing.md}px ${spacing.md}px`,
        borderRadius: borderRadius.md,
        border: `1px solid ${error ? colors.error : colors.border}`,
        backgroundColor: colors.surface,
        color: colors.text,
        boxShadow: '0 1px 0 rgba(20, 36, 58, 0.04)',
        ...style,
      }}
      {...props}
    />
    {error && (
      <span style={{ ...typography.caption, color: colors.error }}>
        {error}
      </span>
    )}
  </div>
);

interface LoadingProps {
  fullScreen?: boolean;
  label?: string;
}

export const Loading: React.FC<LoadingProps> = ({ fullScreen = false, label = 'Загрузка...' }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: fullScreen ? '100vh' : 160,
      gap: spacing.md,
      color: colors.textSecondary,
    }}
  >
    <div
      style={{
        width: 30,
        height: 30,
        border: `3px solid ${colors.border}`,
        borderTop: `3px solid ${colors.primary}`,
        borderRadius: '50%',
        animation: 'spin 0.9s linear infinite',
      }}
    />
    <span style={typography.body}>{label}</span>
  </div>
);

export const SkeletonBlock: React.FC<{ height?: number; width?: number | string; radius?: string; style?: React.CSSProperties }> = ({
  height = 18,
  width = '100%',
  radius = borderRadius.sm,
  style,
}) => (
  <div
    style={{
      position: 'relative',
      overflow: 'hidden',
      height,
      width,
      borderRadius: radius,
      background: colors.surfaceAlt,
      ...style,
    }}
  >
    <span
      style={{
        position: 'absolute',
        inset: 0,
        transform: 'translateX(-100%)',
        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.42), transparent)',
        animation: 'shimmer 1.2s ease-in-out infinite',
      }}
    />
  </div>
);

export const ReceiptSkeleton: React.FC<{ rows?: number }> = ({ rows = 4 }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
    {Array.from({ length: rows }).map((_, index) => (
      <Card key={index}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md }}>
          <div style={{ flex: 1 }}>
            <SkeletonBlock height={20} width={`${70 - (index % 2) * 12}%`} />
            <div style={{ display: 'flex', gap: spacing.sm, marginTop: spacing.md }}>
              <SkeletonBlock height={28} width={92} radius="999px" />
              <SkeletonBlock height={28} width={104} radius="999px" />
            </div>
          </div>
          <SkeletonBlock height={24} width={78} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm, marginTop: spacing.md }}>
          <SkeletonBlock height={38} />
          <SkeletonBlock height={38} />
        </div>
      </Card>
    ))}
  </div>
);

interface ErrorAlertProps {
  message: string;
  onDismiss?: () => void;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({ message, onDismiss }) => (
  <div
    style={{
      backgroundColor: colors.errorSoft,
      color: colors.error,
      padding: spacing.md,
      borderRadius: borderRadius.md,
      border: `1px solid rgba(229,72,77,0.22)`,
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: spacing.md,
      animation: 'riseIn 0.18s ease both',
    }}
  >
    <span style={{ ...typography.bodySmall, fontWeight: 650 }}>{message}</span>
    {onDismiss && (
      <button
        onClick={onDismiss}
        aria-label="Закрыть"
        style={{
          background: 'transparent',
          color: colors.error,
          fontSize: 22,
          cursor: 'pointer',
          lineHeight: 1,
        }}
      >
        ×
      </button>
    )}
  </div>
);

interface HeaderProps {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  rightAction?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle, onBack, rightAction }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: `${spacing.md}px ${spacing.lg}px ${spacing.sm}px`,
      backgroundColor: colors.background,
      gap: spacing.md,
    }}
  >
    {onBack && (
      <button
        onClick={onBack}
        aria-label="Назад"
        style={{
          width: 40,
          height: 40,
          borderRadius: borderRadius.md,
          background: colors.surface,
          color: colors.text,
          fontSize: 22,
          cursor: 'pointer',
          boxShadow: `0 6px 18px rgba(20,36,58,0.08)`,
        }}
      >
        ‹
      </button>
    )}
    <div style={{ flex: 1, minWidth: 0 }}>
      <h1 style={{ ...typography.heading, margin: 0, color: colors.text }}>{title}</h1>
      {subtitle && (
        <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 2 }}>
          {subtitle}
        </div>
      )}
    </div>
    {rightAction && <div>{rightAction}</div>}
  </div>
);

export const PageContainer: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      backgroundColor: colors.background,
      overflow: 'hidden',
      maxWidth: 560,
      margin: '0 auto',
      position: 'relative',
    }}
  >
    {children}
  </div>
);

export const PageContent: React.FC<{ children: React.ReactNode; compact?: boolean }> = ({ children, compact = false }) => (
  <div
    style={{
      flex: 1,
      overflowY: 'auto',
      padding: compact ? spacing.md : spacing.lg,
      display: 'flex',
      flexDirection: 'column',
      gap: spacing.md,
    }}
  >
    {children}
  </div>
);

export const PageFooter: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    className="safe-bottom"
    style={{
      padding: `${spacing.md}px ${spacing.lg}px`,
      background: 'rgba(244, 247, 251, 0.92)',
      borderTop: `1px solid ${colors.divider}`,
      backdropFilter: 'blur(18px)',
      WebkitBackdropFilter: 'blur(18px)',
    }}
  >
    {children}
  </div>
);

export const Pill: React.FC<{ children: React.ReactNode; tone?: 'blue' | 'green' | 'yellow' | 'red' | 'dark'; style?: React.CSSProperties }> = ({
  children,
  tone = 'blue',
  style,
}) => {
  const tones = {
    blue: { backgroundColor: colors.secondaryBg, color: colors.primary },
    green: { backgroundColor: colors.successSoft, color: colors.success },
    yellow: { backgroundColor: colors.warningSoft, color: '#A56400' },
    red: { backgroundColor: colors.errorSoft, color: colors.error },
    dark: { backgroundColor: colors.text, color: '#fff' },
  };
  return (
    <span
      style={{
        ...typography.caption,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 9px',
        borderRadius: 999,
        fontWeight: 750,
        ...tones[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
};

export const BottomSheet: React.FC<{ children: React.ReactNode; onClose?: () => void }> = ({ children, onClose }) => (
  <div
    style={{
      position: 'absolute',
      inset: 0,
      background: 'rgba(23, 33, 43, 0.28)',
      display: 'flex',
      alignItems: 'flex-end',
      zIndex: 20,
      animation: 'pop 0.16s ease both',
    }}
    onClick={onClose}
  >
    <div
      className="safe-bottom"
      style={{
        width: '100%',
        background: colors.surface,
        borderTopLeftRadius: 24,
        borderTopRightRadius: 24,
        padding: spacing.lg,
        boxShadow: `0 -18px 50px ${colors.shadow}`,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <div
        style={{
          width: 42,
          height: 4,
          borderRadius: 999,
          background: colors.border,
          margin: '0 auto 16px',
        }}
      />
      {children}
    </div>
  </div>
);
